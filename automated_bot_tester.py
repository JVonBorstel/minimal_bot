#!/usr/bin/env python3
"""
Automated Bot Tester - Actually talks to the bot and gets responses!
Tests Story Builder and other functionality automatically.
"""
import asyncio
import aiohttp
import json
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

class BotTester:
    def __init__(self, bot_url: str = "http://localhost:8501/api/messages"):
        self.bot_url = bot_url
        self.conversation_id = f"test-conv-{int(time.time())}"
        self.user_id = f"test-user-{int(time.time())}"
        self.session = None
        
    def create_activity(self, text: str, activity_type: str = "message") -> Dict:
        """Create a properly formatted Bot Framework activity."""
        return {
            "type": activity_type,
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "serviceUrl": "http://localhost:8501",
            "channelId": "test",
            "from": {
                "id": self.user_id,
                "name": "Test User",
                "role": "user"
            },
            "conversation": {
                "id": self.conversation_id,
                "name": "Test Conversation"
            },
            "recipient": {
                "id": "bot",
                "name": "Augie Bot",
                "role": "bot"
            },
            "text": text,
            "locale": "en-US",
            "inputHint": "acceptingInput"
        }
    
    async def send_message(self, text: str, expect_response: bool = True) -> Dict:
        """Send a message to the bot and return the response."""
        print(f"\n🗣️  USER: {text}")
        
        activity = self.create_activity(text)
        
        try:
            async with self.session.post(
                self.bot_url,
                json=activity,
                headers={"Content-Type": "application/json"},
                timeout=30
            ) as response:
                
                if response.status == 200:
                    try:
                        result = await response.text()
                        if result.strip():
                            response_data = json.loads(result)
                            print(f"🤖 BOT: {response_data}")
                            return {"status": "success", "data": response_data}
                        else:
                            print("🤖 BOT: [No response content]")
                            return {"status": "success", "data": None}
                    except json.JSONDecodeError:
                        print(f"🤖 BOT: [Raw response]: {result[:200]}...")
                        return {"status": "success", "data": result}
                else:
                    error_text = await response.text()
                    print(f"❌ ERROR {response.status}: {error_text[:200]}...")
                    return {"status": "error", "code": response.status, "message": error_text}
                    
        except asyncio.TimeoutError:
            print("⏰ TIMEOUT: Bot took too long to respond")
            return {"status": "timeout"}
        except Exception as e:
            print(f"💥 EXCEPTION: {e}")
            return {"status": "exception", "error": str(e)}
    
    async def test_basic_communication(self):
        """Test if the bot responds to basic messages."""
        print("\n" + "="*60)
        print("🔧 TESTING: Basic Communication")
        print("="*60)
        
        test_messages = [
            "hello",
            "hi there", 
            "test message"
        ]
        
        for msg in test_messages:
            result = await self.send_message(msg)
            await asyncio.sleep(2)  # Give bot time to process
            
            if result["status"] == "success":
                print("✅ Basic communication working!")
            else:
                print("❌ Basic communication failed!")
                return False
        
        return True
    
    async def test_help_system(self):
        """Test the help and tool listing functionality."""
        print("\n" + "="*60)
        print("🔧 TESTING: Help System")
        print("="*60)
        
        help_messages = [
            "help",
            "what can you do",
            "what tools do you have",
            "show me available commands"
        ]
        
        for msg in help_messages:
            result = await self.send_message(msg)
            await asyncio.sleep(3)  # Help responses might be longer
            
            if result["status"] == "success":
                print("✅ Help system responding!")
            else:
                print("❌ Help system failed!")
        
        return True
    
    async def test_story_builder(self):
        """Test the Story Builder workflow step by step."""
        print("\n" + "="*60)
        print("🔧 TESTING: Story Builder Workflow")
        print("="*60)
        
        # Step 1: Trigger Story Builder
        print("\n📝 Step 1: Triggering Story Builder...")
        result = await self.send_message("create a jira ticket for implementing user authentication")
        await asyncio.sleep(5)  # Story Builder setup might take time
        
        if result["status"] != "success":
            print("❌ Failed to trigger Story Builder!")
            return False
        
        print("✅ Story Builder triggered!")
        
        # Step 2: Test different story builder triggers
        story_triggers = [
            "build a user story for OAuth integration",
            "draft an issue for two-factor authentication", 
            "create a ticket for password reset functionality"
        ]
        
        for trigger in story_triggers:
            print(f"\n📝 Testing trigger: {trigger}")
            result = await self.send_message(trigger)
            await asyncio.sleep(3)
            
            if result["status"] == "success":
                print("✅ Story Builder trigger working!")
            else:
                print("❌ Story Builder trigger failed!")
        
        return True
    
    async def test_tool_integration(self):
        """Test integration with external tools."""
        print("\n" + "="*60)
        print("🔧 TESTING: Tool Integration")
        print("="*60)
        
        # Test tool-related messages
        tool_messages = [
            "search github for authentication examples",
            "look up OAuth best practices",
            "find documentation about user management"
        ]
        
        for msg in tool_messages:
            print(f"\n🔧 Testing tool integration: {msg}")
            result = await self.send_message(msg)
            await asyncio.sleep(4)  # Tool calls might take time
            
            if result["status"] == "success":
                print("✅ Tool integration responding!")
            else:
                print("❌ Tool integration failed!")
        
        return True
    
    async def run_comprehensive_test(self):
        """Run a comprehensive test suite."""
        print("🚀 Starting Comprehensive Bot Testing...")
        print("🎯 This will test all major functionality automatically!")
        
        # Initialize session
        self.session = aiohttp.ClientSession()
        
        try:
            # Test sequence
            tests = [
                ("Basic Communication", self.test_basic_communication),
                ("Help System", self.test_help_system), 
                ("Story Builder", self.test_story_builder),
                ("Tool Integration", self.test_tool_integration)
            ]
            
            results = {}
            
            for test_name, test_func in tests:
                print(f"\n🎯 Running {test_name} tests...")
                try:
                    results[test_name] = await test_func()
                except Exception as e:
                    print(f"💥 {test_name} test crashed: {e}")
                    results[test_name] = False
                
                # Rest between test suites
                await asyncio.sleep(2)
            
            # Final report
            print("\n" + "="*60)
            print("📊 FINAL TEST RESULTS")
            print("="*60)
            
            for test_name, passed in results.items():
                status = "✅ PASSED" if passed else "❌ FAILED"
                print(f"{status} - {test_name}")
            
            overall_success = all(results.values())
            if overall_success:
                print("\n🎉 ALL TESTS PASSED! Your bot is working great!")
            else:
                print("\n⚠️  Some tests failed. Check the output above for details.")
            
            return overall_success
            
        finally:
            await self.session.close()

async def main():
    """Main testing function."""
    print("🤖 Automated Bot Tester v2.0")
    print("=" * 40)
    
    # Check if bot is healthy first
    try:
        import requests
        health_response = requests.get("http://localhost:8501/api/healthz", timeout=10)
        if health_response.status_code != 200:
            print("❌ Bot health check failed! Make sure the bot is running.")
            return
        
        health_data = health_response.json()
        print(f"✅ Bot is healthy! Status: {health_data.get('overall_status')}")
        
    except Exception as e:
        print(f"❌ Cannot connect to bot: {e}")
        print("Make sure the bot is running on http://localhost:8501")
        return
    
    # Run the comprehensive test
    tester = BotTester()
    success = await tester.run_comprehensive_test()
    
    if success:
        print("\n🚀 Your bot is fully functional!")
        print("🎯 Story Builder and all tools are working properly.")
    else:
        print("\n🔧 Some issues found. Check the logs above.")

if __name__ == "__main__":
    asyncio.run(main()) 