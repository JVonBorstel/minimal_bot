#!/usr/bin/env python3
"""
Direct test of the Jira tool to demonstrate it works.
This bypasses the full bot framework and tests just the Jira tool.
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from tools.jira_tools import JiraTools


async def test_jira_tool():
    """Test the Jira tool directly."""
    print("🚀 Testing Jira Tool Directly")
    print("=" * 50)
    
    try:
        # Initialize config
        print("1. Loading configuration...")
        config = get_config()
        
        # Initialize Jira tools
        print("2. Initializing Jira tools...")
        jira_tools = JiraTools(config)
        
        # Test health check first
        print("3. Testing Jira health check...")
        health_result = jira_tools.health_check()
        print(f"   Health Status: {health_result['status']}")
        print(f"   Health Message: {health_result['message']}")
        
        if health_result['status'] != 'OK':
            print("❌ Jira health check failed, cannot proceed with tool test")
            return
            
        print("\n4. Testing jira_get_issues_by_user tool...")
        
        # Get the user email from config
        user_email = config.get_env_value('JIRA_API_EMAIL')
        print(f"   Searching for issues assigned to: {user_email}")
        
        # Test the tool with different parameters
        test_cases = [
            {"status_category": "to do", "max_results": 5},
            {"status_category": "in progress", "max_results": 3},
            {"status_category": "done", "max_results": 5},  # Try completed issues
        ]
        
        for i, params in enumerate(test_cases, 1):
            print(f"\n   Test Case {i}: {params}")
            try:
                # FIXED: Properly await the async method
                result = await jira_tools.get_issues_by_user(
                    user_email=user_email,
                    **params
                )
                
                print(f"   DEBUG: Type of result: {type(result)}")
                
                # Handle wrapped tool response
                if isinstance(result, dict) and 'data' in result:
                    issues = result['data']
                    status = result.get('status', 'UNKNOWN')
                    exec_time = result.get('execution_time_ms', 0)
                    
                    print(f"   ✅ Tool execution: {status} ({exec_time}ms)")
                    print(f"   ✅ Found {len(issues)} issues")
                    
                    # Display first few issues
                    for j, issue in enumerate(issues[:2]):  # Show max 2 issues
                        print(f"      Issue {j+1}:")
                        print(f"        Key: {issue['key']}")
                        print(f"        Summary: {issue['summary'][:80]}...")
                        print(f"        Status: {issue['status']}")
                        print(f"        Project: {issue['project_name']}")
                        print(f"        Type: {issue['issue_type']}")
                        if issue.get('assignee'):
                            print(f"        Assignee: {issue['assignee']}")
                        if issue.get('updated'):
                            print(f"        Updated: {issue['updated']}")
                        
                    if len(issues) > 2:
                        print(f"      ... and {len(issues) - 2} more issues")
                        
                elif isinstance(result, list):
                    # Direct list response (original format)
                    issues = result
                    print(f"   ✅ Found {len(issues)} issues (direct list)")
                    
                    for j, issue in enumerate(issues[:2]):
                        print(f"      Issue {j+1}:")
                        print(f"        Key: {issue['key']}")
                        print(f"        Summary: {issue['summary'][:80]}...")
                        print(f"        Status: {issue['status']}")
                        
                else:
                    print(f"   ⚠️ Unexpected result format: {type(result)}")
                    print(f"   Raw result: {result}")
                    
            except Exception as e:
                print(f"   ❌ Test case failed: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n🎉 Jira tool test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during Jira tool test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_jira_tool()) 