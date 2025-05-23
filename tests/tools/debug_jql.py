#!/usr/bin/env python3
"""Debug the JQL query to find why we're not getting the user's issues."""

import asyncio
from config import get_config
from tools.jira_tools import JiraTools

async def debug_jql():
    print("🔍 DEBUGGING JQL QUERY")
    print("=" * 50)
    
    config = get_config()
    jira_tools = JiraTools(config)
    
    if not jira_tools.jira_client:
        print("❌ Jira client not initialized")
        return
    
    user_email = config.get_env_value('JIRA_API_EMAIL')
    print(f"User email: {user_email}")
    
    # Test different JQL queries to find the issues
    test_queries = [
        # Original query from our tool
        f"assignee = \"{user_email}\" OR assignee = currentUser() AND reporter = \"{user_email}\"",
        
        # Simpler queries
        f"assignee = \"{user_email}\"",
        "assignee = currentUser()",
        
        # Project-specific queries (based on user's UI showing LoanMAPS)
        "project = LoanMAPS",
        f"project = LoanMAPS AND assignee = \"{user_email}\"",
        "project = LoanMAPS AND assignee = currentUser()",
        
        # Recent issues in project
        "project = LoanMAPS AND updated >= -30d ORDER BY updated DESC",
        
        # Specific issue keys from user's UI
        "key in (LM-13282, LM-13048, LM-13286, LM-13285, LM-13284, LM-13283)",
    ]
    
    for i, jql in enumerate(test_queries, 1):
        print(f"\n--- Query {i}: {jql} ---")
        try:
            issues = jira_tools.jira_client.search_issues(jql, maxResults=5)
            print(f"✅ Found {len(issues)} issues")
            
            for j, issue in enumerate(issues[:3], 1):
                print(f"  Issue {j}: {issue.key} - {issue.fields.summary[:50]}...")
                print(f"    Status: {issue.fields.status.name}")
                print(f"    Assignee: {getattr(issue.fields.assignee, 'displayName', None) if issue.fields.assignee else None}")
                
        except Exception as e:
            print(f"❌ Query failed: {e}")
    
    print(f"\n--- CURRENT USER INFO ---")
    try:
        current_user = jira_tools.jira_client.current_user()
        user_info = jira_tools.jira_client.user(current_user)
        print(f"Current user: {current_user}")
        print(f"Display name: {user_info.displayName}")
        print(f"Email: {user_info.emailAddress}")
        print(f"Account type: {getattr(user_info, 'accountType', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed to get user info: {e}")

if __name__ == "__main__":
    asyncio.run(debug_jql()) 