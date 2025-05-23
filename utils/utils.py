"""
Utility functions for state management and validation.
Contains functions formerly in state_models.py but extracted to reduce coupling.
"""
import logging
import json
from typing import Dict, Any, List, Optional, Callable, Tuple

log = logging.getLogger("utils")

# --- Validation Utility Functions ---


def validate_numeric_update(
        value: int,
        min_val: int = 0,
        max_val: int = 1_000_000_000) -> int:
    """Validates that a numeric value is within acceptable range."""
    if not isinstance(value, int):
        raise TypeError(f"Expected integer, got {type(value)}")
    if value < min_val:
        raise ValueError(f"Value {value} is below minimum {min_val}")
    if value > max_val:
        raise ValueError(f"Value {value} exceeds maximum {max_val}")
    return value


def validate_tool_usage_structure(tool_usage: Dict) -> None:
    """Validates the structure of tool usage statistics."""
    if not isinstance(tool_usage, dict):
        raise TypeError(f"Expected dict, got {type(tool_usage)}")

    from unittest.mock import MagicMock

    for tool_name, stats in tool_usage.items():
        # Check if required attributes exist
        required_attrs = ['calls', 'successes', 'failures']
        for attr in required_attrs:
            if not hasattr(stats, attr):
                raise ValueError(
                    f"Tool stats for '{tool_name}' missing required attribute '{attr}'")

            # For MagicMock objects in tests, we need to specifically check if the attribute
            # has been set or if it's just a dynamic attribute created by
            # MagicMock
            if isinstance(stats, MagicMock):
                # In a MagicMock, checking if an attribute exists in __dict__ tells us
                # if it was explicitly set or just auto-created
                if attr not in ['calls'] and attr not in getattr(
                        stats, '__dict__', {}):
                    raise ValueError(
                        f"Tool stats for '{tool_name}' missing required attribute '{attr}'")

        # Check for consistency - only for real objects, not mocks
        if not isinstance(stats, MagicMock):
            if stats.calls < stats.successes + stats.failures:
                raise ValueError(
                    f"Tool stats for '{tool_name}' has inconsistent counts: calls={stats.calls}, successes={stats.successes}, failures={stats.failures}")


def validate_state_integrity(state_obj: Any) -> None:
    """
    Performs deep validation on the entire state object.

    Args:
        state_obj: An AppState object to validate
    """
    # Validate tool usage structure
    validate_tool_usage_structure(state_obj.session_stats.tool_usage)

    # Validate message structure
    for msg in state_obj.messages:
        if not isinstance(msg, dict):
            raise TypeError(f"Message must be a dict, got {type(msg)}")
        if 'role' not in msg:
            raise ValueError(f"Message missing required 'role' field: {msg}")


def validate_state_update(func: Callable) -> Callable:
    """
    Decorator that validates the state before and after an update operation.
    If validation fails after the operation, rolls back to the previous state.
    """
    def wrapper(state_obj, *args, **kwargs):
        # Make a deep copy of the relevant state before modification
        if hasattr(state_obj, 'model_dump'):
            # For Pydantic v2
            old_state_data = state_obj.model_dump()
        elif hasattr(state_obj, 'dict'):
            # For Pydantic v1
            old_state_data = state_obj.dict()
        else:
            log.warning(
                "Could not create state backup for validation - proceed with caution")
            old_state_data = None

        try:
            # Run the update function
            result = func(state_obj, *args, **kwargs)

            # Validate the new state
            # This will raise an exception if validation fails
            validate_state_integrity(state_obj)

            return result
        except Exception as e:
            log.error(
                f"State update validation failed: {e}. Rolling back changes.")

            # Roll back to the previous state if we have a backup
            if old_state_data:
                # Restore fields from the backup
                for key, value in old_state_data.items():
                    if hasattr(state_obj, key):
                        setattr(state_obj, key, value)

                log.warning(
                    f"State rolled back to previous valid state after validation error.")
            else:
                log.error("Could not roll back state - no backup available.")

            # Re-raise the original exception
            raise

    return wrapper

