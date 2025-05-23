#!/usr/bin/env python3
"""
FOCUSED TRIAGE INTELLIGENCE TEST - Test the core intelligent routing
This validates the bot's ability to intelligently select appropriate tools for queries
"""

import asyncio
from typing import List, Dict, Any
from config import get_config
from user_auth.models import UserProfile
from tools.tool_executor import ToolExecutor
from core_logic.tool_selector import ToolSelector
from state_models import AppState
import time

async def test_triage_intelligence():
    print("🧠 FOCUSED TRIAGE INTELLIGENCE TEST")
    print("=" * 50)
    
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
            user_id="triage_test",
            display_name="Triage Tester", 
            email="triage@company.com",
            assigned_role="DEVELOPER"
        )
        
        print(f"✅ Setup complete - {len(tool_executor.get_available_tool_names())} tools available")
        
        # Triage test scenarios
        triage_scenarios = [
            {
                "scenario": "Authentication Analysis",
                "query": "Help me understand our authentication issues and find the best practices to fix them",
                "expected_services": ["jira", "github", "perplexity"],
                "min_tools": 2  # Should intelligently select multiple tools
            },
            {
                "scenario": "Repository Problem Investigation", 
                "query": "What deployment issues do we have in our repos and how should we solve them?",
                "expected_services": ["jira", "github", "greptile"],
                "min_tools": 2
            },
            {
                "scenario": "Code Quality Assessment",
                "query": "Show me code quality problems in our main repository and get current best practices",
                "expected_services": ["github", "greptile", "perplexity"],
                "min_tools": 2
            },
            {
                "scenario": "Project Status Overview",
                "query": "Give me a complete picture of our project issues and repository status",
                "expected_services": ["jira", "github"],
                "min_tools": 2
            },
            {
                "scenario": "Research and Implementation",
                "query": "Find latest React patterns online and see how we're implementing them in our code",
                "expected_services": ["perplexity", "greptile", "github"],
                "min_tools": 2
            },
            {
                "scenario": "Single Service (Help)",
                "query": "What can you help me with?",
                "expected_services": ["help"],
                "min_tools": 1
            },
            {
                "scenario": "Single Service (Jira)",
                "query": "Show me my open Jira tickets",
                "expected_services": ["jira"],
                "min_tools": 1
            }
        ]
        
        results = []
        for scenario in triage_scenarios:
            print(f"\n🔧 Testing: {scenario['scenario']}")
            print(f"   Query: '{scenario['query']}'")
            print(f"   Expected services: {scenario['expected_services']}")
            
            # Use the actual tool selector (the core of triage intelligence)
            app_state = AppState(
                session_id=f"test_{int(time.time())}",
                current_user=test_user
            )
            
            selected_tools = tool_selector.select_tools(
                query=scenario['query'],
                app_state=app_state,
                available_tools=all_tools,
                max_tools=6
            )
            
            print(f"   🎯 Selected tools: {[tool.get('name', 'unknown') for tool in selected_tools]}")
            
            # Analyze which services are represented
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
            
            # Evaluate triage intelligence
            expected_set = set(scenario['expected_services'])
            identified_set = services_identified
            
            # Calculate intelligence metrics
            precision = len(expected_set & identified_set) / len(identified_set) if identified_set else 0
            recall = len(expected_set & identified_set) / len(expected_set) if expected_set else 0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            # Check minimum tool requirement
            meets_min_tools = len(selected_tools) >= scenario['min_tools']
            
            # Overall success
            success = f1_score >= 0.5 and meets_min_tools  # At least 50% intelligence + min tools
            
            result = {
                "scenario": scenario['scenario'],
                "query": scenario['query'][:50] + "...",
                "expected_services": list(expected_set),
                "identified_services": list(identified_set),
                "tool_count": len(selected_tools),
                "min_tools_required": scenario['min_tools'],
                "meets_min_tools": meets_min_tools,
                "precision": precision,
                "recall": recall,
                "f1_score": f1_score,
                "success": success
            }
            
            status = "✅" if success else "❌"
            print(f"   {status} Intelligence Score: {f1_score:.2f} | Tools: {len(selected_tools)}/{scenario['min_tools']} | Services: {list(identified_set)}")
            
            results.append(result)
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 TRIAGE INTELLIGENCE SUMMARY")
        print("=" * 50)
        
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        avg_f1 = sum(r["f1_score"] for r in results) / len(results)
        avg_precision = sum(r["precision"] for r in results) / len(results)
        avg_recall = sum(r["recall"] for r in results) / len(results)
        
        print(f"✅ Successful scenarios: {len(successful)}/{len(results)}")
        print(f"❌ Failed scenarios: {len(failed)}")
        print(f"📈 Average F1 Score: {avg_f1:.2f}")
        print(f"📈 Average Precision: {avg_precision:.2f}")
        print(f"📈 Average Recall: {avg_recall:.2f}")
        
        print(f"\n📋 Detailed Results:")
        for result in results:
            status = "✅" if result["success"] else "❌"
            print(f"   {status} {result['scenario']}: F1={result['f1_score']:.2f} | "
                  f"Tools={result['tool_count']}/{result['min_tools_required']} | "
                  f"Expected={result['expected_services']} | "
                  f"Got={result['identified_services']}")
        
        # Overall assessment
        overall_success = len(successful) >= len(results) * 0.7  # 70% success rate
        
        if overall_success:
            print(f"\n🎉 TRIAGE INTELLIGENCE: WORKING EXCELLENTLY!")
            print(f"✅ {len(successful)}/{len(results)} scenarios passed")
            print(f"✅ Intelligent multi-service coordination confirmed")
            print(f"✅ Tool selection routing working correctly")
            return True
        else:
            print(f"\n⚠️  TRIAGE INTELLIGENCE: NEEDS IMPROVEMENT")
            print(f"❌ Only {len(successful)}/{len(results)} scenarios passed")
            return False
            
    except Exception as e:
        print(f"\n💥 TRIAGE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_triage_intelligence())
    exit(0 if success else 1) 