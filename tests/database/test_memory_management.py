#!/usr/bin/env python3
"""
STEP 1.13 - SCENARIO 2: Memory Management Under Load Test

This test proves that the bot can handle heavy operations without memory leaks
and maintains stable memory usage under extended operation.

CRITICAL TEST - This is a mandatory validation for Step 1.13.
"""

import asyncio
import logging
import os
import sys
import time
import gc
import threading
from typing import Dict, Any, List, Optional

# Memory monitoring
import psutil

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from state_models import AppState, UserProfile
from bot_core.my_bot import SQLiteStorage
from tools.tool_executor import ToolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_memory_management.log')
    ]
)
logger = logging.getLogger(__name__)

class MemoryMonitor:
    """Monitor memory usage over time."""
    
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.monitoring = False
        self.measurements = []
        self.process = psutil.Process()
        self.monitor_thread = None
        
    def start_monitoring(self):
        """Start memory monitoring in background thread."""
        self.monitoring = True
        self.measurements = []
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """Stop memory monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
            
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.monitoring:
            try:
                memory_info = self.process.memory_info()
                memory_percent = self.process.memory_percent()
                
                measurement = {
                    'timestamp': time.time(),
                    'rss_mb': memory_info.rss / 1024 / 1024,  # Resident Set Size in MB
                    'vms_mb': memory_info.vms / 1024 / 1024,  # Virtual Memory Size in MB
                    'percent': memory_percent,
                    'available_mb': psutil.virtual_memory().available / 1024 / 1024
                }
                self.measurements.append(measurement)
                
            except Exception as e:
                logger.warning(f"Memory monitoring error: {e}")
                
            time.sleep(self.interval)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get memory usage summary."""
        if not self.measurements:
            return {}
            
        rss_values = [m['rss_mb'] for m in self.measurements]
        vms_values = [m['vms_mb'] for m in self.measurements]
        percent_values = [m['percent'] for m in self.measurements]
        
        return {
            'duration_seconds': self.measurements[-1]['timestamp'] - self.measurements[0]['timestamp'],
            'total_measurements': len(self.measurements),
            'rss_mb': {
                'start': rss_values[0],
                'end': rss_values[-1],
                'min': min(rss_values),
                'max': max(rss_values),
                'avg': sum(rss_values) / len(rss_values),
                'growth': rss_values[-1] - rss_values[0]
            },
            'vms_mb': {
                'start': vms_values[0],
                'end': vms_values[-1], 
                'min': min(vms_values),
                'max': max(vms_values),
                'avg': sum(vms_values) / len(vms_values),
                'growth': vms_values[-1] - vms_values[0]
            },
            'memory_percent': {
                'start': percent_values[0],
                'end': percent_values[-1],
                'min': min(percent_values),
                'max': max(percent_values),
                'avg': sum(percent_values) / len(percent_values),
                'growth': percent_values[-1] - percent_values[0]
            }
        }

