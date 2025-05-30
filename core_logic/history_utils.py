# --- FILE: core_logic/history_utils.py ---

import time
import json
# import logging # Replaced by custom logging
import re
import datetime
from typing import List, Dict, Any, Optional, Tuple, TypeAlias, Union
import sys
import os
from importlib import import_module
import uuid

# Renamed 'state' to 'state_models' as per project structure and migration plan
from state_models import AppState, ScratchpadEntry, Message, WorkflowContext  # Corrected import
from bot_core.message_handler import SafeTextPart
# Removed: from llm_interface import glm  # For glm.glm.Content, glm.glm.Part etc.

# --- SDK Types Setup for history_utils ---
SDK_AVAILABLE = False

# Minimal mock types needed by history_utils
class _MockGlmType:
    # Enum-like attributes, not strictly needed by history_utils if not using glm.Type directly
    # but good for consistency if other glm.Type attributes were ever used.
    STRING = "STRING"
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    OBJECT = "OBJECT"
    ARRAY = "ARRAY"
    NULL = "NULL"

class _MockGlmContent:
    def __init__(self, role: str, parts: List[Any]):
        self.role = role
        self.parts = parts
    def __str__(self): return f"MockContent(role='{self.role}', parts_count={len(self.parts)})"

class _MockGlmPart:
    def __init__(self, text: Optional[str] = None, function_call: Optional[Any] = None, function_response: Optional[Any] = None, inline_data: Optional[Any] = None, file_data: Optional[Any] = None):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response
        self.inline_data = inline_data
        self.file_data = file_data
    def __str__(self):
        parts_summary = []
        if self.text: parts_summary.append(f"text='{self.text[:20]}...'")
        if self.function_call: parts_summary.append(f"fc={self.function_call}")
        if self.function_response: parts_summary.append(f"fr={self.function_response}")
        return f"MockPart({', '.join(parts_summary)})"

class _MockGlmFunctionCall:
    def __init__(self, name: str, args: Dict[str, Any]):
        self.name = name
        self.args = args
    def __str__(self): return f"MockFunctionCall(name='{self.name}')"

class _MockGlmFunctionResponse:
    def __init__(self, name: str, response: Dict[str, Any]):
        self.name = name
        self.response = response
    def __str__(self): return f"MockFunctionResponse(name='{self.name}')"

class _MockGlm:
    Type = _MockGlmType
    Content = _MockGlmContent
    Part = _MockGlmPart
    FunctionCall = _MockGlmFunctionCall
    FunctionResponse = _MockGlmFunctionResponse
    # Schema and other types not directly used by history_utils's _prepare_history_for_llm logic

# Initialize with mock, then try to import real SDK
glm: Any = _MockGlm()

# CRITICAL FIX: Import real Google AI SDK when available
try:
    import google.ai.generativelanguage as actual_glm
    glm = actual_glm
    SDK_AVAILABLE = True
    # Moved to proper logging after logger is available
except ImportError as e:
    # Will be logged properly after logger is initialized
    _sdk_import_error = str(e)
    # SDK_AVAILABLE remains False, glm remains _MockGlm instance

# --- Start: Robust import of logging_config --- 
# Determine the project root directory dynamically
# Assumes this file (history_utils.py) is in project_root/core_logic/
_history_utils_dir = os.path.dirname(os.path.abspath(__file__))
_core_logic_dir = os.path.dirname(_history_utils_dir) # Should be project_root/core_logic
_project_root_dir = os.path.dirname(_core_logic_dir) # Should be project_root

# Add project_root to sys.path if it's not already there
if _project_root_dir not in sys.path:
    sys.path.insert(0, _project_root_dir)

# Now, try to import from utils.logging_config, which should be resolvable
try:
    _logging_module = import_module('utils.logging_config')
    get_logger = _logging_module.get_logger
    # Import other necessary items if needed, e.g., setup_logging, etc.
except ModuleNotFoundError as e:
    # Fallback or error logging if import still fails
    print(f"CRITICAL: Could not import get_logger from utils.logging_config. Path: {sys.path}, Project Root: {_project_root_dir}, Error: {e}")
    # Define a dummy logger to prevent application crash
    def get_logger(name):
        import logging
        fallback_logger = logging.getLogger(name + "_fallback_history_utils")
        if not fallback_logger.hasHandlers():
            fallback_logger.addHandler(logging.StreamHandler(sys.stdout))
            fallback_logger.setLevel(logging.INFO)
        return fallback_logger
# --- End: Robust import of logging_config ---

# Logging Configuration
log = get_logger("core_logic.history_utils")

# Log SDK status now that logger is available
if SDK_AVAILABLE:
    log.debug("Google AI SDK loaded successfully in history_utils")
else:
    error_msg = globals().get('_sdk_import_error', 'Unknown import error')
    log.debug(f"Using mock Google AI SDK in history_utils (real SDK not available): {error_msg}")

# Project-specific constants
from .constants import (
    WORKFLOW_STAGE_MESSAGE_TYPE,
    THOUGHT_MESSAGE_TYPE,
    REFLECTION_MESSAGE_TYPE,
    PLAN_MESSAGE_TYPE,
    # MAX_HISTORY_MESSAGES is defined in config.py, not constants.py
)

# Import AppState and Message models from state_models
# Simple direct import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# Duplicate import removed (AppState, Message already imported above)

# Type alias for LLM SDK content type
RuntimeContentType = Union[Dict[str, Any], glm.Content] # glm.Content or dicts

# --- Custom Exceptions ---
class HistoryResetRequiredError(Exception):
    """
    Custom exception to signal when the conversation history is unrecoverably
    broken for the API.
    """
    pass

# --- History Management Functions ---

