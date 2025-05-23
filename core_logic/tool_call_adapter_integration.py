"""
Integration module for the ToolCallAdapter.

This module provides functions to handle the integration of the ToolCallAdapter 
with the rest of the system, bridging the LLM's simplified service calls and
the detailed internal tool implementations.
"""

import logging
import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple, Iterable

from config import Config
from state_models import AppState, ScratchpadEntry
from tools.tool_executor import ToolExecutor
from core_logic.tool_call_adapter import ToolCallAdapter

# Import for saving UserProfile
from user_auth import db_manager # For saving UserProfile
from user_auth.utils import _user_profile_cache, _cache_lock # For updating cache
import time # For cache timestamp

log = logging.getLogger("core_logic.tool_call_adapter_integration")

async def process_service_tool_calls(
    tool_calls: List[Dict[str, Any]],
    tool_executor: ToolExecutor,
    app_state: AppState,
    config: Config
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """
    Process service-level tool calls from the LLM using the ToolCallAdapter.
    
    Args:
        tool_calls: The tool calls from the LLM in simplified service-level format.
            Expected format: [{"id": "...", "function": {"name": "service", "arguments": "..."}}]
        tool_executor: The ToolExecutor to execute the detailed tool implementations.
        app_state: The current application state.
        config: The application configuration.
    
    Returns:
        A tuple of (tool result messages, internal messages, has_critical_error).
    """
    tool_result_messages: List[Dict[str, Any]] = []
    internal_messages: List[Dict[str, Any]] = []
    has_critical_error = False
    
    # Initialize the ToolCallAdapter
    adapter = ToolCallAdapter(tool_executor, config)
    log.info(f"Processing {len(tool_calls)} service-level tool calls using ToolCallAdapter")
    
    for idx, tool_call in enumerate(tool_calls):
        tool_call_id = tool_call.get("id", f"tool_call_{idx}_{int(asyncio.get_event_loop().time())}")
        function_call_dict = tool_call.get("function")
        
        if not function_call_dict:
            log.warning(f"Tool call ID '{tool_call_id}' is missing 'function' field. Skipping.")
            error_payload = {
                "error": "MalformedToolCall",
                "tool_call_id": tool_call_id,
                "message": "Tool call is missing the 'function' field."
            }
            error_response_message = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": "unknown_malformed_call",
                "content": json.dumps(error_payload),
                "is_error": True,
                "metadata": {}
            }
            tool_result_messages.append(error_response_message)
            internal_messages.append({
                "role": "system",
                "content": f"Tool Execution Error: Malformed call, ID='{tool_call_id}', Error: {error_payload.get('message')}"
            })
            
            if config.BREAK_ON_CRITICAL_TOOL_ERROR:
                has_critical_error = True
                log.error(f"Critical error: Malformed tool call (ID: {tool_call_id}) missing 'function' field. Breaking execution.")
                break
            continue
        
        # Extract service name and arguments
        service_name = function_call_dict.get("name")
        function_args_json_str = function_call_dict.get("arguments", "{}")
        
        # Validate service name
        if not service_name:
            log.warning(f"Tool call ID '{tool_call_id}' has invalid/missing service name.")
            error_payload = {
                "error": "MalformedToolCall",
                "tool_call_id": tool_call_id,
                "message": "Tool call is missing a valid service name."
            }
            error_response_message = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": "unknown_invalid_service_name",
                "content": json.dumps(error_payload),
                "is_error": True,
                "metadata": {}
            }
            tool_result_messages.append(error_response_message)
            internal_messages.append({
                "role": "system",
                "content": f"Tool Execution Error: Invalid service name, ID='{tool_call_id}'"
            })
            
            if config.BREAK_ON_CRITICAL_TOOL_ERROR:
                has_critical_error = True
                log.error(f"Critical error: Tool call (ID: {tool_call_id}) with invalid service name. Breaking execution.")
                break
            continue
        
        # Parse arguments
        try:
            if not function_args_json_str or function_args_json_str.strip() == "":
                args_dict = {}
            elif isinstance(function_args_json_str, str):
                args_dict = json.loads(function_args_json_str)
                if not isinstance(args_dict, dict):
                    args_dict = {"raw_value": args_dict}
            else:
                # Already parsed object
                args_dict = function_args_json_str if isinstance(function_args_json_str, dict) else {"raw_value": function_args_json_str}
        except json.JSONDecodeError as e:
            log.warning(f"Tool call ID '{tool_call_id}' has invalid JSON arguments: {e}")
            error_payload = {
                "error": "InvalidArguments",
                "tool_call_id": tool_call_id,
                "message": f"Invalid JSON arguments: {str(e)}",
                "raw_arguments": function_args_json_str[:100] if isinstance(function_args_json_str, str) else str(function_args_json_str)[:100]
            }
            error_response_message = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": service_name,
                "content": json.dumps(error_payload),
                "is_error": True,
                "metadata": {}
            }
            tool_result_messages.append(error_response_message)
            internal_messages.append({
                "role": "system",
                "content": f"Tool Execution Error: Invalid arguments for service '{service_name}', ID='{tool_call_id}', Error: {str(e)}"
            })
            
            if config.BREAK_ON_CRITICAL_TOOL_ERROR:
                has_critical_error = True
                log.error(f"Critical error: Tool call (ID: {tool_call_id}) with invalid JSON arguments. Breaking execution.")
                break
            continue
        
        # Prepare tool call for the adapter
        adapter_tool_call = {
            "name": service_name,
            "params": args_dict,
            "id": tool_call_id
        }
        
        try:
            # Use the adapter to process the service-level call and execute the appropriate detailed tool
            result = await adapter.process_llm_tool_call(adapter_tool_call, app_state)
            
            # --- Save UserProfile if metrics were updated by the adapter ---
            # The _record_selection_outcome method in ToolCallAdapter updates app_state.current_user.tool_adapter_metrics.
            # We need to persist this UserProfile change.
            if app_state and app_state.current_user and hasattr(app_state.current_user, 'tool_adapter_metrics'):
                # Assuming _record_selection_outcome was called if app_state was provided to process_llm_tool_call
                # and metrics are part of current_user. A more explicit flag from _record_selection_outcome would be robust.
                try:
                    user_profile_data = app_state.current_user.model_dump(mode='json')
                    if db_manager.save_user_profile(user_profile_data):
                        log.info(f"Saved updated UserProfile (with tool metrics) for {app_state.current_user.user_id} after adapter call.")
                        # Update cache as well
                        with _cache_lock:
                            _user_profile_cache.put(
                                app_state.current_user.user_id,
                                user_profile_data, # The dumped data
                                time.time()
                            )
                            log.debug(f"Updated UserProfile cache for {app_state.current_user.user_id}.")
                    else:
                        log.error(f"Failed to save updated UserProfile for {app_state.current_user.user_id} after adapter call.")
                except Exception as e_save_profile:
                    log.error(f"Error saving/caching UserProfile after adapter call for {app_state.current_user.user_id if app_state.current_user else 'UnknownUser'}: {e_save_profile}", exc_info=True)
            # --- End UserProfile Save ---
            
            # Check if the result indicates an error
            is_error = False
            if isinstance(result, dict) and result.get("status") == "ERROR":
                is_error = True
                log.warning(f"Tool call for service '{service_name}' (ID: {tool_call_id}) failed: {result.get('message', 'Unknown error')}")
            
            # Serialize the result
            result_content = json.dumps(result) if not isinstance(result, str) else result
            
            # Create the standard tool response message
            tool_response_message = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": service_name,
                "content": result_content,
                "is_error": is_error,
                "metadata": {"executed_tool_name": result.get("executed_tool_name", service_name) if isinstance(result, dict) else service_name}
            }
            tool_result_messages.append(tool_response_message)
            
            # Add internal message for logging
            internal_messages.append({
                "role": "system",
                "content": f"Tool Execution: Service='{service_name}', ID='{tool_call_id}', Success={not is_error}, Result (preview): '{result_content[:100]}...'"
            })
            
            # Add to scratchpad if not an error
            if not is_error and app_state and hasattr(app_state, 'scratchpad'):
                try:
                    # Attempt to create a summary
                    summary = f"Service '{service_name}' executed successfully."
                    if isinstance(result, dict) and result.get("executed_tool_name") and result.get("executed_tool_name") != service_name:
                        summary += f" (via detailed tool: {result.get('executed_tool_name')})."
                    else:
                        summary += "."
                    
                    # Create the scratchpad entry
                    app_state.scratchpad.append(
                        ScratchpadEntry(
                            tool_name=service_name,
                            tool_input=json.dumps(args_dict),
                            result=result_content,
                            is_error=is_error,
                            summary=summary
                        )
                    )
                    log.debug(f"Added to scratchpad: {service_name}")
                except Exception as e:
                    log.warning(f"Failed to add scratchpad entry for service '{service_name}': {e}")
            
            # --- STATS UPDATE --- 
            if app_state and hasattr(app_state, 'session_stats') and app_state.session_stats:
                # For adapter, actual execution_time_ms of the detailed tool isn't directly available here
                # We'll use 0 for now, or this could be enhanced if ToolCallAdapter provides timing.
                execution_duration_ms_adapter = 0 
                if isinstance(result, dict):
                    # Check if the adapter's result for the *detailed tool* included timing
                    # This is a guess at a possible structure; adapter might need to be enhanced to provide this.
                    if isinstance(result.get("detailed_tool_result"), dict):
                        execution_duration_ms_adapter = result["detailed_tool_result"].get("execution_time_ms", 0)
                    elif "execution_time_ms" in result: # If adapter itself reports a time
                        execution_duration_ms_adapter = result.get("execution_time_ms", 0)

                app_state.session_stats.tool_calls = getattr(app_state.session_stats, 'tool_calls', 0) + 1
                app_state.session_stats.tool_execution_ms = getattr(app_state.session_stats, 'tool_execution_ms', 0) + execution_duration_ms_adapter
                if is_error:
                    app_state.session_stats.failed_tool_calls = getattr(app_state.session_stats, 'failed_tool_calls', 0) + 1
                
                tool_name_for_stats = service_name # Log the service name for adapter calls
                if hasattr(app_state, 'update_tool_usage') and callable(app_state.update_tool_usage):
                    app_state.update_tool_usage(tool_name_for_stats, execution_duration_ms_adapter, not is_error)
                else:
                    log.warning(f"AppState missing 'update_tool_usage' method. Cannot update detailed tool stats for {tool_name_for_stats}.")
            # --- END STATS UPDATE ---
            
            # Check for critical errors in the result
            if is_error and isinstance(result, dict) and result.get("is_critical") is True:
                has_critical_error = True
                log.error(f"Critical error reported by service '{service_name}' (ID: {tool_call_id}): {result.get('message', 'Unknown critical error')}")
                if config.BREAK_ON_CRITICAL_TOOL_ERROR:
                    break
                
        except Exception as e:
            log.error(f"Error processing tool call for service '{service_name}' (ID: {tool_call_id}): {e}", exc_info=True)
            error_payload = {
                "error": "AdapterProcessingError",
                "tool_call_id": tool_call_id,
                "message": f"Error processing service tool call: {str(e)}"
            }
            error_response_message = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": service_name,
                "content": json.dumps(error_payload),
                "is_error": True,
                "metadata": {}
            }
            tool_result_messages.append(error_response_message)
            internal_messages.append({
                "role": "system",
                "content": f"Tool Execution Error: Failed to process service '{service_name}', ID='{tool_call_id}', Error: {str(e)}"
            })
            
            if config.BREAK_ON_CRITICAL_TOOL_ERROR:
                has_critical_error = True
                log.error(f"Critical error processing service tool call: {e}")
                break
    
    return tool_result_messages, internal_messages, has_critical_error

def create_tool_adapter_for_executor(tool_executor: ToolExecutor, config: Config) -> ToolCallAdapter:
    """
    Create a ToolCallAdapter instance for the given tool executor.
    
    Args:
        tool_executor: The ToolExecutor to use for executing detailed tools.
        config: The application configuration.
    
    Returns:
        A ToolCallAdapter instance.
    """
    return ToolCallAdapter(tool_executor, config) 