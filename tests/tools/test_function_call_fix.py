"""
Test script to verify that the function call extraction logic works properly.
This is a simple script that creates mock function call objects and tests
our extraction logic.
"""
import os
import sys
import unittest
import logging
from unittest.mock import MagicMock, patch

# Add the parent directory to the path so we can import from the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import the necessary modules
from utils.function_call_utils import safe_extract_function_call
from llm_interface import _safe_sdk_object_repr_for_log

# Setup basic logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_function_call_fix")

class TestFunctionCallHandling(unittest.TestCase):
    """Test the function call extraction logic"""
    
    def test_safe_extract_dict(self):
        """Test that we can extract a basic dictionary"""
        test_dict = {"name": "test", "value": 42}
        result = safe_extract_function_call(test_dict)
        self.assertEqual(result, test_dict)
    
    def test_safe_extract_none(self):
        """Test that we handle None gracefully"""
        result = safe_extract_function_call(None)
        self.assertEqual(result, {})
    
    def test_safe_extract_object_with_to_dict(self):
        """Test extracting from an object with to_dict method"""
        mock_obj = MagicMock()
        mock_obj.to_dict.return_value = {"name": "test", "value": 42}
        result = safe_extract_function_call(mock_obj)
        self.assertEqual(result, {"name": "test", "value": 42})
    
    def test_safe_extract_object_with_attributes(self):
        """Test extracting from an object with attributes"""
        class TestObj:
            def __init__(self):
                self.name = "test"
                self.value = 42
                self._private = "hidden"
                
            def method(self):
                pass
        
        obj = TestObj()
        result = safe_extract_function_call(obj)
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 42)
        self.assertNotIn("_private", result)
        self.assertNotIn("method", result)
    
    @patch('utils.function_call_utils.GOOGLE_SDK_AVAILABLE', True)
    def test_safe_extract_protobuf_like(self):
        """Test extracting from a protobuf-like object with DESCRIPTOR"""
        class MockField:
            def __init__(self, name):
                self.name = name
        
        class MockDescriptor:
            def __init__(self):
                self.fields = [MockField("name"), MockField("args")]
        
        class MockProtobuf:
            def __init__(self):
                self.DESCRIPTOR = MockDescriptor()
                self.name = "test_function"
                self.args = {"param1": "value1"}
        
        obj = MockProtobuf()
        result = safe_extract_function_call(obj)
        self.assertEqual(result["name"], "test_function")
        self.assertEqual(result["args"], {"param1": "value1"})
    
    def test_safe_sdk_object_repr(self):
        """Test the safe SDK object representation function"""
        # Test with a simple string
        self.assertEqual(_safe_sdk_object_repr_for_log("test"), "test")
        
        # Test with a simple number
        self.assertEqual(_safe_sdk_object_repr_for_log(42), "42")
        
        # Test with None
        self.assertEqual(_safe_sdk_object_repr_for_log(None), "None")
        
        # Test with a list
        result = _safe_sdk_object_repr_for_log([1, 2, 3])
        self.assertIn("ListLen=3", result)
        
        # Test with a complex object
        class TestObj:
            def __init__(self):
                self.name = "test"
        
        obj = TestObj()
        result = _safe_sdk_object_repr_for_log(obj)
        self.assertIn("Type=TestObj", result)


if __name__ == "__main__":
    print("Testing function call extraction with current SDK...")
    unittest.main() 