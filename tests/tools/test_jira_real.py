#!/usr/bin/env python3
"""Test the actual Jira tool to see what it returns."""

import asyncio
import pytest # Add pytest
from tools.tool_executor import ToolExecutor
from config import get_config
from state_models import AppState

@pytest.mark.asyncio
async def test_real_jira():
    print("🔍 TESTING ACTUAL JIRA TOOL OUTPUT")
    print("=" * 50)
    
    # Initialize
    config = get_config()
    executor = ToolExecutor(config)
    app_state = AppState()
    
    # Get the user email from config
    user_email = config.get_env_value('JIRA_API_EMAIL')
    print(f"Testing with user email: {user_email}")
    
    # Test the actual tool
    print("\n📋 TESTING jira_get_issues_by_user...")
    
    test_cases = [
        {"status_category": "in progress", "max_results": 10},
        {"status_category": "to do", "max_results": 10},
        {"status_category": "done", "max_results": 5},
    ]
    
    for i, params in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {params} ---")
        
        # Prepare tool input
        tool_input = {"user_email": user_email, **params}
        
        try:
            # Execute the tool through the executor
            result = await executor.execute_tool(
                tool_name="jira_get_issues_by_user",
                tool_input=tool_input,
                app_state=app_state
            )
            
            print(f"Tool result type: {type(result)}")
            print(f"Tool result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
            
            # Extract the actual issues data
            if isinstance(result, dict) and 'data' in result:
                issues = result['data']
                print(f"Found {len(issues)} issues")
                
                for j, issue in enumerate(issues[:3], 1):  # Show first 3
                    print(f"  Issue {j}:")
                    print(f"    Key: {issue.get('key', 'N/A')}")
                    print(f"    Summary: {issue.get('summary', 'N/A')[:60]}...")
                    print(f"    Status: {issue.get('status', 'N/A')}")
                    print(f"    Project: {issue.get('project_name', 'N/A')}")
                    
                if len(issues) > 3:
                    print(f"  ... and {len(issues) - 3} more issues")
                    
            elif isinstance(result, list):
                issues = result
                print(f"Found {len(issues)} issues (direct list)")
                
                for j, issue in enumerate(issues[:3], 1):
                    print(f"  Issue {j}:")
                    print(f"    Key: {issue.get('key', 'N/A')}")
                    print(f"    Summary: {issue.get('summary', 'N/A')[:60]}...")
                    print(f"    Status: {issue.get('status', 'N/A')}")
                    
            else:
                print(f"Unexpected result format: {result}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("Expected issues from user's UI:")
    print("- LM-13282: Consumer App: Add Property Value Display...")
    print("- LM-13048: Implement AI-Driven ChatOps Tool...")
    print("- LM-13286: Frontend (Mobile App): Push Notification Integration")
    print("- LM-13285: Backend: Push Notifications...")
    print("- LM-13284: Frontend (Mobile App): Display Property Value")
    print("- LM-13283: Backend: Property Value API")
    print("\n❓ Did our tool find these specific issues?")

if __name__ == "__main__":
    asyncio.run(test_real_jira()) 