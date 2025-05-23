#!/usr/bin/env python3
"""
Test script for multi-service intelligence validation.
Agent-Intelligence-Validator - Critical Intelligence Testing

🧠 CRITICAL - Test the bot's ACTUAL INTELLIGENCE, not just tool execution
This test validates that the LLM can intelligently coordinate multiple services
and follows the sophisticated prompt engineering we've built.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List
from datetime import datetime
import pytest # Add pytest

from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from user_auth.db_manager import save_user_profile
from bot_core.my_bot import MyBot
from core_logic.llm_interactions import _perform_llm_interaction
from tools.tool_executor import ToolExecutor
from llm_interface import LLMInterface

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class MultiServiceIntelligenceValidator:
    """Validates the bot's actual intelligence in multi-service coordination."""
    
    def __init__(self):
        self.config = get_config()
        self.tool_executor = ToolExecutor(self.config)
        self.test_user = None
        self.intelligence_results: List[Dict[str, Any]] = []
        
    def create_test_user(self) -> bool:
        """Create a test user for intelligence testing."""
        print("🔍 CREATING INTELLIGENCE TEST USER")
        
        user_data = {
            "user_id": "intelligence_test_user",
            "display_name": "Intelligence Tester",
            "email": "intel.tester@example.com",
            "assigned_role": "DEVELOPER",
            "profile_data": {"team": "QA", "department": "Testing"}
        }
        
        try:
            success = save_user_profile(user_data)
            if success:
                self.test_user = UserProfile(**user_data)
                print(f"✅ Created intelligence test user: {self.test_user.display_name}")
                return True
            else:
                print("❌ Failed to save test user")
                return False
        except Exception as e:
            print(f"❌ Error creating test user: {e}")
            return False
            
    @pytest.mark.asyncio
    async def test_multi_service_intelligence(self, query: str, expected_services: List[str], scenario_name: str) -> Dict[str, Any]:
        """Test the bot's intelligence for a specific multi-service scenario."""
        print(f"\n🧠 TESTING INTELLIGENCE: {scenario_name}")
        print(f"   Query: '{query}'")
        print(f"   Expected services: {expected_services}")
        
        start_time = time.time()
        
        try:
            # Create user session
            user_session = AppState(
                session_id=f"intelligence_test_{int(time.time())}",
                current_user=self.test_user
            )
            
            # Add user message
            user_session.add_message(role="user", content=query)
            
            # Get available tools 
            available_tools = self.tool_executor.get_available_tool_definitions()
            
            # Get LLM interface from config
            llm = LLMInterface(self.config)
            
            # Perform LLM interaction to see what tools it chooses
            print(f"   📡 Sending to LLM with {len(available_tools)} available tools...")
            
            # Use the actual LLM interaction system with CORRECT parameters
            from core_logic.llm_interactions import _perform_llm_interaction
            
            # Create proper LLM history from user session
            current_llm_history = user_session.messages  # These are already properly formatted
            
            # Call with correct signature
            llm_interaction_generator = _perform_llm_interaction(
                current_llm_history=current_llm_history,
                available_tool_definitions=available_tools, 
                llm=llm,
                cycle_num=0,
                app_state=user_session,
                is_initial_decision_call=True,
                stage_name=None,
                config=self.config
            )
            
            # Process the generator to get the response
            tool_calls_made = []
            response_text = ""
            
            for event_type, event_data in llm_interaction_generator:
                if event_type == "text":
                    response_text += event_data
                elif event_type == "tool_calls":
                    if event_data:  # Check if tool calls exist
                        for tool_call in event_data:
                            if isinstance(tool_call, dict) and 'function' in tool_call:
                                tool_name = tool_call['function'].get('name')
                                if tool_name:
                                    tool_calls_made.append(tool_name)
                                    print(f"   🔧 Tool call found: {tool_name}")
            
            print(f"   🔍 Total tool calls made: {len(tool_calls_made)}")
            
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            
            # Analyze the response
            if not tool_calls_made:
                print(f"   ⚠️  No tool calls found in expected format")
                # Try to extract from session messages if tools were actually executed
                messages = user_session.messages
                print(f"   🔍 Session has {len(messages)} messages")
                for i, msg in enumerate(messages):
                    print(f"     Message {i}: role={msg.get('role')}, content_preview={str(msg.get('content', ''))[:100]}")
            
            # Check if response contained tool calls as expected
            services_identified = set()
            for tool_name in tool_calls_made:
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
                    
            # Evaluate intelligence
            expected_set = set(expected_services)
            identified_set = services_identified
            
            precision = len(expected_set & identified_set) / len(identified_set) if identified_set else 0
            recall = len(expected_set & identified_set) / len(expected_set) if expected_set else 0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            intelligence_score = f1_score  # Use F1 as overall intelligence score
            
            result = {
                "scenario": scenario_name,
                "query": query,
                "expected_services": list(expected_set),
                "identified_services": list(identified_set),
                "tool_calls_made": tool_calls_made,
                "precision": precision,
                "recall": recall,
                "f1_score": f1_score,
                "intelligence_score": intelligence_score,
                "duration_ms": duration_ms,
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "debug_info": {
                    "response_type": str(type(response_text)),
                    "has_tool_calls": bool(tool_calls_made),
                    "session_message_count": len(user_session.messages)
                }
            }
            
            print(f"   🎯 Services identified: {list(identified_set)}")
            print(f"   📊 Intelligence score (F1): {f1_score:.2f}")
            print(f"   ⏱️  Duration: {duration_ms}ms")
            
            return result
            
        except Exception as e:
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            
            print(f"   💥 ERROR in intelligence test: {e}")
            print(f"   📍 Error type: {type(e)}")
            
            return {
                "scenario": scenario_name,
                "query": query,
                "expected_services": expected_services,
                "success": False,
                "error": str(e),
                "error_type": str(type(e)),
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat()
            }
            
    @pytest.mark.asyncio
    async def test_intelligence_scenarios(self) -> bool:
        """Test various multi-service intelligence scenarios."""
        print("\n🧠 TESTING MULTI-SERVICE INTELLIGENCE SCENARIOS")
        
        # Define intelligence test scenarios
        intelligence_scenarios = [
            {
                "scenario": "Authentication Analysis",
                "query": "Help me understand our authentication issues and find the best practices to fix them",
                "expected_services": ["jira", "github", "perplexity"]
            },
            {
                "scenario": "Repository Problem Investigation", 
                "query": "What deployment issues do we have in our repos and how should we solve them?",
                "expected_services": ["jira", "github", "greptile"]
            },
            {
                "scenario": "Code Quality Assessment",
                "query": "Show me code quality problems in our main repository and get current best practices",
                "expected_services": ["github", "greptile", "perplexity"]
            },
            {
                "scenario": "Project Status Overview",
                "query": "Give me a complete picture of our project issues and repository status",
                "expected_services": ["jira", "github"]
            },
            {
                "scenario": "Research and Implementation",
                "query": "Find latest React patterns online and see how we're implementing them in our code",
                "expected_services": ["perplexity", "greptile", "github"]
            },
            {
                "scenario": "Single Service (Help)",
                "query": "What can you help me with?",
                "expected_services": ["help"]
            },
            {
                "scenario": "Single Service (Jira)",
                "query": "Show me my open Jira tickets",
                "expected_services": ["jira"]
            }
        ]
        
        try:
            for scenario in intelligence_scenarios:
                result = await self.test_multi_service_intelligence(
                    scenario["query"],
                    scenario["expected_services"], 
                    scenario["scenario"]
                )
                self.intelligence_results.append(result)
                
                # Brief pause between tests
                await asyncio.sleep(0.5)
                
            return True
            
        except Exception as e:
            print(f"❌ Intelligence scenarios test failed: {e}")
            return False
            
    def test_prompt_engineering_effectiveness(self) -> bool:
        """Analyze how well the bot followed prompt engineering instructions."""
        print("\n🔍 ANALYZING PROMPT ENGINEERING EFFECTIVENESS")
        
        try:
            successful_tests = [r for r in self.intelligence_results if r["success"]]
            failed_tests = [r for r in self.intelligence_results if not r["success"]]
            
            if not successful_tests:
                print("❌ No successful tests to analyze")
                return False
                
            # Analyze intelligence scores
            intelligence_scores = [r["intelligence_score"] for r in successful_tests]
            avg_intelligence = sum(intelligence_scores) / len(intelligence_scores)
            
            # Analyze precision and recall
            precision_scores = [r["precision"] for r in successful_tests]
            recall_scores = [r["recall"] for r in successful_tests]
            avg_precision = sum(precision_scores) / len(precision_scores)
            avg_recall = sum(recall_scores) / len(recall_scores)
            
            # Check for prompt engineering adherence
            multi_service_scenarios = [r for r in successful_tests if len(r["expected_services"]) > 1]
            single_service_scenarios = [r for r in successful_tests if len(r["expected_services"]) == 1]
            
            print(f"📊 PROMPT ENGINEERING ANALYSIS:")
            print(f"   Total scenarios tested: {len(self.intelligence_results)}")
            print(f"   Successful: {len(successful_tests)}")
            print(f"   Failed: {len(failed_tests)}")
            print(f"   Average intelligence score: {avg_intelligence:.2f}")
            print(f"   Average precision: {avg_precision:.2f}")
            print(f"   Average recall: {avg_recall:.2f}")
            
            print(f"\n   Multi-service coordination:")
            print(f"     Scenarios: {len(multi_service_scenarios)}")
            if multi_service_scenarios:
                multi_avg = sum(r["intelligence_score"] for r in multi_service_scenarios) / len(multi_service_scenarios)
                print(f"     Average intelligence: {multi_avg:.2f}")
                
            print(f"\n   Single-service precision:")
            print(f"     Scenarios: {len(single_service_scenarios)}")
            if single_service_scenarios:
                single_avg = sum(r["intelligence_score"] for r in single_service_scenarios) / len(single_service_scenarios)
                print(f"     Average intelligence: {single_avg:.2f}")
                
            # Detailed scenario analysis
            print(f"\n   📋 Detailed scenario results:")
            for result in successful_tests:
                expected = result["expected_services"]
                identified = result["identified_services"]
                score = result["intelligence_score"]
                status = "✅" if score >= 0.7 else "⚠️" if score >= 0.4 else "❌"
                print(f"     {status} {result['scenario']}: {score:.2f} (expected: {expected}, got: {identified})")
                
            # Overall assessment
            excellent_count = len([r for r in successful_tests if r["intelligence_score"] >= 0.8])
            good_count = len([r for r in successful_tests if 0.6 <= r["intelligence_score"] < 0.8])
            poor_count = len([r for r in successful_tests if r["intelligence_score"] < 0.6])
            
            print(f"\n   🎯 Performance tiers:")
            print(f"     Excellent (≥0.8): {excellent_count}")
            print(f"     Good (0.6-0.8): {good_count}")
            print(f"     Poor (<0.6): {poor_count}")
            
            # Success criteria
            overall_success = (
                avg_intelligence >= 0.6 and  # At least 60% average intelligence
                len(failed_tests) <= 1 and   # At most 1 complete failure
                excellent_count >= 2         # At least 2 excellent performances
            )
            
            if overall_success:
                print("✅ Prompt engineering effectiveness: EXCELLENT")
            else:
                print("⚠️  Prompt engineering effectiveness: NEEDS IMPROVEMENT")
                print(f"   Requirements:")
                print(f"     Avg intelligence ≥0.6: {avg_intelligence:.2f} {'✅' if avg_intelligence >= 0.6 else '❌'}")
                print(f"     Failed tests ≤1: {len(failed_tests)} {'✅' if len(failed_tests) <= 1 else '❌'}")
                print(f"     Excellent scenarios ≥2: {excellent_count} {'✅' if excellent_count >= 2 else '❌'}")
                
            return overall_success
            
        except Exception as e:
            print(f"❌ Prompt engineering analysis failed: {e}")
            return False
            
    async def run_intelligence_validation(self) -> bool:
        """Run complete multi-service intelligence validation."""
        print("🧠 STARTING MULTI-SERVICE INTELLIGENCE VALIDATION")
        print("=" * 60)
        
        validation_steps = [
            ("Creating intelligence test user", self.create_test_user),
            ("Testing multi-service intelligence scenarios", self.test_intelligence_scenarios),
            ("Analyzing prompt engineering effectiveness", self.test_prompt_engineering_effectiveness)
        ]
        
        for step_name, step_func in validation_steps:
            print(f"\n🔄 {step_name}...")
            try:
                if asyncio.iscoroutinefunction(step_func):
                    success = await step_func()
                else:
                    success = step_func()
                    
                if not success:
                    print(f"❌ VALIDATION FAILED: {step_name}")
                    return False
                print(f"✅ {step_name} PASSED")
                
            except Exception as e:
                print(f"❌ VALIDATION ERROR in {step_name}: {e}")
                return False
                
        print("\n" + "=" * 60)
        print("🎉 MULTI-SERVICE INTELLIGENCE VALIDATION COMPLETE")
        print("✅ Bot demonstrates intelligent multi-service coordination")
        print("✅ Prompt engineering working effectively")
        return True

async def main():
    """Main test execution."""
    validator = MultiServiceIntelligenceValidator()
    success = await validator.run_intelligence_validation()
    
    if success:
        print("\n🏆 MULTI-SERVICE INTELLIGENCE VALIDATION - COMPLETE SUCCESS")
        print("✅ Bot has proven intelligent multi-service triage capabilities")
        print("✅ Prompt engineering effectiveness validated")
        exit(0)
    else:
        print("\n💥 MULTI-SERVICE INTELLIGENCE VALIDATION - FAILED")
        print("❌ Issues detected with bot intelligence or prompt engineering")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 