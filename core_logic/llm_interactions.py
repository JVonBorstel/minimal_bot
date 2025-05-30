"""Functions for interacting with LLM services."""

import logging # Added
import time
import json # For _serialize_arguments used in _process_llm_stream
from typing import List, Dict, Any, Optional, Tuple, Iterable, TypeAlias, Union
import pprint # ADD THIS IMPORT

import google.api_core.exceptions as google_exceptions
import requests.exceptions  # For _process_llm_stream error handling

from state_models import AppState, SessionDebugStats  # SessionDebugStats for _update_session_stats
from core_logic.text_utils import is_greeting_or_chitchat  # Import the utility function

# Import the robust function_call extraction utility
from utils.function_call_utils import safe_extract_function_call

# --- SDK Types Setup ---
SDK_AVAILABLE = False

# Minimal mock types needed by llm_interactions
class _MockGlmFunctionCall:
    def __init__(self, name: str, args: Optional[Dict[str, Any]] = None):
        self.name = name
        self.args = args or {}
    def __str__(self): 
        return f"MockFunctionCall(name='{self.name}')"

class _MockGlm:
    FunctionCall = _MockGlmFunctionCall
    # Add other types if needed
    class Part: # Add mock Part for type consistency if SDK not available
        def __init__(self, text: Optional[str] = None, function_call: Optional['_MockGlmFunctionCall'] = None):
            self.text = text
            self.function_call = function_call
    
    class Content: # Add mock Content
        def __init__(self, parts: Optional[List[Any]] = None, role: Optional[str] = None):
            self.parts = parts or []
            self.role = role


# Define TypeAliases - these will be valid regardless of SDK availability
ContentType: TypeAlias = Any  # Will be glm.Content or Dict[str, Any]
GenerateContentResponseType: TypeAlias = Any  # Will be type from SDK or Any

glm: Any = _MockGlm() # Initialize with mock

try:
    import google.ai.generativelanguage as actual_glm_sdk # Use a distinct name for import
    glm = actual_glm_sdk  # type: ignore # glm now refers to the SDK module
    SDK_AVAILABLE = True
    # Optional: Configure logging for the SDK
    # sdk_log = logging.getLogger("google.ai.generativelanguage") # Handled by root logger if needed
    # sdk_log.setLevel(logging.WARNING)
except ImportError:
    logging.getLogger("core_logic.llm_interactions").info(
        "google.ai.generativelanguage SDK not found. Using mock glm types for llm_interactions.",
        extra={"event_type": "sdk_not_found", "details": {"sdk_name": "google.ai.generativelanguage"}}
    )
    # SDK_AVAILABLE remains False, glm remains _MockGlm instance

# For forward references to LLMInterface without circular imports
LLMInterface = Any  # Forward reference, will be resolved at runtime

# Relative imports from core_logic
from .constants import (
    STATUS_ERROR_LLM,
    STORY_BUILDER_TRIGGER_TOOL_SCHEMA,
    MAX_TOOL_ARG_PREVIEW_LEN,
    STATUS_THINKING,  # For _determine_status_message
    STATUS_STORY_BUILDER_PREFIX,  # For _determine_status_message
    LLM_API_RETRY_ATTEMPTS,
    TOOL_RETRY_INITIAL_DELAY, # Reusing for LLM backoff
    MAX_RETRY_DELAY, # Reusing for LLM backoff
)
from .history_utils import _reset_conversation_if_broken, HistoryResetRequiredError
from .tool_processing import _generate_tool_call_id, _serialize_arguments  # For _process_llm_stream
from .tool_selector import ToolSelector # IMPORT TOOL SELECTOR

# from utils.logging_config import get_logger # Removed this as we use standard logging now

log = logging.getLogger("core_logic.llm_interactions") # Use standard logging.getLogger

# --- Safe SDK Object Representation for Logging ---

def _format_fc_args_for_safe_repr(args_raw: Any) -> str:
    """Helper to format function call arguments for _safe_sdk_object_repr_for_log."""
    fc_args_dict = safe_extract_function_call(args_raw)
    
    args_summary = "Args=None"
    if fc_args_dict is not None:
        if isinstance(fc_args_dict, dict) and fc_args_dict.get('_unextractable_type'):
            args_summary = f"Args=[Unextractable:{fc_args_dict['_unextractable_type']}]"
        elif isinstance(fc_args_dict, dict) and fc_args_dict.get('_error'):
            args_summary = f"Args=[ErrorExtracting:{fc_args_dict['_error']}]"
        elif isinstance(fc_args_dict, dict):
            args_summary = f"ArgsKeys={list(fc_args_dict.keys())}"
        else:
            args_summary = f"ArgsType={type(fc_args_dict).__name__}"
    return args_summary

