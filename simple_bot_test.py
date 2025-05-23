#!/usr/bin/env python3
"""
Simple bot health and connectivity test.
Verifies the bot is running and all services are healthy.
"""
import requests
import json

def test_bot_health():
    """Test if the bot is healthy and all services are working."""
    print("🏥 Testing Bot Health...")
    
    try:
        response = requests.get("http://localhost:8501/api/healthz", timeout=10)
        
        if response.status_code == 200:
            health_data = response.json()
            print("✅ Bot is HEALTHY!")
            print(f"📊 Overall Status: {health_data.get('overall_status', 'Unknown')}")
            
            components = health_data.get('components', {})
            for service, details in components.items():
                status = details.get('status', 'Unknown')
                emoji = "✅" if status == "OK" else "❌"
                print(f"   {emoji} {service}: {status}")
            
            return True
        else:
            print(f"❌ Bot health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Cannot connect to bot: {e}")
        return False

def test_bot_endpoints():
    """Test if bot endpoints are accessible."""
    print("\n🔌 Testing Bot Endpoints...")
    
    endpoints = [
        "http://localhost:8501/api/healthz",
        "http://localhost:8501/api/messages"
    ]
    
    for endpoint in endpoints:
        try:
            # Just check if endpoint responds (don't send actual messages)
            response = requests.head(endpoint, timeout=5)
            if response.status_code in [200, 405, 501]:  # 405/501 = method not allowed but endpoint exists
                print(f"✅ {endpoint} - Accessible")
            else:
                print(f"❌ {endpoint} - Status {response.status_code}")
        except Exception as e:
            print(f"❌ {endpoint} - Error: {e}")

def print_test_instructions():
    """Print instructions for manual testing."""
    print("\n🎯 MANUAL TESTING INSTRUCTIONS:")
    print("=" * 50)
    print("1. Open Bot Framework Emulator")
    print("2. Connect to: http://localhost:8501/api/messages")
    print("3. Leave App ID and Password BLANK")
    print("4. Click 'Connect'")
    print("")
    print("📝 TEST MESSAGES TO TRY:")
    print("   • create a jira ticket for user authentication")
    print("   • build a user story for OAuth integration") 
    print("   • help")
    print("   • what tools do you have")
    print("")
    print("✅ EXPECTED RESULTS:")
    print("   • Story Builder should start asking questions")
    print("   • Help should list available tools")
    print("   • No crashes or error messages")
    print("=" * 50)

if __name__ == "__main__":
    print("🤖 Minimal Bot Test Suite")
    print("=" * 30)
    
    # Test health
    health_ok = test_bot_health()
    
    # Test endpoints  
    test_bot_endpoints()
    
    # Print manual test instructions
    print_test_instructions()
    
    if health_ok:
        print("\n🎉 Bot is ready for testing!")
        print("💡 Use Bot Framework Emulator for interactive testing")
    else:
        print("\n❌ Bot has issues - check the app.py logs") 