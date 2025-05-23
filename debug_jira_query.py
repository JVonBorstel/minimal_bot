#!/usr/bin/env python3
"""
Debug script to test Jira queries and find out why tickets aren't showing up.
Run this to see exactly what the bot is doing when searching for tickets.
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA

# Load environment variables
load_dotenv()

# Get Jira credentials
JIRA_URL = os.getenv('JIRA_API_URL')
JIRA_EMAIL = os.getenv('JIRA_API_EMAIL') 
JIRA_TOKEN = os.getenv('JIRA_API_TOKEN')

print(f"🔍 JIRA DEBUG - Testing connection and queries")
print(f"📍 Jira URL: {JIRA_URL}")
print(f"👤 Email being used: {JIRA_EMAIL}")
print("=" * 60)

try:
    # Connect to Jira
    options = {'server': JIRA_URL, 'verify': True, 'rest_api_version': 'latest'}
    jira = JIRA(options=options, basic_auth=(JIRA_EMAIL, JIRA_TOKEN), timeout=30)
    
    print("✅ Successfully connected to Jira!")
    server_info = jira.server_info()
    print(f"📊 Server: {server_info.get('serverTitle', 'Unknown')}")
    print(f"🔗 Base URL: {server_info.get('baseUrl', JIRA_URL)}")
    print()
    
    # Test 1: Current user info
    print("🧑‍💻 CURRENT USER INFO:")
    try:
        current_user = jira.current_user()
        print(f"   Key: {current_user}")
        
        # Get detailed user info
        user_details = jira.user(current_user)
        print(f"   Display Name: {user_details.displayName}")
        print(f"   Email: {user_details.emailAddress}")
        print(f"   Account ID: {user_details.accountId}")
    except Exception as e:
        print(f"   ❌ Error getting current user: {e}")
    print()
    
    # Test 2: The exact query the bot uses
    print("🔍 TESTING BOT'S EXACT QUERY:")
    bot_query = f'assignee = "{JIRA_EMAIL}" OR assignee = currentUser() AND reporter = "{JIRA_EMAIL}"'
    print(f"   JQL: {bot_query}")
    
    try:
        issues = jira.search_issues(bot_query, maxResults=50)
        print(f"   ✅ Found {len(issues)} issues with bot's query")
        for issue in issues[:5]:  # Show first 5
            print(f"      - {issue.key}: {issue.fields.summary}")
    except Exception as e:
        print(f"   ❌ Bot's query failed: {e}")
    print()
    
    # Test 3: Simpler queries to debug
    test_queries = [
        f'assignee = "{JIRA_EMAIL}"',
        f'assignee = currentUser()',
        f'reporter = "{JIRA_EMAIL}"',
        f'assignee in (currentUser())',
        'assignee = currentUser() AND status != "Closed"',
        'assignee = currentUser() ORDER BY updated DESC'
    ]
    
    print("🧪 TESTING ALTERNATIVE QUERIES:")
    for query in test_queries:
        try:
            issues = jira.search_issues(query, maxResults=10)
            print(f"   ✅ '{query}' → {len(issues)} issues")
            if len(issues) > 0:
                print(f"      Sample: {issues[0].key} - {issues[0].fields.summary}")
        except Exception as e:
            print(f"   ❌ '{query}' → Error: {e}")
    print()
    
    # Test 4: Check if there are ANY tickets at all
    print("📋 CHECKING FOR ANY TICKETS:")
    try:
        all_recent = jira.search_issues('updated >= -30d ORDER BY updated DESC', maxResults=10)
        print(f"   📊 Found {len(all_recent)} tickets updated in last 30 days")
        for issue in all_recent[:3]:
            assignee_name = issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned"
            assignee_email = getattr(issue.fields.assignee, 'emailAddress', 'No email') if issue.fields.assignee else "No email"
            print(f"      - {issue.key}: {issue.fields.summary}")
            print(f"        Assignee: {assignee_name} ({assignee_email})")
    except Exception as e:
        print(f"   ❌ Error checking recent tickets: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 NEXT STEPS:")
    print("1. Check if any of the alternative queries returned tickets")
    print("2. Compare the assignee emails shown above with your config email")
    print("3. If tickets exist but queries fail, there might be a permission issue")
    print("4. If assignee emails differ, update JIRA_API_EMAIL in your .env file")

except Exception as e:
    print(f"❌ Failed to connect to Jira: {e}")
    print("\n🔧 TROUBLESHOOTING:")
    print("1. Check your JIRA_API_URL, JIRA_API_EMAIL, and JIRA_API_TOKEN in .env")
    print("2. Verify your API token is valid and has the right permissions")
    print("3. Check if your Jira instance requires specific authentication") 