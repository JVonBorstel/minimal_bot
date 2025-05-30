import unittest
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the safe representation functions
from core_logic.llm_interactions import _safe_sdk_object_repr_for_log

class TestSafeSdkRepr(unittest.TestCase):
    """Tests for safely generating string representations of SDK objects."""
    
    def test_safe_repr_for_problematic_function_call(self):
        """Test handling a problematic function_call object that raises on str()."""
        # Create a mock object that raises an error when str() is called on it
        class ProblematicFunctionCall:
            def __init__(self):
                self.name = "test_function"
                self.args = {"arg1": "value1"}
            
            def __str__(self):
                # This simulates the "Could not convert `part.function_call` to text" error
                raise TypeError("Could not convert `part.function_call` to text.")
        
        problematic_obj = ProblematicFunctionCall()
        
        # This should not raise an exception
        result = _safe_sdk_object_repr_for_log(problematic_obj)
        
        # Verify we got a useful string representation
        self.assertIsInstance(result, str)
        self.assertIn("Type=ProblematicFunctionCall", result)
        
    def test_safe_repr_for_part_with_problematic_function_call(self):
        """Test handling a Part object containing a problematic function_call."""
        # Create a mock Part object with a problematic function_call
        class ProblematicFunctionCall:
            def __init__(self):
                self.name = "test_function"
                self.args = {"arg1": "value1"}
            
            def __str__(self):
                # This simulates the "Could not convert `part.function_call` to text" error
                raise TypeError("Could not convert `part.function_call` to text.")
        
        class MockPart:
            def __init__(self):
                self.function_call = ProblematicFunctionCall()
                self.text = None
        
        mock_part = MockPart()
        
        # This should not raise an exception
        result = _safe_sdk_object_repr_for_log(mock_part)
        
        # Verify we got a useful string representation
        self.assertIsInstance(result, str)
        self.assertIn("Type=MockPart", result)
        
    def test_safe_repr_for_response_with_parts(self):
        """Test handling a response object with parts."""
        # Create a mock response object with parts
        class MockPart:
            def __init__(self, has_text=False, has_function_call=False):
                if has_text:
                    self.text = "Some text content"
                if has_function_call:
                    class MockFunctionCall:
                        def __init__(self):
                            self.name = "test_function"
                            self.args = {"arg1": "value1"}
                    self.function_call = MockFunctionCall()
        
        class MockResponse:
            def __init__(self):
                self.parts = [
                    MockPart(has_text=True), 
                    MockPart(has_function_call=True),
                    MockPart(has_text=True, has_function_call=True)
                ]
                self.usage_metadata = Mock()
                self.usage_metadata.total_token_count = 150
        
        mock_response = MockResponse()
        
        # This should not raise an exception
        result = _safe_sdk_object_repr_for_log(mock_response)
        
        # Verify we got a useful string representation
        self.assertIsInstance(result, str)
        self.assertIn("NumParts=3", result)
        self.assertIn("Usage(TotalTokens=150)", result)

if __name__ == "__main__":
    unittest.main() 