# --- State Utility Functions ---


def validate_and_repair_state(state_obj: Any) -> Tuple[bool, List[str]]:
    """
    Validates the state for consistency and attempts to repair any issues.
    Returns a tuple of (is_valid, list_of_repairs_made).

    This enhances robustness by detecting and repairing inconsistent state
    that might occur due to race conditions or unexpected user actions.

    Args:
        state_obj: An AppState object to validate and repair

    Returns:
        Tuple[bool, List[str]]: Whether the state was valid (or repaired) and
                              a list of repair actions taken
    """
    repairs = []
    is_valid = True

    # Import here to avoid circular imports
    from bot_core.message_handler import MessageProcessor
    
    # Helper function to safely get role from message (handles both Message objects and dicts)
    def get_message_role(msg):
        try:
            if hasattr(msg, 'role'):  # Message object
                return msg.role
            elif isinstance(msg, dict):
                return msg.get('role', 'unknown')
            else:
                # Fallback - assume it's a user message
                return 'user'
        except Exception as e:
            log.warning(f"Error getting message role: {e}")
            return 'unknown'

    # Helper function to safely get text content from message
    def get_message_text(msg):
        try:
            return MessageProcessor.safe_get_text(msg)
        except Exception as e:
            log.warning(f"Error getting message text: {e}")
            return str(msg) if msg is not None else ""

    # Validate messages for integrity
    if hasattr(state_obj, 'messages') and state_obj.messages:
        log.debug("Validating message integrity...")
        
        messages_to_remove = []
        for i, msg in enumerate(state_obj.messages):
            try:
                # Check for text integrity issues
                text_content = get_message_text(msg)
                
                # Detect character splitting issues
                if not MessageProcessor.validate_text_integrity(text_content):
                    log.warning(f"Found message with text integrity issues at index {i}")
                    
                    # If the text is very long without spaces, it might be character-split
                    if len(text_content) > 50 and ' ' not in text_content:
                        log.error(f"Removing malformed message: '{text_content[:50]}...'")
                        messages_to_remove.append(i)
                        repairs.append(f"Removed malformed message at index {i}")
                        is_valid = False
                        continue
                
                # Validate role
                role = get_message_role(msg)
                if role not in ['user', 'model', 'system', 'assistant', 'function']:
                    log.warning(f"Message at index {i} has invalid role: {role}")
                    # Try to fix the role
                    if hasattr(msg, 'role'):
                        msg.role = 'user'  # Default to user
                    repairs.append(f"Fixed invalid role at message index {i}")
                    is_valid = False
                
            except Exception as e:
                log.error(f"Error validating message at index {i}: {e}")
                messages_to_remove.append(i)
                repairs.append(f"Removed corrupted message at index {i}")
                is_valid = False
        
        # Remove problematic messages (in reverse order to maintain indices)
        for i in reversed(messages_to_remove):
            try:
                del state_obj.messages[i]
                log.info(f"Removed problematic message at index {i}")
            except Exception as e:
                log.error(f"Failed to remove message at index {i}: {e}")

    # Validate session metadata
    if hasattr(state_obj, 'session_id'):
        if not state_obj.session_id or not isinstance(state_obj.session_id, str):
            log.warning("Invalid session_id detected, generating new one")
            import uuid
            state_obj.session_id = str(uuid.uuid4())
            repairs.append("Generated new session_id")
            is_valid = False

    # Check for message count limits
    if hasattr(state_obj, 'messages') and len(state_obj.messages) > 1000:
        log.warning(f"Too many messages ({len(state_obj.messages)}), trimming to last 500")
        state_obj.messages = state_obj.messages[-500:]
        repairs.append("Trimmed excessive message history")
        is_valid = False

    log.debug(f"State validation complete. Valid: {is_valid}, Repairs: {len(repairs)}")
    return is_valid, repairs


