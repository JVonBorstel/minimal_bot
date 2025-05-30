"""
Test script to verify that the LLM interface can handle function calls properly.
This script creates a simple LLMInterface instance and tests basic functionality.
"""
import os
import sys
import logging
import asyncio
import unittest
from unittest.mock import patch, MagicMock

# Add the parent directory to the path so we can import from the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_llm_interface")

# Import the necessary modules
from llm_interface import LLMInterface, _safe_sdk_object_repr_for_log
from config import Config

class TestLLMInterface(unittest.TestCase):
    """Test the LLM interface function call handling"""
    
    async def test_llm_interface_initialization(self):
        """Test that we can initialize the LLM interface"""
        config = MagicMock(spec=Config)
        config.GEMINI_API_KEY = "fake_api_key"
        config.GEMINI_MODEL = "gemini-1.0-pro"
        config.DEFAULT_API_TIMEOUT_SECONDS = 30
        config.DEFAULT_API_MAX_RETRIES = 3
        config.MAX_FUNCTION_DECLARATIONS = 10
        
        # Mock out the genai module setup
        with patch('llm_interface.genai') as mock_genai:
            mock_genai.configure.return_value = None
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            
            # Initialize the interface
            interface = LLMInterface(config)
            
            # Check that the model was initialized
            mock_genai.configure.assert_called_once()
            mock_genai.GenerativeModel.assert_called_once()
            
            # Verify the model name was passed correctly
            args, kwargs = mock_genai.GenerativeModel.call_args
            self.assertEqual(args[0], config.GEMINI_MODEL)
            
            print("LLM interface initialized successfully")
            return interface
    
    def test_direct_safe_extract(self):
        """Test the safe_extract_function_call utility directly"""
        from utils.function_call_utils import safe_extract_function_call
        
        # Create a mock function call object
        mock_args = {"param1": "value1", "param2": 42}
        result = safe_extract_function_call(mock_args)
        
        # Should return the same dictionary since it's already a dict
        self.assertEqual(result, mock_args)
        print("Direct safe extract test passed")
    
    @patch('llm_interface.SDK_AVAILABLE', True)
    @patch('llm_interface.glm.FunctionCall', MagicMock)
    def test_safe_sdk_object_repr(self):
        """Test the safe SDK object representation function with mocked SDK types"""
        # Create a mock FunctionCall that will pass isinstance checks
        mock_function_call = MagicMock()
        mock_function_call.__class__ = MagicMock()
        mock_function_call.__class__.__name__ = "FunctionCall"
        
        # Add attributes the safe repr function will look for
        mock_function_call.name = "test_function"
        mock_args = MagicMock()
        mock_args.param1 = "value1"
        mock_args.param2 = 42
        mock_function_call.args = mock_args
        
        # Check direct dict representation
        from utils.function_call_utils import safe_extract_function_call
        result_dict = safe_extract_function_call(mock_args)
        print(f"Extracted args dict: {result_dict}")
        
        # Test basic types
        self.assertEqual(_safe_sdk_object_repr_for_log("test"), "test")
        self.assertEqual(_safe_sdk_object_repr_for_log(42), "42")
        self.assertEqual(_safe_sdk_object_repr_for_log(None), "None")
        
        # Test with a list
        list_result = _safe_sdk_object_repr_for_log([1, 2, 3])
        self.assertIn("ListLen=3", list_result)
        
        print("Safe representation tests passed")

def run_tests():
    """Run the tests"""
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

if __name__ == "__main__":
    print("Testing LLM interface with function call support...")
    run_tests() 