# core_logic/tool_processing.py

"""
Handles the execution, validation, and processing of tool calls
requested by the LLM.
"""

import asyncio
import json
# import logging # Replaced by custom logging
import hashlib
import time  # For _execute_tool_calls fallback ID
import uuid  # For _generate_tool_call_id
import difflib
from typing import List, Dict, Any, Tuple, Optional
import sys # Ensure sys is at the top of standard imports
import os
from importlib import import_module

# print(f"DEBUG: sys.path in {__file__} BEFORE robust path setup: {sys.path}") # ADDED FOR DEBUGGING
# --- Robust Path Setup for this file ---
_tool_processing_file_path_for_path_setup = os.path.abspath(__file__)
_core_logic_dir_from_tp_for_path_setup = os.path.dirname(_tool_processing_file_path_for_path_setup)
_project_root_dir_from_tp_for_path_setup = os.path.dirname(_core_logic_dir_from_tp_for_path_setup) # This should be Light-MVP

if _project_root_dir_from_tp_for_path_setup not in sys.path:
    sys.path.insert(0, _project_root_dir_from_tp_for_path_setup)
# print(f"DEBUG: sys.path in {__file__} AFTER robust path setup: {sys.path}") # ADDED FOR DEBUGGING
# --- End Robust Path Setup ---

# Project-specific imports (NOW ATTEMPT AFTER PATH IS SET)
from config import Config
from state_models import AppState, ScratchpadEntry, SessionDebugStats, ToolUsageStats
from tools.tool_executor import ToolExecutor

# Import the ToolCallAdapter integration
from core_logic.tool_call_adapter import ToolCallAdapter
from core_logic.tool_call_adapter_integration import process_service_tool_calls
 
# Relative imports from within core_logic
from .constants import (
    MAX_SIMILAR_TOOL_CALLS,
    SIMILARITY_THRESHOLD,
    MAX_TOOL_EXECUTION_RETRIES,
    TOOL_RETRY_INITIAL_DELAY,
    MAX_RETRY_DELAY,
)

# print(f"DEBUG: sys.path in {__file__} BEFORE importing utils.logging_config: {sys.path}") # ADDED FOR DEBUGGING
from utils.logging_config import get_logger, setup_logging, start_new_turn, clear_turn_ids

try:
    from jsonschema import validate as validate_schema
    from jsonschema.exceptions import ValidationError as SchemaValidationError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

log = get_logger("core_logic.tool_processing") # Use namespaced logger

# --- Main Tool Execution Function ---