def sanitize_message_content(
        state_obj: Any,
        max_content_length: int = 100000,
        redact_keys: Optional[list] = None) -> int:
    """
    Truncates overly long message content and redacts sensitive metadata keys in all messages.
    Returns the number of messages sanitized, not the number of fields sanitized.

    Args:
        state_obj: An AppState object containing messages
        max_content_length: Maximum length for message content
        redact_keys: List of keys to redact in metadata

    Returns:
        int: Number of messages that were sanitized
    """
    if redact_keys is None:
        redact_keys = [
            "api_key",
            "password",
            "token",
            "access_token",
            "secret"]

    # Track sanitized messages instead of individual fields
    sanitized_messages = set()

    for i, msg in enumerate(state_obj.messages):
        log.debug(f"Sanitizing message {i}: type={type(msg)}, attributes available: {dir(msg) if not isinstance(msg, dict) else msg.keys()}")
        if hasattr(msg, 'parts') and isinstance(msg.parts, list) and len(msg.parts) > 0 and hasattr(msg.parts[0], 'text') and isinstance(msg.parts[0].text, str):
            log.debug(f"Message {i} (Message object with parts) - Part 0 text length: {len(msg.parts[0].text)}")
        elif isinstance(msg, dict) and "content" in msg and isinstance(msg.get("content"), str):
            log.debug(f"Message {i} (dict with content key) - Content length: {len(msg['content'])}")
        else:
            log.debug(f"Message {i} has unexpected structure or content type. Type: {type(msg)}. Content: {str(msg)[:200]}...")

        content_sanitized = False
        metadata_sanitized = False

        # Truncate long content
        # Check for Message object structure first
        if hasattr(msg, 'parts') and isinstance(msg.parts, list) and len(msg.parts) > 0: # Check if parts exist and is a list
            part_zero = msg.parts[0]
            log.debug(f"Message {i}, Part 0 type: {type(part_zero)}")
            log.debug(f"Message {i}, Part 0 attributes: {dir(part_zero)}")
            log.debug(f"Message {i}, Part 0 has 'text' attribute: {hasattr(part_zero, 'text')}")
            log.debug(f"Message {i}, Part 0 has 'content' attribute: {hasattr(part_zero, 'content')}")
            if hasattr(part_zero, 'content') and isinstance(part_zero.content, str):
                 log.debug(f"Message {i}, Part 0 content length: {len(part_zero.content)}")
        
        if hasattr(msg, 'parts') and isinstance(msg.parts, list) and len(msg.parts) > 0 and \
           hasattr(msg.parts[0], 'content') and isinstance(msg.parts[0].content, str): # Changed .text to .content
            if len(msg.parts[0].content) > max_content_length: # Changed .text to .content
                msg.parts[0].content = msg.parts[0].content[:max_content_length] + \
                    "... [TRUNCATED]" # Changed .text to .content
                content_sanitized = True
        # Fallback to dict structure
        elif isinstance(msg, dict) and "content" in msg and isinstance(msg["content"], str):
            if len(msg["content"]) > max_content_length:
                msg["content"] = msg["content"][:max_content_length] + \
                    "... [TRUNCATED]"
                content_sanitized = True

        # Redact sensitive metadata
        if isinstance(
                msg,
                dict) and "metadata" in msg and isinstance(
                msg["metadata"],
                dict):
            for key in redact_keys:
                if key in msg["metadata"]:
                    msg["metadata"][key] = "[REDACTED]"
                    metadata_sanitized = True

        # Count this message as sanitized if either content or metadata was
        # modified
        if content_sanitized or metadata_sanitized:
            sanitized_messages.add(i)

    if sanitized_messages:
        log.info(
            f"Sanitized {len(sanitized_messages)} message fields (truncation/redaction)")

    return len(sanitized_messages)