def _add_system_prompt_to_history(app_state: AppState, system_prompt: str) -> None:  # Updated type hint
    """
    Adds the system prompt to the message history if not already present.

    Note: This function's utility is currently limited as the primary system
    prompt is typically passed directly to the LLM SDK (e.g., via a
    'system_prompt' parameter in `generate_content_stream`) rather than being
    part of the explicit message history sent to the model. The
    `_prepare_history_for_llm` function filters out standard system messages
    from the history it prepares. This function might be more relevant for UI
    display purposes or if a model specifically requires the system prompt as
    the first message in the conversational history.

    Args:
        app_state: The application state object, expected to have a 'messages'
                   attribute which is a list of message dictionaries, and an
                   'add_message' method.
        system_prompt: The system prompt string to add.
    """
    has_system_message = any(
        msg.get("role") == "system" and
        msg.get("message_type") != WORKFLOW_STAGE_MESSAGE_TYPE
        for msg in app_state.messages
    )

    if not has_system_message and system_prompt and system_prompt.strip():
        log.debug(
            "System prompt handling is primarily via SDK argument. Adding to history for record/UI if needed.",
            extra={"event_type": "system_prompt_handling_note", "details": {"action": "logged_for_record_ui_if_needed"}}
        )
        pass
    elif has_system_message:
        log.debug("Standard system prompt already exists in history (or handled separately by SDK).", extra={"event_type": "system_prompt_handling_note", "details": {"status": "already_exists_or_sdk_handled"}})
    elif not system_prompt or not system_prompt.strip():
        log.debug("No standard system prompt provided to add to history.", extra={"event_type": "system_prompt_handling_note", "details": {"status": "not_provided"}})


def _optimize_message_history(
    messages: List[Dict[str, Any]],
    max_items: int,
    scratchpad: Optional[List[ScratchpadEntry]] = None
) -> List[Dict[str, Any]]:  # Updated type hint
    """
    Advanced history optimization: intelligently keep the most relevant content
    while preserving context. Optimizes history to fit within token constraints
    by selecting the most important messages.

    Args:
        messages: The list of message dictionaries
        max_items: The maximum number of messages to keep
        scratchpad: Optional list of scratchpad entries to include as context

    Returns:
        List of optimized message dictionaries
    """
    if len(messages) <= max_items:
        return messages

    original_count = len(messages)
    log.debug(
        "History optimization requested.",
        extra={"event_type": "history_optimization_requested", "details": {"original_count": original_count, "max_items": max_items}}
    )
    system_messages = []
    user_messages = []
    assistant_messages = []
    tool_messages = []
    internal_messages = []

    for msg in messages:
        role = msg.get('role', '')
        is_internal = msg.get('is_internal', False)
        # timestamp = msg.get('timestamp', 0)  # Ensure timestamp is present

        if is_internal:
            internal_messages.append(msg)
        elif role == 'system':
            system_messages.append(msg)
        elif role == 'user':
            user_messages.append(msg)
        elif role == 'assistant':
            assistant_messages.append(msg)
        elif role == 'tool':
            tool_messages.append(msg)

    for msg_list in [
        user_messages, assistant_messages, tool_messages, internal_messages
    ]:
        msg_list.sort(key=lambda m: m.get('timestamp', 0))

    optimized_messages = system_messages[:]

    important_internal = [
        msg for msg in internal_messages
        if msg.get('message_type') in (
            WORKFLOW_STAGE_MESSAGE_TYPE,
            REFLECTION_MESSAGE_TYPE,
            PLAN_MESSAGE_TYPE
        )  # Corrected constant name
    ]
    if len(important_internal) > 5:
        log.debug(
            "Reducing important internal messages.",
            extra={"event_type": "history_optimization_reduce_internal", "details": {"original_internal_count": len(important_internal), "new_internal_count": 5}}
        )
        important_internal = important_internal[-5:]
    optimized_messages.extend(important_internal)

    remaining_slots = max_items - len(optimized_messages)
    if remaining_slots <= 0:
        log.warning(
            "No remaining slots for regular messages after keeping system/internal messages.",
            extra={"event_type": "history_optimization_no_slots_for_regular", "details": {"optimized_message_count": len(optimized_messages)}}
        )
        min_conversation_slots = 6
        while remaining_slots < min_conversation_slots and \
              len(optimized_messages) > len(system_messages):
            optimized_messages.pop(len(system_messages))
            remaining_slots += 1
        log.warning(
            "Reduced internal messages to make space.",
            extra={"event_type": "history_optimization_reduced_internal_for_space", "details": {"new_remaining_slots": remaining_slots}}
        )
        if remaining_slots <= 0:
            optimized_messages.sort(key=lambda m: m.get('timestamp', 0))
            log.warning(
                "History optimization resulted in only critical messages due to slot constraints.",
                extra={"event_type": "history_optimization_critical_only", "details": {"final_message_count": len(optimized_messages)}}
            )
            return optimized_messages

    recent_messages_combined = []
    # Get all non-system, non-internal messages from the original 'messages' list,
    # preserving their original chronological order.
    # These are candidates for the "recent messages" pool.
    # We assume 'messages' (the input to this function) is already sorted chronologically.
    candidate_recent_messages = []
    for msg_item in messages: # Iterate over original messages
        role = msg_item.get('role', '')
        is_internal_flag = msg_item.get('is_internal', False)
        
        # We are interested in 'user', 'assistant', or 'tool' messages that are NOT internal.
        # System messages and 'important_internal' messages are already handled and in 'optimized_messages'.
        if role in ('user', 'assistant', 'tool') and not is_internal_flag:
            candidate_recent_messages.append(msg_item)
    
    # 'candidate_recent_messages' should be chronological if 'messages' was.
    # If 'messages' wasn't guaranteed sorted, an explicit sort by timestamp would be needed here.
    # For this function's typical input (app_state.messages), it's chronological.

    if len(candidate_recent_messages) > remaining_slots:
        recent_messages_combined = candidate_recent_messages[-remaining_slots:]
    else:
        recent_messages_combined = candidate_recent_messages

    optimized_messages.extend(recent_messages_combined)
    optimized_messages.sort(key=lambda m: m.get('timestamp', 0))

    while len(optimized_messages) > max_items and \
          len(optimized_messages) > len(system_messages):
        removed_idx = -1
        for idx, msg_to_remove in enumerate(optimized_messages):
            if msg_to_remove.get("role") != "system":
                removed_idx = idx
                break
        if removed_idx != -1:
            optimized_messages.pop(removed_idx)
        else:
            break

    reduction_pct = ((original_count - len(optimized_messages)) / original_count) * 100 if original_count > 0 else 0
    log.info(
        "Optimized history.",
        extra={
            "event_type": "history_optimization_completed",
            "details": {
                "original_count": original_count,
                "optimized_count": len(optimized_messages),
                "reduction_percentage": f"{reduction_pct:.1f}%"
            }
        }
    )
    return optimized_messages


