#!/usr/bin/env python3
"""Test basic help tool execution with real validation."""

import asyncio
import logging
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.tool_executor import ToolExecutor
from config import get_config
from state_models import AppState
from user_auth.models import UserProfile

# Configure logging for test visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("test_help_basic")

async def test_help_tool_execution():
    """Test actual help tool execution and validate response."""
    print("🔍 TESTING HELP TOOL EXECUTION")
    print("=" * 50)
    
    try:
        # Setup
        config = get_config()
        app_state = AppState()
        
        # Create test user
        test_user = UserProfile(
            user_id="help_test_user",
            display_name="Help Test User", 
            email="help@test.com",
            assigned_role="ADMIN"
        )
        app_state.current_user = test_user
        
        print(f"✅ Created test user: {test_user.display_name}")
        
        # Initialize ToolExecutor
        executor = ToolExecutor(config)
        print(f"✅ Initialized ToolExecutor")
        
        # Check if help tool is available
        available_tools = executor.get_available_tool_names()
        print(f"📊 Available tools count: {len(available_tools)}")
        print(f"📋 Available tools: {available_tools}")
        
        if "help" not in available_tools:
            print("❌ CRITICAL ERROR: Help tool not found in available tools!")
            return False, None
        
        print("✅ Help tool found in available tools")
        
        # Execute help tool
        print("\n🚀 Executing help tool...")
        result = await executor.execute_tool("help", {}, app_state)
        
        print(f"📊 Help response type: {type(result)}")
        print(f"📊 Help response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        # Validate response structure
        if isinstance(result, dict) and 'status' in result and result['status'] == 'SUCCESS':
            help_data = result.get('data', {})
            print(f"✅ Help tool executed successfully")
            print(f"📊 Help data type: {type(help_data)}")
            
            # Check help data structure
            if isinstance(help_data, dict):
                print(f"📊 Help data keys: {list(help_data.keys())}")
                
                # Check for expected sections
                expected_keys = ['title', 'description', 'sections']
                for key in expected_keys:
                    if key in help_data:
                        print(f"✅ Found expected key: {key}")
                    else:
                        print(f"❌ Missing expected key: {key}")
                
                # Check sections
                sections = help_data.get('sections', [])
                print(f"📊 Number of help sections: {len(sections)}")
                
                for i, section in enumerate(sections):
                    if isinstance(section, dict):
                        section_name = section.get('name', 'Unnamed')
                        content_count = len(section.get('content', []))
                        print(f"  Section {i+1}: {section_name} ({content_count} items)")
                    
                return True, help_data
            else:
                print(f"❌ Unexpected help data format: {type(help_data)}")
                return False, help_data
        else:
            print(f"❌ Help tool execution failed or unexpected response format")
            print(f"📊 Response: {result}")
            return False, result
            
    except Exception as e:
        print(f"❌ Exception during help tool testing: {e}")
        log.error(f"Help tool test exception: {e}", exc_info=True)
        return False, None

async def test_help_tool_performance():
    """Test help tool execution performance."""
    print("\n⏱️ TESTING HELP TOOL PERFORMANCE")
    print("=" * 50)
    
    try:
        import time
        
        config = get_config()
        app_state = AppState()
        test_user = UserProfile(
            user_id="perf_test_user",
            display_name="Performance Test User",
            email="perf@test.com",
            assigned_role="ADMIN"
        )
        app_state.current_user = test_user
        
        executor = ToolExecutor(config)
        
        # Time the help tool execution
        start_time = time.time()
        result = await executor.execute_tool("help", {}, app_state)
        end_time = time.time()
        
        execution_time = end_time - start_time
        print(f"⏱️ Help tool execution time: {execution_time:.3f} seconds")
        
        # Performance criteria: should complete in under 2 seconds
        if execution_time < 2.0:
            print("✅ Performance test passed: execution time acceptable")
            return True
        else:
            print("❌ Performance test failed: execution time too long")
            return False
            
    except Exception as e:
        print(f"❌ Performance test exception: {e}")
        return False

async def main():
    """Run all help tool basic tests."""
    print("🤖 STEP 1.15: HELP TOOL BASIC VALIDATION")
    print("=" * 60)
    
    # Test 1: Basic execution
    success1, help_data = await test_help_tool_execution()
    
    # Test 2: Performance
    success2 = await test_help_tool_performance()
    
    # Summary
    print("\n📊 TEST SUMMARY")
    print("=" * 30)
    print(f"Basic Execution: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"Performance Test: {'✅ PASS' if success2 else '❌ FAIL'}")
    
    overall_success = success1 and success2
    print(f"\nOverall Result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    return overall_success

if __name__ == "__main__":
    asyncio.run(main()) 