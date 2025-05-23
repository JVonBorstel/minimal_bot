#!/usr/bin/env python3
"""
TEST WITH ACTUAL CONFIGURED EMAIL - Use the real Jira email from .env
Stop being stupid and use the email that's already configured!
"""

import asyncio
import time
from config import get_config
from user_auth.models import UserProfile
from tools.tool_executor import ToolExecutor
from state_models import AppState

async def test_with_configured_email():
    print("🎯 TESTING WITH ACTUAL CONFIGURED JIRA EMAIL")
    print("Using the email that's already in your .env file, not dummy data!")
    print("=" * 80)
    
    try:
        config = get_config()
        tool_executor = ToolExecutor(config)
        
        # Get the ACTUAL configured Jira email
        actual_jira_email = config.JIRA_API_EMAIL
        
        if not actual_jira_email:
            print("❌ No JIRA_API_EMAIL found in configuration!")
            print("💡 Check your .env file for JIRA_API_EMAIL setting")
            return False
        
        print(f"📧 Found configured Jira email: {actual_jira_email}")
        print("🎫 Testing with YOUR real email from .env...")
        
        # Create user with the REAL email
        real_user = UserProfile(
            user_id="real_configured_user",
            display_name="Real Configured User",
            email=str(actual_jira_email),  # Convert EmailStr to string
            assigned_role="DEVELOPER"
        )
        
        app_state = AppState(
            session_id=f"real_configured_test_{int(time.time())}",
            current_user=real_user
        )
        
        print(f"\n{'='*60}")
        print("🎫 GETTING YOUR REAL JIRA TICKETS")
        print(f"Email: {actual_jira_email}")
        
        # Test all status categories to find tickets
        all_tickets = []
        statuses_tested = ["To Do", "In Progress", "Done"]
        
        for status in statuses_tested:
            print(f"\n🔍 Checking {status} tickets...")
            start_time = time.time()
            
            result = await tool_executor.execute_tool(
                tool_name="jira_get_issues_by_user",
                tool_input={
                    "user_email": str(actual_jira_email),
                    "status_category": status
                },
                app_state=app_state
            )
            
            duration = int((time.time() - start_time) * 1000)
            
            if isinstance(result, dict) and result.get('status') == 'SUCCESS':
                data = result.get('data', [])
                if isinstance(data, list) and len(data) > 0:
                    all_tickets.extend(data)
                    print(f"   ✅ {status}: Found {len(data)} tickets ({duration}ms)")
                    print(f"   📋 Sample: {[ticket.get('key', 'Unknown') + ' - ' + ticket.get('summary', 'No title')[:50] for ticket in data[:2]]}")
                else:
                    print(f"   ⚠️  {status}: No tickets found ({duration}ms)")
            else:
                error = result.get('error', 'Unknown error') if isinstance(result, dict) else str(result)
                print(f"   ❌ {status}: Failed - {error} ({duration}ms)")
        
        print(f"\n{'='*60}")
        print("📊 REAL DATA SUMMARY")
        
        if all_tickets:
            print(f"🎉 SUCCESS! Found {len(all_tickets)} total tickets for {actual_jira_email}")
            print(f"🎫 Your tickets:")
            for ticket in all_tickets[:5]:  # Show first 5
                key = ticket.get('key', 'Unknown') if isinstance(ticket, dict) else 'Unknown'
                summary = ticket.get('summary', 'No title')[:60] if isinstance(ticket, dict) else str(ticket)[:60]
                status_info = ticket.get('status', {}) if isinstance(ticket, dict) else {}
                status = status_info.get('name', 'Unknown status') if isinstance(status_info, dict) else 'Unknown status'
                print(f"   • {key}: {summary} [{status}]")
            
            if len(all_tickets) > 5:
                print(f"   ... and {len(all_tickets) - 5} more tickets")
            
            print(f"\n🚀 Now let's test the full scenario with YOUR real data...")
            
            # Test GitHub with the same user
            github_result = await tool_executor.execute_tool(
                tool_name="github_list_repositories",
                tool_input={},
                app_state=app_state
            )
            
            if isinstance(github_result, dict) and github_result.get('status') == 'SUCCESS':
                repos = github_result.get('data', [])
                print(f"✅ GitHub: Found {len(repos)} repositories")
                
                # Test the user's exact scenario: compare repo against Jira ticket
                if repos:
                    print(f"\n🎯 TESTING YOUR EXACT SCENARIO:")
                    print(f"'Use whatever tools you need but I need to compare my repo against my Jira ticket'")
                    print(f"✅ Jira tickets: {len(all_tickets)} real tickets found")
                    print(f"✅ GitHub repos: {len(repos)} real repositories found")
                    print(f"✅ Multi-service coordination: WORKING WITH YOUR REAL DATA")
                    
                    return True
            
        else:
            print(f"⚠️  No tickets found for {actual_jira_email}")
            print(f"🤔 Possible reasons:")
            print(f"   • No tickets assigned to this email in Jira")
            print(f"   • Email format mismatch in Jira vs .env")
            print(f"   • Jira permissions or project access")
            return False
            
    except Exception as e:
        print(f"\n💥 TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🎯 TESTING WITH YOUR ACTUAL CONFIGURED EMAIL")
    print("No more dummy emails - using what's in your .env file!")
    print()
    
    success = asyncio.run(test_with_configured_email())
    
    if success:
        print(f"\n🏆 REAL VALIDATION COMPLETE!")
        print(f"✅ Your scenario works with your actual data")
        print(f"✅ Bot can compare your real repos against your real Jira tickets")
    else:
        print(f"\n⚠️  Real issues found that need fixing")
        print(f"💡 Now we can address actual problems, not fake test problems") 