def add_tool_usage_reminder(messages: List[glm.Content]) -> List[glm.Content]:
    """
    Add a tool usage reminder to the conversation history to encourage the AI to use available tools
    This is especially important for models like Gemini that might not consistently apply system instructions
    
    Args:
        messages: List of formatted messages ready for the LLM
        
    Returns:
        List of messages with the tool usage reminder added
    """
    if not messages:
        return messages
        
    # Find the last user message position to insert the reminder before it
    last_user_idx = None
    for i in range(len(messages)-1, -1, -1):
        if hasattr(messages[i], 'role') and messages[i].role == 'user':
            last_user_idx = i
            break
            
    if last_user_idx is None:
        return messages  # No user message found
        
    # Create the tool usage reminder
    reminder_text = (
        "IMPORTANT: I should utilize the available tools to help the user when appropriate. "
        "Available tools include search, weather, and other utilities that can provide real-time information. "
        "When the user asks for current information, I should always consider using these tools rather than "
        "saying I don't have access to that information."
    )
    
    reminder_content = glm.Content(
        role="user", 
        parts=[glm.Part(text=f"[TOOL REMINDER]: {reminder_text}")]
    )
    
    # Insert before the last user message
    new_messages = messages[:last_user_idx] + [reminder_content] + messages[last_user_idx:]
    return new_messages


def prepare_messages_for_llm_from_appstate(app_state: AppState, config_max_history_items: Optional[int] = None) -> Tuple[List[RuntimeContentType], List[str]]:
    """
    Prepares messages from AppState for LLM consumption using the new Message structure.
    Integrates history optimization and active workflow context.
    """
    preparation_notes = []
    formatted_messages: List[RuntimeContentType] = []
    
    max_items = config_max_history_items if config_max_history_items is not None else (app_state.config.LLM_MAX_HISTORY_ITEMS if hasattr(app_state, 'config') and app_state.config and hasattr(app_state.config, 'LLM_MAX_HISTORY_ITEMS') else 30)

    # Convert Pydantic Message objects to dictionaries for _optimize_message_history
    # as it currently expects List[Dict[str, Any]]
    messages_as_dicts: List[Dict[str, Any]] = []
    for msg_obj in app_state.messages:
        try:
            # Ensure timestamp is a float (Unix timestamp) if _optimize_message_history expects that for sorting
            # The Message model uses datetime, so convert it.
            msg_dict = msg_obj.model_dump(mode='json') # mode='json' handles datetime to ISO string
            # If _optimize_message_history needs float timestamp, convert msg_dict['timestamp']
            # For now, assuming _optimize_message_history can handle ISO string or can be adapted.
            # Let's ensure timestamp is present for sorting in _optimize_message_history
            if 'timestamp' not in msg_dict or msg_dict['timestamp'] is None:
                msg_dict['timestamp'] = datetime.utcnow().isoformat() + "Z" # Fallback timestamp
            messages_as_dicts.append(msg_dict)
        except Exception as e_dump:
            log.warning(f"Error converting Message object to dict for history prep: {e_dump}. Skipping message.")
            preparation_notes.append(f"Skipped one message due to conversion error: {e_dump}")

    # 1. Optimize history if too long
    if len(messages_as_dicts) > max_items:
        log.info(f"History length ({len(messages_as_dicts)}) exceeds max_items ({max_items}). Optimizing...")
        # Pass app_state.scratchpad if _optimize_message_history is to use it
        scratchpad_for_opt: Optional[List[ScratchpadEntry]] = app_state.scratchpad if hasattr(app_state, 'scratchpad') else None
        history_to_convert_dicts = _optimize_message_history(messages_as_dicts, max_items, scratchpad_for_opt)
        note = f"History optimized from {len(messages_as_dicts)} to {len(history_to_convert_dicts)} messages."
        log.debug(note, extra={"event_type": "history_optimization_applied"})
        preparation_notes.append(note)
    else:
        history_to_convert_dicts = messages_as_dicts

    # 2. Inject active workflow context as a system message (if any)
    active_workflow_ctx: Optional[WorkflowContext] = None
    if hasattr(app_state, 'get_active_workflow_by_type'): # Check if method exists
        # Attempt to get a primary active workflow, e.g., onboarding or the first one found
        primary_wf_type = app_state.get_primary_active_workflow_name()
        if primary_wf_type:
            active_workflow_ctx = app_state.get_active_workflow_by_type(primary_wf_type)

    if active_workflow_ctx:
        workflow_info_text = (
            f"System Context: You are currently assisting the user within the '{active_workflow_ctx.workflow_type}' workflow. "
            f"Current stage is '{active_workflow_ctx.current_stage}'. "
            f"Relevant data for this stage might include: {str(active_workflow_ctx.data)[:200]}..."
        )
        # Create a system message part for this context.
        # This will be converted to glm.Content later. For now, represent as dict.
        workflow_context_msg_dict = {
            "role": "system", # Or "user" if preferred to make it seem like a user reminder to the assistant
            "parts": [{"type": "text", "text": workflow_info_text}],
            "timestamp": datetime.utcnow().isoformat() + "Z", # Ensure it's placed correctly in history if sorted
            "is_internal": True, # Mark as internal so it might be treated specially or not shown to user
            "message_type": "workflow_context_injection"
        }
        # Insert it before the last user message, or at the end if no user messages.
        # For simplicity, adding to the list that will be converted. Sorting later might be needed if not added at right place.
        # This simple append might not be ideal if strict ordering is needed before the last user message.
        # A better approach might be to find the last user message and insert before it.
        # For now, adding it to the list to be converted. _optimize_message_history runs before this.
        # Let's convert this to a Message object and add it to a temporary list to be merged and sorted.
        temp_context_messages = [Message.model_validate(workflow_context_msg_dict)]
        
        # Re-convert to dicts for consistent processing before glm.Content conversion
        history_to_convert_dicts.extend([m.model_dump(mode='json') for m in temp_context_messages])
        # Re-sort if timestamps matter for this injected context
        history_to_convert_dicts.sort(key=lambda m: m.get('timestamp', datetime.min.isoformat()))
        # Re-apply max_items limit if injection pushed it over, prioritizing newest
        if len(history_to_convert_dicts) > max_items:
            history_to_convert_dicts = history_to_convert_dicts[-max_items:]

        note = f"Injected active workflow context ('{active_workflow_ctx.workflow_type}' - '{active_workflow_ctx.current_stage}') into LLM history."
        log.debug(note, extra={"event_type": "workflow_context_injected"})
        preparation_notes.append(note)

    # 3. Convert to glm.Content (or SDK dicts)
    for msg_index, msg_dict_from_history in enumerate(history_to_convert_dicts):
        sdk_parts = []
        # Ensure parts is a list of dicts, as MessagePart is a Union of Pydantic models
        parts_list = msg_dict_from_history.get('parts', [])
        if not isinstance(parts_list, list):
            log.warning(f"Message at index {msg_index} has parts of type {type(parts_list)}, expected list. Converting text.")
            # Fallback: try to get text from raw_text or content if parts is not a list
            raw_text_content = msg_dict_from_history.get('raw_text', msg_dict_from_history.get('content'))
            if isinstance(raw_text_content, str):
                parts_list = [{'type': 'text', 'text': raw_text_content}]
            else:
                parts_list = [] # Cannot determine parts
        
        for part_data_dict in parts_list: # part_data_dict should be a dict here
            part_type = part_data_dict.get('type')
            if part_type == "text":
                sdk_parts.append(glm.Part(text=part_data_dict.get('text', '')))
            elif part_type == "function_call":
                fc_data = part_data_dict.get('function_call', {})
                sdk_parts.append(glm.Part(function_call=glm.FunctionCall(
                    name=fc_data.get('name'),
                    args=fc_data.get('args') 
                )))
            elif part_type == "function_response":
                fr_data = part_data_dict.get('function_response', {})
                fr_response_data = fr_data.get('response', {})
                sdk_parts.append(glm.Part(function_response=glm.FunctionResponse(
                    name=fr_data.get('name'),
                    response={'content': fr_response_data.get('content')} 
                )))
        
        if sdk_parts:
            role_for_sdk = msg_dict_from_history.get('role', 'user')
            
            # Handle system messages since Gemini doesn't support them directly
            if role_for_sdk == "system":
                if msg_dict_from_history.get("message_type") == "workflow_context_injection":
                    # For workflow context, keep as is but convert to user message
                    role_for_sdk = "user"
                    # Prepend context indicator to make it clear this is system information
                    for part in sdk_parts:
                        if hasattr(part, 'text') and part.text:
                            part.text = f"[SYSTEM CONTEXT]: {part.text}"
                    note = f"Converted workflow context system message to user message at index {msg_index}"
                    log.debug(note)
                    preparation_notes.append(note)
                else:
                    # For regular system messages, convert to user message with clear system prompt indicator
                    role_for_sdk = "user"
                    for part in sdk_parts:
                        if hasattr(part, 'text') and part.text:
                            part.text = f"[SYSTEM INSTRUCTION]: You are Aughie, an AI development assistant. {part.text}"
                    note = f"Converted system message to user message with system instruction prefix at index {msg_index}"
                    log.debug(note)
                    preparation_notes.append(note)
            elif role_for_sdk == "function": # Gemini uses 'function' role for tool responses
                pass # Keep as 'function' if parts are FunctionResponse as per Gemini examples

            try:
                formatted_messages.append(glm.Content(parts=sdk_parts, role=role_for_sdk))
            except Exception as e_glm_content:
                note = f"Error creating glm.Content for message at index {msg_index} (Role: {role_for_sdk}): {e_glm_content}"
                log.error(note, exc_info=True)
                preparation_notes.append(note)
        else:
            note = f"Message at index {msg_index} (role '{msg_dict_from_history.get('role')}') had no convertible parts after processing. Skipping."
            log.warning(note, extra={"event_type": "message_no_convertible_parts_final"})
            preparation_notes.append(note)
            
    # Basic sequence validation/repair (simplified from guide for now)
    # The Gemini SDK is more flexible, but some models might still prefer strict alternation.
    # For now, rely on the AppState.Message validation for roles and parts.
    # Advanced repair (like in the old _prepare_history_for_llm) can be added if needed.
    if not formatted_messages and app_state.messages:
        note = "Formatted history is empty, but original messages existed. This might indicate all messages were filtered or had issues."
        log.warning(note, extra={"event_type": "empty_formatted_history_with_originals"})
        preparation_notes.append(note)

    # Add tool usage reminder before final user message
    if formatted_messages:
        formatted_messages = add_tool_usage_reminder(formatted_messages)
        preparation_notes.append("Added tool usage reminder to conversation history")

    log.debug(
        "Prepared messages for LLM from AppState.",
        extra={"event_type": "prepare_messages_from_appstate_completed", "details": {"formatted_message_count": len(formatted_messages), "original_truncated_count": len(history_to_convert_dicts), "preparation_notes_count": len(preparation_notes)}}
    )
    return formatted_messages, preparation_notes


