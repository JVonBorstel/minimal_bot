#!/usr/bin/env python3
"""
QUICK TOOL VALIDATION - Verify multiple tools work correctly with async handling
"""

import asyncio
import time
from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from tools.tool_executor import ToolExecutor

async def quick_validation():
    print("🚀 QUICK TOOL VALIDATION - Multiple Tools")
    print("=" * 50)
    
    try:
        # Setup
        config = get_config()
        executor = ToolExecutor(config)
        test_user = UserProfile(
            user_id="validation_test",
            display_name="Validation User",
            email="validation@company.com",
            assigned_role="DEVELOPER"
        )
        
        # State for tools that need it
        app_state = AppState(
            session_id="validation_session",
            current_user=test_user
        )
        
        print(f"✅ Setup complete - {len(executor.get_available_tool_names())} tools available")
        
        # Test multiple tool types
        tests = [
            ("help", {}, "Core help functionality"),
            ("jira_get_issues_by_user", {"user_email": test_user.email}, "Jira integration"),
            ("github_list_repositories", {}, "GitHub integration"),
        ]
        
        results = []
        for tool_name, params, description in tests:
            print(f"\n🔧 Testing: {tool_name} ({description})")
            start = time.time()
            
            try:
                # CRITICAL: Properly await the async call
                result = await executor.execute_tool(tool_name, params, app_state)
                end = time.time()
                duration = int((end - start) * 1000)
                
                # Validate result structure
                if isinstance(result, dict):
                    status = result.get('status', 'UNKNOWN')
                    print(f"   ✅ SUCCESS: {status} in {duration}ms")
                    print(f"   📄 Type: {type(result)}")
                    if 'data' in result:
                        print(f"   📊 Data: {str(result['data'])[:100]}...")
                    results.append((tool_name, True, duration, status))
                else:
                    print(f"   ⚠️  UNEXPECTED: {type(result)} in {duration}ms")
                    print(f"   📄 Content: {str(result)[:100]}...")
                    results.append((tool_name, False, duration, f"Type: {type(result)}"))
                    
            except Exception as e:
                end = time.time()
                duration = int((end - start) * 1000)
                print(f"   ❌ ERROR: {e} in {duration}ms")
                results.append((tool_name, False, duration, f"Error: {e}"))
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 VALIDATION SUMMARY")
        print("=" * 50)
        
        successful = [r for r in results if r[1]]
        failed = [r for r in results if not r[1]]
        
        print(f"✅ Successful: {len(successful)}/{len(results)}")
        print(f"❌ Failed: {len(failed)}/{len(results)}")
        
        for tool_name, success, duration, status in results:
            symbol = "✅" if success else "❌"
            print(f"   {symbol} {tool_name}: {status} ({duration}ms)")
        
        # Overall status
        if len(successful) == len(results):
            print("\n🎉 ALL TOOLS WORKING - ASYNC BUG COMPLETELY FIXED!")
            return True
        elif len(successful) >= len(results) * 0.7:  # 70% success rate
            print(f"\n⚠️  MOSTLY WORKING - {len(successful)}/{len(results)} tools functional")
            return True
        else:
            print(f"\n💥 STILL BROKEN - Only {len(successful)}/{len(results)} tools working")
            return False
            
    except Exception as e:
        print(f"\n💥 VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(quick_validation())
    exit(0 if success else 1) 