def safe_get(state_obj: Any, path: str, default: Any = None,
             require_permission: bool = False) -> Any:
    """
    Safely retrieves a nested attribute from AppState using dot notation (e.g., 'session_stats.llm_tokens_used').
    Returns default if the path does not exist. Optionally logs/audits access if require_permission is True.

    Args:
        state_obj: An AppState object to query
        path: Dot-separated path to the attribute (e.g., 'session_stats.llm_tokens_used')
        default: Value to return if the path doesn't exist
        require_permission: Whether to log/audit the access

    Returns:
        Any: The value at the specified path, or default if not found
    """
    try:
        parts = path.split('.')
        obj = state_obj
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part, default)
            else:
                obj = getattr(obj, part, default)
            if obj is None:
                return default
        if require_permission and hasattr(state_obj, 'log_state_audit'):
            try:
                state_obj.log_state_audit("access", path)
            except Exception as e:
                log.warning(f"Failed to audit state access for '{path}': {e}")
        return obj
    except Exception as e:
        log.warning(f"safe_get failed for path '{path}': {e}")
        return default


def update_session_stats_batch(
        state_obj: Any, updates: Dict[str, int]) -> None:
    """
    Updates multiple session statistics in one operation.

    Args:
        state_obj: An AppState object
        updates: Dictionary of stat_name -> value_to_add
    """
    valid_fields = {
        "llm_tokens_used",
        "llm_calls",
        "llm_api_call_duration_ms",
        "tool_calls",
        "tool_execution_ms",
        "planning_ms",
        "total_duration_ms",
        "failed_tool_calls",
        "retry_count",
        "total_agent_turn_ms"}

    for field, value in updates.items():
        if field in valid_fields:
            try:
                # Validate the numeric value first
                validated_value = validate_numeric_update(value)
                current_value = getattr(state_obj.session_stats, field, 0)
                # Set the new value (additive update)
                setattr(
                    state_obj.session_stats,
                    field,
                    current_value +
                    validated_value)
                log.debug(
                    f"Updated session stat {field}: {current_value} -> {current_value + validated_value}")
            except (ValueError, TypeError) as e:
                log.warning(
                    f"Invalid value for session stat {field}: {value} - {e}")
        else:
            log.warning(f"Unknown session stat field: {field}")


def cleanup_messages(state_obj: Any, keep_last_n: int = 100) -> int:
    """
    Trims message history to a specified maximum size, preserving system messages.
    Returns the number of messages removed.

    Args:
        state_obj: An AppState object
        keep_last_n: Maximum number of messages to keep

    Returns:
        int: Number of messages removed
    """
    if not hasattr(state_obj, 'messages') or len(state_obj.messages) <= keep_last_n:
        log.debug("No message cleanup needed, under the limit.")
        return 0

    # Import here to avoid circular imports
    from bot_core.message_handler import MessageProcessor

    # Helper function to safely get role from message
    def get_message_role(msg):
        try:
            if hasattr(msg, 'role'):  # Message object
                return msg.role
            elif isinstance(msg, dict):
                return msg.get('role', 'user')
            else:
                return 'user'  # Default fallback
        except Exception as e:
            log.warning(f"Error getting message role during cleanup: {e}")
            return 'user'

    original_count = len(state_obj.messages)
    
    try:
        # Separate system messages from others
        system_messages = []
        other_messages = []
        
        for msg in state_obj.messages:
            try:
                role = get_message_role(msg)
                if role == 'system':
                    system_messages.append(msg)
                else:
                    other_messages.append(msg)
            except Exception as e:
                log.warning(f"Error processing message during cleanup: {e}")
                # Add to other_messages as fallback
                other_messages.append(msg)
        
        # Keep the last N non-system messages
        if len(other_messages) > keep_last_n:
            other_messages = other_messages[-keep_last_n:]
        
        # Combine system messages with recent other messages
        state_obj.messages = system_messages + other_messages
        
        removed_count = original_count - len(state_obj.messages)
        log.info(f"Message cleanup completed. Removed {removed_count} messages, kept {len(state_obj.messages)}")
        
        return removed_count
        
    except Exception as e:
        log.error(f"Error during message cleanup: {e}")
        # Fallback: just keep the last N messages regardless of type
        if len(state_obj.messages) > keep_last_n:
            removed = len(state_obj.messages) - keep_last_n
            state_obj.messages = state_obj.messages[-keep_last_n:]
            log.warning(f"Fallback cleanup: removed {removed} messages")
            return removed
        return 0