def _prepare_history_for_llm(
    session_messages: List[Dict[str, Any]],
    max_history_items: int = 30,
    app_state: Optional[AppState] = None
) -> Tuple[List[glm.Content], List[str]]:  # Use glm.Content directly
    """
    Prepares the AppState message history for the LLM SDK format
    (as glm.Content objects).

    Args:
        session_messages: List of message dictionaries from the AppState
        max_history_items: Maximum number of messages to include (default: 30)
        app_state: Optional AppState object to include scratchpad content

    Returns:
        Tuple of (glm.Content list, list of error messages)
    """
    preparation_errors = []

    # CRITICAL FIX: Handle both Message objects and dictionaries
    normalized_messages = []
    for msg in session_messages:
        if hasattr(msg, 'model_dump'):  # Pydantic Message object
            try:
                # Convert Message object to dictionary
                msg_dict = msg.model_dump()
                # Ensure backward compatibility attributes
                if not msg_dict.get('id'):
                    msg_dict['id'] = getattr(msg, 'id', str(uuid.uuid4()))
                normalized_messages.append(msg_dict)
            except Exception as e:
                log.warning(f"Failed to convert Message object to dict: {e}. Using fallback conversion.")
                # Fallback conversion
                msg_dict = {
                    'id': getattr(msg, 'id', str(uuid.uuid4())),
                    'role': getattr(msg, 'role', 'user'),
                    'content': getattr(msg, 'text', str(msg)),
                    'timestamp': getattr(msg, 'timestamp', time.time()),
                    'is_internal': getattr(msg, 'is_internal', False),
                    'message_type': getattr(msg, 'message_type', None),
                }
                normalized_messages.append(msg_dict)
        elif isinstance(msg, dict):
            # Already a dictionary, ensure it has required fields
            msg_dict = msg.copy()
            if 'id' not in msg_dict:
                msg_dict['id'] = str(uuid.uuid4())
            normalized_messages.append(msg_dict)
        else:
            # Unknown message format, create safe fallback
            log.warning(f"Unknown message format: {type(msg)}. Creating fallback message.")
            msg_dict = {
                'id': str(uuid.uuid4()),
                'role': 'user',
                'content': str(msg),
                'timestamp': time.time(),
                'is_internal': False,
                'message_type': None,
            }
            normalized_messages.append(msg_dict)

    filtered_msgs = []
    for msg in normalized_messages:
        role = msg.get("role", "")
        is_internal = msg.get("is_internal", False)
        message_type = msg.get("message_type", "")

        if role == "system":
            if message_type == WORKFLOW_STAGE_MESSAGE_TYPE:
                filtered_msgs.append(msg)
            continue

        if is_internal:
            if message_type in (
                WORKFLOW_STAGE_MESSAGE_TYPE, THOUGHT_MESSAGE_TYPE,
                REFLECTION_MESSAGE_TYPE, PLAN_MESSAGE_TYPE, "context_summary"
            ):
                filtered_msgs.append(msg)
            continue

        if role in ("user", "assistant", "tool"):
            filtered_msgs.append(msg)

    scratchpad_entries = app_state.scratchpad if app_state and \
        hasattr(app_state, 'scratchpad') else None
    history_to_process = _optimize_message_history(
        filtered_msgs,
        max_history_items,
        scratchpad_entries
    )

    if scratchpad_entries and len(scratchpad_entries) > 0:
        scratchpad_already_present = any(
            msg.get("message_type") == "context_summary" for msg in
            history_to_process
        )
        if not scratchpad_already_present:
            scratchpad_text = "Recent Tool Results Memory (most relevant first):\n"
            for entry in reversed(scratchpad_entries[-5:]):  # type: ignore
                timestamp_dt = datetime.datetime.fromtimestamp(entry.timestamp)
                scratchpad_text += (
                    f"- Tool: {entry.tool_name}, Args: "
                    f"{str(entry.tool_input)[:50]}..., Result: "
                    f"{entry.summary[:100]}... "
                    f"(Time: {timestamp_dt.strftime('%H:%M:%S')})\n"
                )

            scratchpad_message = {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": scratchpad_text,
                "is_internal": True,
                "message_type": "context_summary",
                "timestamp": time.time()
            }
            insert_pos = 0
            for i, msg_item in enumerate(history_to_process):
                if msg_item.get("role") == "system":
                    insert_pos = i + 1
                else:
                    break
            history_to_process.insert(insert_pos, scratchpad_message)
            log.info(
                "Added explicit scratchpad summary message to LLM history.",
                extra={"event_type": "scratchpad_summary_added_to_history", "details": {"entry_count": len(scratchpad_entries)}}
            )
    glm_history: List[glm.Content] = []
    sdk_role_map = {
        "user": "user", "assistant": "model",
        "system": "model", "tool": "tool"
    }
    expected_tool_calls_info: List[Dict[str, str]] = []

    for i, msg in enumerate(history_to_process):
        role = msg.get("role", "")
        content = msg.get("content")
        app_tool_calls = msg.get("tool_calls", [])
        is_internal = msg.get("is_internal", False)
        message_type = msg.get("message_type", "")
        skip_current_message_due_to_repair = False # Initialize flag

        sdk_role = sdk_role_map.get(role)
        if not sdk_role:
            err = f"Skipping message {i} with unsupported role '{role}' for LLM history."
            log.warning(err, extra={"event_type": "history_prep_skip_unsupported_role", "details": {"message_index": i, "role": role}})
            preparation_errors.append(err)
            continue

        parts: List[glm.Part] = []

        if sdk_role == "user":
            if not content:
                log.debug(f"Skipping user message {i} due to empty content.", extra={"event_type": "history_prep_skip_empty_user_content", "details": {"message_index": i}})
                continue
            parts.append(glm.Part(text=str(content)))

        elif sdk_role == "model":
            if message_type == WORKFLOW_STAGE_MESSAGE_TYPE and content:
                parts.append(glm.Part(text=f"[WORKFLOW CONTEXT: {message_type}] {content}"))
            elif is_internal and message_type == "context_summary" and content:
                parts.append(glm.Part(text=f"===== MEMORY CONTEXT =====\n{content}\n=========================="))
            elif is_internal and content:
                parts.append(glm.Part(text=f"[{message_type.upper()}] {content}"))
            elif content:
                parts.append(glm.Part(text=str(content)))

            if app_tool_calls:
                current_msg_tool_call_ids_names = []
                for tc_data in app_tool_calls:
                    if tc_data.get("type") == "function":
                        func_details = tc_data.get("function", {})
                        func_name = func_details.get("name")
                        args_str = func_details.get("arguments", "{}")
                        tool_call_id = tc_data.get("id")

                        if not func_name or tool_call_id is None:
                            err = f"Model message {i}: Malformed tool call (missing name or id): {tc_data}"
                            log.warning(err, extra={"event_type": "history_prep_malformed_tool_call", "details": {"message_index": i, "tool_call_data": tc_data}})
                            preparation_errors.append(err)
                            continue
                        try:
                            if args_str is None: args_dict = {}
                            elif isinstance(args_str, str):
                                if args_str.strip(): args_dict = json.loads(args_str)
                                else: args_dict = {}
                            elif isinstance(args_str, dict): args_dict = args_str
                            else:
                                log.warning(f"Model message {i}: Unexpected type for tool call arguments '{type(args_str)}'. Defaulting to empty dict.", extra={"event_type": "history_prep_tool_call_unexpected_args_type", "details": {"message_index": i, "args_type": str(type(args_str))}})
                                args_dict = {}
                            parts.append(glm.Part(function_call=glm.FunctionCall(name=func_name, args=args_dict)))
                            current_msg_tool_call_ids_names.append({"id": tool_call_id, "name": func_name})
                        except json.JSONDecodeError as json_e:
                            err = f"Model message {i}: Invalid JSON in tool call arguments for '{func_name}': {args_str[:100]}... Error: {json_e}"
                            log.warning(err, extra={"event_type": "history_prep_tool_call_json_decode_error", "details": {"message_index": i, "function_name": func_name, "args_preview": args_str[:100], "error": str(json_e)}})
                            preparation_errors.append(err)
                            continue
                        except Exception as e:
                            err = f"Model message {i}: Error creating FunctionCall for '{func_name}': {e}"
                            log.warning(err, exc_info=True, extra={"event_type": "history_prep_function_call_creation_error", "details": {"message_index": i, "function_name": func_name, "error": str(e)}})
                            preparation_errors.append(err)
                            continue
                if current_msg_tool_call_ids_names:
                    expected_tool_calls_info = current_msg_tool_call_ids_names
                    log.debug(
                        f"Model message {i} expects tool responses.",
                        extra={"event_type": "history_prep_model_expects_tool_responses", "details": {"message_index": i, "expected_calls": expected_tool_calls_info}}
                    )
        elif sdk_role == "tool":
            function_name = msg.get("name")
            tool_call_id = msg.get("tool_call_id")
            tool_result_content_str = msg.get("content")

            if not function_name:
                err = f"Tool message {i} is missing function name. Skipping."
                log.warning(err, extra={"event_type": "history_prep_tool_msg_missing_name", "details": {"message_index": i}})
                preparation_errors.append(err)
                continue

            if not tool_call_id and len(expected_tool_calls_info) == 1:
                inferred_id = expected_tool_calls_info[0]["id"]
                expected_name_for_inferred_id = expected_tool_calls_info[0].get("name")
                log_details_inference = {"message_index": i, "function_name": function_name, "inferred_id": inferred_id, "expected_name": expected_name_for_inferred_id}
                if function_name and expected_name_for_inferred_id == function_name:
                    log.warning("Tool message missing tool_call_id. Inferred as it's the only pending call and function name matches.", extra={"event_type": "history_prep_tool_id_inferred_match", "details": log_details_inference})
                    tool_call_id = inferred_id
                elif function_name and not expected_name_for_inferred_id:
                     log.warning("Tool message missing tool_call_id. Inferred as it's the only pending call (expected had no name).", extra={"event_type": "history_prep_tool_id_inferred_no_expected_name", "details": log_details_inference})
                     tool_call_id = inferred_id
                elif not function_name and expected_name_for_inferred_id :
                    log.warning("Tool message (no function name) missing tool_call_id. Inferred using expected name.", extra={"event_type": "history_prep_tool_id_inferred_use_expected_name", "details": log_details_inference})
                    tool_call_id = inferred_id
                    function_name = expected_name_for_inferred_id
                elif function_name and expected_name_for_inferred_id and expected_name_for_inferred_id != function_name:
                    log.warning("Tool message missing tool_call_id. NOT inferring due to name mismatch with single pending call.", extra={"event_type": "history_prep_tool_id_inference_failed_name_mismatch", "details": log_details_inference})
                else:
                    log.warning("Tool message (no function name) missing tool_call_id. Inferred as only pending call (also no name).", extra={"event_type": "history_prep_tool_id_inferred_both_no_name", "details": log_details_inference})
                    tool_call_id = inferred_id

            if not tool_call_id:
                err = f"Tool message {i} (function: {function_name or 'Unknown'}) is missing tool_call_id and could not be reliably inferred. Skipping."
                log.warning(err, extra={"event_type": "history_prep_tool_msg_missing_id_uninferrable", "details": {"message_index": i, "function_name": function_name or 'Unknown'}})
                preparation_errors.append(err)
                continue
            
            if not function_name and tool_call_id and len(expected_tool_calls_info) == 1 and expected_tool_calls_info[0]["id"] == tool_call_id:
                inferred_function_name = expected_tool_calls_info[0].get("name")
                if inferred_function_name:
                    log.debug(f"Tool message {i} had its function name inferred as '{inferred_function_name}' to match expected call.", extra={"event_type": "history_prep_tool_name_inferred", "details": {"message_index": i, "inferred_name": inferred_function_name}})
                    function_name = inferred_function_name

            if not function_name:
                err = f"Tool message {i} (tool_call_id: {tool_call_id}) is still missing function name after potential inference. Skipping."
                log.warning(err, extra={"event_type": "history_prep_tool_msg_still_missing_name", "details": {"message_index": i, "tool_call_id": tool_call_id}})
                continue

            matching_expected_call = next((call for call in expected_tool_calls_info if call["id"] == tool_call_id), None)
            log.debug(
                f"Tool message {i} (name: {function_name}, id: {tool_call_id}): matching_expected_call result.",
                extra={"event_type": "history_prep_matching_expected_call", "details": {"message_index": i, "function_name": function_name, "tool_call_id": tool_call_id, "expected_tool_calls_before_match": expected_tool_calls_info, "match_found": matching_expected_call is not None}}
            )
            if not matching_expected_call:
                err = f"History sequence error: Tool response for ID '{tool_call_id}' (name: {function_name}) was not expected. Expected calls: {expected_tool_calls_info}. Skipping."
                log.warning(err, extra={"event_type": "history_prep_unexpected_tool_response", "details": {"message_index": i, "tool_call_id": tool_call_id, "function_name": function_name, "expected_calls": expected_tool_calls_info}})
                preparation_errors.append(err)
                continue

            if matching_expected_call and matching_expected_call["name"] != function_name:
                warning_msg = f"Tool response ID '{tool_call_id}' matches, but name differs. Expected: '{matching_expected_call['name']}', Got: '{function_name}'. Correcting to expected name."
                log.warning(warning_msg, extra={"event_type": "history_prep_tool_name_mismatch_corrected", "details": {"message_index": i, "tool_call_id": tool_call_id, "expected_name": matching_expected_call['name'], "actual_name": function_name}})
                preparation_errors.append(warning_msg)
                function_name = matching_expected_call["name"]

            try:
                if tool_result_content_str is None: response_dict = {"result": "Tool returned no content."}
                elif isinstance(tool_result_content_str, str):
                    if tool_result_content_str.strip():
                        try: response_dict = json.loads(tool_result_content_str)
                        except json.JSONDecodeError as json_e_inner:
                            log.warning(f"Tool message {i}: Content for tool '{function_name}' is a string but not valid JSON. Wrapping as string result.", extra={"event_type": "history_prep_tool_content_invalid_json_string", "details": {"message_index": i, "function_name": function_name, "content_preview": tool_result_content_str[:100], "error": str(json_e_inner)}})
                            response_dict = {"result": tool_result_content_str}
                    else: response_dict = {"result": "Tool returned empty content."}
                elif isinstance(tool_result_content_str, dict): response_dict = tool_result_content_str
                elif SDK_AVAILABLE and isinstance(tool_result_content_str, MapComposite):
                    try:
                        response_dict = dict(tool_result_content_str)
                        log.debug(f"Successfully converted MapComposite to dict for tool '{function_name}'", extra={"event_type": "history_prep_mapcomposite_converted", "details": {"function_name": function_name}})
                    except Exception as map_err:
                        log.warning(f"Error converting MapComposite to dict for tool '{function_name}'.", exc_info=True, extra={"event_type": "history_prep_mapcomposite_conversion_error", "details": {"function_name": function_name, "error": str(map_err)}})
                        response_dict = {"result": str(tool_result_content_str)}
                else:
                    log.warning(f"Tool message {i}: Unexpected type for tool result content '{type(tool_result_content_str)}' for '{function_name}'. Converting to string and wrapping.", extra={"event_type": "history_prep_tool_content_unexpected_type", "details": {"message_index": i, "function_name": function_name, "content_type": str(type(tool_result_content_str))}})
                    response_dict = {"result": str(tool_result_content_str)}
                parts.append(glm.Part(function_response=glm.FunctionResponse(name=function_name, response=response_dict)))
                expected_tool_calls_info = [call for call in expected_tool_calls_info if call["id"] != tool_call_id]
                log.debug(
                    f"Processed tool response for {function_name} (ID: {tool_call_id}).",
                    extra={"event_type": "history_prep_tool_response_processed", "details": {"function_name": function_name, "tool_call_id": tool_call_id, "remaining_expected_count": len(expected_tool_calls_info)}}
                )
            except json.JSONDecodeError as json_e:
                preview_content = str(tool_result_content_str)
                err = f"Tool message {i}: Invalid JSON in tool result content for '{function_name}': {preview_content[:100]}... Error: {json_e}"
                log.warning(err, extra={"event_type": "history_prep_tool_result_json_decode_error", "details": {"message_index": i, "function_name": function_name, "content_preview": preview_content[:100], "error": str(json_e)}})
                preparation_errors.append(err)
                f_name_for_error = function_name if 'function_name' in locals() and function_name else "unknown_tool_error"
                parts.append(glm.Part(function_response=glm.FunctionResponse(name=f_name_for_error, response={"error": "Failed to parse tool output as JSON", "details": str(json_e), "original_content_preview": preview_content[:100]})))
                expected_tool_calls_info = [call for call in expected_tool_calls_info if call["id"] != tool_call_id]
            except Exception as e:
                err = f"Tool message {i}: Error creating FunctionResponse for '{function_name}': {e}"
                log.warning(err, exc_info=True, extra={"event_type": "history_prep_function_response_creation_error", "details": {"message_index": i, "function_name": function_name, "error": str(e)}})
                preparation_errors.append(err)
                continue

        if not parts:
            if sdk_role == "model" and not app_tool_calls:
                log.debug(
                    f"Skipping message {i} (role: {role}, sdk_role: {sdk_role}) as it resulted in empty parts and no tool calls.",
                    extra={"event_type": "history_prep_skip_empty_model_message_no_tools", "details": {"message_index": i, "role": role, "sdk_role": sdk_role}}
                )
            continue

        if sdk_role not in ["user", "model", "tool"]:
            err = f"Internal Error: Attempting to add message {i} with invalid SDK role '{sdk_role}'. Skipping."
            log.error(err, extra={"event_type": "history_prep_invalid_sdk_role", "details": {"message_index": i, "sdk_role": sdk_role}})
            preparation_errors.append(err)
            continue

        if glm_history:
            last_sdk_role = glm_history[-1].role
            if last_sdk_role == "user" and sdk_role != "model":
                log.warning("History sequence repair: User message must be followed by a model message. Inserting empty model response.", extra={"event_type": "history_repair_user_model_sequence", "details": {"current_sdk_role": sdk_role}})
                preparation_errors.append(f"Repaired sequence: Added missing model message after user (before {sdk_role})")
                repair_parts = [glm.Part(text="[No response was provided for this message]")]
                glm_history.append(glm.Content(role="model", parts=repair_parts))
            elif last_sdk_role == "model":
                last_model_had_tool_calls = any(hasattr(p, 'function_call') and p.function_call is not None for p in glm_history[-1].parts)
                if last_model_had_tool_calls and sdk_role != "tool":
                    log.warning("History sequence repair: Model message with tool_calls must be followed by tool message(s). Inserting placeholder tool responses.", extra={"event_type": "history_repair_model_tool_sequence", "details": {"current_sdk_role": sdk_role}})
                    temp_expected_calls_for_repair = list(expected_tool_calls_info)
                    for expected_call in temp_expected_calls_for_repair:
                        tool_name = expected_call.get("name", "unknown_tool")
                        tool_id = expected_call.get("id", "unknown_id")
                        log.debug(f"Adding placeholder tool response for {tool_name} (ID: {tool_id}) as current message is not its match.", extra={"event_type": "history_repair_add_placeholder_tool_response", "details": {"tool_name": tool_name, "tool_id": tool_id}})
                        placeholder_response = {"result": f"[No tool result was provided for {tool_name}]"}
                        repair_parts = [glm.Part(function_response=glm.FunctionResponse(name=tool_name, response=placeholder_response))]
                        glm_history.append(glm.Content(role="tool", parts=repair_parts))
                        preparation_errors.append(f"Repaired sequence: Added missing tool response for {tool_name}")
                    # After inserting placeholders for the previous model's tool calls:
                    if sdk_role == "model": # If the current message (that triggered this repair) is also a model message
                        log.info(f"Flagging current model message {i} (role: {role}) for skipping after model-tool_call-model repair.", extra={"event_type": "history_repair_flag_skip_model", "details": {"message_index": i}})
                        skip_current_message_due_to_repair = True
                elif not last_model_had_tool_calls and sdk_role != "user":
                    if not (is_internal or message_type == WORKFLOW_STAGE_MESSAGE_TYPE or message_type == "context_summary"):
                        log.warning("History sequence note: Model message without tool calls normally followed by user message. Allowing as this may be a valid workflow pattern.", extra={"event_type": "history_note_model_user_sequence_allow_workflow", "details": {"current_sdk_role": sdk_role}})
            elif last_sdk_role == "tool" and sdk_role != "model":
                if not expected_tool_calls_info:
                    log.warning("History sequence repair: Tool message(s) must be followed by a model message. Inserting placeholder model message.", extra={"event_type": "history_repair_tool_model_sequence", "details": {"current_sdk_role": sdk_role}})
                    repair_parts = [glm.Part(text="[Placeholder response after tool execution]")]
                    glm_history.append(glm.Content(role="model", parts=repair_parts))
                    preparation_errors.append("Repaired sequence: Added missing model message after tool response")
        
        if skip_current_message_due_to_repair:
            log.debug(f"Skipping append of current model message {i} (role: {role}) due to model-tool_call-model sequence repair.", extra={"event_type": "history_repair_skipped_model_append", "details": {"message_index": i}})
            continue
            
        glm_history.append(glm.Content(role=sdk_role, parts=parts))

    if expected_tool_calls_info:
        err = f"History ends prematurely: Model requested tool calls ({expected_tool_calls_info}) but corresponding tool responses are missing at the end of the history."
        log.warning(err, extra={"event_type": "history_premature_end_pending_tool_calls", "details": {"expected_tool_calls": expected_tool_calls_info}})
        preparation_errors.append(err)
        if glm_history and glm_history[-1].role == "model":
            last_model_parts = glm_history[-1].parts
            is_last_model_problematic = any(hasattr(p, 'function_call') and p.function_call is not None and any(expected_call["name"] == p.function_call.name for expected_call in expected_tool_calls_info) for p in last_model_parts) # type: ignore
            if is_last_model_problematic:
                log.warning(
                    "Last model message in history has unresolved pending tool calls. The message will be KEPT in history to reflect the pending calls.",
                    extra={"event_type": "history_keep_last_model_with_pending_calls"}
                )

    log.debug(
        "Prepared history for LLM.",
        extra={"event_type": "history_preparation_finalized", "details": {"glm_history_count": len(glm_history), "source_message_count": len(history_to_process)}}
    )
    return glm_history, preparation_errors


