#!/usr/bin/env python3
"""
Debug script focused on Jira permissions and authentication methods.
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA
import requests
from requests.auth import HTTPBasicAuth

# Load environment variables
load_dotenv()

JIRA_URL = os.getenv('JIRA_API_URL')
JIRA_EMAIL = os.getenv('JIRA_API_EMAIL') 
JIRA_TOKEN = os.getenv('JIRA_API_TOKEN')

print(f"🔍 JIRA PERMISSIONS DEBUG")
print(f"📍 URL: {JIRA_URL}")
print(f"👤 Email: {JIRA_EMAIL}")
print(f"🔑 Token: {JIRA_TOKEN[:8]}..." if JIRA_TOKEN else "❌ NO TOKEN")
print("=" * 60)

# Test 1: Raw REST API call
print("🧪 TEST 1: Raw REST API Authentication")
try:
    # Direct REST API call to test basic auth
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
    response = requests.get(f"{JIRA_URL}/rest/api/3/myself", auth=auth, timeout=10)
    
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        user_data = response.json()
        print(f"   ✅ REST API Success!")
        print(f"   👤 Account ID: {user_data.get('accountId')}")
        print(f"   📧 Email: {user_data.get('emailAddress')}")
        print(f"   🏷️  Display Name: {user_data.get('displayName')}")
    else:
        print(f"   ❌ REST API Failed: {response.text}")
        print(f"   Headers: {dict(response.headers)}")
except Exception as e:
    print(f"   ❌ Raw REST Error: {e}")

print()

# Test 2: Try different JIRA API versions
print("🧪 TEST 2: Different API Versions")
api_versions = ['3', 'latest', '2']
for version in api_versions:
    try:
        options = {'server': JIRA_URL, 'verify': True, 'rest_api_version': version}
        jira_test = JIRA(options=options, basic_auth=(JIRA_EMAIL, JIRA_TOKEN), timeout=10)
        current_user = jira_test.current_user()
        print(f"   ✅ API Version {version}: Success - User: {current_user}")
        break  # If this works, use this version
    except Exception as e:
        print(f"   ❌ API Version {version}: {str(e)[:100]}...")

print()

# Test 3: Check if it's a permission vs authentication issue
print("🧪 TEST 3: Permission Level Testing")
try:
    # Use the working connection (basic server info works)
    options = {'server': JIRA_URL, 'verify': True, 'rest_api_version': 'latest'}
    jira = JIRA(options=options, basic_auth=(JIRA_EMAIL, JIRA_TOKEN), timeout=10)
    
    # Test different endpoints to see what's accessible
    tests = [
        ("Server Info", lambda: jira.server_info()),
        ("Current User", lambda: jira.current_user()),
        ("Search All Issues", lambda: jira.search_issues('', maxResults=1)),
        ("Get Projects", lambda: jira.projects()),
        ("Search Recent", lambda: jira.search_issues('updated >= -7d', maxResults=5)),
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            print(f"   ✅ {test_name}: Success")
            if test_name == "Search Recent" and result:
                print(f"      Found {len(result)} recent issues")
                for issue in result[:2]:
                    assignee = issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned"
                    print(f"      - {issue.key}: {issue.fields.summary[:50]}... (Assignee: {assignee})")
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                print(f"   ❌ {test_name}: Authentication failed")
            elif "403" in error_msg:
                print(f"   ❌ {test_name}: Permission denied")
            else:
                print(f"   ❌ {test_name}: {error_msg[:100]}...")

except Exception as e:
    print(f"   ❌ Connection failed: {e}")

print()

# Test 4: Check specific user/email scenarios
print("🧪 TEST 4: User/Email Matching")
try:
    # Try different ways to reference the user
    options = {'server': JIRA_URL, 'verify': True, 'rest_api_version': 'latest'}
    jira = JIRA(options=options, basic_auth=(JIRA_EMAIL, JIRA_TOKEN), timeout=10)
    
    # Get all users matching the email (if we have permission)
    try:
        # Different ways to search for users
        search_queries = [
            f'assignee = "{JIRA_EMAIL}"',
            f'assignee in ("{JIRA_EMAIL}")',
            'assignee = currentUser()',
            'assignee in (currentUser())',
        ]
        
        for query in search_queries:
            try:
                issues = jira.search_issues(query, maxResults=5)
                print(f"   ✅ Query '{query}': {len(issues)} issues")
                if issues:
                    sample = issues[0]
                    assignee_email = getattr(sample.fields.assignee, 'emailAddress', 'No email') if sample.fields.assignee else "No assignee"
                    print(f"      Sample assignee email: {assignee_email}")
            except Exception as e:
                print(f"   ❌ Query '{query}': {str(e)[:80]}...")
                
    except Exception as e:
        print(f"   ❌ User search failed: {e}")

except Exception as e:
    print(f"   ❌ User test failed: {e}")

print()
print("=" * 60)
print("🎯 DIAGNOSIS:")
print("1. If REST API works but JIRA library fails → Library/version issue")
print("2. If basic queries fail but server info works → Permission issue")
print("3. If no recent issues found → Empty project or restricted access")
print("4. Check if your email matches exactly what's in Jira user accounts")
print("5. Verify your API token has 'Browse projects' and 'View issues' permissions") 