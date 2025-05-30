"""
Direct test of function call handling with the actual Google SDK.
This test script creates a real function call object and tests if we can 
handle it properly without the "Could not convert part.function_call to text" error.
"""
import os
import sys
import logging
import json
from typing import Dict, Any

# Add the parent directory to the path so we can import from the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_function_call_fix_direct")

try:
    # Import Google's AI SDK
    import google.generativeai as genai
    import google.ai.generativelanguage as glm
    
    # Import our fixed utility functions
    from utils.function_call_utils import safe_extract_function_call
    from llm_interface import _safe_sdk_object_repr_for_log
    
    # Import the config module to get the API key
    from config import get_config
    
    def test_with_real_function_call():
        """Test our function call handling with a real function call from the SDK"""
        print("Testing with real function call from Google SDK...")
        
        # Get configuration
        config = get_config()
        api_key = config.GEMINI_API_KEY
        
        # Configure the SDK
        genai.configure(api_key=api_key)
        
        # Define a tool for the LLM to use
        tool = glm.Tool(
            function_declarations=[
                glm.FunctionDeclaration(
                    name="get_weather",
                    description="Get the current weather in a given location",
                    parameters=glm.Schema(
                        type_=glm.Type.OBJECT,
                        properties={
                            "location": glm.Schema(
                                type_=glm.Type.STRING,
                                description="The city and state, e.g. San Francisco, CA"
                            ),
                            "unit": glm.Schema(
                                type_=glm.Type.STRING,
                                description="The temperature unit to use. Infer this from the user's location.",
                                enum=["celsius", "fahrenheit"]
                            )
                        },
                        required=["location"]
                    )
                )
            ]
        )
        
        # Create a model
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # Send a message that will trigger a function call
        try:
            response = model.generate_content(
                "What's the weather like in Miami?", 
                tools=[tool],
                stream=False
            )
            
            print("Got response from model. Processing function call...")
            
            # Now process the function call using our fixed code
            # First check if there's a function call in the response
            function_call = None
            
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        function_call = part.function_call
                        break
                if function_call:
                    break
            
            if function_call:
                print("Found function call in response!")
                
                # Test our safe_extract_function_call utility
                print("\nTesting safe_extract_function_call...")
                try:
                    args_dict = safe_extract_function_call(function_call.args)
                    print(f"Successfully extracted args: {json.dumps(args_dict, indent=2)}")
                except Exception as e:
                    print(f"ERROR: Extraction failed: {e}")
                
                # Test our _safe_sdk_object_repr_for_log function
                print("\nTesting _safe_sdk_object_repr_for_log...")
                try:
                    safe_repr = _safe_sdk_object_repr_for_log(function_call)
                    print(f"Successfully created representation: {safe_repr}")
                except Exception as e:
                    print(f"ERROR: Safe representation failed: {e}")
                    
                # This is the function that was failing - trying to directly string-convert the function call
                print("\nTesting with direct string conversion (previously failing case)...")
                try:
                    # This would normally fail with "Could not convert part.function_call to text"
                    # But we should handle it gracefully now
                    str_repr = str(function_call)
                    print(f"Successfully converted to string! This is progress. Length: {len(str_repr)}")
                except Exception as e:
                    print(f"Still having issues with direct string conversion: {e}")
                    
                print("\nAll tests completed!")
            else:
                print("No function call found in response. Try running again.")
            
        except Exception as e:
            print(f"Error: {e}")
            return False
        
        return True
    
    if __name__ == "__main__":
        test_with_real_function_call()
        
except ImportError as e:
    print(f"ERROR: Cannot import required modules: {e}")
    print("This test requires the Google AI SDK to be installed.")
    print("Install with: pip install google-generativeai") 