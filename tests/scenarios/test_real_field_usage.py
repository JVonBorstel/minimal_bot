#!/usr/bin/env python3
"""
REAL FIELD USAGE TEST - Does this bot actually work for real users?

This is NOT about fancy test scenarios. This is about:
"If I deploy this bot today, can someone actually use it?"
"""

import asyncio
import time
from typing import Dict, Any

from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from user_auth.db_manager import save_user_profile
from bot_core.my_bot import MyBot

class RealFieldUsageTest:
    """Test if the bot actually works for real users doing real work."""
    
    def __init__(self):
        self.config = get_config()
        self.bot = MyBot(self.config)
        
    def create_real_user(self) -> UserProfile:
        """Create a realistic user."""
        user_data = {
            "user_id": "real_user_test",
            "display_name": "Jordan Developer",
            "email": "jordan@company.com", 
            "assigned_role": "DEVELOPER",
            "profile_data": {"team": "Backend", "department": "Engineering"}
        }
        
        save_user_profile(user_data)
        return UserProfile(**user_data)
        
    async def test_real_conversation(self, user_message: str, user: UserProfile) -> Dict[str, Any]:
        """Test a real conversation like someone would actually have."""
        print(f"\n👤 USER: {user_message}")
        start_time = time.time()
        
        try:
            # This is what happens when someone sends a message to the bot
            result = await self.bot.process_user_message(
                user_message=user_message,
                user_id=user.user_id,
                conversation_id=f"real_test_{int(time.time())}"
            )
            
            end_time = time.time()
            duration = int((end_time - start_time) * 1000)
            
            print(f"🤖 BOT: {result}")
            print(f"⏱️  Response time: {duration}ms")
            
            return {
                "user_message": user_message,
                "bot_response": result,
                "duration_ms": duration,
                "success": True
            }
            
        except Exception as e:
            end_time = time.time()
            duration = int((end_time - start_time) * 1000)
            
            print(f"💥 BOT ERROR: {e}")
            print(f"⏱️  Failed after: {duration}ms")
            
            return {
                "user_message": user_message,
                "error": str(e),
                "duration_ms": duration,
                "success": False
            }
            
    async def run_real_field_test(self):
        """Run real field usage scenarios."""
        print("🚀 TESTING REAL FIELD USAGE")
        print("=" * 50)
        print("Testing: Can someone actually use this bot for work?")
        print("=" * 50)
        
        # Create a real user
        user = self.create_real_user()
        print(f"✅ Created user: {user.display_name}")
        
        # Real conversations someone might have
        real_conversations = [
            "Hi, what can you help me with?",
            "Show me my Jira tickets",
            "List my GitHub repositories", 
            "Search for authentication code in GitHub",
            "Help me find deployment issues",
            "What are the latest React best practices?"
        ]
        
        results = []
        for conversation in real_conversations:
            result = await self.test_real_conversation(conversation, user)
            results.append(result)
            await asyncio.sleep(1)  # Real users pause between messages
            
        # Analyze results
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        print(f"\n📊 REAL FIELD USAGE RESULTS:")
        print(f"   Total conversations: {len(results)}")
        print(f"   Successful: {len(successful)}")
        print(f"   Failed: {len(failed)}")
        
        if len(successful) > 0:
            avg_response_time = sum(r["duration_ms"] for r in successful) / len(successful)
            print(f"   Average response time: {avg_response_time:.0f}ms")
            
        print(f"\n🎯 FIELD READINESS:")
        if len(failed) == 0:
            print("✅ PRODUCTION READY - All conversations successful")
        elif len(successful) >= len(failed) * 2:
            print("⚠️  MOSTLY READY - Some issues but mostly works")
        else:
            print("❌ NOT READY - Too many failures for production")
            
        for failure in failed:
            print(f"   💥 FAILED: '{failure['user_message']}' -> {failure['error']}")
            
        return len(failed) == 0

async def main():
    """Test if the bot actually works in the field."""
    tester = RealFieldUsageTest()
    success = await tester.run_real_field_test()
    
    if success:
        print("\n🏆 REAL FIELD TEST: PASSED")
        print("✅ Bot works for real users doing real work")
    else:
        print("\n💥 REAL FIELD TEST: FAILED") 
        print("❌ Bot is NOT ready for real users")

if __name__ == "__main__":
    asyncio.run(main()) 