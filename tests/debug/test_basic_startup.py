#!/usr/bin/env python3
"""
BASIC STARTUP TEST - Can the bot even start up?
"""

import os
import sys
import time
import asyncio
import pytest # Add pytest

# Add the root directory to Python path for imports (go up two levels from tests/debug)
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, root_dir)

@pytest.mark.asyncio
async def test_basic_startup():
    print("🔍 Testing basic bot startup...")

    try:
        print("1. Loading config...")
        from config import get_config
        config = get_config()
        print("   ✅ Config loaded")
        
        print("2. Loading tool executor...")
        from tools.tool_executor import ToolExecutor
        executor = ToolExecutor(config)
        print(f"   ✅ Tool executor loaded - {len(executor.get_available_tool_names())} tools")
        
        print("3. Loading bot core...")
        from bot_core.my_bot import MyBot
        bot = MyBot(config)
        print("   ✅ Bot core loaded")
        
        print("4. Testing simple help...")
        start = time.time()
        
        # Just try to get help - simplest possible operation
        from user_auth.models import UserProfile
        test_user = UserProfile(
            user_id="startup_test",
            display_name="Test User",
            email="test@example.com",
            assigned_role="DEVELOPER"
        )
        
        # FIXED: Properly await the async execute_tool call
        result = await executor.execute_tool("help", {}, None)
        end = time.time()
        
        print(f"   ✅ Help tool executed in {int((end-start)*1000)}ms")
        print(f"   📄 Result type: {type(result)}")
        print(f"   📄 Result preview: {str(result)[:200]}...")
        
        print("\n🎉 BASIC STARTUP: SUCCESS")
        print("✅ Bot can start up and execute basic tools")
        return True
        
    except Exception as e:
        print(f"\n💥 BASIC STARTUP: FAILED")
        print(f"❌ Error: {e}")
        print(f"📍 Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_basic_startup())
    exit(0 if success else 1) 