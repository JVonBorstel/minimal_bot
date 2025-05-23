#!/usr/bin/env python3
"""
Find ANY tickets in Jira to see what's available.
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA

# Load environment variables
load_dotenv()

JIRA_URL = os.getenv('JIRA_API_URL')
JIRA_EMAIL = os.getenv('JIRA_API_EMAIL') 
JIRA_TOKEN = os.getenv('JIRA_API_TOKEN')

print(f"🔍 SEARCHING FOR ANY JIRA TICKETS")
print(f"📍 URL: {JIRA_URL}")
print("=" * 80)

try:
    # Connect to Jira
    options = {'server': JIRA_URL, 'verify': True, 'rest_api_version': 'latest'}
    jira = JIRA(options=options, basic_auth=(JIRA_EMAIL, JIRA_TOKEN), timeout=30)
    
    print("✅ Connected to Jira successfully!")
    print()
    
    # Try different searches to find tickets
    searches = [
        ("All tickets (any date)", "ORDER BY created DESC"),
        ("Last 90 days", "updated >= -90d ORDER BY updated DESC"),  
        ("Last 365 days", "updated >= -365d ORDER BY updated DESC"),
        ("All tickets in any status", "status in (Open, 'In Progress', Closed, Done, 'To Do') ORDER BY updated DESC"),
        ("Just get ANYTHING", "")
    ]
    
    for search_name, jql in searches:
        print(f"🔍 {search_name}:")
        try:
            issues = jira.search_issues(jql, maxResults=10)
            if issues:
                print(f"   ✅ Found {len(issues)} tickets!")
                for i, issue in enumerate(issues[:5], 1):
                    assignee = "Unassigned"
                    assignee_email = "No email"
                    
                    if issue.fields.assignee:
                        assignee = issue.fields.assignee.displayName
                        assignee_email = getattr(issue.fields.assignee, 'emailAddress', 'No email')
                    
                    print(f"   {i}. {issue.key}: {issue.fields.summary[:50]}...")
                    print(f"      Assignee: {assignee} ({assignee_email})")
                    print(f"      Status: {issue.fields.status.name}")
                    print(f"      Project: {issue.fields.project.name}")
                    
                print()
                break  # Found tickets, no need to try other searches
            else:
                print(f"   ❌ No tickets found")
        except Exception as e:
            print(f"   ❌ Search failed: {e}")
        print()
    
    # Check projects
    print("📁 AVAILABLE PROJECTS:")
    try:
        projects = jira.projects()
        if projects:
            for project in projects[:10]:  # Show first 10 projects
                print(f"   • {project.key}: {project.name}")
                
                # Try to get a few tickets from this project
                try:
                    project_issues = jira.search_issues(f'project = {project.key}', maxResults=3)
                    if project_issues:
                        print(f"     → Has {len(project_issues)} sample tickets")
                        for issue in project_issues:
                            assignee = issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned"
                            print(f"       - {issue.key}: {assignee}")
                    else:
                        print(f"     → No tickets visible")
                except:
                    print(f"     → Cannot access tickets")
        else:
            print("   ❌ No projects found")
    except Exception as e:
        print(f"   ❌ Cannot get projects: {e}")

except Exception as e:
    print(f"❌ Failed to connect: {e}")
    
print()
print("🎯 If NO tickets are found at all:")
print("1. Check with your Jira admin about your account permissions")  
print("2. Make sure you're added to the right Jira projects")
print("3. Verify your API token has 'Browse projects' permission")
print("4. Try logging into Jira web interface with the same email/password") 