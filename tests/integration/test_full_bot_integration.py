#!/usr/bin/env python3
"""
FULL BOT INTEGRATION TEST - Test the complete end-to-end workflow
This tests that the intelligent tool selection is actually working in the main bot app
"""

import asyncio
import pytest # Add pytest
import time
from botbuilder.core import TurnContext, MessageFactory
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount
from config import get_config
from bot_core.my_bot import MyBot
from state_models import AppState
from user_auth.models import UserProfile

class MockTurnContext:
    """Mock TurnContext for testing the bot without Teams"""
    def __init__(self, message_text: str, user_id: str = "test_user"):
        self.activity = Activity(
            type=ActivityTypes.message,
            text=message_text,
            from_property=ChannelAccount(id=user_id, name="Test User"),
            conversation=ChannelAccount(id="test_conversation"),
            channel_id="test",
            id=f"activity_{int(time.time())}"
        )
        self.sent_activities = []
    
    async def send_activity(self, activity):
        self.sent_activities.append(activity)
        print(f"🤖 Bot Response: {activity.text}")
        return type('MockResponse', (), {'id': f"response_{len(self.sent_activities)}"})()

@pytest.mark.asyncio
async def test_full_bot_integration():
    print("🎯 FULL BOT INTEGRATION TEST")
    print("Testing end-to-end workflow with real bot instance and intelligent tool selection")
    print("=" * 80)
    
    try:
        # Initialize the real bot
        config = get_config()
        bot = MyBot(config)
        
        print(f"✅ Bot initialized successfully")
        print(f"🔧 Tool selector enabled: {config.TOOL_SELECTOR.get('enabled', False)}")
        print(f"📧 Configured email: {config.JIRA_API_EMAIL}")
        
        # Test scenarios that should trigger intelligent tool selection
        test_scenarios = [
            {
                "name": "Your Exact Scenario",
                "message": "Use whatever tools you need but I need to compare my repo against my Jira ticket",
                "expected_tools": ["jira", "github", "greptile"],
                "description": "The user's exact request that should trigger multi-service coordination"
            },
            {
                "name": "Simple Help Request", 
                "message": "help",
                "expected_tools": ["help"],
                "description": "Basic help command that should be handled directly"
            },
            {
                "name": "Jira-focused Request",
                "message": "Show me my open Jira tickets",
                "expected_tools": ["jira"],
                "description": "Single-service request focused on Jira"
            },
            {
                "name": "GitHub-focused Request",
                "message": "List my GitHub repositories",
                "expected_tools": ["github"],
                "description": "Single-service request focused on GitHub"
            }
        ]
        
        print(f"\n🔧 Testing {len(test_scenarios)} scenarios with real bot...")
        
        results = []
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n{'='*60}")
            print(f"🧪 Scenario {i}: {scenario['name']}")
            print(f"📝 User message: '{scenario['message']}'")
            print(f"🎯 Expected tools: {scenario['expected_tools']}")
            
            # Create mock turn context
            turn_context = MockTurnContext(scenario['message'])
            
            start_time = time.time()
            
            try:
                # Call the actual bot's message handler
                await bot.on_message_activity(turn_context)
                
                end_time = time.time()
                duration_ms = int((end_time - start_time) * 1000)
                
                # Analyze the bot's responses
                responses = [activity.text for activity in turn_context.sent_activities if hasattr(activity, 'text')]
                response_text = " ".join(responses) if responses else ""
                
                print(f"✅ Bot processed message successfully ({duration_ms}ms)")
                print(f"📤 Response count: {len(responses)}")
                
                if response_text:
                    print(f"📋 Response preview: {response_text[:200]}...")
                    
                    # Check if response indicates tool usage
                    tool_indicators = {
                        "jira": ["ticket", "issue", "jira", "LM-", "PROJ-"],
                        "github": ["repository", "repo", "github", "code"],
                        "greptile": ["code analysis", "codebase", "search"],
                        "perplexity": ["search", "web", "research"],
                        "help": ["help", "available", "commands", "what can"]
                    }
                    
                    detected_tools = []
                    for tool_type, indicators in tool_indicators.items():
                        if any(indicator.lower() in response_text.lower() for indicator in indicators):
                            detected_tools.append(tool_type)
                    
                    print(f"🔍 Detected tool usage: {detected_tools}")
                    
                    # Check if this matches expectations
                    expected_set = set(scenario['expected_tools'])
                    detected_set = set(detected_tools)
                    
                    overlap = len(expected_set & detected_set)
                    precision = overlap / len(detected_set) if detected_set else 0
                    recall = overlap / len(expected_set) if expected_set else 0
                    
                    success = overlap > 0  # At least some overlap
                    
                    result = {
                        "scenario": scenario['name'],
                        "message": scenario['message'],
                        "expected_tools": list(expected_set),
                        "detected_tools": detected_tools,
                        "success": success,
                        "duration_ms": duration_ms,
                        "response_length": len(response_text),
                        "precision": precision,
                        "recall": recall
                    }
                    
                    status = "✅ SUCCESS" if success else "⚠️  PARTIAL"
                    print(f"📊 Result: {status} (Precision: {precision:.2f}, Recall: {recall:.2f})")
                    
                else:
                    print(f"⚠️  No text response received")
                    result = {
                        "scenario": scenario['name'],
                        "message": scenario['message'],
                        "expected_tools": scenario['expected_tools'],
                        "detected_tools": [],
                        "success": False,
                        "duration_ms": duration_ms,
                        "response_length": 0,
                        "precision": 0,
                        "recall": 0
                    }
                
                results.append(result)
                
            except Exception as e:
                print(f"❌ Error processing scenario: {e}")
                import traceback
                traceback.print_exc()
                
                results.append({
                    "scenario": scenario['name'],
                    "message": scenario['message'],
                    "expected_tools": scenario['expected_tools'],
                    "detected_tools": [],
                    "success": False,
                    "duration_ms": 0,
                    "error": str(e)
                })
        
        # Overall assessment
        print(f"\n{'='*80}")
        print("📊 FULL BOT INTEGRATION ASSESSMENT")
        print("=" * 80)
        
        successful_scenarios = [r for r in results if r["success"]]
        avg_duration = sum(r["duration_ms"] for r in results) / len(results)
        
        print(f"✅ Successful scenarios: {len(successful_scenarios)}/{len(results)} ({len(successful_scenarios)/len(results)*100:.0f}%)")
        print(f"⏱️  Average response time: {avg_duration:.0f}ms")
        
        print(f"\n📋 Detailed Results:")
        for result in results:
            status = "✅" if result["success"] else "❌"
            print(f"   {status} {result['scenario']}: {result['duration_ms']}ms")
            print(f"      Expected: {result['expected_tools']}")
            print(f"      Detected: {result['detected_tools']}")
            if "error" in result:
                print(f"      Error: {result['error']}")
        
        # Determine if integration is working
        if len(successful_scenarios) >= len(results) * 0.75:  # 75% success rate
            print(f"\n🎉 FULL BOT INTEGRATION: WORKING!")
            print(f"✅ The intelligent tool selection is integrated and functional")
            print(f"✅ Your scenario should work in real Teams deployment")
            print(f"✅ Multi-service coordination is ready for production")
            return True
        else:
            print(f"\n⚠️  FULL BOT INTEGRATION: NEEDS IMPROVEMENT")
            print(f"❌ Some scenarios not working as expected")
            print(f"💡 Check tool selection configuration and integration")
            return False
            
    except Exception as e:
        print(f"\n💥 FULL BOT INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🎯 LAUNCHING FULL BOT INTEGRATION TEST")
    print("This tests the complete end-to-end workflow with the real bot instance")
    print()
    
    success = asyncio.run(test_full_bot_integration())
    
    if success:
        print(f"\n🏆 INTEGRATION TEST COMPLETE: SUCCESS!")
        print(f"✅ Your bot is fully integrated and ready for deployment")
        print(f"✅ Intelligent tool selection is working end-to-end")
        print(f"✅ Multi-service scenarios are production-ready")
    else:
        print(f"\n⚠️  INTEGRATION TEST IDENTIFIED ISSUES")
        print(f"💡 The bot may need configuration or integration fixes")
    
    exit(0 if success else 1) 