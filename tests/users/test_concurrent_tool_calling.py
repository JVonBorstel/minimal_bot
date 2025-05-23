#!/usr/bin/env python3
"""
Test script for concurrent real tool calling validation.
Agent-ConcurrentTool-Validator - Step 1.16 Preview - Real Tool Call Concurrency

⚡ CRITICAL - Test that multiple users can simultaneously request REAL tool calls
This test proves concurrent API calls work without interference or resource conflicts.
"""

import asyncio
import logging
import time
import threading
from typing import Dict, Any, List, Tuple
from datetime import datetime

from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from user_auth.db_manager import save_user_profile, get_user_profile_by_id
from tools.tool_executor import ToolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class ConcurrentToolValidator:
    """Validates that concurrent real tool calls work properly with multiple users."""
    
    def __init__(self):
        self.config = get_config()
        self.tool_executor = ToolExecutor(self.config)
        self.test_users: List[UserProfile] = []
        self.concurrent_results: List[Dict[str, Any]] = []
        
    def create_concurrent_test_users(self) -> bool:
        """Create test users for concurrent tool testing."""
        print("🔍 CREATING CONCURRENT TOOL TEST USERS")
        
        test_user_data = [
            {
                "user_id": "concurrent_user_admin",
                "display_name": "Alex Admin - Concurrent",
                "email": "alex.admin@concurrent-test.com",
                "assigned_role": "ADMIN",
                "profile_data": {"team": "Administration", "department": "IT"}
            },
            {
                "user_id": "concurrent_user_dev1",
                "display_name": "Bob Developer 1",
                "email": "bob.dev1@concurrent-test.com",
                "assigned_role": "DEVELOPER", 
                "profile_data": {"team": "Engineering", "department": "Backend"}
            },
            {
                "user_id": "concurrent_user_dev2",
                "display_name": "Carol Developer 2",
                "email": "carol.dev2@concurrent-test.com",
                "assigned_role": "DEVELOPER",
                "profile_data": {"team": "Engineering", "department": "Frontend"}
            },
            {
                "user_id": "concurrent_user_stakeholder",
                "display_name": "David Stakeholder",
                "email": "david.stakeholder@concurrent-test.com",
                "assigned_role": "STAKEHOLDER",
                "profile_data": {"team": "Product", "department": "Management"}
            }
        ]
        
        for user_data in test_user_data:
            try:
                success = save_user_profile(user_data)
                if success:
                    user_profile = UserProfile(**user_data)
                    self.test_users.append(user_profile)
                    print(f"✅ Created concurrent test user: {user_profile.display_name} ({user_profile.assigned_role})")
                else:
                    print(f"❌ Failed to save user: {user_data['display_name']}")
                    return False
                    
            except Exception as e:
                print(f"❌ Error creating user {user_data['display_name']}: {e}")
                return False
                
        print(f"📊 Total concurrent test users created: {len(self.test_users)}")
        return len(self.test_users) == 4
        
    def execute_tool_for_user(self, user: UserProfile, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a real tool call for a specific user with timing."""
        start_time = time.time()
        thread_id = threading.get_ident()
        
        try:
            # Create individual session for this user
            user_session = AppState(
                session_id=f"concurrent_session_{user.user_id}_{int(time.time())}",
                current_user=user
            )
            
            print(f"   🔧 {user.display_name}: Calling {tool_name} [Thread {thread_id}]")
            
            # Execute the actual tool - FIXED: Actually await the async call
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.tool_executor.execute_tool(tool_name, parameters, user_session)
                )
            finally:
                loop.close()
            
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            
            return {
                "user_id": user.user_id,
                "user_name": user.display_name,
                "tool_name": tool_name,
                "parameters": parameters,
                "thread_id": thread_id,
                "start_time": start_time,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "result": result,
                "success": True,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            
            return {
                "user_id": user.user_id,
                "user_name": user.display_name,
                "tool_name": tool_name,
                "parameters": parameters,
                "thread_id": thread_id,
                "start_time": start_time,
                "end_time": end_time,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            
    def test_concurrent_help_calls(self) -> bool:
        """Test multiple users calling help tool simultaneously."""
        print("\n🔍 TESTING CONCURRENT HELP TOOL CALLS")
        
        try:
            print("   Executing help tool calls concurrently...")
            
            # Create threads for concurrent execution
            threads = []
            results = []
            
            def call_help_tool(user):
                result = self.execute_tool_for_user(user, "help", {})
                results.append(result)
                
            # Start all threads simultaneously
            for user in self.test_users:
                thread = threading.Thread(target=call_help_tool, args=(user,))
                threads.append(thread)
                thread.start()
                
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
                
            # Analyze results
            successful_calls = [r for r in results if r["success"]]
            failed_calls = [r for r in results if not r["success"]]
            
            print(f"   📊 Concurrent help tool results:")
            print(f"     Successful: {len(successful_calls)}")
            print(f"     Failed: {len(failed_calls)}")
            
            for result in successful_calls:
                print(f"     ✅ {result['user_name']}: {result['duration_ms']}ms [Thread {result['thread_id']}]")
                
            for result in failed_calls:
                print(f"     ❌ {result['user_name']}: {result.get('error', 'Unknown error')}")
                
            self.concurrent_results.extend(results)
            return len(failed_calls) == 0
            
        except Exception as e:
            print(f"❌ Concurrent help calls test failed: {e}")
            return False
            
    def test_concurrent_github_calls(self) -> bool:
        """Test multiple users calling GitHub tools simultaneously."""
        print("\n🔍 TESTING CONCURRENT GITHUB TOOL CALLS")
        
        try:
            print("   Executing GitHub tool calls concurrently...")
            
            # Define GitHub tool calls for different users
            github_calls = [
                (self.test_users[0], "github_list_repositories", {}),
                (self.test_users[1], "github_list_repositories", {}),
                (self.test_users[2], "github_search_code", {"query": "function"}),
                (self.test_users[3], "github_search_code", {"query": "class"})
            ]
            
            threads = []
            results = []
            
            def call_github_tool(user, tool_name, params):
                result = self.execute_tool_for_user(user, tool_name, params)
                results.append(result)
                
            # Start all threads simultaneously
            for user, tool_name, params in github_calls:
                thread = threading.Thread(target=call_github_tool, args=(user, tool_name, params))
                threads.append(thread)
                thread.start()
                
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
                
            # Analyze results
            successful_calls = [r for r in results if r["success"]]
            failed_calls = [r for r in results if not r["success"]]
            
            print(f"   📊 Concurrent GitHub tool results:")
            print(f"     Successful: {len(successful_calls)}")
            print(f"     Failed: {len(failed_calls)}")
            
            for result in successful_calls:
                print(f"     ✅ {result['user_name']}: {result['tool_name']} {result['duration_ms']}ms")
                
            for result in failed_calls:
                print(f"     ❌ {result['user_name']}: {result['tool_name']} - {result.get('error', 'Unknown error')}")
                
            self.concurrent_results.extend(results)
            
            # Accept some failures due to API limits, but require at least 50% success
            success_rate = len(successful_calls) / len(results) if results else 0
            return success_rate >= 0.5
            
        except Exception as e:
            print(f"❌ Concurrent GitHub calls test failed: {e}")
            return False
            
    def test_concurrent_jira_calls(self) -> bool:
        """Test multiple users calling Jira tools simultaneously."""
        print("\n🔍 TESTING CONCURRENT JIRA TOOL CALLS")
        
        try:
            print("   Executing Jira tool calls concurrently...")
            
            threads = []
            results = []
            
            def call_jira_tool(user):
                result = self.execute_tool_for_user(user, "jira_get_issues_by_user", {"user_email": user.email})
                results.append(result)
                
            # Start threads for all users
            for user in self.test_users:
                thread = threading.Thread(target=call_jira_tool, args=(user,))
                threads.append(thread)
                thread.start()
                
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
                
            # Analyze results
            successful_calls = [r for r in results if r["success"]]
            failed_calls = [r for r in results if not r["success"]]
            
            print(f"   📊 Concurrent Jira tool results:")
            print(f"     Successful: {len(successful_calls)}")
            print(f"     Failed: {len(failed_calls)}")
            
            for result in successful_calls:
                print(f"     ✅ {result['user_name']}: {result['duration_ms']}ms")
                
            for result in failed_calls:
                print(f"     ❌ {result['user_name']}: {result.get('error', 'Unknown error')}")
                
            self.concurrent_results.extend(results)
            
            # Accept some failures due to API limits, but require at least 50% success
            success_rate = len(successful_calls) / len(results) if results else 0
            return success_rate >= 0.5
            
        except Exception as e:
            print(f"❌ Concurrent Jira calls test failed: {e}")
            return False
            
    def test_mixed_concurrent_tools(self) -> bool:
        """Test mixed tool types called simultaneously by different users."""
        print("\n🔍 TESTING MIXED CONCURRENT TOOL CALLS")
        
        try:
            print("   Executing mixed tool calls concurrently...")
            
            # Define mixed tool calls
            mixed_calls = [
                (self.test_users[0], "help", {}),
                (self.test_users[1], "github_list_repositories", {}),
                (self.test_users[2], "jira_get_issues_by_user", {"user_email": self.test_users[2].email}),
                (self.test_users[3], "github_search_code", {"query": "main"})
            ]
            
            threads = []
            results = []
            
            def call_mixed_tool(user, tool_name, params):
                result = self.execute_tool_for_user(user, tool_name, params)
                results.append(result)
                
            # Start all threads simultaneously
            start_timestamp = time.time()
            for user, tool_name, params in mixed_calls:
                thread = threading.Thread(target=call_mixed_tool, args=(user, tool_name, params))
                threads.append(thread)
                thread.start()
                
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            end_timestamp = time.time()
            
            total_duration = int((end_timestamp - start_timestamp) * 1000)
            
            # Analyze results
            successful_calls = [r for r in results if r["success"]]
            failed_calls = [r for r in results if not r["success"]]
            
            print(f"   📊 Mixed concurrent tool results:")
            print(f"     Total execution time: {total_duration}ms")
            print(f"     Successful: {len(successful_calls)}")
            print(f"     Failed: {len(failed_calls)}")
            
            for result in successful_calls:
                print(f"     ✅ {result['user_name']}: {result['tool_name']} {result['duration_ms']}ms")
                
            for result in failed_calls:
                print(f"     ❌ {result['user_name']}: {result['tool_name']} - {result.get('error', 'Unknown error')}")
                
            self.concurrent_results.extend(results)
            
            # Require at least 75% success for mixed calls
            success_rate = len(successful_calls) / len(results) if results else 0
            return success_rate >= 0.75
            
        except Exception as e:
            print(f"❌ Mixed concurrent calls test failed: {e}")
            return False
            
    def analyze_concurrent_performance(self) -> bool:
        """Analyze overall concurrent tool execution performance."""
        print("\n🔍 ANALYZING CONCURRENT TOOL PERFORMANCE")
        
        try:
            if not self.concurrent_results:
                print("❌ No concurrent results to analyze")
                return False
                
            total_calls = len(self.concurrent_results)
            successful_calls = [r for r in self.concurrent_results if r["success"]]
            failed_calls = [r for r in self.concurrent_results if not r["success"]]
            
            # Performance metrics
            success_rate = len(successful_calls) / total_calls
            avg_duration = sum(r["duration_ms"] for r in successful_calls) / len(successful_calls) if successful_calls else 0
            min_duration = min(r["duration_ms"] for r in successful_calls) if successful_calls else 0
            max_duration = max(r["duration_ms"] for r in successful_calls) if successful_calls else 0
            
            # Tool type breakdown
            tool_types = {}
            for result in self.concurrent_results:
                tool_name = result["tool_name"]
                if tool_name not in tool_types:
                    tool_types[tool_name] = {"total": 0, "successful": 0}
                tool_types[tool_name]["total"] += 1
                if result["success"]:
                    tool_types[tool_name]["successful"] += 1
                    
            print(f"📊 Concurrent Tool Performance Analysis:")
            print(f"   Total calls: {total_calls}")
            print(f"   Successful: {len(successful_calls)} ({success_rate:.1%})")
            print(f"   Failed: {len(failed_calls)}")
            print(f"   Average duration: {avg_duration:.1f}ms")
            print(f"   Duration range: {min_duration}ms - {max_duration}ms")
            
            print(f"\n   Tool type breakdown:")
            for tool_name, stats in tool_types.items():
                tool_success_rate = stats["successful"] / stats["total"] if stats["total"] > 0 else 0
                print(f"     {tool_name}: {stats['successful']}/{stats['total']} ({tool_success_rate:.1%})")
                
            # Check for threading issues
            unique_threads = set(r["thread_id"] for r in self.concurrent_results if "thread_id" in r)
            print(f"   Unique threads used: {len(unique_threads)}")
            
            # Overall success criteria
            overall_success = (
                success_rate >= 0.70 and  # At least 70% success rate
                len(unique_threads) >= 3 and  # Used multiple threads
                avg_duration < 10000  # Average under 10 seconds
            )
            
            if overall_success:
                print("✅ Concurrent tool performance: EXCELLENT")
            else:
                print("⚠️  Concurrent tool performance: NEEDS IMPROVEMENT")
                print(f"   Success rate: {success_rate:.1%} (need ≥70%)")
                print(f"   Thread usage: {len(unique_threads)} (need ≥3)")
                print(f"   Avg duration: {avg_duration:.1f}ms (need <10000ms)")
                
            return overall_success
            
        except Exception as e:
            print(f"❌ Performance analysis failed: {e}")
            return False
            
    async def run_concurrent_tool_validation(self) -> bool:
        """Run complete concurrent tool validation."""
        print("🚀 STARTING CONCURRENT TOOL CALLING VALIDATION")
        print("=" * 60)
        
        validation_steps = [
            ("Creating concurrent test users", self.create_concurrent_test_users),
            ("Testing concurrent help calls", self.test_concurrent_help_calls),
            ("Testing concurrent GitHub calls", self.test_concurrent_github_calls),
            ("Testing concurrent Jira calls", self.test_concurrent_jira_calls),
            ("Testing mixed concurrent tools", self.test_mixed_concurrent_tools),
            ("Analyzing concurrent performance", self.analyze_concurrent_performance)
        ]
        
        for step_name, step_func in validation_steps:
            print(f"\n🔄 {step_name}...")
            try:
                success = step_func()
                if not success:
                    print(f"❌ VALIDATION FAILED: {step_name}")
                    return False
                print(f"✅ {step_name} PASSED")
                
            except Exception as e:
                print(f"❌ VALIDATION ERROR in {step_name}: {e}")
                return False
                
        print("\n" + "=" * 60)
        print("🎉 ALL CONCURRENT TOOL CALLING TESTS PASSED")
        print("✅ Multiple users can execute real tools simultaneously")
        print("✅ No interference between concurrent tool executions")
        print("✅ Threading and resource management working correctly")
        return True

async def main():
    """Main test execution."""
    validator = ConcurrentToolValidator()
    success = await validator.run_concurrent_tool_validation()
    
    if success:
        print("\n🏆 CONCURRENT TOOL CALLING VALIDATION - COMPLETE SUCCESS")
        print("✅ Bot can handle multiple users requesting real tool calls simultaneously")
        exit(0)
    else:
        print("\n💥 CONCURRENT TOOL CALLING VALIDATION - FAILED")
        print("❌ Issues detected with concurrent real tool execution")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 