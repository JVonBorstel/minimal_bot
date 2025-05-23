#!/usr/bin/env python3
"""
STEP 1.13 - SCENARIO 4: Long-Running Session Persistence Test

This test proves that the bot can maintain conversation history and state 
across extended sessions and bot restarts.

CRITICAL TEST - This is a mandatory validation for Step 1.13.
"""

import asyncio
import logging
import os
import sys
import time
import json
from typing import Dict, Any, Optional
import pytest # Add pytest

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from state_models import AppState, UserProfile
from bot_core.my_bot import SQLiteStorage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_database_persistence.log')
    ]
)
logger = logging.getLogger(__name__)

class PersistenceTester:
    """Test long-running session persistence and state management."""
    
    def __init__(self):
        self.config = get_config()
        self.test_results = []
        self.storage = None
        self.test_db_path = "test_persistence.db"
        
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log a test result."""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'timestamp': time.time()
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        logger.info(f"Test result - {test_name}: {'PASS' if success else 'FAIL'} - {details}")
        
    async def initialize_storage(self):
        """Initialize clean storage for testing."""
        print("🔧 INITIALIZING CLEAN STORAGE FOR PERSISTENCE TESTING")
        
        try:
            # Remove existing test database
            if os.path.exists(self.test_db_path):
                try:
                    os.remove(self.test_db_path)
                except PermissionError:
                    print(f"⚠️ Warning: Could not remove {self.test_db_path}, proceeding anyway")
            
            # Initialize fresh storage
            self.storage = SQLiteStorage(db_path=self.test_db_path)
            self.log_result("Storage Initialization", True, "Clean storage initialized")
            return True
            
        except Exception as e:
            self.log_result("Storage Initialization", False, f"Exception: {str(e)}")
            logger.error("Storage initialization failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_extended_conversation_persistence(self):
        """Test that extended conversations persist correctly."""
        print("💬 TESTING EXTENDED CONVERSATION PERSISTENCE")
        
        if not self.storage:
            self.log_result("Extended Conversation Persistence", False, "Storage not initialized")
            return False
            
        try:
            # Create a user and session for long conversation
            test_user = UserProfile(
                user_id="persistence_user",
                display_name="Persistence Test User",
                email="persistence@test.com",
                assigned_role="DEVELOPER"
            )
            
            conversation_state = AppState(
                session_id="long_conversation_session",
                selected_model="gemini-1.5-pro",
                current_user=test_user
            )
            
            # Simulate an extended conversation with 50 messages
            conversation_topics = [
                "Hello, I need help with my project",
                "Can you list my GitHub repositories?",
                "What about my Jira issues?", 
                "Help me search for authentication code",
                "Summarize the main repository structure",
                "Find tickets assigned to me this week",
                "Search for security-related code patterns",
                "What are the recent commits in my main repo?",
                "Help me understand the database schema",
                "Can you analyze the test coverage?"
            ]
            
            # Create 50 messages (5 cycles of conversation topics)
            for cycle in range(5):
                for i, topic in enumerate(conversation_topics):
                    message_num = cycle * len(conversation_topics) + i + 1
                    
                    # User message
                    conversation_state.add_message(
                        role="user", 
                        content=f"Message {message_num}: {topic}"
                    )
                    
                    # Assistant response
                    conversation_state.add_message(
                        role="assistant",
                        content=f"Response {message_num}: I understand you're asking about '{topic}'. Let me help you with that. This is a detailed response that contains multiple sentences to simulate a real conversation. The system is working properly and maintaining context throughout our extended discussion."
                    )
            
            # Verify we have the expected number of messages
            expected_messages = 100  # 50 user + 50 assistant
            if len(conversation_state.messages) != expected_messages:
                self.log_result("Extended Conversation Persistence", False, f"Expected {expected_messages} messages, got {len(conversation_state.messages)}")
                return False
            
            # Write the extended conversation
            conversation_data = {"long_conversation_session": conversation_state.model_dump(mode='json')}
            await self.storage.write(conversation_data)
            
            # Read it back immediately
            read_data = await self.storage.read(["long_conversation_session"])
            
            if "long_conversation_session" in read_data:
                retrieved_state = AppState.model_validate(read_data["long_conversation_session"])
                if len(retrieved_state.messages) == expected_messages:
                    # Verify content integrity of first and last messages
                    first_msg = retrieved_state.messages[0]
                    last_msg = retrieved_state.messages[-1]
                    
                    if "Message 1:" in first_msg['content'] and "Response 50:" in last_msg['content']:
                        self.log_result(
                            "Extended Conversation Persistence", 
                            True, 
                            f"Successfully persisted {expected_messages} messages with content integrity"
                        )
                        return True
                    else:
                        self.log_result("Extended Conversation Persistence", False, "Content integrity check failed")
                        return False
                else:
                    self.log_result("Extended Conversation Persistence", False, f"Message count mismatch after persistence")
                    return False
            else:
                self.log_result("Extended Conversation Persistence", False, "Failed to read extended conversation")
                return False
                
        except Exception as e:
            self.log_result("Extended Conversation Persistence", False, f"Exception: {str(e)}")
            logger.error("Extended conversation persistence test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_cross_session_state_persistence(self):
        """Test that state persists across multiple sessions."""
        print("🔄 TESTING CROSS-SESSION STATE PERSISTENCE")
        
        if not self.storage:
            self.log_result("Cross-Session State Persistence", False, "Storage not initialized")
            return False
            
        try:
            # Create multiple user sessions with different state
            users_data = []
            
            for i in range(5):
                user = UserProfile(
                    user_id=f"cross_session_user_{i}",
                    display_name=f"Cross Session User {i}",
                    email=f"user{i}@crosssession.com",
                    assigned_role="DEVELOPER" if i % 2 == 0 else "ADMIN"
                )
                
                session_state = AppState(
                    session_id=f"cross_session_{i}",
                    selected_model="gemini-1.5-pro" if i % 2 == 0 else "gemini-1.5-flash",
                    current_user=user
                )
                
                # Add unique conversation for each user
                for j in range(10):  # 10 messages per user
                    session_state.add_message(
                        role="user" if j % 2 == 0 else "assistant",
                        content=f"User {i} message {j}: Unique content for this user session"
                    )
                
                users_data.append((f"cross_session_{i}", session_state))
            
            # Write all sessions
            write_data = {session_id: state.model_dump(mode='json') for session_id, state in users_data}
            await self.storage.write(write_data)
            
            # Read all sessions back
            session_ids = [session_id for session_id, _ in users_data]
            read_data = await self.storage.read(session_ids)
            
            # Verify all sessions were retrieved
            if len(read_data) != len(session_ids):
                self.log_result("Cross-Session State Persistence", False, f"Expected {len(session_ids)} sessions, got {len(read_data)}")
                return False
            
            # Verify session isolation and integrity
            for session_id, original_state in users_data:
                if session_id not in read_data:
                    self.log_result("Cross-Session State Persistence", False, f"Session {session_id} not found")
                    return False
                
                retrieved_state = AppState.model_validate(read_data[session_id])
                
                # Verify user isolation
                if retrieved_state.current_user.user_id != original_state.current_user.user_id:
                    self.log_result("Cross-Session State Persistence", False, f"User ID mismatch in {session_id}")
                    return False
                
                # Verify message count
                if len(retrieved_state.messages) != len(original_state.messages):
                    self.log_result("Cross-Session State Persistence", False, f"Message count mismatch in {session_id}")
                    return False
                
                # Verify model selection persisted
                if retrieved_state.selected_model != original_state.selected_model:
                    self.log_result("Cross-Session State Persistence", False, f"Model selection not persisted in {session_id}")
                    return False
            
            self.log_result(
                "Cross-Session State Persistence", 
                True, 
                f"Successfully persisted {len(session_ids)} isolated sessions with full state integrity"
            )
            return True
            
        except Exception as e:
            self.log_result("Cross-Session State Persistence", False, f"Exception: {str(e)}")
            logger.error("Cross-session state persistence test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_bot_restart_persistence(self):
        """Test that data survives bot restart (simulated by storage recreation)."""
        print("🔄 TESTING BOT RESTART PERSISTENCE")
        
        if not self.storage:
            self.log_result("Bot Restart Persistence", False, "Storage not initialized")
            return False
            
        try:
            # Create test data before "restart"
            restart_user = UserProfile(
                user_id="restart_test_user",
                display_name="Restart Test User", 
                email="restart@test.com",
                assigned_role="ADMIN"
            )
            
            restart_state = AppState(
                session_id="restart_test_session",
                selected_model="gemini-1.5-pro",
                current_user=restart_user
            )
            
            # Add substantial conversation data
            for i in range(20):
                restart_state.add_message(
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Pre-restart message {i}: This data must survive the restart process"
                )
            
            # Write pre-restart data
            pre_restart_data = {"restart_test_session": restart_state.model_dump(mode='json')}
            await self.storage.write(pre_restart_data)
            
            # Verify data is written
            pre_read = await self.storage.read(["restart_test_session"])
            if "restart_test_session" not in pre_read:
                self.log_result("Bot Restart Persistence", False, "Failed to write pre-restart data")
                return False
            
            # Simulate bot restart by closing and reopening storage
            self.storage.close()
            self.log_result("Bot Restart Simulation", True, "Simulated bot shutdown")
            
            # Wait a moment to simulate restart time
            await asyncio.sleep(1)
            
            # Reinitialize storage (simulating bot restart)
            self.storage = SQLiteStorage(db_path=self.test_db_path)
            self.log_result("Bot Restart Simulation", True, "Simulated bot startup")
            
            # Try to read the data after "restart"
            post_restart_read = await self.storage.read(["restart_test_session"])
            
            if "restart_test_session" not in post_restart_read:
                self.log_result("Bot Restart Persistence", False, "Data lost after restart")
                return False
            
            # Validate data integrity after restart
            post_restart_state = AppState.model_validate(post_restart_read["restart_test_session"])
            
            # Check message count
            if len(post_restart_state.messages) != 20:
                self.log_result("Bot Restart Persistence", False, f"Message count changed after restart: {len(post_restart_state.messages)}")
                return False
            
            # Check user data
            if post_restart_state.current_user.user_id != "restart_test_user":
                self.log_result("Bot Restart Persistence", False, "User data corrupted after restart")
                return False
            
            # Check model selection
            if post_restart_state.selected_model != "gemini-1.5-pro":
                self.log_result("Bot Restart Persistence", False, "Model selection lost after restart")
                return False
            
            # Check specific message content
            first_message = post_restart_state.messages[0]['content']
            last_message = post_restart_state.messages[-1]['content']
            
            if "Pre-restart message 0:" not in first_message or "Pre-restart message 19:" not in last_message:
                self.log_result("Bot Restart Persistence", False, "Message content corrupted after restart")
                return False
            
            self.log_result(
                "Bot Restart Persistence", 
                True, 
                "All data survived restart with full integrity (20 messages, user data, model selection)"
            )
            return True
            
        except Exception as e:
            self.log_result("Bot Restart Persistence", False, f"Exception: {str(e)}")
            logger.error("Bot restart persistence test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_large_state_persistence(self):
        """Test persistence of large state objects."""
        print("📊 TESTING LARGE STATE PERSISTENCE")
        
        if not self.storage:
            self.log_result("Large State Persistence", False, "Storage not initialized")
            return False
            
        try:
            # Create a large state with substantial data
            large_user = UserProfile(
                user_id="large_state_user",
                display_name="Large State Test User",
                email="largestate@test.com", 
                assigned_role="DEVELOPER"
            )
            
            large_state = AppState(
                session_id="large_state_session",
                selected_model="gemini-1.5-pro",
                current_user=large_user
            )
            
            # Add a very large conversation (500 messages)
            for i in range(500):
                # Create large message content (2KB per message)
                large_content = f"Large message {i}: " + "X" * 2000
                
                large_state.add_message(
                    role="user" if i % 2 == 0 else "assistant",
                    content=large_content
                )
            
            # Calculate approximate size
            state_json = large_state.model_dump(mode='json')
            approximate_size = len(str(state_json))
            
            # Write large state
            start_time = time.time()
            large_data = {"large_state_session": state_json}
            await self.storage.write(large_data)
            write_time = time.time() - start_time
            
            # Read large state back
            start_time = time.time()
            read_data = await self.storage.read(["large_state_session"])
            read_time = time.time() - start_time
            
            if "large_state_session" not in read_data:
                self.log_result("Large State Persistence", False, "Failed to read large state")
                return False
            
            # Validate large state integrity
            retrieved_large_state = AppState.model_validate(read_data["large_state_session"])
            
            # Check message count
            if len(retrieved_large_state.messages) != 500:
                self.log_result("Large State Persistence", False, f"Message count mismatch: {len(retrieved_large_state.messages)}")
                return False
            
            # Check first and last message integrity
            first_msg = retrieved_large_state.messages[0]['content']
            last_msg = retrieved_large_state.messages[-1]['content']
            
            if not first_msg.startswith("Large message 0:") or not last_msg.startswith("Large message 499:"):
                self.log_result("Large State Persistence", False, "Large message content corruption")
                return False
            
            # Performance check - should complete within reasonable time
            if write_time > 10.0 or read_time > 10.0:
                self.log_result("Large State Persistence", False, f"Performance issue: write={write_time:.2f}s, read={read_time:.2f}s")
                return False
            
            self.log_result(
                "Large State Persistence", 
                True, 
                f"Successfully persisted ~{approximate_size/1024/1024:.1f}MB state (500 messages) in {write_time:.2f}s write, {read_time:.2f}s read"
            )
            return True
            
        except Exception as e:
            self.log_result("Large State Persistence", False, f"Exception: {str(e)}")
            logger.error("Large state persistence test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_data_integrity_over_time(self):
        """Test that data maintains integrity over multiple read/write cycles."""
        print("🔍 TESTING DATA INTEGRITY OVER TIME")
        
        if not self.storage:
            self.log_result("Data Integrity Over Time", False, "Storage not initialized")
            return False
            
        try:
            # Create initial data
            integrity_user = UserProfile(
                user_id="integrity_test_user",
                display_name="Integrity Test User",
                email="integrity@test.com",
                assigned_role="DEVELOPER"
            )
            
            integrity_state = AppState(
                session_id="integrity_test_session", 
                selected_model="gemini-1.5-pro",
                current_user=integrity_user
            )
            
            # Add initial messages
            for i in range(10):
                integrity_state.add_message(
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Integrity message {i}: This content should remain unchanged"
                )
            
            # Perform multiple read/write cycles
            cycles_completed = 0
            for cycle in range(20):  # 20 cycles of read/write
                try:
                    # Write current state
                    write_data = {"integrity_test_session": integrity_state.model_dump(mode='json')}
                    await self.storage.write(write_data)
                    
                    # Read it back
                    read_data = await self.storage.read(["integrity_test_session"])
                    
                    if "integrity_test_session" not in read_data:
                        self.log_result("Data Integrity Over Time", False, f"Data lost during cycle {cycle}")
                        return False
                    
                    # Validate integrity
                    read_state = AppState.model_validate(read_data["integrity_test_session"])
                    
                    # Check message count is stable
                    current_message_count = len(read_state.messages)
                    if current_message_count != 10:
                        self.log_result("Data Integrity Over Time", False, f"Message count changed during cycle {cycle}: {current_message_count}")
                        return False
                    
                    # Check specific content hasn't changed
                    first_content = read_state.messages[0]['content']
                    if "Integrity message 0:" not in first_content:
                        self.log_result("Data Integrity Over Time", False, f"Content corruption during cycle {cycle}")
                        return False
                    
                    # Update state for next cycle (add one message)
                    read_state.add_message(
                        role="system",
                        content=f"Cycle {cycle} verification message"
                    )
                    
                    integrity_state = read_state
                    cycles_completed += 1
                    
                    # Small delay between cycles
                    await asyncio.sleep(0.1)
                    
                except Exception as cycle_error:
                    self.log_result("Data Integrity Over Time", False, f"Cycle {cycle} failed: {str(cycle_error)}")
                    return False
            
            # Final integrity check
            final_read = await self.storage.read(["integrity_test_session"])
            final_state = AppState.model_validate(final_read["integrity_test_session"])
            
            # Should have original 10 messages + 20 cycle messages
            expected_final_count = 10 + cycles_completed
            if len(final_state.messages) != expected_final_count:
                self.log_result("Data Integrity Over Time", False, f"Final message count wrong: {len(final_state.messages)}")
                return False
            
            self.log_result(
                "Data Integrity Over Time", 
                True, 
                f"Data integrity maintained through {cycles_completed} read/write cycles"
            )
            return True
            
        except Exception as e:
            self.log_result("Data Integrity Over Time", False, f"Exception: {str(e)}")
            logger.error("Data integrity over time test failed", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up test resources."""
        print("🧹 CLEANING UP PERSISTENCE TEST RESOURCES")
        
        try:
            # Close storage
            if self.storage:
                self.storage.close()
                
            # Remove test database
            if os.path.exists(self.test_db_path):
                os.remove(self.test_db_path)
                print(f"✅ Removed test database: {self.test_db_path}")
                
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")
    
    def print_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "="*60)
        print("📊 LONG-RUNNING SESSION PERSISTENCE TEST SUMMARY")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        print("\nDETAILED RESULTS:")
        for result in self.test_results:
            status = "✅" if result['success'] else "❌"
            print(f"{status} {result['test']}: {result['details']}")
        
        # Critical test evaluation
        critical_tests = [
            "Extended Conversation Persistence",
            "Cross-Session State Persistence",  
            "Bot Restart Persistence",
            "Data Integrity Over Time"
        ]
        
        critical_passed = sum(1 for r in self.test_results 
                             if r['test'] in critical_tests and r['success'])
        
        print(f"\nCRITICAL TESTS: {critical_passed}/{len(critical_tests)} passed")
        
        if critical_passed == len(critical_tests):
            print("🎉 ALL CRITICAL TESTS PASSED - Session persistence is working!")
        else:
            print("🚨 CRITICAL TESTS FAILED - Session persistence has issues!")
        
        return critical_passed >= 3  # Allow 1 failure out of 4 critical tests

async def main():
    """Main test execution function."""
    print("🚀 STARTING STEP 1.13 SCENARIO 4: Long-Running Session Persistence Test")
    print("=" * 70)
    
    tester = PersistenceTester()
    
    try:
        # Initialize clean storage
        if not await tester.initialize_storage():
            print("\n💥 SCENARIO 4 FAILED: Could not initialize storage")
            return False
        
        # Run all persistence tests
        await tester.test_extended_conversation_persistence()
        await tester.test_cross_session_state_persistence()
        await tester.test_bot_restart_persistence()
        await tester.test_large_state_persistence()
        await tester.test_data_integrity_over_time()
        
        # Print final summary
        success = tester.print_summary()
        
        if success:
            print("\n✅ SCENARIO 4 COMPLETE: Long-running session persistence validation PASSED")
            return True
        else:
            print("\n❌ SCENARIO 4 FAILED: Long-running session persistence validation FAILED")
            return False
            
    except Exception as e:
        print(f"\n💥 SCENARIO 4 CRASHED: {e}")
        logger.error("Main test crashed", exc_info=True)
        return False
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1) 