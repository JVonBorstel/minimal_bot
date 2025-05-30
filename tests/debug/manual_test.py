"""
Manual test script to reproduce and debug the function call issue.
This script directly tests the function call handling with the current SDK.
"""
import os
import sys
import asyncio
import logging
from typing import Dict, Any, List

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("manual_test")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import necessary modules
from llm_interface import LLMInterface
from config import get_config
from state_models import AppState

# Import Google SDK
import google.generativeai as genai
import google.ai.generativelanguage as glm

async def test_function_call_handling():
    """
    Test function call handling with a weather query that should trigger a tool call
    """
    config = get_config()
    app_state = AppState()
    
    # Initialize LLM interface
    logger.info("Initializing LLM interface")
    llm = LLMInterface(config)
    
    # Define a query that should trigger a function call
    query = "What's the weather forecast for Denver tomorrow?"
    
    # Define a manual weather tool
    weather_tool = {
        "name": "get_weather",
        "description": "Get the current weather forecast for a specific location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. 'Denver, CO'"
                },
                "date": {
                    "type": "string",
                    "description": "The date for the forecast, e.g. 'tomorrow', 'today', '2023-06-01'"
                }
            },
            "required": ["location"]
        }
    }
    
    # Create messages
    messages = [
        {"role": "user", "parts": [{"text": query}]}
    ]
    
    # Call the LLM with tools
    logger.info(f"Sending query to LLM with manual weather tool: '{query}'")
    try:
        async for chunk in llm.generate_content_stream(messages, app_state, [weather_tool], query):
            chunk_type = chunk.get('type', 'unknown')
            
            if chunk_type == 'text_chunk':
                logger.info(f"Received text: {chunk.get('content', '')[:50]}...")
            elif chunk_type == 'tool_calls':
                tool_calls = chunk.get('content', [])
                logger.info(f"Received tool calls: {len(tool_calls)}")
                for call in tool_calls:
                    logger.info(f"Tool call: {call.get('function', {}).get('name')}")
                    logger.info(f"Arguments: {call.get('function', {}).get('arguments')}")
            elif chunk_type == 'error':
                logger.error(f"Error: {chunk.get('content')}")
            else:
                logger.info(f"Other chunk type: {chunk_type}")
                
    except Exception as e:
        logger.error(f"Error in generate_content_stream: {e}", exc_info=True)
    
    # Also test with direct SDK to see the actual response format
    logger.info("Testing with direct SDK access to understand response format")
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        
        # Create a tool declaration directly with the SDK
        weather_tool_sdk = glm.Tool(
            function_declarations=[
                glm.FunctionDeclaration(
                    name="get_weather",
                    description="Get the current weather forecast for a specific location",
                    parameters=glm.Schema(
                        type_=glm.Type.OBJECT,
                        properties={
                            "location": glm.Schema(
                                type_=glm.Type.STRING,
                                description="The city and state, e.g. 'Denver, CO'"
                            ),
                            "date": glm.Schema(
                                type_=glm.Type.STRING,
                                description="The date for the forecast, e.g. 'tomorrow', 'today', '2023-06-01'"
                            )
                        },
                        required=["location"]
                    )
                )
            ]
        )
        
        # Call the model directly
        logger.info("Making direct SDK call")
        response = model.generate_content(
            [{"role": "user", "parts": [{"text": query}]}],
            tools=[weather_tool_sdk],
            tool_config=genai.types.ToolConfig(
                function_calling_config=genai.types.FunctionCallingConfig(
                    mode=genai.types.FunctionCallingConfig.Mode.ANY
                )
            )
        )
        
        # Attempt to understand the structure without causing the error
        logger.info(f"Response type: {type(response)}")
        if hasattr(response, 'candidates') and response.candidates:
            for i, candidate in enumerate(response.candidates):
                logger.info(f"Candidate {i} type: {type(candidate)}")
                if hasattr(candidate, 'content') and candidate.content:
                    logger.info(f"Candidate {i} content type: {type(candidate.content)}")
                    if hasattr(candidate.content, 'parts'):
                        logger.info(f"Candidate {i} has {len(candidate.content.parts)} parts")
                        for j, part in enumerate(candidate.content.parts):
                            logger.info(f"Part {j} type: {type(part)}")
                            if hasattr(part, 'function_call'):
                                logger.info(f"Part {j} has function_call attribute")
                                # Don't try to print the function_call directly
                                function_call = part.function_call
                                logger.info(f"Function call type: {type(function_call)}")
                                # Check for name and args attributes
                                if hasattr(function_call, 'name'):
                                    logger.info(f"Function name: {function_call.name}")
                                if hasattr(function_call, 'args'):
                                    logger.info(f"Args type: {type(function_call.args)}")
                                    from utils.function_call_utils import safe_extract_function_call
                                    args = safe_extract_function_call(function_call.args)
                                    logger.info(f"Extracted args: {args}")
                            elif hasattr(part, 'text'):
                                logger.info(f"Part {j} text: {part.text[:50]}...")
    except Exception as e:
        logger.error(f"Error in direct SDK test: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Starting manual test")
    asyncio.run(test_function_call_handling())
    logger.info("Manual test complete") 