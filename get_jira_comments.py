#!/usr/bin/env python3
"""
Get the last comment from a Jira ticket
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from state_models import AppState, Message, TextPart
from user_auth.models import UserProfile
from tools.jira_tools import JiraTools

async def get_last_comment(ticket_key="LM-13048"):
    """Get the last comment from the specified Jira ticket"""
    config = Config()
    jira_tools = JiraTools(config)
    
    # Create mock app state
    user = UserProfile(
        user_id='jvonborstel',
        email='jvonborstel@take3tech.com',
        display_name='JVonBorstel'
    )
    app_state = AppState(
        session_id='test',
        current_user=user,
        messages=[]
    )
    
    print(f'🎫 Getting comments from {ticket_key}...')
    print(f'📧 User: {config.get_env_value("JIRA_API_EMAIL")}')
    
    try:
        # Try to access the Jira client directly
        jira_client = jira_tools._get_jira_client(app_state)
        if not jira_client:
            print('❌ No Jira client available')
            return
            
        print(f'✅ Jira client connected')
        
        # Get the issue and its comments
        print(f'🔍 Fetching issue {ticket_key} with comments...')
        issue = jira_client.issue(ticket_key, expand='comments')
        
        print(f'📝 Issue: {issue.fields.summary}')
        print(f'📊 Status: {issue.fields.status.name}')
        
        comments = issue.fields.comment.comments
        print(f'💬 Found {len(comments)} total comments')
        
        if comments:
            # Get the last comment (most recent)
            last_comment = comments[-1]
            print(f'\n🕐 LAST COMMENT:')
            print(f'👤 Author: {last_comment.author.displayName} ({last_comment.author.emailAddress})')
            print(f'📅 Date: {last_comment.created}')
            print(f'🆔 ID: {last_comment.id}')
            print(f'\n💬 Comment Body:')
            print('-' * 50)
            print(last_comment.body)
            print('-' * 50)
            
            # If there are multiple comments, show a few recent ones
            if len(comments) > 1:
                print(f'\n📋 Recent Comments ({min(3, len(comments))} most recent):')
                for i, comment in enumerate(comments[-3:], 1):
                    print(f'  {i}. {comment.author.displayName} ({comment.created[:10]}): {comment.body[:100]}...')
        else:
            print('📭 No comments found on this ticket')
            
    except Exception as e:
        print(f'❌ Error getting comments: {e}')
        print(f'🔍 This is likely due to the token scope issue we identified')

if __name__ == "__main__":
    asyncio.run(get_last_comment()) 