def _safe_sdk_object_repr_for_log(sdk_obj: Any, max_len: int = 500) -> str:
    if sdk_obj is None:
        return "None"

    obj_type_name = type(sdk_obj).__name__
    parts_to_join = [f"Type={obj_type_name}"]

    try:
        # --- SDK-Specific Handling (if SDK is available and types match) ---
        if SDK_AVAILABLE:
            if isinstance(sdk_obj, glm.FunctionCall):
                fc_name = getattr(sdk_obj, 'name', '[UnknownFCName]')
                fc_args_raw = getattr(sdk_obj, 'args', None)
                args_summary = _format_fc_args_for_safe_repr(fc_args_raw)
                parts_to_join.append(f"FunctionCall(Name='{fc_name}', {args_summary})")
                # This is specific enough, join and return
                final_str_val = ", ".join(parts_to_join)
                return final_str_val[:max_len-3] + "..." if len(final_str_val) > max_len else final_str_val

            elif isinstance(sdk_obj, glm.Part):
                if hasattr(sdk_obj, 'function_call') and sdk_obj.function_call:
                    # Recursively call for the FunctionCall object within the Part
                    parts_to_join.append(f"FunctionCall={{{_safe_sdk_object_repr_for_log(sdk_obj.function_call, max_len=150)}}}")
                if hasattr(sdk_obj, 'text') and sdk_obj.text:
                    text_preview = sdk_obj.text.replace('\n', ' ')[:70]
                    text_val = text_preview + ("..." if len(sdk_obj.text) > 70 else "")
                    parts_to_join.append(f"Text='{text_val}'")
                if not (hasattr(sdk_obj, 'text') and sdk_obj.text) and \
                   not (hasattr(sdk_obj, 'function_call') and sdk_obj.function_call):
                    parts_to_join.append("EmptyPart")
                # This is specific enough, join and return
                final_str_val = ", ".join(parts_to_join)
                return final_str_val[:max_len-3] + "..." if len(final_str_val) > max_len else final_str_val
            # Note: glm.Content is also handled by hasattr(sdk_obj, 'parts') below

        # --- Generic Attribute-Based Handling (Covers Mocks and SDK objects if not caught above or SDK unavailable) ---
        # This section handles objects that look like Parts or Content based on attributes
        
        # Check for Part-like attributes
        is_part_like_by_attr = hasattr(sdk_obj, 'function_call') or hasattr(sdk_obj, 'text')

        if is_part_like_by_attr:
            if hasattr(sdk_obj, 'function_call') and sdk_obj.function_call:
                fc_obj = sdk_obj.function_call
                # If fc_obj is an actual SDK FunctionCall, recurse for safety. Otherwise, format its name/args.
                if SDK_AVAILABLE and isinstance(fc_obj, glm.FunctionCall):
                     parts_to_join.append(f"FunctionCallContained={{{_safe_sdk_object_repr_for_log(fc_obj, max_len=150)}}}")
                else: # Mock FunctionCall or other structure
                    fc_name = getattr(fc_obj, 'name', '[UnknownFCName]')
                    fc_args_raw = getattr(fc_obj, 'args', None)
                    args_summary = _format_fc_args_for_safe_repr(fc_args_raw)
                    parts_to_join.append(f"FunctionCall(Name='{fc_name}', {args_summary})")

            if hasattr(sdk_obj, 'text') and sdk_obj.text:
                text_preview = str(sdk_obj.text).replace('\n', ' ')[:70] # Ensure text is string
                text_val = text_preview + ("..." if len(str(sdk_obj.text)) > 70 else "")
                parts_to_join.append(f"Text='{text_val}'")
            
            if not (hasattr(sdk_obj, 'text') and sdk_obj.text) and \
               not (hasattr(sdk_obj, 'function_call') and sdk_obj.function_call):
                 parts_to_join.append("EmptyOrUnknownPartLike")

        # Check for Content-like attributes (e.g., glm.Content, GenerateContentResponse, Chunks)
        elif hasattr(sdk_obj, 'parts') and isinstance(sdk_obj.parts, list):
            parts_to_join.append(f"NumParts={len(sdk_obj.parts)}")
            sub_parts_summary = []
            for p_idx, p_obj_in_list in enumerate(sdk_obj.parts[:3]): # Limit to 3 for preview
                sub_parts_summary.append(f"P[{p_idx}]:{{{_safe_sdk_object_repr_for_log(p_obj_in_list, max_len=100)}}}") # Recursive
            if sub_parts_summary:
                parts_to_join.append(f"PartsSummary=[{'; '.join(sub_parts_summary)} {'...' if len(sdk_obj.parts) > 3 else ''}]")
            
            if hasattr(sdk_obj, 'usage_metadata') and sdk_obj.usage_metadata:
                um = sdk_obj.usage_metadata
                total_tokens = getattr(um, 'total_token_count', None)
                if total_tokens is not None and isinstance(total_tokens, int): # Check type
                    parts_to_join.append(f"Usage(TotalTokens={total_tokens})")
                else:
                    prompt_tokens = getattr(um, 'prompt_token_count', 'N/A')
                    cand_tokens = getattr(um, 'candidates_token_count', 'N/A')
                    parts_to_join.append(f"Usage(PromptTokens={prompt_tokens}, CandidateTokens={cand_tokens})")
        
        # Handle if sdk_obj is a string itself
        elif isinstance(sdk_obj, str):
            final_str_val = sdk_obj.replace('\n', ' ')
            return final_str_val[:max_len-3] + "..." if len(final_str_val) > max_len else final_str_val
        
        # Fallback if only "Type=..." was added (no specific attributes matched)
        elif len(parts_to_join) == 1:
            try:
                repr_str = repr(sdk_obj) 
                repr_val = repr_str.replace('\n', ' ')[:60] # Short preview
                if len(repr_str) > 60: repr_val += "..."
                parts_to_join.append(f"GenericRepr='{repr_val}'")
            except Exception:
                parts_to_join.append("GenericRepr=[ErrorInRepr]")
        
        final_str_val = ", ".join(parts_to_join)
        
    except Exception as e_repr:
        error_repr_str_val = "[Error getting str(e_repr)]"
        try:
            error_repr_str_val = str(e_repr).replace('\n', ' ')
        except Exception:
            pass 
        final_str_val = f"Type={obj_type_name}, ErrorInSafeRepr='{error_repr_str_val[:100]}...'"

    return final_str_val[:max_len-3] + "..." if len(final_str_val) > max_len else final_str_val

# --- Co-located Helper Functions ---


def _safely_extract_text(part: Any) -> str:
    """Safely extracts text from a glm.Part object, handling potential errors."""
    try:
        if hasattr(part, 'text'):
            if part.text is None:
                return ""  # Return empty string instead of None
            return part.text
        # No text attribute found, return empty string
        return ""  # Return empty string instead of None
    except Exception as e:
        log.error("Error extracting text from part.", exc_info=True, extra={"event_type": "text_extraction_error", "details": {"error": str(e)}})
        return ""