async def _execute_tool_calls(
    tool_calls: List[Dict[str, Any]],
    tool_executor: ToolExecutor,
    previous_calls: List[Tuple[str, str, str, str]],  # Updated to include hash: (id, name, args_str, hash)
    app_state: AppState,  # Type updated from Any
    config: Config,  # Type updated from Any
    available_tool_definitions: List[Dict[str, Any]] # Added for validation
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool, List[Tuple[str, str, str, str]]]: # Updated return for previous_calls
    """
    Execute tool calls requested by the LLM.
    
    This function handles both detailed tool calls (e.g., "github_list_repositories") 
    and service-level tool calls (e.g., "github") via the ToolCallAdapter.
    
    Args:
        tool_calls: The tool calls from the LLM
        tool_executor: The ToolExecutor to execute the tools
        previous_calls: Previously executed tool calls (for circular call detection)
        app_state: The current application state
        config: The application configuration
        available_tool_definitions: Tool definitions available for validation
        
    Returns:
        A tuple of (tool result messages, internal messages, has_critical_error, updated_previous_calls)
    """
    log.debug(
        f"Received {len(tool_calls)} tool calls to execute.",
        extra={"event_type": "tool_execution_start", "details": {"tool_call_count": len(tool_calls)}}
    )
    
    use_adapter = False
    for tool_call in tool_calls:
        function_name = tool_call.get("function", {}).get("name", "")
        if function_name and "_" not in function_name:
            use_adapter = True
            log.info(
                f"Detected service-level tool call: '{function_name}'. Using ToolCallAdapter.",
                extra={"event_type": "service_tool_call_detected", "details": {"function_name": function_name}}
            )
            break
    
    if use_adapter:
        # For adapter path, we need to perform circular detection for each call before processing.
        tool_result_messages_adapter: List[Dict[str, Any]] = []
        internal_messages_adapter: List[Dict[str, Any]] = []
        has_critical_error_adapter = False
        updated_previous_calls_adapter = list(previous_calls)
        
        calls_to_pass_to_adapter: List[Dict[str, Any]] = []
        pre_checked_ids = set() # To track IDs handled by pre-check

        for tool_call in tool_calls:
            tool_call_id_adapter = tool_call.get("id", f"tool_call_adapter_precheck_{int(time.time())}")
            pre_checked_ids.add(tool_call_id_adapter) # Track all original IDs
            function_name_adapter = tool_call.get("function", {}).get("name", "unknown_service")
            args_str_adapter = tool_call.get("function", {}).get("arguments", "{}")
            
            previous_for_detection_transformed = [(p_name, p_args, p_hash) for _, p_name, p_args, p_hash in updated_previous_calls_adapter]
            is_circular, circular_message = _detect_circular_calls(function_name_adapter, args_str_adapter, previous_for_detection_transformed)

            if is_circular:
                log.warning(
                    f"Circular call detected for service '{function_name_adapter}' (ID: {tool_call_id_adapter}) before adapter processing: {circular_message}",
                    extra={"event_type": "circular_service_call_detected_pre_adapter", "details": {"service_name": function_name_adapter, "tool_call_id": tool_call_id_adapter, "message": circular_message}}
                )
                error_payload = {"error": "CircularToolCallDetected", "tool_call_id": tool_call_id_adapter, "tool_name": function_name_adapter, "message": circular_message}
                tool_part = {"tool_call_id": tool_call_id_adapter, "tool_name": function_name_adapter, "output": json.dumps(error_payload), "is_error": True}
                tool_result_messages_adapter.append({"role": "tool", "parts": [tool_part]}) # Match structure of process_service_tool_calls
                internal_messages_adapter.append({"role": "system", "content": f"Tool Execution: Service='{function_name_adapter}', ID='{tool_call_id_adapter}', Error: Circular call detected - {circular_message}"})
                current_call_hash_adapter = _compute_tool_call_hash(function_name_adapter, args_str_adapter)
                updated_previous_calls_adapter.append((tool_call_id_adapter, function_name_adapter, args_str_adapter, current_call_hash_adapter))
                if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False): # Circular can be critical
                    has_critical_error_adapter = True
                    # If critical, we stop all further processing for this batch.
                    # The already accumulated messages will be returned.
                    break 
                continue # to next tool_call in the pre-check loop
            
            # If not circular, it's a candidate for the adapter
            calls_to_pass_to_adapter.append(tool_call)

        if has_critical_error_adapter: # If a pre-adapter circular call broke the loop entirely
             return tool_result_messages_adapter, internal_messages_adapter, has_critical_error_adapter, updated_previous_calls_adapter

        # Original adapter call if no pre-circularity detected that breaks the loop, or if non-critical circulars were handled
        if calls_to_pass_to_adapter: # Only call adapter if there are pending calls
            tool_result_messages_from_adapter, internal_messages_from_adapter, has_critical_error_from_adapter = await process_service_tool_calls(
                tool_calls=calls_to_pass_to_adapter, # MODIFIED: Pass only non-circular calls
                tool_executor=tool_executor, app_state=app_state, config=config
            )
            # Combine results
            tool_result_messages = tool_result_messages_adapter + tool_result_messages_from_adapter
            internal_messages = internal_messages_adapter + internal_messages_from_adapter
            has_critical_error = has_critical_error_adapter or has_critical_error_from_adapter
        else: # No calls left for adapter (all were pre-checked circular and non-critical, or list was empty)
            tool_result_messages = tool_result_messages_adapter
            internal_messages = internal_messages_adapter
            has_critical_error = has_critical_error_adapter
        
        # Update previous_calls based on what the adapter processed and what was pre-checked
        # The updated_previous_calls_adapter already contains entries from the pre-check loop.
        # We need to add entries for calls processed by the adapter, if any.
        current_previous_calls_copy = list(updated_previous_calls_adapter) 

        for tool_call_processed_by_adapter in calls_to_pass_to_adapter: 
            # Check if this call was already added by the pre-check (it shouldn't have been if it reached here)
            # This logic primarily ensures that if calls_to_pass_to_adapter was a subset, we only add those.
            tool_call_id = tool_call_processed_by_adapter.get("id", f"tool_call_adapter_post_{int(time.time())}")
            # Ensure not to add duplicates if pre_checked_ids was somehow out of sync (defensive)
            if not any(tc[0] == tool_call_id for tc in updated_previous_calls_adapter):
                function_name = tool_call_processed_by_adapter.get("function", {}).get("name", "unknown_service_post")
                args_str = tool_call_processed_by_adapter.get("function", {}).get("arguments", "{}")
                call_hash = _compute_tool_call_hash(function_name, args_str)
                current_previous_calls_copy.append((tool_call_id, function_name, args_str, call_hash))
        
        final_updated_previous_calls = current_previous_calls_copy

        return tool_result_messages, internal_messages, has_critical_error, final_updated_previous_calls
    
    tool_result_messages: List[Dict[str, Any]] = []
    internal_messages: List[Dict[str, Any]] = []
    has_critical_error = False
    updated_previous_calls = list(previous_calls)

    for idx, tool_call in enumerate(tool_calls):
        tool_call_id = tool_call.get("id", f"tool_call_{idx}_{int(time.time())}")
        function_call_dict = tool_call.get("function")
        if not function_call_dict:
            log.warning(
                f"Tool call ID '{tool_call_id}' is missing 'function' field. Skipping.",
                extra={"event_type": "malformed_tool_call_skipped", "details": {"tool_call_id": tool_call_id, "reason": "missing_function_field"}}
            )
            error_payload = {"error": "MalformedToolCall", "tool_call_id": tool_call_id, "message": "Tool call is missing the 'function' field."}
            tool_part = {"tool_call_id": tool_call_id, "tool_name": "unknown_malformed_call", "output": json.dumps(error_payload), "is_error": True}
            tool_result_messages.append({"role": "tool", "parts": [tool_part]})
            internal_messages.append({"role": "system", "content": f"Tool Execution: Malformed call, ID='{tool_call_id}', Error: {error_payload.get('message')}"})
            if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False):
                has_critical_error = True
                log.error(
                    f"Critical error: Malformed tool call (ID: {tool_call_id}) missing 'function' field. Breaking execution.",
                    extra={"event_type": "critical_tool_error_malformed", "details": {"tool_call_id": tool_call_id}}
                )
                if app_state and hasattr(app_state, 'current_step_error'):
                    app_state.current_step_error = f"Critical: Malformed tool call (ID: {tool_call_id}): {error_payload.get('message')}"
            if has_critical_error: break
            continue
 
        function_name = function_call_dict.get("name")
        function_args_json_str = function_call_dict.get("arguments")
        args_dict_for_processing: Dict[str, Any] = {}

        if function_args_json_str is None or not str(function_args_json_str).strip():
            effective_args_json_str_for_log_hash = "{}"
            args_dict_for_processing = {}
        else:
            effective_args_json_str_for_log_hash = str(function_args_json_str)
            try:
                args_dict_for_processing = json.loads(effective_args_json_str_for_log_hash)
                if not isinstance(args_dict_for_processing, dict):
                    log.warning(
                        f"Deserialized arguments for tool '{function_name}' (ID: {tool_call_id}) are not a dict.",
                        extra={
                            "event_type": "tool_args_deserialization_not_dict",
                            "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "args_type": str(type(args_dict_for_processing)), "raw_args_string": effective_args_json_str_for_log_hash}
                        }
                    )
            except json.JSONDecodeError as e:
                log.error(
                    f"Failed to deserialize 'arguments' JSON string for tool '{function_name}' (ID: {tool_call_id}).",
                    exc_info=True, # Add exc_info for structured logging
                    extra={
                        "event_type": "tool_args_deserialization_failed",
                        "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "error": str(e), "raw_args_string": effective_args_json_str_for_log_hash}
                    }
                )
                args_dict_for_processing = {"__tool_arg_error__": "JSONDecodeError", "message": str(e), "raw_arguments": effective_args_json_str_for_log_hash}

        log.info(
            "Preparing to execute tool.",
            extra={
                "event_type": "tool_execution_prepare",
                "details": {
                    "tool_call_id": tool_call_id, "tool_name": function_name,
                    "args_preview": effective_args_json_str_for_log_hash[:150] + ('...' if len(effective_args_json_str_for_log_hash) > 150 else '')
                }
            }
        )
        result_content_for_output = ""
        current_call_is_error = False
        effective_tool_name_for_part = function_name

        if not function_name:
            log.warning(
                f"Tool call ID '{tool_call_id}' has invalid/missing function name: '{function_name}'.",
                extra={"event_type": "invalid_tool_function_name", "details": {"tool_call_id": tool_call_id, "attempted_name": function_name}}
            )
            effective_tool_name_for_part = "unknown_invalid_function_name"
            error_payload = {"error": "MalformedToolCall", "tool_call_id": tool_call_id, "message": "Tool call is missing a valid function name.", "attempted_name": function_name}
            result_content_for_output = json.dumps(error_payload)
            current_call_is_error = True
            if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False):
                has_critical_error = True
                log.error(
                    f"Critical error: Malformed tool call (ID: {tool_call_id}) with invalid function name. Breaking execution.",
                    extra={"event_type": "critical_tool_error_invalid_name", "details": {"tool_call_id": tool_call_id}}
                )
                if app_state and hasattr(app_state, 'current_step_error'):
                    app_state.current_step_error = f"Critical: Malformed tool call (ID: {tool_call_id}): Invalid function name '{function_name}'."
        else:
            previous_calls_for_detection_transformed = [(p_name, p_args, p_hash) for _, p_name, p_args, p_hash in updated_previous_calls]
            is_circular, circular_message = _detect_circular_calls(function_name, effective_args_json_str_for_log_hash, previous_calls_for_detection_transformed)

            if is_circular:
                log.warning(
                    f"Circular call detected for tool '{function_name}' (ID: {tool_call_id}): {circular_message}",
                    extra={"event_type": "circular_tool_call_detected", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "message": circular_message}}
                )
                error_payload = {"error": "CircularToolCallDetected", "tool_call_id": tool_call_id, "tool_name": function_name, "message": circular_message}
                result_content_for_output = json.dumps(error_payload)
                current_call_is_error = True
                if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False):
                    log.error(
                        f"Critical error: Circular tool call detected for '{function_name}' (ID: {tool_call_id}). Breaking execution.",
                        extra={"event_type": "critical_tool_error_circular_call", "details": {"tool_name": function_name, "tool_call_id": tool_call_id}}
                    )
                    has_critical_error = True
            elif not hasattr(tool_executor, 'execute_tool'):
                err_msg = "Tool executor misconfiguration: 'execute_tool' method not available."
                log.error(
                    f"Configuration error for tool call ID '{tool_call_id}' (Tool: '{function_name}'): {err_msg}",
                    extra={"event_type": "tool_executor_misconfiguration", "details": {"tool_call_id": tool_call_id, "tool_name": function_name}}
                )
                error_payload = {"error": "ToolExecutorConfigurationError", "tool_call_id": tool_call_id, "tool_name": function_name, "message": err_msg}
                result_content_for_output = json.dumps(error_payload)
                current_call_is_error = True
                if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False):
                    has_critical_error = True
                    log.error(
                        f"Critical error: ToolExecutor misconfiguration for tool '{function_name}'. Breaking execution.",
                        extra={"event_type": "critical_tool_error_executor_misconfig", "details": {"tool_name": function_name}}
                    )
                    if app_state and hasattr(app_state, 'current_step_error'):
                        app_state.current_step_error = f"Critical: ToolExecutor misconfiguration for tool '{function_name}'."
            else:
                is_valid, validation_error_msg, validated_args_dict = _validate_tool_parameters(function_name, args_dict_for_processing, available_tool_definitions)
                if not is_valid:
                    log.warning(
                        f"Parameter validation failed for tool '{function_name}' (ID: {tool_call_id}): {validation_error_msg}",
                        extra={"event_type": "tool_parameter_validation_failed", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "error_message": validation_error_msg}}
                    )
                    error_payload = {"error": "ToolParameterValidationError", "tool_call_id": tool_call_id, "tool_name": function_name, "message": validation_error_msg}
                    result_content_for_output = json.dumps(error_payload)
                    current_call_is_error = True
                    if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False):
                        has_critical_error = True
                        log.error(
                            f"Critical error: Parameter validation failed for tool '{function_name}'. Breaking execution.",
                            extra={"event_type": "critical_tool_error_param_validation", "details": {"tool_name": function_name}}
                        )
                        if app_state and hasattr(app_state, 'current_step_error'):
                            app_state.current_step_error = f"Critical: Parameter validation failed for tool '{function_name}'."
                else:
                    last_exception = None
                    was_permission_denied_in_retry_loop = False # Flag to indicate if permission was denied in the retry loop
                    for attempt in range(MAX_TOOL_EXECUTION_RETRIES):
                        try:
                            log.info(
                                f"Attempt {attempt + 1}/{MAX_TOOL_EXECUTION_RETRIES} for tool '{function_name}' (ID: {tool_call_id})",
                                extra={"event_type": "tool_execution_attempt", "details": {"attempt_num": attempt + 1, "max_attempts": MAX_TOOL_EXECUTION_RETRIES, "tool_name": function_name, "tool_call_id": tool_call_id}}
                            )
                            raw_result_content = await tool_executor.execute_tool(function_name, validated_args_dict, app_state=app_state)
                            attempt_produced_error = False

                            # --- BEGIN PERMISSION_DENIED HANDLING ---
                            if isinstance(raw_result_content, dict) and raw_result_content.get("status") == "PERMISSION_DENIED":
                                permission_denied_message = raw_result_content.get('message', 'No reason provided')
                                user_id_for_log = app_state.current_user.user_id if app_state and app_state.current_user else "unknown_user" # Corrected .id to .user_id
                                log.warning(
                                    f"Permission denied for tool '{function_name}' for user '{user_id_for_log}'. Reason: {permission_denied_message}",
                                    extra={
                                        "event_type": "permission_denied_tool_call",
                                        "details": {
                                            "tool_name": function_name,
                                            "tool_call_id": tool_call_id,
                                            "user_id": user_id_for_log,
                                            "denial_message": permission_denied_message
                                        }
                                    }
                                )
                                user_facing_denial_message = f"Sorry, you don't have permission to use the '{function_name}' tool for this action."
                                if app_state and hasattr(app_state, 'add_message') and callable(app_state.add_message):
                                    app_state.add_message(
                                        role="assistant", # Or other appropriate role for bot's user-facing messages
                                        content=user_facing_denial_message,
                                        message_type="permission_denial" # Custom type for easier filtering/UI
                                    )
                                else:
                                    log.error(f"AppState missing 'add_message' method. Cannot add permission denial message for user for tool {function_name}.")

                                error_payload = {
                                    "status": "PERMISSION_DENIED", # Ensure MyBot can detect this
                                    "error": "PermissionDenied",
                                    "tool_call_id": tool_call_id,
                                    "tool_name": function_name,
                                    "message": permission_denied_message # Message from the decorator
                                }
                                result_content_for_output = json.dumps(error_payload)
                                current_call_is_error = True
                                last_exception = None # Not an exception, but a handled denial

                                # Update stats for failed tool call due to permission denial
                                execution_duration_ms_denied = raw_result_content.get("execution_time_ms", 0)
                                if app_state and hasattr(app_state, 'session_stats') and app_state.session_stats:
                                    app_state.session_stats.tool_calls = getattr(app_state.session_stats, 'tool_calls', 0) + 1
                                    app_state.session_stats.tool_execution_ms = getattr(app_state.session_stats, 'tool_execution_ms', 0) + execution_duration_ms_denied
                                    app_state.session_stats.failed_tool_calls = getattr(app_state.session_stats, 'failed_tool_calls', 0) + 1
                                    if hasattr(app_state, 'update_tool_usage') and callable(app_state.update_tool_usage):
                                        app_state.update_tool_usage(function_name, execution_duration_ms_denied, False) # False for is_success
                                    was_permission_denied_in_retry_loop = True # Mark that permission was denied and handled
                                 
                                # Add to tool_result_messages and internal_messages
                                # This part is moved outside the try-except block for tool execution attempts
                                # and will be handled by the main loop's message appending logic.
                                # However, we need to ensure current_call_is_error and result_content_for_output are set.
                                
                                # Break from the retry loop for this tool call as it's a definitive denial
                                break # from the for attempt in range(MAX_TOOL_EXECUTION_RETRIES) loop

                            # --- END PERMISSION_DENIED HANDLING ---

                            if isinstance(raw_result_content, dict):
                                result_content_for_output = json.dumps(raw_result_content)
                                # Check for general errors *after* specific PERMISSION_DENIED handling
                                if raw_result_content.get("error") is not None or raw_result_content.get("status", "").upper() == "ERROR":
                                    attempt_produced_error = True
                                    log.warning(
                                        f"ToolExecutor returned an error structure for tool '{function_name}' (ID: {tool_call_id}) on attempt {attempt + 1}.",
                                        extra={"event_type": "tool_executor_error_structure", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "attempt": attempt + 1, "result_preview": result_content_for_output[:200]}}
                                    )
                                    if isinstance(raw_result_content, dict) and raw_result_content.get("is_critical") is True:
                                        log.warning(f"Tool '{function_name}' (ID: {tool_call_id}) reported a critical error in its response (is_critical=True). Setting has_critical_error=True.", extra={"event_type": "tool_reported_critical_error", "details": {"tool_name": function_name, "tool_call_id": tool_call_id}})
                                        has_critical_error = True
                                else:
                                    log.info(
                                        f"Tool '{function_name}' (ID: {tool_call_id}) returned a successful dictionary on attempt {attempt + 1}.",
                                        extra={"event_type": "tool_execution_success_dict", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "attempt": attempt + 1, "result_preview": result_content_for_output[:100]}}
                                    )
                            elif isinstance(raw_result_content, list):
                                result_content_for_output = json.dumps(raw_result_content)
                                log.info(
                                    f"Tool '{function_name}' (ID: {tool_call_id}) returned a list (assumed success) on attempt {attempt + 1}.",
                                    extra={"event_type": "tool_execution_success_list", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "attempt": attempt + 1, "result_preview": result_content_for_output[:100]}}
                                )
                            else:
                                result_content_for_output = str(raw_result_content)
                                log.info(
                                    f"Tool '{function_name}' (ID: {tool_call_id}) returned a primitive (assumed success) on attempt {attempt + 1}.",
                                    extra={"event_type": "tool_execution_success_primitive", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "attempt": attempt + 1, "result_preview": result_content_for_output[:100]}}
                                )
                            
                            current_call_is_error = attempt_produced_error
                            if current_call_is_error: # This is for general tool errors, not PERMISSION_DENIED
                                last_exception = None
                                break
                            else: # Successful execution
                                last_exception = None
                                break
                        except Exception as exec_e:
                            last_exception = exec_e
                            log.warning(
                                f"Exception on attempt {attempt + 1}/{MAX_TOOL_EXECUTION_RETRIES} for tool '{function_name}' (ID: {tool_call_id}).",
                                exc_info=True, # Add exc_info
                                extra={"event_type": "tool_execution_exception_attempt", "details": {"attempt": attempt + 1, "max_attempts": MAX_TOOL_EXECUTION_RETRIES, "tool_name": function_name, "tool_call_id": tool_call_id, "error": str(exec_e)}}
                            )
                            if attempt < MAX_TOOL_EXECUTION_RETRIES - 1:
                                delay = min(TOOL_RETRY_INITIAL_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                                log.info(f"Retrying in {delay:.2f} seconds...", extra={"event_type": "tool_execution_retry_delay", "details": {"delay_seconds": delay}})
                                await asyncio.sleep(delay)
                            else:
                                log.error(
                                    f"All {MAX_TOOL_EXECUTION_RETRIES} retries failed for tool '{function_name}' (ID: {tool_call_id}).",
                                    exc_info=True, # Add exc_info
                                    extra={"event_type": "tool_execution_all_retries_failed", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "last_exception": str(exec_e)}}
                                )
                                error_payload = {"error": "ToolExecutionExceptionAfterRetries", "tool_call_id": tool_call_id, "tool_name": function_name, "exception_type": type(exec_e).__name__, "details": str(exec_e), "attempts": MAX_TOOL_EXECUTION_RETRIES}
                                result_content_for_output = json.dumps(error_payload)
                                current_call_is_error = True
                                if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False):
                                    has_critical_error = True
                                    log.error(
                                        f"Critical exception after retries for tool '{function_name}' (ID: {tool_call_id}). Breaking execution.",
                                        extra={"event_type": "critical_tool_error_after_retries", "details": {"tool_name": function_name, "tool_call_id": tool_call_id}}
                                    )
                    if last_exception and current_call_is_error is False:
                        log.error(
                            f"Tool '{function_name}' (ID: {tool_call_id}) failed after all retries. Final exception: {last_exception}",
                            exc_info=True, # Add exc_info
                            extra={"event_type": "tool_execution_failed_catchall_after_retries", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "final_exception": str(last_exception)}}
                        )
                        error_payload = {"error": "ToolExecutionFailedAfterRetriesCatchAll", "tool_call_id": tool_call_id, "tool_name": function_name, "exception_type": type(last_exception).__name__, "details": str(last_exception), "attempts": MAX_TOOL_EXECUTION_RETRIES}
                        result_content_for_output = json.dumps(error_payload)
                        current_call_is_error = True
                        if config and getattr(config, 'BREAK_ON_CRITICAL_TOOL_ERROR', False): has_critical_error = True
                
                # If permission was denied, the specific stats update already occurred. Skip general one.
                if not was_permission_denied_in_retry_loop:
                    execution_duration_ms = 0
                    if 'raw_result_content' in locals() and isinstance(raw_result_content, dict): # Check if raw_result_content is defined
                        execution_duration_ms = raw_result_content.get("execution_time_ms", 0)
                    
                    if app_state and hasattr(app_state, 'session_stats') and app_state.session_stats:
                        tool_name_for_stats = effective_tool_name_for_part
                        is_success_for_stats = not current_call_is_error
                        app_state.session_stats.tool_calls = getattr(app_state.session_stats, 'tool_calls', 0) + 1
                        app_state.session_stats.tool_execution_ms = getattr(app_state.session_stats, 'tool_execution_ms', 0) + execution_duration_ms
                        if current_call_is_error: app_state.session_stats.failed_tool_calls = getattr(app_state.session_stats, 'failed_tool_calls', 0) + 1
                        if hasattr(app_state, 'update_tool_usage') and callable(app_state.update_tool_usage):
                            app_state.update_tool_usage(tool_name_for_stats, execution_duration_ms, is_success_for_stats)
                        else:
                            log.warning(
                                f"AppState missing 'update_tool_usage' method. Cannot update detailed tool stats for {tool_name_for_stats}.",
                                extra={"event_type": "missing_update_tool_usage_method", "details": {"tool_name": tool_name_for_stats}}
                            )

                if current_call_is_error and not has_critical_error:
                    try:
                        error_payload_check = json.loads(result_content_for_output)
                        log.debug(
                            "Checking tool error payload for 'is_critical'.",
                            extra={"event_type": "check_tool_error_payload_critical", "details": {"payload": error_payload_check, "is_critical_type": str(type(error_payload_check.get('is_critical'))), "is_critical_value": error_payload_check.get('is_critical')}}
                        )
                        if isinstance(error_payload_check, dict) and error_payload_check.get("is_critical") is True:
                            log.warning(
                                f"Tool '{function_name}' (ID: {tool_call_id}) reported a critical error in its response. Setting has_critical_error=True.",
                                extra={"event_type": "tool_reported_critical_error_response", "details": {"tool_name": function_name, "tool_call_id": tool_call_id}}
                            )
                            has_critical_error = True
                    except Exception as e_parse:
                        log.warning(
                            f"Could not parse tool's error response for '{function_name}' (ID: {tool_call_id}) to check 'is_critical'.",
                            exc_info=True, # Add exc_info
                            extra={"event_type": "parse_tool_error_response_failed_critical_check", "details": {"tool_name": function_name, "tool_call_id": tool_call_id, "error": str(e_parse)}}
                        )

        tool_result_messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": effective_tool_name_for_part, "content": result_content_for_output, "is_error": current_call_is_error})
        internal_messages.append({"role": "system", "content": f"Tool Execution: Name='{effective_tool_name_for_part}', ID='{tool_call_id}', Success={not current_call_is_error}, Result (preview)='{result_content_for_output[:100]}...'"})
        current_call_hash_for_history = _compute_tool_call_hash(effective_tool_name_for_part, effective_args_json_str_for_log_hash)
        updated_previous_calls.append((tool_call_id, effective_tool_name_for_part, effective_args_json_str_for_log_hash, current_call_hash_for_history))

        if not current_call_is_error and app_state and hasattr(app_state, 'scratchpad'):
            try:
                parsed_output_for_summary = json.loads(result_content_for_output)
                summary = _summarize_tool_result(parsed_output_for_summary)
            except (json.JSONDecodeError, TypeError):
                summary = f"Tool '{effective_tool_name_for_part}' executed. Raw output (preview): {result_content_for_output[:100]}..."
            scratchpad_input_args_str = json.dumps(args_dict_for_processing)
            app_state.scratchpad.append(ScratchpadEntry(tool_name=effective_tool_name_for_part, tool_input=scratchpad_input_args_str, result=result_content_for_output, is_error=current_call_is_error, summary=summary))
            log.debug(f"Added to scratchpad: {effective_tool_name_for_part}", extra={"event_type": "scratchpad_entry_added", "details": {"tool_name": effective_tool_name_for_part}})
 
        # If a critical error occurred during this tool call's processing, break the loop.
        if has_critical_error:
            log.info(f"Critical error flag is set after processing tool '{effective_tool_name_for_part}'. Breaking from tool call loop.", extra={"event_type": "critical_error_break_loop", "details": {"tool_name": effective_tool_name_for_part, "tool_call_id": tool_call_id}})
            break
 
    log.debug(
        "_execute_tool_calls: Completed.",
        extra={"event_type": "tool_execution_end", "details": {"result_message_count": len(tool_result_messages), "has_critical_error": has_critical_error}}
    )
    return tool_result_messages, internal_messages, has_critical_error, updated_previous_calls
 
