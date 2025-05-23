"""
Minimal utility functions for the chatbot.
These are stub implementations to allow the bot to start up.
"""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("utils")


def sanitize_message_content(content: Any) -> str:
    """
    Sanitize message content for safe display.
    
    Args:
        content: The content to sanitize
        
    Returns:
        Sanitized string content
    """
    if content is None:
        return ""
    
    # Basic sanitization - convert to string and strip
    sanitized = str(content).strip()
    
    # Remove any potential control characters (basic implementation)
    sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
    
    return sanitized


def cleanup_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Clean up message list by removing invalid or corrupted messages.
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        Cleaned list of messages
    """
    if not messages:
        return []
    
    cleaned_messages = []
    for msg in messages:
        if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
            # Basic validation - ensure message has required fields
            cleaned_msg = {
                'role': str(msg['role']),
                'content': sanitize_message_content(msg['content'])
            }
            
            # Preserve other fields if they exist
            for key, value in msg.items():
                if key not in ['role', 'content']:
                    cleaned_msg[key] = value
            
            cleaned_messages.append(cleaned_msg)
        else:
            log.warning(f"Skipping invalid message format: {type(msg)}")
    
    return cleaned_messages


def optimize_tool_usage_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimize tool usage statistics for performance.
    
    Args:
        stats: Tool usage statistics dictionary
        
    Returns:
        Optimized statistics dictionary
    """
    if not isinstance(stats, dict):
        return {}
    
    # Basic optimization - ensure stats don't grow too large
    optimized_stats = {}
    
    for key, value in stats.items():
        if isinstance(value, dict):
            # Limit nested dictionaries to prevent unbounded growth
            if len(value) > 100:
                # Keep only the most recent/important entries
                sorted_items = sorted(value.items(), key=lambda x: str(x[1]), reverse=True)
                optimized_stats[key] = dict(sorted_items[:50])
            else:
                optimized_stats[key] = value
        elif isinstance(value, list):
            # Limit list sizes
            optimized_stats[key] = value[-50:] if len(value) > 50 else value
        else:
            optimized_stats[key] = value
    
    return optimized_stats


def log_session_summary_adapted(
    session_id: str,
    summary_data: Dict[str, Any],
    log_level: str = "INFO"
) -> None:
    """
    Log session summary in an adapted format.
    
    Args:
        session_id: The session identifier
        summary_data: Summary data to log
        log_level: Log level to use
    """
    try:
        # Basic session summary logging
        log_func = getattr(log, log_level.lower(), log.info)
        
        message_count = summary_data.get('message_count', 0)
        tool_calls = summary_data.get('tool_calls', 0)
        duration = summary_data.get('duration_seconds', 0)
        
        summary_msg = (
            f"Session {session_id} summary: "
            f"{message_count} messages, {tool_calls} tool calls, "
            f"{duration:.1f}s duration"
        )
        
        log_func(summary_msg)
        
    except Exception as e:
        log.error(f"Error logging session summary for {session_id}: {e}")


# Additional utility functions that might be needed

def format_error_message(error: Exception, context: str = "") -> str:
    """Format an error message for user display."""
    error_msg = str(error) if error else "Unknown error"
    if context:
        return f"{context}: {error_msg}"
    return error_msg


def truncate_text(text: str, max_length: int = 1000) -> str:
    """Truncate text to a maximum length."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length-3] + "..." 