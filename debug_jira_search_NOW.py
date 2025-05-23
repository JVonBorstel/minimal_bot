#!/usr/bin/env python3
"""
EMERGENCY Jira diagnostic - find out why we can't see tickets that exist
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from tools.jira_tools import JiraTools
from state_models import AppState

async def emergency_jira_debug():
    """Find out exactly what's wrong with Jira search"""
    print("🚨 EMERGENCY JIRA DIAGNOSTIC")
    print("=" * 50)
    
    config = get_config()
    jira_tools = JiraTools(config)
    app_state = AppState()
    
    if not jira_tools.jira_client:
        print("❌ No Jira client available")
        return
    
    client = jira_tools.jira_client
    
    # 1. Check current user info
    print("\n🔍 CHECKING CURRENT USER:")
    try:
        current_user = client.current_user()
        print(f"Current user account ID: {current_user}")
        
        user_details = client.user(current_user)
        print(f"Display name: {user_details.displayName}")
        print(f"Email: {getattr(user_details, 'emailAddress', 'Not available')}")
        print(f"Account ID: {user_details.accountId}")
    except Exception as e:
        print(f"Error getting current user: {e}")
    
    # 2. Search for ANY tickets in the system
    print("\n🔍 CHECKING FOR ANY TICKETS:")
    try:
        all_issues = client.search_issues("order by created DESC", maxResults=5)
        print(f"Total tickets found in system: {len(all_issues)}")
        for issue in all_issues:
            assignee_name = getattr(issue.fields.assignee, 'displayName', 'Unassigned') if issue.fields.assignee else 'Unassigned'
            assignee_email = getattr(issue.fields.assignee, 'emailAddress', 'No email') if issue.fields.assignee else 'No email'
            print(f"- {issue.key}: {issue.fields.summary[:50]}...")
            print(f"  Assignee: {assignee_name} ({assignee_email})")
    except Exception as e:
        print(f"Error searching for any tickets: {e}")
    
    # 3. Try different search approaches
    print("\n🔍 TRYING DIFFERENT SEARCH METHODS:")
    
    search_queries = [
        "assignee = currentUser()",
        "reporter = currentUser()",
        "assignee = currentUser() OR reporter = currentUser()",
        'assignee = "jvonborstel@take3tech.com"',
        'reporter = "jvonborstel@take3tech.com"',
        'assignee = "jvonborstel@take3tech.com" OR reporter = "jvonborstel@take3tech.com"',
        "assignee in (currentUser())",
        "project in (projectsWhereUserHasPermission('Browse'))",
    ]
    
    for i, query in enumerate(search_queries, 1):
        try:
            print(f"\n{i}. Testing: {query}")
            issues = client.search_issues(query, maxResults=5)
            print(f"   Results: {len(issues)} tickets found")
            for issue in issues:
                print(f"   - {issue.key}: {issue.fields.summary[:40]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # 4. Check projects user has access to
    print("\n🔍 CHECKING ACCESSIBLE PROJECTS:")
    try:
        projects = client.projects()
        print(f"Accessible projects: {len(projects)}")
        for project in projects[:5]:  # Show first 5
            print(f"- {project.key}: {project.name}")
    except Exception as e:
        print(f"Error getting projects: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 DIAGNOSIS COMPLETE")

if __name__ == "__main__":
    asyncio.run(emergency_jira_debug()) 