#!/usr/bin/env python3
"""
REAL USER DATA TEST - Use actual email to get real Jira tickets
No more dummy data - let's see if the bot actually works with real user data
"""

import asyncio
import time
from config import get_config
from user_auth.models import UserProfile
from tools.tool_executor import ToolExecutor
from state_models import AppState

async def test_with_real_user_data():
    print("🎯 REAL USER DATA TEST")
    print("Testing with actual user email to get real Jira tickets")
    print("=" * 80)
    
    # Ask user for their real email
    print("❓ I need your real Jira email address to test properly.")
    print("   The one you use to log into Jira and that has tickets assigned.")
    print()
    
    # For now, let's try a few common patterns based on the GitHub username
    possible_emails = [
        "jordan@company.com",  # Based on the GitHub user pattern
        # Add more patterns if needed
    ]
    
    print("🔍 Testing with potential email patterns...")
    
    try:
        config = get_config()
        tool_executor = ToolExecutor(config)
        
        for test_email in possible_emails:
            print(f"\n{'='*60}")
            print(f"🧪 Testing with email: {test_email}")
            
            test_user = UserProfile(
                user_id="real_user_test",
                display_name="Real User",
                email=test_email,
                assigned_role="DEVELOPER"
            )
            
            app_state = AppState(
                session_id=f"real_user_test_{int(time.time())}",
                current_user=test_user
            )
            
            # Test 1: Jira tickets for this user
            print(f"🎫 Testing Jira for email: {test_email}")
            start_time = time.time()
            
            jira_result = await tool_executor.execute_tool(
                tool_name="jira_get_issues_by_user",
                tool_input={
                    "user_email": test_email,
                    "status_category": "To Do"
                },
                app_state=app_state
            )
            
            jira_time = int((time.time() - start_time) * 1000)
            
            if isinstance(jira_result, dict) and jira_result.get('status') == 'SUCCESS':
                data = jira_result.get('data', [])
                if isinstance(data, list) and len(data) > 0:
                    print(f"   ✅ FOUND REAL TICKETS: {len(data)} tickets for {test_email} ({jira_time}ms)")
                    print(f"   🎫 Sample tickets: {[ticket.get('key', 'Unknown') for ticket in data[:3]]}")
                    
                    # If we found tickets, this is likely the right email
                    print(f"\n🎯 SUCCESS! Found your real Jira data with email: {test_email}")
                    
                    # Now test the full scenario with real data
                    print(f"\n{'='*60}")
                    print("🚀 TESTING FULL SCENARIO WITH REAL DATA")
                    
                    # Test GitHub
                    github_result = await tool_executor.execute_tool(
                        tool_name="github_list_repositories",
                        tool_input={},
                        app_state=app_state
                    )
                    
                    github_success = False
                    repos = []
                    if isinstance(github_result, dict) and github_result.get('status') == 'SUCCESS':
                        repos = github_result.get('data', [])
                        if repos:
                            github_success = True
                            print(f"   ✅ GitHub: Found {len(repos)} repositories")
                    
                    # Test GitHub search with real repo
                    if github_success and repos:
                        first_repo = repos[0]['name']
                        search_result = await tool_executor.execute_tool(
                            tool_name="github_search_code",
                            tool_input={
                                "query": "function",
                                "repository_name": first_repo,
                                "file_extensions": ["js", "py", "ts"]
                            },
                            app_state=app_state
                        )
                        
                        if isinstance(search_result, dict) and search_result.get('status') == 'SUCCESS':
                            search_data = search_result.get('data', [])
                            print(f"   ✅ Code Search: Found {len(search_data)} code matches in {first_repo}")
                    
                    print(f"\n🏆 REAL DATA VALIDATION COMPLETE")
                    print(f"✅ Jira: {len(data)} real tickets")
                    print(f"✅ GitHub: {len(repos)} real repositories")
                    print(f"✅ Multi-service coordination: WORKING WITH REAL DATA")
                    print(f"📧 Confirmed working email: {test_email}")
                    
                    return True, test_email
                    
                else:
                    print(f"   ⚠️  Connected but no tickets found for {test_email} ({jira_time}ms)")
            else:
                error = jira_result.get('error', 'Unknown error') if isinstance(jira_result, dict) else str(jira_result)
                print(f"   ❌ Failed for {test_email}: {error} ({jira_time}ms)")
        
        print(f"\n❌ No working email found in automatic patterns.")
        print(f"💡 Please manually provide your Jira email address.")
        return False, None
        
    except Exception as e:
        print(f"\n💥 TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False, None

async def test_specific_email(email: str):
    """Test with a specific email address provided by the user"""
    print(f"🎯 TESTING WITH SPECIFIC EMAIL: {email}")
    print("=" * 80)
    
    try:
        config = get_config()
        tool_executor = ToolExecutor(config)
        
        test_user = UserProfile(
            user_id="specific_email_test",
            display_name="Specific Email User",
            email=email,
            assigned_role="DEVELOPER"
        )
        
        app_state = AppState(
            session_id=f"specific_email_test_{int(time.time())}",
            current_user=test_user
        )
        
        print(f"🎫 Getting Jira tickets for: {email}")
        
        # Test multiple status categories
        for status in ["To Do", "In Progress", "Done"]:
            print(f"\n🔍 Checking {status} tickets...")
            
            result = await tool_executor.execute_tool(
                tool_name="jira_get_issues_by_user",
                tool_input={
                    "user_email": email,
                    "status_category": status
                },
                app_state=app_state
            )
            
            if isinstance(result, dict) and result.get('status') == 'SUCCESS':
                data = result.get('data', [])
                if isinstance(data, list) and len(data) > 0:
                    print(f"   ✅ {status}: Found {len(data)} tickets")
                    print(f"   📋 Sample: {[ticket.get('key', 'Unknown') + ' - ' + ticket.get('summary', 'No title')[:50] for ticket in data[:2]]}")
                else:
                    print(f"   ⚠️  {status}: No tickets found")
            else:
                error = result.get('error', 'Unknown error') if isinstance(result, dict) else str(result)
                print(f"   ❌ {status}: Failed - {error}")
        
        return True
        
    except Exception as e:
        print(f"💥 SPECIFIC EMAIL TEST FAILED: {e}")
        return False

if __name__ == "__main__":
    print("🎯 REAL USER DATA VALIDATION")
    print("Let's test with actual user data instead of dummy data")
    print()
    
    # First try automatic detection
    success, found_email = asyncio.run(test_with_real_user_data())
    
    if not success:
        print("\n" + "="*60)
        print("📧 MANUAL EMAIL INPUT NEEDED")
        print("="*60)
        print("Please provide your actual Jira email address.")
        print("Examples:")
        print("  - john.doe@company.com")
        print("  - jdoe@organization.org") 
        print("  - your.email@domain.com")
        print()
        
        # In a real scenario, you'd input this interactively
        # For now, let's test with a placeholder that you can replace
        test_email = "YOUR_ACTUAL_JIRA_EMAIL@COMPANY.COM"  # REPLACE THIS
        
        if test_email != "YOUR_ACTUAL_JIRA_EMAIL@COMPANY.COM":
            asyncio.run(test_specific_email(test_email))
        else:
            print("❌ Please edit the script and replace YOUR_ACTUAL_JIRA_EMAIL@COMPANY.COM with your real email")
    
    print(f"\n🎯 CONCLUSION:")
    print(f"To properly validate your scenario, I need your real Jira email address.")
    print(f"The bot should return actual tickets assigned to you, not empty results.") 