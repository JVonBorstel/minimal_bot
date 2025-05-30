#!/usr/bin/env python3
"""
Test script for Story Builder functionality.
Sends properly formatted Bot Framework activities to test the bot.
"""
import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Bot endpoint
BOT_URL = "http://localhost:8501/api/messages"

def create_bot_activity(text: str, conversation_id: str = None, user_id: str = None):
    """Create a properly formatted Bot Framework activity."""
    if conversation_id is None:
        conversation_id = f"test-conversation-{int(time.time())}"
    if user_id is None:
        user_id = f"test-user-{int(time.time())}"
    
    return {
        "type": "message",
        "id": f"msg-{int(time.time() * 1000)}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "serviceUrl": "http://localhost:8501",
        "channelId": "emulator",
        "from": {
            "id": user_id,
            "name": "Test User"
        },
        "conversation": {
            "id": conversation_id
        },
        "recipient": {
            "id": "bot",
            "name": "Augie"
        },
        "text": text,
        "inputHint": "acceptingInput",
        "replyToId": None
    }

async def test_story_builder():
    """Test the Story Builder functionality."""
    print("🚀 Testing Story Builder functionality...")
    
    # Test messages for Story Builder
    test_messages = [
        "create a jira ticket for implementing user authentication",
        "build a user story for adding two-factor authentication",
        "draft an issue for implementing OAuth integration",
        "help",  # Test help command too
        "what tools do you have"  # Test tool listing
    ]
    
    conversation_id = f"test-story-builder-{int(time.time())}"
    
    async with aiohttp.ClientSession() as session:
        for i, message in enumerate(test_messages, 1):
            print(f"\n📝 Test {i}: '{message}'")
            
            # Create properly formatted activity
            activity = create_bot_activity(message, conversation_id)
            
            try:
                async with session.post(
                    BOT_URL,
                    json=activity,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        result = await response.text()
                        print(f"✅ SUCCESS - Status: {response.status}")
                        if result:
                            print(f"📄 Response: {result[:200]}...")
                    else:
                        error_text = await response.text()
                        print(f"❌ ERROR - Status: {response.status}")
                        print(f"📄 Error: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"❌ EXCEPTION: {e}")
            
            # Wait between requests
            await asyncio.sleep(2)
    
    print("\n🎯 Story Builder test completed!")
    print("\n💡 For interactive testing, use Bot Framework Emulator:")
    print("   1. Download: https://github.com/Microsoft/BotFramework-Emulator/releases")
    print("   2. Connect to: http://localhost:8501/api/messages")
    print("   3. Type: 'create a jira ticket for user management'")

if __name__ == "__main__":
    asyncio.run(test_story_builder()) 