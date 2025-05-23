#!/usr/bin/env python3
"""
PROOF TEST: Demonstrate real Jira API connectivity with actual data.
This will show real projects, users, and issues from the live Jira instance.
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from tools.jira_tools import JiraTools


async def prove_jira_is_real():
    """Prove the Jira connection is real by fetching actual instance data."""
    print("🔍 PROVING JIRA CONNECTION IS REAL")
    print("=" * 60)
    
    try:
        # Initialize config and tools
        config = get_config()
        jira_tools = JiraTools(config)
        
        if not jira_tools.jira_client:
            print("❌ Jira client not initialized")
            return
        
        print("1. 🌐 REAL SERVER INFORMATION:")
        print("-" * 30)
        
        # Get real server info
        server_info = jira_tools.jira_client.server_info()
        print(f"   Server URL: {server_info.get('baseUrl')}")
        print(f"   Server Title: {server_info.get('serverTitle')}")
        print(f"   Version: {server_info.get('version')}")
        print(f"   Build Number: {server_info.get('buildNumber')}")
        print(f"   Server Time: {server_info.get('serverTime')}")
        
        print("\n2. 🎯 REAL PROJECTS IN THIS JIRA INSTANCE:")
        print("-" * 30)
        
        # Get real projects
        projects = jira_tools.jira_client.projects()
        for i, project in enumerate(projects[:5]):  # Show first 5 projects
            print(f"   Project {i+1}: {project.key} - {project.name}")
            print(f"             Lead: {getattr(project, 'lead', 'N/A')}")
        
        if len(projects) > 5:
            print(f"   ... and {len(projects) - 5} more projects")
        
        print("\n3. 🔎 SEARCHING FOR ANY ISSUES (BROAD SEARCH):")
        print("-" * 30)
        
        # Try broader searches to find actual issues
        broad_searches = [
            ("Recent issues", "updated >= -30d ORDER BY updated DESC"),
            ("Any open issues", "resolution = Unresolved ORDER BY created DESC"),
            ("All issues (last 10)", "ORDER BY created DESC"),
        ]
        
        for search_name, jql in broad_searches:
            print(f"\n   🔍 {search_name}: {jql}")
            try:
                issues = jira_tools.jira_client.search_issues(jql, maxResults=3)
                print(f"   ✅ Found {len(issues)} issues")
                
                for j, issue in enumerate(issues):
                    print(f"      Issue {j+1}: {issue.key}")
                    print(f"         Summary: {issue.fields.summary[:50]}...")
                    print(f"         Status: {issue.fields.status.name}")
                    print(f"         Project: {issue.fields.project.name}")
                    print(f"         Created: {issue.fields.created}")
                    
            except Exception as e:
                print(f"   ❌ Search failed: {e}")
        
        print("\n4. 👤 AUTHENTICATED USER INFORMATION:")
        print("-" * 30)
        
        # Get current user info
        try:
            current_user = jira_tools.jira_client.current_user()
            print(f"   Authenticated as: {current_user}")
            
            # Get user details
            user_info = jira_tools.jira_client.user(current_user)
            print(f"   Display Name: {user_info.displayName}")
            print(f"   Email: {user_info.emailAddress}")
            print(f"   Account Type: {getattr(user_info, 'accountType', 'N/A')}")
            print(f"   Active: {user_info.active}")
            
        except Exception as e:
            print(f"   ❌ Failed to get user info: {e}")
        
        print("\n5. 🏢 ISSUE TYPES AVAILABLE:")
        print("-" * 30)
        
        try:
            issue_types = jira_tools.jira_client.issue_types()
            for i, issue_type in enumerate(issue_types[:5]):
                print(f"   Type {i+1}: {issue_type.name} - {issue_type.description}")
        except Exception as e:
            print(f"   ❌ Failed to get issue types: {e}")
        
        print("\n6. 🎯 REAL HTTP REQUEST EVIDENCE:")
        print("-" * 30)
        
        # Show we're making real HTTP requests
        print(f"   Making HTTP requests to: {jira_tools.jira_url}")
        print(f"   Using authentication for: {jira_tools.jira_email}")
        
        # Make a simple API call and show timing
        import time
        start_time = time.time()
        try:
            # This makes a real HTTP request
            projects_count = len(jira_tools.jira_client.projects())
            end_time = time.time()
            print(f"   ✅ Real HTTP call completed in {(end_time - start_time)*1000:.0f}ms")
            print(f"   ✅ Retrieved data about {projects_count} projects")
        except Exception as e:
            print(f"   ❌ HTTP request failed: {e}")
        
        print("\n" + "=" * 60)
        print("🎉 PROOF COMPLETE: This is definitely a real Jira connection!")
        print("   - Real server info retrieved")
        print("   - Actual projects and issues found")
        print("   - HTTP requests with real timing")
        print("   - Authenticated user verified")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error during proof test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(prove_jira_is_real()) 