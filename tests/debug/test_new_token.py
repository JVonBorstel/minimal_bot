#!/usr/bin/env python3
"""
IMMEDIATE TEST for new Jira API token with scopes.
Run this as soon as you update .env with the new token.
"""

import asyncio
from config import get_config
from tools.jira_tools import JiraTools
from tools.tool_executor import ToolExecutor
from state_models import AppState

async def test_new_token():
    print("🔑 TESTING NEW SCOPED API TOKEN")
    print("=" * 60)
    
    config = get_config()
    user_email = config.get_env_value('JIRA_API_EMAIL')
    print(f"User email: {user_email}")
    print()
    
    # Test 1: Basic Connection
    print("📋 TEST 1: Basic Jira Connection")
    print("-" * 30)
    jira_tools = JiraTools(config)
    
    if not jira_tools.jira_client:
        print("❌ FAILED: Jira client not initialized")
        return
    else:
        print("✅ PASSED: Jira client initialized")
    
    # Test 2: Authentication Check
    print("\n👤 TEST 2: Authentication Check")
    print("-" * 30)
    try:
        current_user = jira_tools.jira_client.current_user()
        user_info = jira_tools.jira_client.user(current_user)
        print(f"✅ PASSED: Authenticated as {user_info.displayName} ({user_info.emailAddress})")
    except Exception as e:
        print(f"❌ FAILED: Authentication error - {e}")
        return
    
    # Test 3: Project Access
    print("\n🏢 TEST 3: Project Access")
    print("-" * 30)
    try:
        projects = jira_tools.jira_client.projects()
        project_names = [p.name for p in projects]
        print(f"✅ PASSED: Can access {len(projects)} projects")
        if any('loan' in p.lower() for p in project_names):
            loan_projects = [p for p in project_names if 'loan' in p.lower()]
            print(f"  Found loan-related projects: {loan_projects}")
        else:
            print(f"  Available projects: {project_names[:3]}...")
    except Exception as e:
        print(f"❌ FAILED: Cannot access projects - {e}")
        return
    
    # Test 4: Specific Issue Access
    print("\n🎯 TEST 4: Your Specific Issues")
    print("-" * 30)
    your_issues = ["LM-13282", "LM-13048", "LM-13286", "LM-13285", "LM-13284", "LM-13283"]
    
    found_issues = []
    for issue_key in your_issues:
        try:
            issue = jira_tools.jira_client.issue(issue_key)
            found_issues.append({
                "key": issue.key,
                "summary": issue.fields.summary[:50] + "...",
                "status": issue.fields.status.name,
                "assignee": getattr(issue.fields.assignee, 'displayName', 'Unassigned') if issue.fields.assignee else 'Unassigned'
            })
            print(f"✅ Found {issue_key}: {issue.fields.summary[:40]}...")
        except Exception as e:
            print(f"❌ Cannot access {issue_key}: {e}")
    
    if found_issues:
        print(f"\n🎉 SUCCESS: Found {len(found_issues)}/{len(your_issues)} of your issues!")
    else:
        print(f"\n⚠️  WARNING: Could not access any of your specific issues")
        print("   This might be normal if they're in a different project or restricted")
    
    # Test 5: Our Tool Function
    print("\n🔧 TEST 5: Our jira_get_issues_by_user Tool")
    print("-" * 30)
    
    try:
        executor = ToolExecutor(config)
        app_state = AppState()
        
        # Test with different queries
        test_cases = [
            {"status_category": "in progress", "max_results": 5},
            {"status_category": "to do", "max_results": 5},
        ]
        
        total_found = 0
        for i, params in enumerate(test_cases, 1):
            tool_input = {"user_email": user_email, **params}
            
            result = await executor.execute_tool(
                tool_name="jira_get_issues_by_user",
                tool_input=tool_input,
                app_state=app_state
            )
            
            if isinstance(result, dict) and 'data' in result:
                issues = result['data']
                total_found += len(issues)
                print(f"  Query {i}: Found {len(issues)} issues ({params['status_category']})")
                
                # Show first issue if found
                if issues:
                    first_issue = issues[0]
                    print(f"    Example: {first_issue.get('key')} - {first_issue.get('summary', '')[:40]}...")
        
        if total_found > 0:
            print(f"✅ PASSED: Tool found {total_found} total issues")
        else:
            print("⚠️  Tool found 0 issues - might need different query parameters")
            
    except Exception as e:
        print(f"❌ FAILED: Tool execution error - {e}")
        import traceback
        traceback.print_exc()
    
    # Test 6: Broader Search
    print("\n🔍 TEST 6: Broader Issue Search")
    print("-" * 30)
    try:
        # Try to find ANY issues you're involved with
        broad_queries = [
            "assignee = currentUser()",
            "reporter = currentUser()",
            f"assignee = '{user_email}'",
            "assignee = currentUser() OR reporter = currentUser()",
        ]
        
        for query in broad_queries:
            try:
                issues = jira_tools.jira_client.search_issues(query, maxResults=3)
                if issues:
                    print(f"✅ '{query}' → Found {len(issues)} issues")
                    break
                else:
                    print(f"⚪ '{query}' → 0 issues")
            except Exception as e:
                print(f"❌ '{query}' → Error: {e}")
                
    except Exception as e:
        print(f"❌ Broader search failed: {e}")
    
    print("\n" + "=" * 60)
    print("🏁 TEST COMPLETE")
    print("=" * 60)
    
    if found_issues:
        print("🎉 SUCCESS: New token works! You can access your issues.")
        print(f"   Found your specific issues: {[i['key'] for i in found_issues]}")
    else:
        print("⚠️  PARTIAL: Token works but may need query adjustments.")
        print("   The tool connects and authenticates successfully.")
    
    print("\nNext steps:")
    print("1. If you see your specific issues above → Tool is working perfectly! ✅")
    print("2. If you see 0 issues → May need to adjust JQL queries in the tool")
    print("3. If you see auth errors → Token may need additional scopes")

if __name__ == "__main__":
    asyncio.run(test_new_token()) 