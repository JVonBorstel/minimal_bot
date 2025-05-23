#!/usr/bin/env python3
"""
EMERGENCY TEST - Test Jira with currentUser() fix
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from tools.tool_executor import ToolExecutor
from state_models import AppState, UserProfile

async def emergency_test():
    print("🚨 EMERGENCY JIRA TEST WITH CURRENTUSER() FIX")
    print("=" * 55)
    
    config = get_config()
    tool_executor = ToolExecutor(config)
    
    app_state = AppState()
    app_state.current_user = UserProfile(
        user_id="test_user",
        email="jvonborstel@take3tech.com",
        display_name="Test User"
    )
    
    print("🎫 Testing Jira with currentUser() fix...")
    
    result = await tool_executor.execute_tool(
        "jira_get_issues_by_user",
        {"user_email": "jvonborstel@take3tech.com"},
        app_state=app_state
    )
    
    print(f"📊 RESULT: {len(result) if isinstance(result, list) else 'Error'} tickets found")
    
    if isinstance(result, list) and result:
        print("\n✅ SUCCESS! Found tickets:")
        for i, ticket in enumerate(result[:5], 1):
            print(f"{i}. {ticket.get('key', 'Unknown')}: {ticket.get('summary', 'No summary')}")
    elif isinstance(result, list):
        print("\n⚠️  Still no tickets found - need more debugging")
    else:
        print(f"\n❌ Error: {result}")
    
    print("\n" + "=" * 55)

if __name__ == "__main__":
    asyncio.run(emergency_test()) 