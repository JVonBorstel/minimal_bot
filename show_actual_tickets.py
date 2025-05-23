#!/usr/bin/env python3
"""
Show actual tickets and their assignees to identify email format issues.
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

print(f"🎫 SHOWING ACTUAL JIRA TICKETS")
print(f"📍 URL: {JIRA_URL}")
print(f"👤 Looking for tickets assigned to: {JIRA_EMAIL}")
print("=" * 80)

try:
    # Connect to Jira (we know this works from previous tests)
    options = {'server': JIRA_URL, 'verify': True, 'rest_api_version': 'latest'}
    jira = JIRA(options=options, basic_auth=(JIRA_EMAIL, JIRA_TOKEN), timeout=30)
    
    print("✅ Connected to Jira successfully!")
    print()
    
    # Get recent tickets (we know this works)
    print("📋 RECENT TICKETS (Last 30 days):")
    try:
        recent_issues = jira.search_issues(
            'updated >= -30d ORDER BY updated DESC', 
            maxResults=20,
            fields='summary,assignee,reporter,status,updated,project'
        )
        
        if recent_issues:
            print(f"   Found {len(recent_issues)} recent tickets")
            print()
            
            # Track unique assignee emails
            assignee_emails = set()
            your_tickets = []
            
            for i, issue in enumerate(recent_issues, 1):
                # Get assignee info
                if issue.fields.assignee:
                    assignee_name = issue.fields.assignee.displayName
                    assignee_email = getattr(issue.fields.assignee, 'emailAddress', 'No email available')
                    assignee_account_id = getattr(issue.fields.assignee, 'accountId', 'No account ID')
                    assignee_emails.add(assignee_email)
                    
                    # Check if this might be your ticket
                    if JIRA_EMAIL.lower() in assignee_email.lower() or assignee_email.lower() in JIRA_EMAIL.lower():
                        your_tickets.append(issue)
                else:
                    assignee_name = "❌ Unassigned"
                    assignee_email = "❌ Unassigned"
                    assignee_account_id = "❌ Unassigned"
                
                # Get reporter info
                if issue.fields.reporter:
                    reporter_name = issue.fields.reporter.displayName
                    reporter_email = getattr(issue.fields.reporter, 'emailAddress', 'No email available')
                else:
                    reporter_name = "❌ No reporter"
                    reporter_email = "❌ No reporter"
                
                print(f"{i:2}. {issue.key}: {issue.fields.summary[:60]}...")
                print(f"    📊 Status: {issue.fields.status.name}")
                print(f"    👤 Assignee: {assignee_name} ({assignee_email})")
                print(f"    📝 Reporter: {reporter_name} ({reporter_email})")
                print(f"    🏷️  Project: {issue.fields.project.name}")
                print(f"    🕒 Updated: {issue.fields.updated[:10]}")
                print()
            
            # Summary of findings
            print("=" * 80)
            print("🔍 ANALYSIS:")
            print()
            
            if your_tickets:
                print(f"✅ FOUND {len(your_tickets)} TICKETS THAT MIGHT BE YOURS:")
                for ticket in your_tickets:
                    assignee_email = getattr(ticket.fields.assignee, 'emailAddress', 'No email')
                    print(f"   • {ticket.key}: {assignee_email}")
                print()
            
            print(f"📧 UNIQUE ASSIGNEE EMAILS FOUND ({len(assignee_emails)}):")
            for email in sorted(assignee_emails):
                if email != "No email available":
                    match_indicator = "👈 THIS MIGHT BE YOU!" if JIRA_EMAIL.lower() in email.lower() else ""
                    print(f"   • {email} {match_indicator}")
            print()
            
            print(f"🔍 EMAIL COMPARISON:")
            print(f"   Your config email: '{JIRA_EMAIL}'")
            
            # Check for common variations
            potential_matches = [email for email in assignee_emails 
                               if JIRA_EMAIL.lower().replace('@', '').replace('.', '') in 
                                  email.lower().replace('@', '').replace('.', '')]
            
            if potential_matches:
                print(f"   🎯 Potential matches found:")
                for match in potential_matches:
                    print(f"      → '{match}'")
                print()
                print("💡 SOLUTION: Update your .env file with the correct email:")
                print(f"   JIRA_API_EMAIL={potential_matches[0]}")
            else:
                print(f"   ❌ No close matches found in assignee emails")
                print(f"   💡 Check if your tickets are assigned to a different email variant")
        
        else:
            print("   ❌ No recent tickets found")
            print("   💡 Either no tickets exist, or you don't have permission to see them")
    
    except Exception as e:
        print(f"   ❌ Error getting recent tickets: {e}")

    print()
    print("=" * 80)
    print("🎯 NEXT STEPS:")
    print("1. Look for your email in the list above")
    print("2. If you see a close match, update JIRA_API_EMAIL in .env")
    print("3. If no tickets shown, check with your Jira admin about permissions")
    print("4. Try creating a test ticket assigned to yourself")

except Exception as e:
    print(f"❌ Failed to connect: {e}") 