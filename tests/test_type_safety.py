"""
Type safety tests to catch function signature mismatches.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from state_models import AppState, Message, TextPart # Added Message, TextPart
from utils.utils import sanitize_message_content

def test_sanitize_message_content_returns_int():
    """Test that sanitize_message_content returns an integer count, not a string."""
    # Create a mock AppState with some messages
    app_state = AppState()
    app_state.messages = [
        Message(role="user", parts=[TextPart(text="test message")]),
        Message(role="model", parts=[TextPart(text="response")])
    ]
    
    # Call the function
    result = sanitize_message_content(app_state)
    
    # Verify it returns an integer
    assert isinstance(result, int), f"sanitize_message_content should return int, got {type(result)}"
    assert result >= 0, f"sanitize_message_content should return non-negative count, got {result}"

def test_sanitize_message_content_with_long_content():
    """Test that sanitize_message_content handles long content and returns correct count."""
    app_state = AppState()
    app_state.messages = [
        Message(role="user", parts=[TextPart(text="x" * 200000)]),  # Very long content
        Message(role="model", parts=[TextPart(text="short response")])
    ]
    
    result = sanitize_message_content(app_state)
    
    assert isinstance(result, int), f"Expected int, got {type(result)}"
    # Should return 1 since one message was sanitized (truncated)
    assert result == 1, f"Expected 1 sanitized message, got {result}"

def test_sanitize_message_content_with_no_sanitization_needed():
    """Test that sanitize_message_content returns 0 when no sanitization is needed."""
    app_state = AppState()
    app_state.messages = [
        Message(role="user", parts=[TextPart(text="short message")]),
        Message(role="model", parts=[TextPart(text="short response")])
    ]
    
    result = sanitize_message_content(app_state)
    
    assert isinstance(result, int), f"Expected int, got {type(result)}"
    assert result == 0, f"Expected 0 sanitized messages, got {result}"

if __name__ == "__main__":
    test_sanitize_message_content_returns_int()
    test_sanitize_message_content_with_long_content()
    test_sanitize_message_content_with_no_sanitization_needed()
    print("✅ All type safety tests passed!") 