def _determine_status_message(
    cycle_num: int,
    is_initial_decision_call: bool,
    stage_name: Optional[str]
) -> str:
    """
    Determines the appropriate status message based on interaction context.

    Args:
        cycle_num: Current interaction cycle number (0-indexed)
        is_initial_decision_call: Whether this is the first LLM call for user
            request
        stage_name: Current workflow stage name if in a workflow

    Returns:
        str: Formatted status message for display to the user
    """
    if is_initial_decision_call:
        if stage_name:
            # Original: "dYc Planning..."
            return f"⚙️ Planning {stage_name.replace('_', ' ').title()} approach..."
        else:
            # Original: "dY Analyzing..."
            return f"{STATUS_THINKING} Analyzing request and planning response..."
    elif stage_name:
        formatted_stage = stage_name.replace('_', ' ').title()
        # Use cycle_num+1 for 1-based display
        # cycle_num is 0-indexed stage_cycle
        step_info = f" (Step {cycle_num + 1})" if cycle_num > 0 else ""
        if stage_name == "collecting_info":
            return f"{STATUS_STORY_BUILDER_PREFIX}Gathering information{step_info}"
        elif stage_name == "detailing":
            return (
                f"{STATUS_STORY_BUILDER_PREFIX}Generating detailed "
                f"requirements{step_info}"
            )
        elif stage_name == "drafting_1":
            return f"{STATUS_STORY_BUILDER_PREFIX}Creating initial draft{step_info}"
        elif stage_name == "drafting_2":
            return f"{STATUS_STORY_BUILDER_PREFIX}Refining draft{step_info}"
        elif stage_name in ("draft1_review", "draft2_review",
                            "awaiting_confirmation"):
            # These stages typically wait for user, not LLM calls
            return (
                f"{STATUS_STORY_BUILDER_PREFIX}{formatted_stage} - Awaiting user "
                f"input"
            )
        elif stage_name == "creating_ticket":
            return f"{STATUS_STORY_BUILDER_PREFIX}Creating Jira ticket..."
        else:
            return f"{STATUS_STORY_BUILDER_PREFIX}{formatted_stage}{step_info}"
    else:
        # General non-workflow cycles
        if cycle_num == 0:  # cycle_num is 0-indexed general cycle
            return f"{STATUS_THINKING} Analyzing your request..."
        else:
            return (
                f"{STATUS_THINKING} Processing information "
                f"(Cycle {cycle_num + 1})"
            )


def _update_session_stats(
    app_state: AppState,
    llm_debug_info: Dict[str, Any],
    start_time: float  # This should be the start time of the specific LLM call
) -> None:
    """
    Updates session statistics with LLM call metrics.

    Args:
        app_state: Current application state
        llm_debug_info: Debug information from LLM call
                        (_process_llm_stream's debug_info)
        start_time: Start time of the LLM call (from time.monotonic())
    """
    session_stats = app_state.session_stats
    # Check llm_debug_info is not None
    if isinstance(session_stats, SessionDebugStats) and llm_debug_info:
        session_stats.llm_calls += 1
        # Use stream_duration_ms from debug_info if available, otherwise calculate
        duration_ms = llm_debug_info.get("stream_duration_ms")
        if duration_ms is None:  # Fallback if not in debug_info
            duration_ms = int((time.monotonic() - start_time) * 1000)
        session_stats.llm_api_call_duration_ms += duration_ms
        usage_meta = llm_debug_info.get("usage_metadata")
        if usage_meta and isinstance(usage_meta.get("total_token_count"), int):
            session_stats.llm_tokens_used += usage_meta["total_token_count"]
    elif not llm_debug_info:
        log.warning("Cannot update LLM stats: llm_debug_info is missing.", extra={"event_type": "llm_stats_update_failed", "reason": "missing_debug_info"})
    else:
        log.warning(
            "Cannot update LLM stats: session_stats object is invalid or missing.",
            extra={"event_type": "llm_stats_update_failed", "reason": "invalid_session_stats_object"}
        )


# --- LLM Interaction Functions ---
def _should_provide_tools(
    is_initial_decision_call: bool,
    stage_name: Optional[str],
    user_query: Optional[str] = None
) -> bool:
    """
    Determines whether tools should be provided to the LLM for this interaction.

    Args:
        is_initial_decision_call: Whether this is the first LLM call for user
            request
        stage_name: Current workflow stage name if in a workflow
        user_query: The latest user query, used to determine if this is a
                   greeting or chitchat (which don't need tools)

    Returns:
        bool: True if tools should be provided, False otherwise
    """
    # 1. No tools for initial greeting or chitchat, BUT allow help commands
    if user_query and is_initial_decision_call and is_greeting_or_chitchat(user_query):
        # Allow help commands to get tools for proper help responses
        if any(help_pattern in user_query.lower() for help_pattern in ["help", "commands", "what can you do", "available"]):
            log.debug("Tools provided: help command needs tools for response.", extra={"event_type": "tool_provision_decision", "details": {"provide_tools": True, "reason": "help_command", "user_query_preview": user_query[:50]}})
            return True
        else:
            log.debug("Tools not provided: initial greeting or chitchat.", extra={"event_type": "tool_provision_decision", "details": {"provide_tools": False, "reason": "initial_greeting_chitchat", "user_query_preview": user_query[:50]}})
            return False

    # 2. Specific workflow stages that REQUIRE tools
    if stage_name in ("collecting_info", "drafting_1", "drafting_2", "creating_ticket"):
        log.debug(f"Tools provided: workflow stage '{stage_name}' requires tools.", extra={"event_type": "tool_provision_decision", "details": {"provide_tools": True, "reason": "workflow_stage_requires_tools", "stage_name": stage_name}})
        return True
    
    # 3. Specific workflow stages that explicitly DISABLE tools
    if stage_name in ("detailing", "draft1_review", "draft2_review"):
        log.debug(f"Tools not provided: workflow stage '{stage_name}' explicitly disables tools.", extra={"event_type": "tool_provision_decision", "details": {"provide_tools": False, "reason": "workflow_stage_disables_tools", "stage_name": stage_name}})
        return False
        
    # 4. Otherwise
    log.debug(f"Tools provided: default for general loop or unspecified workflow stage.", extra={"event_type": "tool_provision_decision", "details": {"provide_tools": True, "reason": "default_behavior", "stage_name": stage_name, "is_initial_decision_call": is_initial_decision_call}})
    return True


