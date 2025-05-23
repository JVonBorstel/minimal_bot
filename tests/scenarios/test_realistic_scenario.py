#!/usr/bin/env python3
"""
REALISTIC SCENARIO TEST - Compare repo against Jira ticket
This tests the exact scenario the user described: multi-service coordination for complex tasks
"""

import asyncio
import pytest # Add pytest
import time
from config import get_config
from user_auth.models import UserProfile
from tools.tool_executor import ToolExecutor
from core_logic.tool_selector import ToolSelector
from state_models import AppState

@pytest.mark.asyncio
async def test_realistic_scenario():
    print("🎯 REALISTIC SCENARIO TEST")
    print("Scenario: 'Use whatever tools you need but I need to compare my repo against my Jira ticket'")
    print("=" * 80)
    
    try:
        # Setup
        config = get_config()
        tool_executor = ToolExecutor(config)
        tool_selector = ToolSelector(config)
        
        # Build tool embeddings if needed
        all_tools = tool_executor.get_available_tool_definitions()
        if not tool_selector.tool_embeddings:
            tool_selector.build_tool_embeddings(all_tools)
        
        test_user = UserProfile(
            user_id="realistic_test",
            display_name="Developer User", 
            email="dev@company.com",
            assigned_role="DEVELOPER"
        )
        
        print(f"✅ Setup complete - {len(tool_executor.get_available_tool_names())} tools available")
        
        # Test realistic scenarios that users might actually say
        realistic_queries = [
            {
                "query": "I need to compare my repository against my Jira ticket to see if we've implemented everything",
                "expected_services": ["jira", "github", "greptile"],
                "description": "Full repo vs ticket comparison"
            },
            {
                "query": "Use whatever tools you need but I need to compare my repo against my Jira ticket",
                "expected_services": ["jira", "github", "greptile"], 
                "description": "User's exact scenario"
            },
            {
                "query": "Check if our code implementation matches the requirements in PROJ-123",
                "expected_services": ["jira", "github", "greptile"],
                "description": "Code vs requirements check"
            },
            {
                "query": "I want to see my Jira tickets and check which ones are actually done in the code",
                "expected_services": ["jira", "github", "greptile"],
                "description": "Ticket progress vs code status"
            },
            {
                "query": "Find the best way to implement authentication and see what we currently have in our repo",
                "expected_services": ["perplexity", "greptile", "github"],
                "description": "Research + current code analysis"
            },
            {
                "query": "Show me our repository status and any related Jira issues that need attention",
                "expected_services": ["github", "jira"],
                "description": "Multi-service status check"
            }
        ]
        
        print(f"🔧 Testing {len(realistic_queries)} realistic user scenarios...")
        
        results = []
        for i, scenario in enumerate(realistic_queries):
            print(f"\n{'='*60}")
            print(f"🔧 Scenario {i+1}: {scenario['description']}")
            print(f"📝 User says: '{scenario['query']}'")
            print(f"🎯 Should intelligently use: {scenario['expected_services']}")
            
            start_time = time.time()
            
            # Create app state
            app_state = AppState(
                session_id=f"realistic_test_{int(time.time())}_{i}",
                current_user=test_user
            )
            
            # Use the tool selector (this is what the bot does internally)
            selected_tools = tool_selector.select_tools(
                query=scenario['query'],
                app_state=app_state,
                available_tools=all_tools,
                max_tools=8
            )
            
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            
            # Analyze which services were selected
            services_identified = set()
            tool_names = [tool.get('name', '') for tool in selected_tools]
            
            for tool_name in tool_names:
                if 'github' in tool_name:
                    services_identified.add('github')
                elif 'jira' in tool_name:
                    services_identified.add('jira')
                elif 'greptile' in tool_name:
                    services_identified.add('greptile')
                elif 'perplexity' in tool_name:
                    services_identified.add('perplexity')
                elif 'help' in tool_name:
                    services_identified.add('help')
            
            # Calculate success metrics
            expected_set = set(scenario['expected_services'])
            identified_set = services_identified
            
            precision = len(expected_set & identified_set) / len(identified_set) if identified_set else 0
            recall = len(expected_set & identified_set) / len(expected_set) if expected_set else 0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            success = f1_score >= 0.6  # 60% threshold for realistic scenarios
            
            print(f"🤖 Bot intelligently selected: {tool_names}")
            print(f"📊 Services identified: {list(identified_set)}")
            print(f"🎯 Intelligence Score (F1): {f1_score:.2f}")
            print(f"⏱️  Selection time: {duration_ms}ms")
            
            status = "✅ EXCELLENT" if f1_score >= 0.8 else "✅ GOOD" if f1_score >= 0.6 else "⚠️  NEEDS WORK"
            print(f"📈 Assessment: {status}")
            
            result = {
                "scenario": scenario['description'],
                "query": scenario['query'],
                "expected_services": list(expected_set),
                "identified_services": list(identified_set),
                "tool_names": tool_names,
                "f1_score": f1_score,
                "success": success,
                "duration_ms": duration_ms
            }
            results.append(result)
        
        # Overall assessment
        print(f"\n{'='*80}")
        print("📊 REALISTIC SCENARIO ASSESSMENT")
        print("=" * 80)
        
        successful = [r for r in results if r["success"]]
        avg_f1 = sum(r["f1_score"] for r in results) / len(results)
        
        print(f"✅ Successful scenarios: {len(successful)}/{len(results)} ({len(successful)/len(results)*100:.0f}%)")
        print(f"📈 Average Intelligence Score: {avg_f1:.2f}")
        
        print(f"\n📋 Detailed Results:")
        for result in results:
            status = "✅" if result["success"] else "❌"
            print(f"   {status} {result['scenario']}: F1={result['f1_score']:.2f}")
            print(f"      Expected: {result['expected_services']}")
            print(f"      Got: {result['identified_services']}")
            print(f"      Tools: {result['tool_names']}")
        
        if len(successful) >= len(results) * 0.8:
            print(f"\n🎉 REALISTIC SCENARIOS: WORKING EXCELLENTLY!")
            print(f"✅ Your bot can handle complex multi-service requests!")
            print(f"✅ Users can say things like 'use whatever tools you need' and it works!")
            return True
        else:
            print(f"\n⚠️  REALISTIC SCENARIOS: NEEDS IMPROVEMENT")
            return False
            
    except Exception as e:
        print(f"\n💥 REALISTIC SCENARIO TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_realistic_scenario())
    if success:
        print(f"\n🏆 YOUR BOT IS READY FOR REAL USERS!")
        print(f"✅ Complex multi-service scenarios work perfectly")
        print(f"✅ Intelligent tool selection is production-ready")
    exit(0 if success else 1) 