def _reset_conversation_if_broken(
    app_state: AppState, error_message: str
) -> bool:  # Updated type hint
    """
    Checks error messages for patterns that indicate conversation history issues
    and resets the application state's conversation history if a pattern is
    matched.

    Args:
        app_state: The current application state object.
        error_message: The error message string from the LLM API call.

    Returns:
        True if history was reset, False otherwise.
    """
    reset_patterns = [
        re.compile(r"content does not match the expected proto schema", re.IGNORECASE),
        re.compile(r"Please ensure that the messages alternate between user and model roles", re.IGNORECASE),
        re.compile(r"invalid history", re.IGNORECASE),
        re.compile(r"Request contains an invalid argument", re.IGNORECASE),
        re.compile(r"must alternate between 'user' and 'model' roles", re.IGNORECASE),
        re.compile(r"Role 'tool' must follow 'model' with 'function_call'", re.IGNORECASE),
        re.compile(r"Role 'model' must follow 'tool' with 'function_response'", re.IGNORECASE),
    ]

    should_reset = False
    matched_pattern_str = ""
    for pattern in reset_patterns:
        if pattern.search(error_message):
            should_reset = True
            matched_pattern_str = pattern.pattern
            log.warning(
                "Detected pattern in error indicating history issue. Requesting history reset.",
                extra={"event_type": "history_reset_pattern_detected", "details": {"pattern": matched_pattern_str, "error_preview": error_message[:150]}}
            )
            break

    if not should_reset and "400" in error_message:
        if "finish reason SAFETY" not in error_message and "blocked" not in error_message.lower():
            should_reset = True
            matched_pattern_str = "HTTP 400 Bad Request (likely history)"
            log.warning(
                "Detected HTTP 400 error (not safety/blocked). Requesting history reset.",
                extra={"event_type": "history_reset_http_400_detected", "details": {"error_preview": error_message[:150]}}
            )

    if should_reset:
        user_facing_error_summary = f"Sorry, there was an issue with our conversation flow ({matched_pattern_str[:50]}...). I've reset our chat to fix it. Please try your request again."
        # Preserve existing system messages (excluding workflow stage markers) while ensuring they are Message objects
        preserved_messages: List[Message] = []
        for msg in app_state.messages:
            try:
                # Support both Message objects and legacy dict structures
                if isinstance(msg, Message):
                    if msg.role == "system" and getattr(msg, "message_type", None) != WORKFLOW_STAGE_MESSAGE_TYPE:
                        preserved_messages.append(msg)
                elif isinstance(msg, dict):
                    if msg.get("role") == "system" and msg.get("message_type") != WORKFLOW_STAGE_MESSAGE_TYPE:
                        preserved_messages.append(Message(role="system", parts=[SafeTextPart(content=str(msg.get("content", "")))]))
            except Exception:
                # If any unexpected structure, skip the message to avoid corrupting the new history
                continue

        # Reset the conversation history to only the preserved system messages
        app_state.messages = preserved_messages

        # Add the self-notification error message using the standard helper so it's a proper Message object
        app_state.add_message("assistant", user_facing_error_summary, is_error=True, metadata={"error_type": "HistoryCorruptionSelfNotification"})

        if hasattr(app_state, 'active_workflows') and app_state.active_workflows:
            workflow_ids = list(app_state.active_workflows.keys())
            active_workflows_info = [f"{wf_id}: {app_state.active_workflows[wf_id].workflow_type}" for wf_id in workflow_ids]
            log.warning(
                "Resetting active workflows due to history reset.",
                extra={"event_type": "history_reset_active_workflows", "details": {"active_workflows_info": active_workflows_info}}
            )
            if hasattr(app_state, 'end_workflow') and callable(app_state.end_workflow): app_state.end_workflow()
            else:
                if hasattr(app_state, 'active_workflows') and app_state.active_workflows:
                    for wf_id in list(app_state.active_workflows.keys()):
                        workflow = app_state.active_workflows.pop(wf_id)
                        workflow.status = "failed"
                        if hasattr(app_state, 'completed_workflows'): app_state.completed_workflows.append(workflow)
                if hasattr(app_state, 'current_workflow'): app_state.current_workflow = None
                if hasattr(app_state, 'workflow_stage'): app_state.workflow_stage = None
                if hasattr(app_state, 'workflow_context'): app_state.workflow_context = {}

        if hasattr(app_state, 'last_interaction_status'): app_state.last_interaction_status = "HISTORY_RESET_REQUIRED"
        if hasattr(app_state, 'current_status_message'): app_state.current_status_message = "[RESET] Conversation history reset due to an error."

        log.info(
            "Conversation history and related state reset due to API error indicating corruption.",
            extra={"event_type": "history_reset_completed"}
        )
        return True
    else:
        log.debug(
            "API error did not match specific history reset patterns.",
            extra={"event_type": "history_reset_no_pattern_match", "details": {"error_preview": error_message[:150]}}
        )
        return False
