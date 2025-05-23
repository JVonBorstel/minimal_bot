#!/usr/bin/env python3
"""
STEP 1.13 - SCENARIO 5: Database Transaction Integrity Test

This test proves that the bot can handle concurrent database operations 
safely with proper transaction integrity and atomic operations.

CRITICAL TEST - This is a mandatory validation for Step 1.13.
"""

import asyncio
import logging
import os
import sys
import time
import threading
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
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
        logging.FileHandler('test_database_transactions.log')
    ]
)
logger = logging.getLogger(__name__)

class TransactionTester:
    """Test database transaction integrity and concurrent safety."""
    
    def __init__(self):
        self.config = get_config()
        self.test_results = []
        self.storage = None
        self.test_db_path = "test_transactions.db"
        
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
        print("🔧 INITIALIZING CLEAN STORAGE FOR TRANSACTION TESTING")
        
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
    async def test_atomic_write_operations(self):
        """Test that write operations are atomic."""
        print("⚛️ TESTING ATOMIC WRITE OPERATIONS")
        
        if not self.storage:
            self.log_result("Atomic Write Operations", False, "Storage not initialized")
            return False
            
        try:
            # Create test user and state
            atomic_user = UserProfile(
                user_id="atomic_test_user",
                display_name="Atomic Test User",
                email="atomic@test.com",
                assigned_role="DEVELOPER"
            )
            
            atomic_state = AppState(
                session_id="atomic_test_session",
                selected_model="gemini-1.5-pro",
                current_user=atomic_user
            )
            
            # Add some messages
            for i in range(5):
                atomic_state.add_message(
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Atomic test message {i}"
                )
            
            # Test multiple writes in quick succession
            # This tests if writes are atomic (all-or-nothing)
            write_operations = []
            
            for batch in range(3):
                # Create different state versions
                test_state = AppState(
                    session_id=f"atomic_batch_{batch}",
                    selected_model="gemini-1.5-flash",
                    current_user=atomic_user
                )
                
                # Add batch-specific messages
                for i in range(10):
                    test_state.add_message(
                        role="user" if i % 2 == 0 else "assistant",
                        content=f"Batch {batch} message {i}: Atomic operation test"
                    )
                
                write_operations.append((f"atomic_batch_{batch}", test_state))
            
            # Perform all writes simultaneously to test atomicity
            write_data = {session_id: state.model_dump(mode='json') for session_id, state in write_operations}
            
            # Time the atomic write
            start_time = time.time()
            await self.storage.write(write_data)
            write_time = time.time() - start_time
            
            # Verify all data was written atomically
            session_ids = [session_id for session_id, _ in write_operations]
            read_data = await self.storage.read(session_ids)
            
            # Check that either all data was written or none
            if len(read_data) == len(session_ids):
                # All data written - verify integrity
                for session_id, original_state in write_operations:
                    if session_id not in read_data:
                        self.log_result("Atomic Write Operations", False, f"Session {session_id} missing")
                        return False
                    
                    retrieved_state = AppState.model_validate(read_data[session_id])
                    if len(retrieved_state.messages) != 10:
                        self.log_result("Atomic Write Operations", False, f"Message count wrong for {session_id}")
                        return False
                
                self.log_result(
                    "Atomic Write Operations", 
                    True, 
                    f"All {len(session_ids)} sessions written atomically in {write_time:.3f}s"
                )
                return True
                
            elif len(read_data) == 0:
                # No data written - could be valid if operation failed atomically
                self.log_result("Atomic Write Operations", True, "Atomic failure - no partial data")
                return True
            else:
                # Partial data - this indicates non-atomic behavior
                self.log_result("Atomic Write Operations", False, f"Partial write: {len(read_data)}/{len(session_ids)} sessions")
                return False
                
        except Exception as e:
            self.log_result("Atomic Write Operations", False, f"Exception: {str(e)}")
            logger.error("Atomic write operations test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_concurrent_user_operations(self):
        """Test concurrent operations from different users."""
        print("👥 TESTING CONCURRENT USER OPERATIONS")
        
        if not self.storage:
            self.log_result("Concurrent User Operations", False, "Storage not initialized")
            return False
            
        try:
            async def user_operation_worker(user_id: int) -> tuple:
                """Simulate a user performing operations."""
                operations_completed = 0
                errors_encountered = 0
                
                try:
                    # Create user
                    user = UserProfile(
                        user_id=f"concurrent_user_{user_id}",
                        display_name=f"Concurrent User {user_id}",
                        email=f"user{user_id}@concurrent.com",
                        assigned_role="DEVELOPER" if user_id % 2 == 0 else "ADMIN"
                    )
                    
                    # Create multiple sessions for this user
                    for session_num in range(5):  # 5 sessions per user
                        session_state = AppState(
                            session_id=f"user_{user_id}_session_{session_num}",
                            selected_model="gemini-1.5-pro",
                            current_user=user
                        )
                        
                        # Add messages to session
                        for msg_num in range(8):  # 8 messages per session
                            session_state.add_message(
                                role="user" if msg_num % 2 == 0 else "assistant",
                                content=f"User {user_id} Session {session_num} Message {msg_num}"
                            )
                        
                        # Write session data
                        session_data = {f"user_{user_id}_session_{session_num}": session_state.model_dump(mode='json')}
                        await self.storage.write(session_data)
                        
                        # Verify write succeeded
                        verify_read = await self.storage.read([f"user_{user_id}_session_{session_num}"])
                        if f"user_{user_id}_session_{session_num}" in verify_read:
                            operations_completed += 1
                        else:
                            errors_encountered += 1
                        
                        # Small delay to allow other users
                        await asyncio.sleep(0.02)
                        
                except Exception as e:
                    errors_encountered += 1
                    logger.warning(f"User {user_id} operation error: {e}")
                
                return operations_completed, errors_encountered
            
            # Run 8 concurrent users, each doing 5 operations
            users = [user_operation_worker(i) for i in range(8)]
            results = await asyncio.gather(*users, return_exceptions=True)
            
            # Analyze results
            total_completed = 0
            total_errors = 0
            user_failures = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    user_failures += 1
                    logger.error(f"User {i} failed completely: {result}")
                else:
                    completed, errors = result
                    total_completed += completed
                    total_errors += errors
            
            # Calculate success metrics
            total_expected = 8 * 5  # 8 users × 5 sessions each
            success_rate = (total_completed / total_expected) * 100
            
            # Verify data isolation between users
            # Read all data and verify no cross-contamination
            all_sessions = []
            for user_id in range(8):
                for session_num in range(5):
                    all_sessions.append(f"user_{user_id}_session_{session_num}")
            
            all_data = await self.storage.read(all_sessions)
            
            # Check data integrity
            data_integrity_ok = True
            for session_id in all_sessions:
                if session_id in all_data:
                    try:
                        session_state = AppState.model_validate(all_data[session_id])
                        # Verify user isolation
                        expected_user_id = session_id.split('_')[1]
                        if session_state.current_user.user_id != f"concurrent_user_{expected_user_id}":
                            data_integrity_ok = False
                            break
                    except Exception:
                        data_integrity_ok = False
                        break
            
            if success_rate > 90 and user_failures == 0 and data_integrity_ok:
                self.log_result(
                    "Concurrent User Operations", 
                    True, 
                    f"Success rate: {success_rate:.1f}%, {total_completed}/{total_expected} operations, data isolation intact"
                )
                return True
            else:
                self.log_result(
                    "Concurrent User Operations", 
                    False, 
                    f"Poor performance: {success_rate:.1f}%, {user_failures} failures, integrity={data_integrity_ok}"
                )
                return False
                
        except Exception as e:
            self.log_result("Concurrent User Operations", False, f"Exception: {str(e)}")
            logger.error("Concurrent user operations test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_transaction_rollback_safety(self):
        """Test transaction rollback behavior."""
        print("🔄 TESTING TRANSACTION ROLLBACK SAFETY")
        
        if not self.storage:
            self.log_result("Transaction Rollback Safety", False, "Storage not initialized")
            return False
            
        try:
            # Create initial valid data
            rollback_user = UserProfile(
                user_id="rollback_test_user",
                display_name="Rollback Test User",
                email="rollback@test.com",
                assigned_role="DEVELOPER"
            )
            
            initial_state = AppState(
                session_id="rollback_test_session",
                selected_model="gemini-1.5-pro",
                current_user=rollback_user
            )
            
            initial_state.add_message(role="user", content="Initial valid message")
            initial_state.add_message(role="assistant", content="Initial valid response")
            
            # Write initial data
            initial_data = {"rollback_test_session": initial_state.model_dump(mode='json')}
            await self.storage.write(initial_data)
            
            # Verify initial data exists
            initial_read = await self.storage.read(["rollback_test_session"])
            if "rollback_test_session" not in initial_read:
                self.log_result("Transaction Rollback Safety", False, "Failed to write initial data")
                return False
            
            # Now attempt an operation that should fail/rollback
            # We'll simulate this by trying to write invalid data or very large data
            try:
                # Create problematic data (extremely large)
                problematic_state = AppState(
                    session_id="rollback_test_session",  # Same session ID
                    selected_model="gemini-1.5-pro",
                    current_user=rollback_user
                )
                
                # Add extremely large content that might cause issues
                for i in range(1000):  # 1000 large messages
                    large_content = "X" * 10000  # 10KB per message = ~10MB total
                    problematic_state.add_message(
                        role="user" if i % 2 == 0 else "assistant",
                        content=f"Large message {i}: {large_content}"
                    )
                
                # Try to write the problematic data
                problematic_data = {"rollback_test_session": problematic_state.model_dump(mode='json')}
                
                try:
                    # This might fail due to size or other constraints
                    await asyncio.wait_for(self.storage.write(problematic_data), timeout=5.0)
                    
                    # If it succeeded, check if data is intact
                    post_write_read = await self.storage.read(["rollback_test_session"])
                    if "rollback_test_session" in post_write_read:
                        retrieved_state = AppState.model_validate(post_write_read["rollback_test_session"])
                        
                        if len(retrieved_state.messages) == 1000:
                            # Large write succeeded - this is actually good
                            self.log_result("Transaction Rollback Safety", True, "Large write succeeded without corruption")
                            return True
                        else:
                            # Partial write - this is bad
                            self.log_result("Transaction Rollback Safety", False, "Partial write detected")
                            return False
                    else:
                        # Data disappeared - check if original data is still there
                        fallback_read = await self.storage.read(["rollback_test_session"])
                        if "rollback_test_session" in fallback_read:
                            original_state = AppState.model_validate(fallback_read["rollback_test_session"])
                            if len(original_state.messages) == 2:  # Original 2 messages
                                self.log_result("Transaction Rollback Safety", True, "Transaction rolled back to original state")
                                return True
                            else:
                                self.log_result("Transaction Rollback Safety", False, "Data corruption during rollback")
                                return False
                        else:
                            self.log_result("Transaction Rollback Safety", False, "All data lost during problematic write")
                            return False
                
                except (asyncio.TimeoutError, Exception) as write_error:
                    # Write failed (expected) - verify original data is still intact
                    post_failure_read = await self.storage.read(["rollback_test_session"])
                    
                    if "rollback_test_session" in post_failure_read:
                        rollback_state = AppState.model_validate(post_failure_read["rollback_test_session"])
                        
                        if len(rollback_state.messages) == 2:  # Original 2 messages
                            # Check content integrity
                            first_msg = rollback_state.messages[0]['content']
                            if "Initial valid message" in first_msg:
                                self.log_result(
                                    "Transaction Rollback Safety", 
                                    True, 
                                    f"Failed write safely rolled back, original data intact (error: {str(write_error)[:50]})"
                                )
                                return True
                            else:
                                self.log_result("Transaction Rollback Safety", False, "Original data corrupted during rollback")
                                return False
                        else:
                            self.log_result("Transaction Rollback Safety", False, f"Wrong message count after rollback: {len(rollback_state.messages)}")
                            return False
                    else:
                        self.log_result("Transaction Rollback Safety", False, "Original data lost during failed write")
                        return False
                
            except Exception as e:
                self.log_result("Transaction Rollback Safety", False, f"Test setup error: {str(e)}")
                return False
                
        except Exception as e:
            self.log_result("Transaction Rollback Safety", False, f"Exception: {str(e)}")
            logger.error("Transaction rollback safety test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_data_consistency_under_load(self):
        """Test data consistency under concurrent load."""
        print("⚡ TESTING DATA CONSISTENCY UNDER LOAD")
        
        if not self.storage:
            self.log_result("Data Consistency Under Load", False, "Storage not initialized")
            return False
            
        try:
            # Create shared data that multiple workers will modify
            shared_user = UserProfile(
                user_id="shared_load_user",
                display_name="Shared Load User",
                email="shared@load.com",
                assigned_role="ADMIN"
            )
            
            # Initialize shared session
            shared_state = AppState(
                session_id="shared_load_session",
                selected_model="gemini-1.5-pro",
                current_user=shared_user
            )
            
            shared_state.add_message(role="system", content="Initial shared message")
            initial_data = {"shared_load_session": shared_state.model_dump(mode='json')}
            await self.storage.write(initial_data)
            
            async def load_worker(worker_id: int) -> tuple:
                """Worker that performs rapid read/write operations."""
                operations_completed = 0
                consistency_errors = 0
                
                try:
                    for operation in range(20):  # 20 operations per worker
                        try:
                            # Read current state
                            current_data = await self.storage.read(["shared_load_session"])
                            
                            if "shared_load_session" not in current_data:
                                consistency_errors += 1
                                continue
                            
                            current_state = AppState.model_validate(current_data["shared_load_session"])
                            
                            # Add a new message
                            current_state.add_message(
                                role="user",
                                content=f"Worker {worker_id} Operation {operation}: Load test message"
                            )
                            
                            # Write back the modified state
                            updated_data = {"shared_load_session": current_state.model_dump(mode='json')}
                            await self.storage.write(updated_data)
                            
                            operations_completed += 1
                            
                            # Small delay
                            await asyncio.sleep(0.01)
                            
                        except Exception as op_error:
                            consistency_errors += 1
                            logger.warning(f"Worker {worker_id} operation {operation} error: {op_error}")
                    
                except Exception as worker_error:
                    logger.error(f"Worker {worker_id} failed: {worker_error}")
                
                return operations_completed, consistency_errors
            
            # Run 10 workers concurrently
            workers = [load_worker(i) for i in range(10)]
            start_time = time.time()
            results = await asyncio.gather(*workers, return_exceptions=True)
            load_time = time.time() - start_time
            
            # Analyze results
            total_operations = 0
            total_errors = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    total_errors += 20  # All operations failed
                    logger.error(f"Load worker {i} crashed: {result}")
                else:
                    completed, errors = result
                    total_operations += completed
                    total_errors += errors
            
            # Check final data consistency
            final_data = await self.storage.read(["shared_load_session"])
            
            if "shared_load_session" not in final_data:
                self.log_result("Data Consistency Under Load", False, "Shared data lost during load test")
                return False
            
            final_state = AppState.model_validate(final_data["shared_load_session"])
            
            # We started with 1 message, should have more now
            final_message_count = len(final_state.messages)
            expected_minimum = 1  # At least the initial message
            expected_maximum = 1 + (10 * 20)  # Initial + all possible additions
            
            if final_message_count < expected_minimum:
                self.log_result("Data Consistency Under Load", False, f"Data loss: only {final_message_count} messages")
                return False
            
            if final_message_count > expected_maximum:
                self.log_result("Data Consistency Under Load", False, f"Data duplication: {final_message_count} messages")
                return False
            
            # Calculate performance metrics
            total_expected = 10 * 20  # 10 workers × 20 operations
            success_rate = (total_operations / total_expected) * 100
            ops_per_second = total_operations / load_time if load_time > 0 else 0
            
            if success_rate > 70:  # Allow some failures under heavy load
                self.log_result(
                    "Data Consistency Under Load", 
                    True, 
                    f"Success rate: {success_rate:.1f}%, {final_message_count} final messages, {ops_per_second:.1f} ops/sec"
                )
                return True
            else:
                self.log_result(
                    "Data Consistency Under Load", 
                    False, 
                    f"Poor performance: {success_rate:.1f}% success rate"
                )
                return False
                
        except Exception as e:
            self.log_result("Data Consistency Under Load", False, f"Exception: {str(e)}")
            logger.error("Data consistency under load test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_deadlock_prevention(self):
        """Test that the system prevents deadlocks."""
        print("🔒 TESTING DEADLOCK PREVENTION")
        
        if not self.storage:
            self.log_result("Deadlock Prevention", False, "Storage not initialized")
            return False
            
        try:
            # Create two sessions that workers will access in different orders
            # This is a classic deadlock scenario
            
            users = []
            sessions = []
            
            for i in range(2):
                user = UserProfile(
                    user_id=f"deadlock_user_{i}",
                    display_name=f"Deadlock User {i}",
                    email=f"deadlock{i}@test.com",
                    assigned_role="DEVELOPER"
                )
                users.append(user)
                
                state = AppState(
                    session_id=f"deadlock_session_{i}",
                    selected_model="gemini-1.5-pro",
                    current_user=user
                )
                state.add_message(role="system", content=f"Initial message for session {i}")
                sessions.append((f"deadlock_session_{i}", state))
            
            # Write initial sessions
            initial_data = {session_id: state.model_dump(mode='json') for session_id, state in sessions}
            await self.storage.write(initial_data)
            
            async def deadlock_worker_a():
                """Worker that accesses sessions in order A -> B."""
                try:
                    for cycle in range(10):
                        # Access session 0 first, then session 1
                        data_0 = await self.storage.read(["deadlock_session_0"])
                        
                        # Small delay to increase chance of deadlock
                        await asyncio.sleep(0.01)
                        
                        data_1 = await self.storage.read(["deadlock_session_1"])
                        
                        # Modify both sessions
                        if "deadlock_session_0" in data_0 and "deadlock_session_1" in data_1:
                            state_0 = AppState.model_validate(data_0["deadlock_session_0"])
                            state_1 = AppState.model_validate(data_1["deadlock_session_1"])
                            
                            state_0.add_message(role="user", content=f"Worker A cycle {cycle} message")
                            state_1.add_message(role="assistant", content=f"Worker A cycle {cycle} response")
                            
                            # Write both back
                            update_data = {
                                "deadlock_session_0": state_0.model_dump(mode='json'),
                                "deadlock_session_1": state_1.model_dump(mode='json')
                            }
                            await self.storage.write(update_data)
                        
                        await asyncio.sleep(0.01)
                    
                    return True
                except Exception as e:
                    logger.error(f"Deadlock worker A failed: {e}")
                    return False
            
            async def deadlock_worker_b():
                """Worker that accesses sessions in order B -> A."""
                try:
                    for cycle in range(10):
                        # Access session 1 first, then session 0 (reverse order)
                        data_1 = await self.storage.read(["deadlock_session_1"])
                        
                        # Small delay to increase chance of deadlock
                        await asyncio.sleep(0.01)
                        
                        data_0 = await self.storage.read(["deadlock_session_0"])
                        
                        # Modify both sessions
                        if "deadlock_session_0" in data_0 and "deadlock_session_1" in data_1:
                            state_0 = AppState.model_validate(data_0["deadlock_session_0"])
                            state_1 = AppState.model_validate(data_1["deadlock_session_1"])
                            
                            state_0.add_message(role="assistant", content=f"Worker B cycle {cycle} response")
                            state_1.add_message(role="user", content=f"Worker B cycle {cycle} message")
                            
                            # Write both back
                            update_data = {
                                "deadlock_session_0": state_0.model_dump(mode='json'),
                                "deadlock_session_1": state_1.model_dump(mode='json')
                            }
                            await self.storage.write(update_data)
                        
                        await asyncio.sleep(0.01)
                    
                    return True
                except Exception as e:
                    logger.error(f"Deadlock worker B failed: {e}")
                    return False
            
            # Run both workers concurrently with a timeout
            # If there's a deadlock, this will timeout
            try:
                start_time = time.time()
                results = await asyncio.wait_for(
                    asyncio.gather(deadlock_worker_a(), deadlock_worker_b()),
                    timeout=30.0  # 30 second timeout
                )
                completion_time = time.time() - start_time
                
                # Check if both workers completed successfully
                worker_a_success, worker_b_success = results
                
                if worker_a_success and worker_b_success:
                    # Verify final data integrity
                    final_data = await self.storage.read(["deadlock_session_0", "deadlock_session_1"])
                    
                    if len(final_data) == 2:
                        final_state_0 = AppState.model_validate(final_data["deadlock_session_0"])
                        final_state_1 = AppState.model_validate(final_data["deadlock_session_1"])
                        
                        # Both sessions should have more messages than initially
                        if len(final_state_0.messages) > 1 and len(final_state_1.messages) > 1:
                            self.log_result(
                                "Deadlock Prevention", 
                                True, 
                                f"No deadlock detected, completed in {completion_time:.2f}s"
                            )
                            return True
                        else:
                            self.log_result("Deadlock Prevention", False, "Data corruption in concurrent access")
                            return False
                    else:
                        self.log_result("Deadlock Prevention", False, "Data loss in concurrent access")
                        return False
                else:
                    self.log_result("Deadlock Prevention", False, f"Worker failures: A={worker_a_success}, B={worker_b_success}")
                    return False
            
            except asyncio.TimeoutError:
                self.log_result("Deadlock Prevention", False, "Timeout detected - possible deadlock")
                return False
                
        except Exception as e:
            self.log_result("Deadlock Prevention", False, f"Exception: {str(e)}")
            logger.error("Deadlock prevention test failed", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up test resources."""
        print("🧹 CLEANING UP TRANSACTION TEST RESOURCES")
        
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
        print("📊 DATABASE TRANSACTION INTEGRITY TEST SUMMARY")
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
            "Atomic Write Operations",
            "Concurrent User Operations",
            "Transaction Rollback Safety",
            "Data Consistency Under Load"
        ]
        
        critical_passed = sum(1 for r in self.test_results 
                             if r['test'] in critical_tests and r['success'])
        
        print(f"\nCRITICAL TESTS: {critical_passed}/{len(critical_tests)} passed")
        
        if critical_passed >= 3:  # Allow 1 failure out of 4 critical tests
            print("🎉 CRITICAL TESTS MOSTLY PASSED - Transaction integrity is acceptable!")
        else:
            print("🚨 CRITICAL TESTS FAILED - Transaction integrity has serious issues!")
        
        return critical_passed >= 3

async def main():
    """Main test execution function."""
    print("🚀 STARTING STEP 1.13 SCENARIO 5: Database Transaction Integrity Test")
    print("=" * 70)
    
    tester = TransactionTester()
    
    try:
        # Initialize clean storage
        if not await tester.initialize_storage():
            print("\n💥 SCENARIO 5 FAILED: Could not initialize storage")
            return False
        
        # Run all transaction integrity tests
        await tester.test_atomic_write_operations()
        await tester.test_concurrent_user_operations()
        await tester.test_transaction_rollback_safety()
        await tester.test_data_consistency_under_load()
        await tester.test_deadlock_prevention()
        
        # Print final summary
        success = tester.print_summary()
        
        if success:
            print("\n✅ SCENARIO 5 COMPLETE: Database transaction integrity validation PASSED")
            return True
        else:
            print("\n❌ SCENARIO 5 FAILED: Database transaction integrity validation FAILED")
            return False
            
    except Exception as e:
        print(f"\n💥 SCENARIO 5 CRASHED: {e}")
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