def _prepare_tool_definitions(
    available_tool_definitions: List[Dict[str, Any]],
    is_initial_decision_call: bool,
    provide_tools: bool,  # This flag is now determined by _should_provide_tools
    user_query: Optional[str] = None,
    config: Optional[Any] = None, # Added config
    app_state: Optional[Any] = None # Added app_state
) -> Optional[List[Dict[str, Any]]]:
    """
    Prepares the final tool definitions to provide to the LLM.

    Args:
        available_tool_definitions: List of all available tool definitions
        is_initial_decision_call: Whether this is the first LLM call for user
                                  request (in general agent loop)
        provide_tools: Whether tools should be provided for this interaction
                       (can be True even if not initial_decision_call, e.g.
                       in a workflow stage)
        user_query: The latest user query, used to determine if story builder
                    trigger should be added.
        config: Configuration object for additional processing
        app_state: Current application state for additional processing

    Returns:
        Optional[List[Dict[str, Any]]]: Final tool definitions or None if no
                                         tools should be provided
    """
    if not provide_tools:
        return None

    # Create a copy to avoid modifying original
    final_tool_definitions = list(available_tool_definitions)

    # --- Apply ToolSelector if enabled ---
    if config and hasattr(config, 'TOOL_SELECTOR') and config.TOOL_SELECTOR.get("enabled") and app_state and user_query:
        log.info("Tool selector is enabled. Selecting relevant tools.", extra={"event_type": "tool_selector_invoked"})
        try:
            tool_selector_instance = ToolSelector(config) # Assumes ToolSelector takes config
            selected_tools = tool_selector_instance.select_tools(
                query=user_query,
                app_state=app_state, # app_state should be passed here
                available_tools=final_tool_definitions # Pass the current full list
            )
            if selected_tools is not None: # select_tools might return None if it fails and default_fallback is False
                log.info(f"ToolSelector selected {len(selected_tools)} tools out of {len(final_tool_definitions)}.", extra={"event_type": "tool_selector_completed", "details": {"selected_count": len(selected_tools), "original_count": len(final_tool_definitions)}})
                final_tool_definitions = selected_tools
            else:
                log.warning("ToolSelector returned None. Using original full list of tools (or whatever was passed in).", extra={"event_type": "tool_selector_returned_none"})
                # Keep final_tool_definitions as is (full list)
        except Exception as e:
            log.error(f"Error during tool selection: {e}. Falling back to using all tools.", exc_info=True, extra={"event_type": "tool_selector_error"})
            # Fallback to using the original list if selector fails
            # final_tool_definitions remains the full list from copy above
    elif config and hasattr(config, 'TOOL_SELECTOR') and config.TOOL_SELECTOR.get("enabled"):
        log.warning("Tool selector is enabled in config, but not applied due to missing app_state or user_query for selection process.", extra={"event_type": "tool_selector_skipped_missing_context"})


    # Add story builder trigger tool only for initial calls (general agent loop)
    # and only if the user's query suggests story creation and it's not already present.
    # This should happen *after* tool selection, so it's always available if conditions are met.
    if is_initial_decision_call:
        should_add_story_builder_trigger = False
        if user_query:
            story_keywords = [
                "create ticket", "build a user story", "draft an issue",
                "make a ticket", "new issue", "new ticket", "jira ticket",
                "create jira", "story builder", "create story"
            ]
            if any(keyword in user_query.lower() for keyword in story_keywords):
                should_add_story_builder_trigger = True
                log.info("User query suggests story creation.", extra={"event_type": "story_builder_trigger_check", "details": {"query_suggests_story": True, "user_query_preview": user_query[:50]}})
            else:
                log.info("User query does not suggest story creation. Story builder trigger will not be added based on query.", extra={"event_type": "story_builder_trigger_check", "details": {"query_suggests_story": False, "user_query_preview": user_query[:50]}})
        else:
            log.info("No user query provided. Story builder trigger will not be added based on query.", extra={"event_type": "story_builder_trigger_check", "details": {"query_suggests_story": False, "reason": "no_user_query"}})

        if should_add_story_builder_trigger:
            trigger_tool_name = STORY_BUILDER_TRIGGER_TOOL_SCHEMA["name"]
            if not any(t.get("name") == trigger_tool_name for t in final_tool_definitions):
                final_tool_definitions.append(STORY_BUILDER_TRIGGER_TOOL_SCHEMA)
                log.info(
                    f"Added '{trigger_tool_name}' tool schema for initial LLM call based on user query.",
                    extra={"event_type": "tool_definition_added", "details": {"tool_name": trigger_tool_name, "reason": "user_query_trigger"}}
                )
            else:
                log.debug(
                    f"'{trigger_tool_name}' tool already present for initial call.",
                    extra={"event_type": "tool_definition_skipped", "details": {"tool_name": trigger_tool_name, "reason": "already_present"}}
                )
        # If not should_add_story_builder_trigger, the tool is not added.
        # This means if the query doesn't match, even on an initial call, the trigger is omitted.
    # If not is_initial_decision_call but provide_tools is True (e.g. inside a
    # workflow stage that needs tools), we just use the
    # available_tool_definitions without adding the trigger, as this logic is for initiation.

    return final_tool_definitions