class MemoryLoadTester:
    """Comprehensive memory management and load tester."""
    
    def __init__(self):
        self.config = get_config()
        self.test_results = []
        self.storage = None
        self.tool_executor = None
        self.monitor = MemoryMonitor(interval=0.5)  # Monitor every 0.5 seconds
        
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
        
    async def test_baseline_memory_usage(self):
        """Establish baseline memory usage."""
        print("📊 TESTING BASELINE MEMORY USAGE")
        
        try:
            # Force garbage collection before baseline
            gc.collect()
            
            # Get initial memory
            process = psutil.Process()
            initial_memory = process.memory_info()
            
            self.log_result(
                "Baseline Memory Measurement",
                True,
                f"RSS: {initial_memory.rss / 1024 / 1024:.2f} MB, VMS: {initial_memory.vms / 1024 / 1024:.2f} MB"
            )
            
            # Initialize core components
            db_path = "test_memory_load.db"
            if os.path.exists(db_path):
                os.remove(db_path)
                
            self.storage = SQLiteStorage(db_path=db_path)
            self.tool_executor = ToolExecutor(self.config)
            
            # Memory after initialization
            post_init_memory = process.memory_info()
            init_growth = (post_init_memory.rss - initial_memory.rss) / 1024 / 1024
            
            self.log_result(
                "Post-Initialization Memory",
                True,
                f"Growth: {init_growth:.2f} MB, RSS: {post_init_memory.rss / 1024 / 1024:.2f} MB"
            )
            
            return True
            
        except Exception as e:
            self.log_result("Baseline Memory Measurement", False, f"Exception: {str(e)}")
            logger.error("Baseline memory test failed", exc_info=True)
            return False
    
    async def test_heavy_database_operations(self):
        """Test memory usage under heavy database operations."""
        print("💾 TESTING HEAVY DATABASE OPERATIONS")
        
        if not self.storage:
            self.log_result("Heavy Database Operations", False, "Storage not initialized")
            return False
            
        try:
            self.monitor.start_monitoring()
            
            # Create many user profiles and states
            user_profiles = []
            app_states = []
            
            for i in range(100):  # Create 100 users
                user = UserProfile(
                    user_id=f"load_test_user_{i}",
                    display_name=f"Load Test User {i}",
                    email=f"loadtest{i}@test.com",
                    assigned_role="DEVELOPER" if i % 2 == 0 else "STAKEHOLDER"
                )
                user_profiles.append(user)
                
                # Create app state with multiple messages
                app_state = AppState(
                    session_id=f"load_test_session_{i}",
                    selected_model="gemini-1.5-pro",
                    current_user=user
                )
                
                # Add multiple messages to each state
                for j in range(20):  # 20 messages per user
                    app_state.add_message(
                        role="user" if j % 2 == 0 else "assistant",
                        content=f"Load test message {j} for user {i}. This is a longer message to simulate real conversation data with more content and complexity."
                    )
                
                app_states.append(app_state)
            
            # Write all states to database
            write_data = {}
            for i, state in enumerate(app_states):
                write_data[f"load_test_session_{i}"] = state.model_dump(mode='json')
                
            await self.storage.write(write_data)
            
            # Read all states back
            read_keys = [f"load_test_session_{i}" for i in range(100)]
            read_data = await self.storage.read(read_keys)
            
            # Perform updates
            for i in range(50):  # Update half the states
                state = app_states[i]
                state.add_message(role="user", content=f"Updated message for load test {i}")
                update_data = {f"load_test_session_{i}": state.model_dump(mode='json')}
                await self.storage.write(update_data)
            
            # Stop monitoring and analyze
            self.monitor.stop_monitoring()
            memory_summary = self.monitor.get_summary()
            
            # Validate results
            if len(read_data) == 100:
                memory_growth = memory_summary['rss_mb']['growth']
                max_memory = memory_summary['rss_mb']['max']
                
                # Memory growth should be reasonable (less than 500MB for this test)
                if memory_growth < 500 and max_memory < 1000:
                    self.log_result(
                        "Heavy Database Operations",
                        True,
                        f"Processed 100 users, 2000 messages. Memory growth: {memory_growth:.2f} MB, Max: {max_memory:.2f} MB"
                    )
                else:
                    self.log_result(
                        "Heavy Database Operations",
                        False,
                        f"Excessive memory usage. Growth: {memory_growth:.2f} MB, Max: {max_memory:.2f} MB"
                    )
            else:
                self.log_result("Heavy Database Operations", False, f"Data integrity issue: {len(read_data)}/100 records")
                
            return True
            
        except Exception as e:
            self.monitor.stop_monitoring()
            self.log_result("Heavy Database Operations", False, f"Exception: {str(e)}")
            logger.error("Heavy database operations test failed", exc_info=True)
            return False
    
    async def test_extended_operation_memory_stability(self):
        """Test memory stability over extended operation period."""
        print("⏱️ TESTING EXTENDED OPERATION MEMORY STABILITY")
        
        if not self.storage:
            self.log_result("Extended Operation Stability", False, "Storage not initialized")
            return False
            
        try:
            # Start memory monitoring
            self.monitor.start_monitoring()
            
            # Run operations for extended period (2 minutes)
            start_time = time.time()
            operation_count = 0
            
            while (time.time() - start_time) < 120:  # Run for 2 minutes
                # Simulate realistic bot operations
                
                # Create temporary user and state
                temp_user = UserProfile(
                    user_id=f"temp_user_{operation_count}",
                    display_name=f"Temp User {operation_count}",
                    email=f"temp{operation_count}@test.com",
                    assigned_role="DEVELOPER"
                )
                
                temp_state = AppState(
                    session_id=f"temp_session_{operation_count}",
                    selected_model="gemini-1.5-flash",
                    current_user=temp_user
                )
                
                # Add messages
                for i in range(5):
                    temp_state.add_message(
                        role="user" if i % 2 == 0 else "assistant",
                        content=f"Extended test message {i} for operation {operation_count}"
                    )
                
                # Write to database
                temp_data = {f"temp_session_{operation_count}": temp_state.model_dump(mode='json')}
                await self.storage.write(temp_data)
                
                # Read back
                read_data = await self.storage.read([f"temp_session_{operation_count}"])
                
                # Clean up every 10 operations to prevent indefinite growth
                if operation_count % 10 == 0:
                    # Delete old temp data
                    delete_keys = [f"temp_session_{i}" for i in range(max(0, operation_count - 20), operation_count)]
                    if delete_keys:
                        await self.storage.delete(delete_keys)
                    
                    # Force garbage collection
                    gc.collect()
                
                operation_count += 1
                
                # Small delay to prevent overwhelming
                await asyncio.sleep(0.1)
            
            # Stop monitoring
            self.monitor.stop_monitoring()
            memory_summary = self.monitor.get_summary()
            
            # Analyze memory stability
            memory_growth = memory_summary['rss_mb']['growth']
            max_memory = memory_summary['rss_mb']['max']
            duration = memory_summary['duration_seconds']
            
            # Memory growth should be minimal for extended operation
            growth_rate_mb_per_minute = (memory_growth / duration) * 60
            
            if growth_rate_mb_per_minute < 10:  # Less than 10MB/minute growth
                self.log_result(
                    "Extended Operation Stability",
                    True,
                    f"Ran {operation_count} operations over {duration:.1f}s. Growth rate: {growth_rate_mb_per_minute:.2f} MB/min"
                )
            else:
                self.log_result(
                    "Extended Operation Stability",
                    False,
                    f"Memory leak detected. Growth rate: {growth_rate_mb_per_minute:.2f} MB/min"
                )
                
            return True
            
        except Exception as e:
            self.monitor.stop_monitoring()
            self.log_result("Extended Operation Stability", False, f"Exception: {str(e)}")
            logger.error("Extended operation stability test failed", exc_info=True)
            return False
    
    async def test_concurrent_memory_operations(self):
        """Test memory behavior under concurrent operations."""
        print("🔄 TESTING CONCURRENT MEMORY OPERATIONS")
        
        if not self.storage:
            self.log_result("Concurrent Memory Operations", False, "Storage not initialized")
            return False
            
        try:
            self.monitor.start_monitoring()
            
            async def worker_task(worker_id: int):
                """Individual worker task."""
                for i in range(20):  # Each worker does 20 operations
                    user = UserProfile(
                        user_id=f"worker_{worker_id}_user_{i}",
                        display_name=f"Worker {worker_id} User {i}",
                        email=f"worker{worker_id}user{i}@test.com",
                        assigned_role="DEVELOPER"
                    )
                    
                    state = AppState(
                        session_id=f"worker_{worker_id}_session_{i}",
                        selected_model="gemini-1.5-pro",
                        current_user=user
                    )
                    
                    # Add messages
                    for j in range(3):
                        state.add_message(
                            role="user" if j % 2 == 0 else "assistant",
                            content=f"Concurrent worker {worker_id} message {j} operation {i}"
                        )
                    
                    # Database operations
                    key = f"worker_{worker_id}_session_{i}"
                    data = {key: state.model_dump(mode='json')}
                    await self.storage.write(data)
                    
                    # Read back to verify
                    read_data = await self.storage.read([key])
                    
                    # Small delay
                    await asyncio.sleep(0.05)
            
            # Run 5 concurrent workers
            workers = [worker_task(i) for i in range(5)]
            await asyncio.gather(*workers)
            
            self.monitor.stop_monitoring()
            memory_summary = self.monitor.get_summary()
            
            memory_growth = memory_summary['rss_mb']['growth']
            max_memory = memory_summary['rss_mb']['max']
            
            # Verify operations completed and memory usage is reasonable
            if memory_growth < 200 and max_memory < 800:
                self.log_result(
                    "Concurrent Memory Operations",
                    True,
                    f"5 workers completed 100 total operations. Memory growth: {memory_growth:.2f} MB"
                )
            else:
                self.log_result(
                    "Concurrent Memory Operations", 
                    False,
                    f"Excessive memory usage in concurrent operations. Growth: {memory_growth:.2f} MB"
                )
                
            return True
            
        except Exception as e:
            self.monitor.stop_monitoring()
            self.log_result("Concurrent Memory Operations", False, f"Exception: {str(e)}")
            logger.error("Concurrent memory operations test failed", exc_info=True)
            return False
    
    async def test_memory_cleanup_and_gc(self):
        """Test memory cleanup and garbage collection."""
        print("🧹 TESTING MEMORY CLEANUP AND GARBAGE COLLECTION")
        
        try:
            # Get initial memory
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024
            
            # Create large temporary objects
            large_objects = []
            for i in range(100):
                # Create large state objects
                user = UserProfile(
                    user_id=f"cleanup_test_user_{i}",
                    display_name=f"Cleanup Test User {i}",
                    email=f"cleanup{i}@test.com",
                    assigned_role="ADMIN"
                )
                
                state = AppState(
                    session_id=f"cleanup_test_session_{i}",
                    selected_model="gemini-1.5-pro",
                    current_user=user
                )
                
                # Add many messages
                for j in range(50):
                    state.add_message(
                        role="user" if j % 2 == 0 else "assistant",
                        content=f"Large cleanup test message {j} for test {i}. " * 10  # Make messages larger
                    )
                
                large_objects.append(state)
            
            # Check memory after object creation
            after_creation_memory = process.memory_info().rss / 1024 / 1024
            creation_growth = after_creation_memory - initial_memory
            
            # Clear references and force garbage collection
            large_objects.clear()
            gc.collect()
            
            # Wait a moment for cleanup
            await asyncio.sleep(1)
            
            # Check memory after cleanup
            after_cleanup_memory = process.memory_info().rss / 1024 / 1024
            cleanup_reduction = after_creation_memory - after_cleanup_memory
            
            # Memory should have been reduced after cleanup
            cleanup_efficiency = (cleanup_reduction / creation_growth) * 100 if creation_growth > 0 else 0
            
            if cleanup_efficiency > 50:  # At least 50% of memory should be reclaimed
                self.log_result(
                    "Memory Cleanup and GC",
                    True,
                    f"Created {creation_growth:.2f} MB, reclaimed {cleanup_reduction:.2f} MB ({cleanup_efficiency:.1f}%)"
                )
            else:
                self.log_result(
                    "Memory Cleanup and GC",
                    False,
                    f"Poor cleanup efficiency: {cleanup_efficiency:.1f}% reclaimed"
                )
                
            return True
            
        except Exception as e:
            self.log_result("Memory Cleanup and GC", False, f"Exception: {str(e)}")
            logger.error("Memory cleanup test failed", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up test resources."""
        print("🧹 CLEANING UP MEMORY TEST RESOURCES")
        
        try:
            # Stop any running monitoring
            if hasattr(self, 'monitor'):
                self.monitor.stop_monitoring()
                
            # Close storage
            if self.storage:
                self.storage.close()
                
            # Remove test database
            test_db = "test_memory_load.db"
            if os.path.exists(test_db):
                os.remove(test_db)
                print(f"✅ Removed test database: {test_db}")
                
            # Force garbage collection
            gc.collect()
                
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")
    
    def print_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "="*60)
        print("📊 MEMORY MANAGEMENT TEST SUMMARY")
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
            "Heavy Database Operations",
            "Extended Operation Stability",
            "Concurrent Memory Operations",
            "Memory Cleanup and GC"
        ]
        
        critical_passed = sum(1 for r in self.test_results 
                             if r['test'] in critical_tests and r['success'])
        
        print(f"\nCRITICAL TESTS: {critical_passed}/{len(critical_tests)} passed")
        
        if critical_passed == len(critical_tests):
            print("🎉 ALL CRITICAL TESTS PASSED - Memory management is working!")
        else:
            print("🚨 CRITICAL TESTS FAILED - Memory management has issues!")
        
        return critical_passed == len(critical_tests)

async def main():
    """Main test execution function."""
    print("🚀 STARTING STEP 1.13 SCENARIO 2: Memory Management Under Load Test")
    print("=" * 70)
    
    tester = MemoryLoadTester()
    
    try:
        # Run all tests
        await tester.test_baseline_memory_usage()
        await tester.test_heavy_database_operations()
        await tester.test_extended_operation_memory_stability()
        await tester.test_concurrent_memory_operations()
        await tester.test_memory_cleanup_and_gc()
        
        # Print final summary
        success = tester.print_summary()
        
        if success:
            print("\n✅ SCENARIO 2 COMPLETE: Memory management validation PASSED")
            return True
        else:
            print("\n❌ SCENARIO 2 FAILED: Memory management validation FAILED")
            return False
            
    except Exception as e:
        print(f"\n💥 SCENARIO 2 CRASHED: {e}")
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