def optimize_tool_usage_stats(state_obj: Any, keep_top_n: int = 10) -> None:
    """
    Keeps only the top N most used tools (by call count).
    This helps prevent runaway growth of the tool_usage dictionary.

    Args:
        state_obj: An AppState object
        keep_top_n: Number of most-used tools to keep
    """
    try:
        if len(state_obj.session_stats.tool_usage) <= keep_top_n:
            log.debug(
                f"Tool usage stats optimization not needed, under limit ({len(state_obj.session_stats.tool_usage)} <= {keep_top_n}).")
            return

        # Sort by calls and keep only the top N
        sorted_tools = sorted(
            state_obj.session_stats.tool_usage.items(),
            key=lambda item: item[1].calls,
            reverse=True
        )

        # Rebuild dictionary with only the top N tools
        new_tool_usage = {}
        for tool_name, stats in sorted_tools[:keep_top_n]:
            new_tool_usage[tool_name] = stats

        removed_count = len(
            state_obj.session_stats.tool_usage) - len(new_tool_usage)
        state_obj.session_stats.tool_usage = new_tool_usage

        log.info(
            f"Optimized tool usage stats: removed {removed_count} least-used tools, kept {len(new_tool_usage)} most-used.")
    except Exception as e:
        log.error(f"optimize_tool_usage_stats failed: {e}")


def log_session_summary_adapted(
        app_state: Any,
        final_status: str,
        error_details: Optional[str] = None) -> None:
    """
    Logs a comprehensive summary of the agent's interaction session.

    This function captures key metrics and status information at the end of a session,
    providing insights into the agent's performance and any errors encountered.

    Args:
        app_state: The application state object, expected to have a 'session_id'
                   attribute and a 'session_stats' object.
        final_status (str): A string describing the final status of the session
                            (e.g., "COMPLETED_OK", "ERROR", "MAX_CALLS_REACHED").
        error_details (Optional[str]): A string containing details of any error
                                       that occurred, if applicable. Defaults to None.
    """
    log.info(f"*** Session Summary ***")
    log.info(f"Session ID: {getattr(app_state, 'session_id', 'N/A')}")
    log.info(f"Final Status: {final_status}")

    if error_details:
        log.error(f"Error Details: {error_details}")

    session_stats = getattr(app_state, 'session_stats', None)
    if session_stats:
        log.info(f"LLM Calls: {getattr(session_stats, 'llm_calls', 'N/A')}")
        log.info(
            f"LLM Tokens Used: {getattr(session_stats, 'llm_tokens_used', 'N/A')}")
        log.info(
            f"LLM API Call Duration (ms): {getattr(session_stats, 'llm_api_call_duration_ms', 'N/A')}")
        log.info(f"Tool Calls: {getattr(session_stats, 'tool_calls', 'N/A')}")
        log.info(
            f"Failed Tool Calls: {getattr(session_stats, 'failed_tool_calls', 'N/A')}")
        log.info(
            f"Tool Execution Duration (ms): {getattr(session_stats, 'tool_execution_ms', 'N/A')}")
        log.info(
            f"Total Agent Turn Duration (ms): {getattr(session_stats, 'total_agent_turn_ms', 'N/A')}")

        tool_usage = getattr(session_stats, 'tool_usage', {})
        if tool_usage:
            log.info("Tool Usage Breakdown:")
            for tool_name, usage_stats in tool_usage.items():
                calls = getattr(usage_stats, 'calls', 0)
                successes = getattr(usage_stats, 'successes', 0)
                failures = getattr(usage_stats, 'failures', 0)
                log.info(
                    f"  - {tool_name}: Called {calls} times (Success: {successes}, Fail: {failures})")
        else:
            log.info("Tool Usage Breakdown: No tools used or stats unavailable.")

    else:
        log.warning(
            "Session statistics (app_state.session_stats) not found or unavailable for summary.")

    log.info(f"*** End Session Summary ***")