# Add a new function to format tool results for better LLM processing
def _format_tool_results_for_llm(tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Format tool execution results to optimize LLM's ability to synthesize and use them.
    
    Args:
        tool_results: List of tool execution results
        
    Returns:
        Formatted results with improved structure for LLM consumption
    """
    formatted_results = {
        "results": [],
        "summary": {
            "total_tools_executed": len(tool_results),
            "successful": 0,
            "failed": 0,
            "tool_types": set()
        }
    }
    
    for result in tool_results:
        # Skip None results
        if result is None:
            continue
            
        # Extract core fields
        result_dict = result.copy() if isinstance(result, dict) else {"raw_result": str(result)}
        tool_name = result_dict.get("tool_name", "unknown_tool")
        status = result_dict.get("status", "UNKNOWN").upper()
        
        # Track summary statistics
        if status == "SUCCESS":
            formatted_results["summary"]["successful"] += 1
        elif status in ["ERROR", "FAILED", "FAILURE"]:
            formatted_results["summary"]["failed"] += 1
            
        # Extract tool type for categorization
        tool_type = None
        if "_" in tool_name:
            tool_type = tool_name.split("_")[0]
            formatted_results["summary"]["tool_types"].add(tool_type)
            
        # Process data field for better consumption
        data = result_dict.get("data")
        if isinstance(data, list):
            # For list results, add count and truncate if very large
            result_dict["result_count"] = len(data)
            if len(data) > 100:
                result_dict["data_truncated"] = True
                result_dict["data"] = data[:100]
                result_dict["truncation_message"] = f"Result truncated: {len(data)} total items, showing first 100."
        
        # Add formatted result to the list
        formatted_results["results"].append(result_dict)
        
    # Convert set of tool types to list for serialization
    formatted_results["summary"]["tool_types"] = list(formatted_results["summary"]["tool_types"])
    
    return formatted_results


def _process_llm_stream(
    stream: Iterable[GenerateContentResponseType],
    app_state: Optional[AppState] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None
) -> Iterable[Tuple[str, Any]]:
    """
    Processes the LLM response stream, yielding text chunks, tool calls, and debug info.

    Args:
        stream: The stream of GenerateContentResponse objects
        app_state: Optional AppState for updating streaming placeholder
        tool_results: Optional list of recent tool execution results to help with result synthesis

    Yields:
        Tuple[str, Any]: A tuple where the first element is the type ('text', 'tool_calls', 'debug_info')
                         and the second element is the corresponding data.

    Note:
        All function_call argument extraction is now handled via safe_extract_function_call for robustness.
    """
    start_time = time.monotonic()
    # Store raw FunctionCall objects as they are assembled across chunks
    raw_function_calls: Dict[str, glm.FunctionCall] = {}
    raw_chunks_debug: List[str] = []
    usage_metadata: Optional[Dict[str, Any]] = None
    formatted_tool_calls_for_state: List[Dict[str, Any]] = []
    accumulated_text_for_log = ""  # For final log message
    
    # Track context for result synthesis
    has_tool_results = bool(tool_results and len(tool_results) > 0)
    needs_result_synthesis = False
    synthesis_hints = []

    try:
        for chunk in stream:
            # Log chunk representation safely
            try:
                chunk_repr = _safe_sdk_object_repr_for_log(chunk)
                raw_chunks_debug.append(
                    chunk_repr # _safe_sdk_object_repr_for_log already handles max_len
                )
            except Exception as log_e:
                raw_chunks_debug.append(f"[Error logging chunk via _safe_sdk_object_repr_for_log: {log_e}]")

            # Check for usage metadata (usually at the end)
            if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                usage_metadata = {
                    "prompt_token_count": getattr(chunk.usage_metadata, 'prompt_token_count', None),
                    "candidates_token_count": getattr(chunk.usage_metadata, 'candidates_token_count', None),
                    "total_token_count": getattr(chunk.usage_metadata, 'total_token_count', None)
                }
                log.debug("Received usage metadata.", extra={"event_type": "llm_usage_metadata_received", "details": usage_metadata})

            try:
                parts = chunk.parts if hasattr(chunk, 'parts') else []
                for part in parts:
                    delta_text = _safely_extract_text(part)
                    if delta_text:
                        if has_tool_results:
                            lower_text = delta_text.lower()
                            if any(phrase in lower_text for phrase in ["based on the tool results", "according to the tool", "the tool returned", "as shown by the tool", "from the data provided by"]):
                                needs_result_synthesis = True
                                synthesis_hints.append(delta_text)
                        if app_state is not None and hasattr(app_state, 'streaming_placeholder_content'):
                            if app_state.streaming_placeholder_content is None: app_state.streaming_placeholder_content = ""
                            app_state.streaming_placeholder_content += delta_text
                        yield ("text", delta_text)
                        accumulated_text_for_log += delta_text
                    elif hasattr(part, 'function_call'):
                        if part.function_call is None or not isinstance(part.function_call, glm.FunctionCall):
                            log.warning(
                                "Malformed SDK part: 'function_call' attribute is None or not a glm.FunctionCall object. Skipping.",
                                extra={"event_type": "malformed_sdk_function_call_part", 
                                       "details": {"part_type": str(type(part.function_call)), 
                                                   "part_data_preview": _safe_sdk_object_repr_for_log(part, max_len=200)}}
                            )
                            continue
                        fc_part: glm.FunctionCall = part.function_call
                        if hasattr(fc_part, 'name') and fc_part.name:
                            call_name = fc_part.name
                            if call_name not in raw_function_calls:
                                raw_function_calls[call_name] = glm.FunctionCall(name=call_name, args={})
                                log.debug(f"Initializing FunctionCall object for '{call_name}'.", extra={"event_type": "function_call_initialized", "details": {"call_name": call_name}})
                            # Use the unified utility for argument extraction
                            raw_function_calls[call_name].args = safe_extract_function_call(getattr(fc_part, 'args', None))
                        else:
                            malformation_details = []
                            if not hasattr(fc_part, 'name'): malformation_details.append("'name' attribute missing")
                            elif not fc_part.name: malformation_details.append(f"'name' attribute is present but empty or invalid (value: {repr(fc_part.name)})")
                            log.warning(
                                "Skipping malformed glm.FunctionCall part from SDK stream.",
                                extra={"event_type": "malformed_sdk_function_call_skipped", 
                                       "details": {"reasons": malformation_details or "Unknown issue", 
                                                   "part_preview": _safe_sdk_object_repr_for_log(fc_part, max_len=200)}}
                            )
                    else:
                        log.debug(f"Ignoring unknown stream part type: {type(part)}", extra={"event_type": "unknown_stream_part_type", "details": {"part_type": str(type(part)), "part_preview": _safe_sdk_object_repr_for_log(part, max_len=100)}}) # Added safe preview
            except StopIteration:
                log.warning("Stream ended unexpectedly with StopIteration.", extra={"event_type": "stream_stop_iteration"})
                break
            except AttributeError as e:
                error_message_str = "[Error getting str(e) for AttributeError]"
                try:
                    error_message_str = str(e)
                except Exception as str_e_err:
                    error_message_str = f"[Failed to str(e) for AttributeError: {type(str_e_err).__name__}]"
                log.error("Unexpected SDK response structure.", exc_info=True, 
                          extra={"event_type": "sdk_structure_error", 
                                 "details": {"error_type": type(e).__name__, "error_message": error_message_str, 
                                             "chunk_preview": _safe_sdk_object_repr_for_log(chunk, max_len=200)}})
                raw_chunks_debug.append(f"[SDK structure error: {type(e).__name__} - {error_message_str}]")
            except (TypeError, ValueError) as e:
                error_message_str = "[Error getting str(e) for TypeError/ValueError]"
                try:
                    error_message_str = str(e)
                except Exception as str_e_err:
                    error_message_str = f"[Failed to str(e) for TypeError/ValueError: {type(str_e_err).__name__}]"
                log.error("Error parsing chunk data.", exc_info=True, 
                          extra={"event_type": "chunk_parsing_error", 
                                 "details": {"error_type": type(e).__name__, "error_message": error_message_str, 
                                             "chunk_preview": _safe_sdk_object_repr_for_log(chunk, max_len=200)}})
                raw_chunks_debug.append(f"[Data parsing error: {type(e).__name__} - {error_message_str}]")
            except Exception as e:
                error_message_str = "[Error getting str(e) for generic Exception]"
                try:
                    error_message_str = str(e)
                except Exception as str_e_err:
                    error_message_str = f"[Failed to str(e) for generic Exception: {type(str_e_err).__name__}]"
                log.error("Unexpected error processing chunk part.", exc_info=True, 
                          extra={"event_type": "chunk_processing_error", 
                                 "details": {"error_type": type(e).__name__, "error_message": error_message_str, 
                                             "chunk_preview": _safe_sdk_object_repr_for_log(chunk, max_len=200)}})
                raw_chunks_debug.append(f"[Error processing part: {type(e).__name__} - {error_message_str}]")

        if not accumulated_text_for_log and not raw_function_calls:
            log.warning("LLM stream finished without generating any text or tool calls.", extra={"event_type": "llm_stream_empty_output"})

        for name, fc in raw_function_calls.items():
            try:
                args_data = fc.args
                # Use the unified utility for argument extraction
                args_dict_for_serialization = safe_extract_function_call(args_data)
                args_str = _serialize_arguments(args_dict_for_serialization)
                tool_call_id = _generate_tool_call_id(name)
                formatted_tool_calls_for_state.append({"id": tool_call_id, "type": "function", "function": {"name": name, "arguments": args_str}})
                log.debug(
                    f"Formatted tool call request for state: ID {tool_call_id}, Name: {name}",
                    extra={"event_type": "tool_call_formatted_for_state", "details": {"tool_call_id": tool_call_id, "tool_name": name, "args_preview": args_str[:MAX_TOOL_ARG_PREVIEW_LEN]}}
                )
            except AttributeError as e:
                log.error("Invalid function call structure after assembly.", exc_info=True, 
                          extra={"event_type": "invalid_function_call_structure", 
                                 "details": {"error": str(e), 
                                             "function_call_preview": _safe_sdk_object_repr_for_log(fc, max_len=200)}})
            except (TypeError, ValueError) as e:
                log.error("Error formatting final function call arguments.", exc_info=True, 
                          extra={"event_type": "function_call_args_formatting_error", 
                                 "details": {"error": str(e), 
                                             "args_preview": _safe_sdk_object_repr_for_log(getattr(fc, 'args', 'N/A'), max_len=200)}})

        if needs_result_synthesis and has_tool_results and tool_results:
            synthesis_text = "\n\nAdditional context from tool results:\n"
            formatted_results = _format_tool_results_for_llm(tool_results)
            summary = formatted_results["summary"]
            synthesis_text += f"- Summary: {summary['successful']} successful and {summary['failed']} failed tool executions\n"
            for result in formatted_results["results"]:
                tool_name = result.get("tool_name", "unknown_tool")
                status = result.get("status", "UNKNOWN")
                if status.upper() == "SUCCESS":
                    synthesis_text += f"- Result from {tool_name}: "
                    data = result.get("data")
                    if isinstance(data, list) and data:
                        if len(data) == 1: synthesis_text += f"Found 1 item: {str(data[0])[:300]}\n"
                        else:
                            synthesis_text += f"Found {len(data)} items. First item: {str(data[0])[:150]}"
                            if len(data) > 1: synthesis_text += f", Second: {str(data[1])[:150]}"
                            synthesis_text += "\n"
                    elif isinstance(data, dict): synthesis_text += f"Found data: {str(data)[:300]}\n"
                    else: synthesis_text += f"{str(data)[:300]}\n"
                else: synthesis_text += f"- Tool {tool_name} failed: {result.get('message', 'No error message')}\n"
            if app_state is not None and hasattr(app_state, 'streaming_placeholder_content'):
                if app_state.streaming_placeholder_content is None: app_state.streaming_placeholder_content = ""
                app_state.streaming_placeholder_content += synthesis_text
            yield ("text", synthesis_text)
            accumulated_text_for_log += synthesis_text
            log.debug("Added tool result synthesis text to stream.", extra={"event_type": "tool_result_synthesis_added", "details": {"synthesis_text_length": len(synthesis_text)}})
        
        yield ("tool_calls", formatted_tool_calls_for_state)

        end_time = time.monotonic()
        stream_duration_ms = int((end_time - start_time) * 1000)
        debug_info: Dict[str, Any] = {
            "stream_duration_ms": stream_duration_ms, "usage_metadata": usage_metadata,
            "raw_chunk_count": len(raw_chunks_debug), "tool_result_synthesis": needs_result_synthesis
        }
        log.info(
            "LLM stream processing completed.",
            extra={
                "event_type": "llm_stream_processing_completed",
                "details": {
                    "duration_ms": stream_duration_ms, "text_length": len(accumulated_text_for_log),
                    "tool_calls_requested": len(formatted_tool_calls_for_state)
                }
            }
        )
        yield ("debug_info", debug_info)

    except (StopIteration, GeneratorExit):
        log.info("Stream processing terminated normally.", extra={"event_type": "stream_terminated_normally"})
        end_time = time.monotonic()
        formatted_tool_calls_for_state = []
        for name, fc in raw_function_calls.items():
            try:
                args_dict = fc.args if isinstance(fc.args, dict) else {}
                if fc.args is None:
                    log.warning(f"Function call '{name}' has None args during early termination. Initializing with empty dict.", extra={"event_type": "function_call_none_args_early_termination", "details": {"tool_name": name}})
                    args_dict = {}
                args_str = _serialize_arguments(args_dict)
                tool_call_id = _generate_tool_call_id(name)
                formatted_tool_calls_for_state.append({"id": tool_call_id, "type": "function", "function": {"name": name, "arguments": args_str}})
            except Exception as fmt_e:
                log.error("Error formatting function call during early termination.", exc_info=True, extra={"event_type": "function_call_formatting_error_early_termination", "details": {"error": str(fmt_e)}})
        yield ("tool_calls", formatted_tool_calls_for_state)
        debug_info = {
            "stream_duration_ms": int((time.monotonic() - start_time) * 1000), "raw_chunk_count": len(raw_chunks_debug),
            "usage_metadata": usage_metadata, "status": "terminated_normally"
        }
        yield ("debug_info", debug_info)
    except google_exceptions.GoogleAPIError as e:
        error_msg = f"Google API error during stream processing: {e}"
        log.exception(error_msg, extra={"event_type": "google_api_error_stream_processing"})
        debug_info = {
            "stream_duration_ms": int((time.monotonic() - start_time) * 1000), "error": error_msg, "error_type": "GoogleAPIError",
            "raw_chunk_count": len(raw_chunks_debug), "usage_metadata": usage_metadata
        }
        yield ("debug_info", debug_info)
        yield ("text", f"[Stream Processing Error: API Error - {str(e)}]")
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error during stream processing: {e}"
        log.exception(error_msg, extra={"event_type": "network_error_stream_processing"})
        debug_info = {
            "stream_duration_ms": int((time.monotonic() - start_time) * 1000), "error": error_msg, "error_type": "NetworkError",
            "raw_chunk_count": len(raw_chunks_debug), "usage_metadata": usage_metadata
        }
        yield ("debug_info", debug_info)
        yield ("text", f"[Stream Processing Error: Network Error - {str(e)}]")
    except Exception as e:
        # Create a safe error message that won't cause cascading issues if e contains SDK objects
        error_msg = "Fatal error during LLM stream processing"
        error_details = "[Error getting exception details]"
        try:
            error_details = str(e)
        except Exception as str_e:
            try:
                error_details = f"Error contains unstringifiable object of type {type(e).__name__}"
            except Exception:
                pass  # Keep default error_details message
            
        log.exception(f"{error_msg}: {error_details}", extra={"event_type": "fatal_error_stream_processing"})
        debug_info = {
            "stream_duration_ms": int((time.monotonic() - start_time) * 1000), 
            "error": error_msg, 
            "error_type": "UnexpectedStreamError",
            "error_details": error_details,
            "raw_chunk_count": len(raw_chunks_debug), 
            "usage_metadata": usage_metadata
        }
        yield ("debug_info", debug_info)
        yield ("text", f"[Stream Processing Error: {error_details}]")


def _handle_llm_api_error(
    app_state: AppState,
    e: google_exceptions.GoogleAPIError,
    cycle_num: int,
    stage_name: Optional[str]
) -> None:  # Return type changed to None as it raises or logs
    """
    Handles Google API errors during LLM calls.
    This is typically for errors that _perform_llm_interaction itself re-raises
    (e.g., fatal setup issues). Stream processing errors within
    _perform_llm_interaction are handled there by yielding text & debug_info.

    Args:
        app_state: Current application state
        e: The GoogleAPIError exception
        cycle_num: Current interaction cycle number
        stage_name: Current workflow stage name

    Raises:
        HistoryResetRequiredError: If the error requires a conversation
                                   history reset.
        GoogleAPIError: Re-raises the original exception if history reset is
                        not needed or not a specific pattern.
    """
    error_msg = f"LLM API Error (Cycle {cycle_num+1}, Stage: {stage_name or 'General'}): {e}"
    log.exception(error_msg, extra={"event_type": "llm_api_error_handled", "details": {"cycle_num": cycle_num + 1, "stage_name": stage_name or 'General', "error": str(e)}})
    app_state.current_status_message = f"{STATUS_ERROR_LLM}: {str(e)[:60]}..."
    if hasattr(app_state, 'current_step_error'):
        app_state.current_step_error = str(e)

    error_str = str(e)
    if "invalid argument" in error_str.lower() or \
       "content does not match" in error_str.lower() or \
       "must alternate" in error_str.lower() or \
       "invalid history" in error_str.lower() or \
       "400" in error_str:
        log.warning(
            "LLM API error suggests potential history issue. Attempting reset.",
            extra={"event_type": "llm_api_error_history_issue_suspected", "details": {"error_preview": error_str[:100]}}
        )
        if _reset_conversation_if_broken(app_state, error_str):
            raise HistoryResetRequiredError(f"LLM API error led to history reset: {e}") from e
        else:
            log.warning(
                "History reset not performed or pattern not matched. Re-raising original API error.",
                extra={"event_type": "history_reset_not_performed_api_error"}
            )
            raise e
    raise e


def _get_message_role(message: Any) -> Optional[str]:
    """Safely extract role from message, handling both dict and SDK Content objects."""
    if isinstance(message, dict):
        return message.get("role")
    elif hasattr(message, 'role'):
        return message.role
    else:
        return None

def _get_message_content(message: Any) -> Optional[str]:
    """Safely extract content from message, handling both dict and SDK Content objects."""
    if isinstance(message, dict):
        return message.get("content", "")
    elif hasattr(message, 'parts') and message.parts:
        # Extract text from SDK Content object
        content_parts = []
        for part in message.parts:
            if hasattr(part, 'text') and part.text:
                content_parts.append(part.text)
        return "".join(content_parts)
    else:
        return ""

def _perform_llm_interaction(
    current_llm_history: List[ContentType],
    available_tool_definitions: Optional[List[Dict[str, Any]]],  # Can be None
    llm: LLMInterface,
    cycle_num: int,  # General cycle or stage-specific cycle
    app_state: AppState,
    is_initial_decision_call: bool = False,  # For first call in general agent loop
    stage_name: Optional[str] = None,  # Name of the current workflow stage, if any
    config: Optional[Any] = None # Added config for pass-through
) -> Iterable[Tuple[str, Any]]:
    """
    Perform an interaction with the LLM, handling both text generation and tool calls.
    
    Args:
        current_llm_history: The current conversation history
        available_tool_definitions: List of available tool definitions
        llm: The LLM interface to use
        cycle_num: The current cycle number
        app_state: The current application state
        is_initial_decision_call: Whether this is the initial decision call
        stage_name: Optional name of the current workflow stage
        config: Configuration object for additional processing
        
    Yields:
        Tuples of (event_type, event_data) for streaming responses
    """
    start_time = time.monotonic()
    
    user_query = None
    if current_llm_history and _get_message_role(current_llm_history[-1]) == "user":
        user_query = _get_message_content(current_llm_history[-1])
    
    final_tool_definitions = available_tool_definitions

    # Determine if tools should be provided and prepare them
    provide_tools_flag = _should_provide_tools(is_initial_decision_call, stage_name, user_query)
    
    final_tool_definitions = _prepare_tool_definitions(
        available_tool_definitions=llm.get_tool_manager().get_all_tool_definitions() if llm.get_tool_manager() else [], # Get fresh tools
        is_initial_decision_call=is_initial_decision_call,
        provide_tools=provide_tools_flag,
        user_query=user_query,
        config=config,
        app_state=app_state
    )
    
    # --- START OF NEW LOGGING ---
    # Safely log history and tools
    history_preview_for_log = [_safe_sdk_object_repr_for_log(msg, max_len=300) for msg in current_llm_history]
    tools_preview_for_log = "None"
    if final_tool_definitions:
        try:
            # Assuming tool definitions are simple dicts/JSON-like, pprint should be safe.
            # If they could contain complex SDK objects, this would need similar safe repr treatment.
            tools_preview_for_log = pprint.pformat([
                {k: (v if not isinstance(v, (dict, list)) else "COMPLEX_VALUE") for k, v in tool.items()} 
                for tool in final_tool_definitions
            ]) # Basic preview of tool names and top-level keys
        except Exception:
            tools_preview_for_log = "[Error formatting tools for log]"


    log.debug(
        f"LLM interaction starting: cycle={cycle_num}, initial_call={is_initial_decision_call}, "
        f"stage={stage_name}, tools_count={len(final_tool_definitions) if final_tool_definitions else 0}, provide_tools_flag={provide_tools_flag}",
        extra={
            "event_type": "llm_interaction_start_debug", 
            "details": {
                "cycle_num": cycle_num,
                "is_initial_call": is_initial_decision_call,
                "stage_name": stage_name,
                "tools_provided_count": len(final_tool_definitions) if final_tool_definitions else 0,
                "user_query_preview": user_query[:150] if user_query else None,
                "history_sent_to_llm_preview": history_preview_for_log, # Use the safe repr list
                "tools_sent_to_llm_structure_preview": tools_preview_for_log 
            }
        }
    )
    # --- END OF NEW LOGGING ---

    try:
        response_stream = llm.generate_content_stream(
            messages=current_llm_history,
            app_state=app_state,
            tools=final_tool_definitions,
            query=user_query
        )
        
        for event_type, event_data in _process_llm_stream(response_stream, app_state):
            yield (event_type, event_data)
            
    except google_exceptions.GoogleAPIError as e:
        _handle_llm_api_error(app_state, e, cycle_num, stage_name)
    except Exception as e:
        error_msg = f"Unexpected error in LLM interaction: {e}"
        log.error(error_msg, exc_info=True, extra={"event_type": "llm_interaction_error", "details": {"error": str(e)}})
        
        _update_session_stats(app_state, {"error": str(e), "error_type": type(e).__name__}, start_time)
        
        yield ("debug_info", {
            "error": error_msg,
            "error_type": type(e).__name__,
            "stream_duration_ms": int((time.monotonic() - start_time) * 1000)
        })
        yield ("text", f"[LLM Interaction Error: {str(e)}]")