# --- Tool Parameter Validation ---
 
def _validate_tool_parameters(
    function_name: str,
    function_args: Dict[str, Any],
    available_tool_definitions: List[Dict[str, Any]]
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Validates tool function arguments against the tool's parameter schema using jsonschema.

    Args:
        function_name: The name of the tool to validate arguments for
        function_args: The deserialized arguments dictionary
        available_tool_definitions: List of tool definitions with schemas

    Returns:
        Tuple containing:
        - Boolean indicating if validation passed
        - Error message string if validation failed, None otherwise
        - Dictionary with original arguments (jsonschema.validate does not
          modify the instance unless a validator like `default` is used and 
          a validating instance of a DraftXValidator is created and used, 
          which is more advanced usage).
    """
    if not JSONSCHEMA_AVAILABLE:
        log.error(
            "jsonschema library not available. Cannot perform robust validation for tool '%s'. Falling back to basic validation (all valid).", 
            function_name,
            extra={"event_type": "jsonschema_not_available", "details": {"tool_name": function_name}}
        )
        # Fallback: consider valid but log error. Or could return False.
        # For now, to minimize disruption if library temporarily missing,
        # let's assume valid but clearly log it's not a proper validation.
        return True, "jsonschema library not available, validation skipped.", function_args

    tool_def = next((tool for tool in available_tool_definitions if tool.get("name") == function_name), None)

    if not tool_def:
        log.warning(
            f"Tool definition not found for '{function_name}' during parameter validation.",
            extra={"event_type": "tool_def_not_found_validation", "details": {"tool_name": function_name}}
        )
        return False, f"Tool '{function_name}' not found in available tool definitions", function_args

    parameter_schema = tool_def.get("parameters")

    # If no "parameters" field or it's empty, or not a dict, consider it valid as there's no schema to check against.
    if not parameter_schema or not isinstance(parameter_schema, dict) or not parameter_schema.get("properties"):
        log.debug(
            f"No parameter schema or properties defined for tool '{function_name}'. Skipping jsonschema validation.",
            extra={"event_type": "no_parameter_schema_for_validation", "details": {"tool_name": function_name}}
        )
        return True, None, function_args

    try:
        # Validate the function_args against the parameter_schema
        # jsonschema.validate raises ValidationError on failure, or returns None on success.
        validate_schema(instance=function_args, schema=parameter_schema)
        
        # If validation passes, the original function_args are considered valid.
        # The jsonschema `validate` function itself doesn't return the validated instance
        # or an instance with defaults applied unless you use a validator instance
        # that is configured to do so (e.g. Draft7Validator(schema).validate_filling_defaults(instance)).
        # For now, we assume the primary goal is validation, not default filling here.
        log.debug(
            f"jsonschema validation successful for tool '{function_name}'.",
            extra={"event_type": "jsonschema_validation_success", "details": {"tool_name": function_name, "args": function_args}}
        )
        return True, None, function_args
    except SchemaValidationError as e:
        # Construct a detailed error message
        path_str = " -> ".join(map(str, e.path)) if e.path else "N/A"
        validator_str = f"validator: '{e.validator}' with value '{e.validator_value}'"
        schema_path_str = " -> ".join(map(str, e.schema_path)) if e.schema_path else "N/A"
        
        error_message = (
            f"Parameter validation failed for '{function_name}': {e.message}. "
            f"Path in data: '{path_str}'. Validator: {validator_str}. Schema path: '{schema_path_str}'."
        )
        log.warning(
            error_message,
            extra={
                "event_type": "tool_parameter_jsonschema_validation_failed",
                "details": {
                    "tool_name": function_name,
                    "raw_error": str(e), # Full exception string
                    "message": e.message,
                    "path": list(e.path),
                    "validator": e.validator,
                    "validator_value": e.validator_value,
                    "schema_path": list(e.schema_path),
                    "schema": e.schema, # The sub-schema that failed
                    "instance_value_at_failure": e.instance # The value in the instance that failed
                }
            }
        )
        # Return original args for context, but indicate failure with the detailed message
        return False, error_message, function_args
    except Exception as e:  # Catch other potential errors from the validation library itself or schema issues
        log.error(
            f"An unexpected error occurred during jsonschema validation for tool '{function_name}': {e}",
            exc_info=True,
            extra={"event_type": "jsonschema_unexpected_error", "details": {"tool_name": function_name, "error": str(e)}}
        )
        return False, f"Unexpected validation error for '{function_name}': {str(e)}", function_args

# --- Circular Call Detection ---


def _compute_tool_call_hash(function_name: str, args_str: str) -> str:
    """Computes a stable hash for a tool call."""
    normalized_content = f"{function_name.lower()}:{args_str.strip()}"
    return hashlib.md5(normalized_content.encode()).hexdigest()


def _are_tool_args_similar(args_str1: str, args_str2: str) -> bool:
    """Checks if two serialized argument strings are highly similar."""
    # Both empty
    if not args_str1 and not args_str2:
        return True
    
    # One empty, one not
    if bool(args_str1.strip()) != bool(args_str2.strip()):
        return False
        
    if not isinstance(args_str1, str) or not isinstance(args_str2, str):
        return False
        
    # Both non-empty, check similarity
    similarity = difflib.SequenceMatcher(None, args_str1, args_str2).ratio()
    return similarity >= SIMILARITY_THRESHOLD


def _detect_circular_calls(
    function_name: str,
    args_str: str,
    previous_calls: List[Tuple[str, str, str]]  # List of (name, args, hash)
) -> Tuple[bool, Optional[str]]:
    """Detects exact duplicate or highly similar repeated tool calls, but allows retries after failures."""
    if not isinstance(args_str, str):
        log.warning(
            "Attempted to detect circular call with non-string args_str. Treating as non-circular.",
            extra={"event_type": "circular_call_detection_invalid_args", "details": {"function_name": function_name, "args_type": str(type(args_str))}}
        )
        return False, None

    current_hash = _compute_tool_call_hash(function_name, args_str)
    
    # Count consecutive failures for the same tool call
    consecutive_failures = 0
    hash_matches = []
    
    # Look through previous calls in reverse order (most recent first)
    for i in range(len(previous_calls) - 1, -1, -1):
        prev_name, prev_args, prev_hash = previous_calls[i]
        
        if prev_hash == current_hash and prev_name == function_name:
            hash_matches.append((prev_name, i))
            consecutive_failures += 1
        else:
            # If we hit a different call, stop counting consecutive failures
            break
    
    if hash_matches:
        # Allow up to 2 retries for the same exact call (total of 3 attempts)
        MAX_RETRIES = 2
        if consecutive_failures <= MAX_RETRIES:
            log.info(
                f"Allowing retry #{consecutive_failures + 1} for tool '{function_name}' after previous failures",
                extra={"event_type": "retry_allowed", "details": {"function_name": function_name, "retry_number": consecutive_failures + 1}}
            )
            return False, None
        else:
            prev_name, idx = hash_matches[0]
            return True, (
                f"Excessive retries detected: '{function_name}' attempted {consecutive_failures + 1} times "
                f"with identical arguments (exceeds max retries of {MAX_RETRIES + 1})"
            )

    similar_calls = [(i, prev_args) for i, (prev_name, prev_args, _)
                     in enumerate(previous_calls)
                     if prev_name == function_name and
                     _are_tool_args_similar(args_str, prev_args)]
    if len(similar_calls) >= MAX_SIMILAR_TOOL_CALLS - 1:
        repetition_count = len(similar_calls) + 1
        indices = [i + 1 for i, _ in similar_calls]
        return True, (
            f"Circular pattern suspected: '{function_name}' called "
            f"{repetition_count} times with similar arguments "
            f"(calls #{', #'.join(map(str, indices))})"
        )
    return False, None

# --- Argument Serialization/Deserialization ---


def _serialize_arguments(args: Any) -> str:
    """Serializes tool arguments robustly into a JSON string."""
    try:
        if args is None:
            return "{}"
        if isinstance(args, str):
            try:
                # Attempt to parse if it's a JSON string already
                parsed = json.loads(args)
                return json.dumps(parsed)  # Re-serialize for consistent format
            except json.JSONDecodeError:
                # If not JSON, wrap it as a string value in a JSON object
                return json.dumps({"value": args})

        def default_serializer(o):
            try:
                if isinstance(o, (set, frozenset)):
                    return list(o)
                elif hasattr(o, '__dict__'):
                    return o.__dict__
                return repr(o)
            except Exception as e:
                log.warning(f"Serialization failed for type {type(o)}.", exc_info=True, extra={"event_type": "serialization_default_handler_error", "details": {"object_type": str(type(o)), "error": str(e)}})
                return f"[Unserializable object: {type(o).__name__}]"

        return json.dumps(args, default=default_serializer)

    except TypeError as e:
        log.error("Failed to serialize arguments due to TypeError.", exc_info=True, extra={"event_type": "serialization_type_error", "details": {"args_type": str(type(args)), "error": str(e)}})
        return json.dumps({"error": "Serialization failed", "error_type": "TypeError", "error_message": str(e), "args_type": str(type(args)), "args_repr": repr(args)[:500]})
    except Exception as e:
        log.error("Unexpected error during argument serialization.", exc_info=True, extra={"event_type": "serialization_unexpected_error", "details": {"error": str(e)}})
        return json.dumps({"error": "Serialization failed", "error_type": str(type(e).__name__), "error_message": str(e)})


def _deserialize_arguments(args_str: str) -> Dict[str, Any]:
    """Deserializes a JSON argument string into a Python dict."""
    if not isinstance(args_str, str):
        log.error("Invalid type for argument deserialization.", extra={"event_type": "deserialization_invalid_input_type", "details": {"input_type": str(type(args_str))}})
        return {"error": "InvalidInputType", "raw_arguments": repr(args_str)}

    if not args_str.strip():
        return {}
    try:
        args = json.loads(args_str)
        if isinstance(args, dict) and "error" in args and "args_repr" in args:
            log.warning("Deserializing previously errored arguments.", extra={"event_type": "deserialization_errored_args", "details": {"error_details": args.get('error')}})
            return args
        if not isinstance(args, dict):
            log.warning("Deserialized arguments are not a dict. Wrapping in 'value' key.", extra={"event_type": "deserialization_not_dict", "details": {"args_type": str(type(args))}})
            return {"value": args}
        return args
    except json.JSONDecodeError as e:
        log.error(f"JSON decode error for argument string: '{args_str[:100]}...'.", exc_info=True, extra={"event_type": "deserialization_json_decode_error", "details": {"error": str(e), "position": e.pos, "args_preview": args_str[:100]}})
        return {"error": "JSONDecodeError", "message": str(e), "position": e.pos, "raw_arguments": args_str[:500]}
    except Exception as e:
        log.error("Unexpected error during argument deserialization.", exc_info=True, extra={"event_type": "deserialization_unexpected_error", "details": {"error": str(e), "args_preview": args_str[:100]}})
        return {"error": str(type(e).__name__), "message": str(e), "raw_arguments": args_str[:500]}

# --- Tool Response Formatting ---


def _format_tool_response_payload(function_name: str, result_content: Any) -> dict:
    """
    Formats the result from a tool execution into the proper tool response message format.

    Args:
        function_name: The name of the function/tool that was called
        result_content: The return value from the function/tool

    Returns:
        A dictionary with role='tool', name=function_name, and content=<serialized>
    """
    if result_content is None:
        result_content = {}  # Ensure it's a dict if None

    def fallback_serializer(obj):
        if hasattr(obj, 'to_dict') and callable(obj.to_dict):
            return obj.to_dict()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

    if isinstance(result_content, str):
        # If it's already a string, try to parse as JSON, then re-dump for consistency
        # or keep as string if not valid JSON.
        try:
            parsed_content = json.loads(result_content)
            content = json.dumps(parsed_content, default=fallback_serializer, ensure_ascii=False)
        except json.JSONDecodeError:
            content = result_content  # Keep as string if not valid JSON
    else:
        try:
            content = json.dumps(result_content, default=fallback_serializer, ensure_ascii=False)
        except (TypeError, ValueError):
            # Fallback to string representation if JSON serialization fails
            content = str(result_content)

    response = {
        "role": "tool",
        "name": function_name,
        "content": content
    }
    return response

# --- Utility Functions ---


def _summarize_tool_result(result: Dict[str, Any], max_length: int = 150) -> str:
    """Creates a brief summary of a tool execution result."""
    if not result or not isinstance(result, dict):
        return "No result or invalid result format"
    if result.get("status", "").upper() == "ERROR":
        error_type = result.get("error_type", "Unknown error")
        message = result.get("message", "No details provided")
        return f"Error: {error_type} - {message}"
    data_to_summarize = result.get("data", result)
    if not isinstance(data_to_summarize, (dict, list)):
        summary = str(data_to_summarize)
    elif isinstance(data_to_summarize, list):
        item_type = data_to_summarize[0].__class__.__name__ if data_to_summarize else "item"
        summary = f"Retrieved {len(data_to_summarize)} {item_type}s"
    elif isinstance(data_to_summarize, dict):
        summary_parts = []
        priority_keys = ["name", "title", "id", "status", "message", "count", "result", "key", "summary", "answer"]
        for key in priority_keys:
            if key in data_to_summarize:
                value = data_to_summarize[key]
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                summary_parts.append(f"{key}: {value}")
        if len(summary_parts) < 3:
            for key, value in data_to_summarize.items():
                if key not in priority_keys and len(summary_parts) < 3:
                    if isinstance(value, (dict, list)):
                        continue
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:47] + "..."
                    summary_parts.append(f"{key}: {value}")
        summary = "; ".join(summary_parts)
    else:
        summary = "[Unexpected data format]"

    if len(summary) > max_length:
        summary = summary[:max_length - 3] + "..."
    return summary or "[No summary generated]"


def _generate_tool_call_id(function_name: str) -> str:
    """Generates a unique ID for a tool call."""
    return f"call_{function_name}_{uuid.uuid4().hex[:8]}"
