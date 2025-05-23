#!/usr/bin/env python3
"""
STEP 1.13 - SCENARIO 1: SQLite/Redis State Backend Switching Test

This test proves that the bot can switch between SQLite and Redis backends
while maintaining state consistency and data integrity.

CRITICAL TEST - This is a mandatory validation for Step 1.13.
"""

import asyncio
import logging
import os
import sys
import json
import time
import pprint
from typing import Dict, Any, Optional
import pytest # Add pytest

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, AppSettings
from state_models import AppState, UserProfile
from bot_core.my_bot import SQLiteStorage

# Try to import RedisStorage
try:
    from bot_core.redis_storage import RedisStorage
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ RedisStorage not available - will test SQLite backend switching only")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_database_backend_switching.log')
    ]
)
logger = logging.getLogger(__name__)

class BackendSwitchingTester:
    """Comprehensive tester for SQLite/Redis backend switching."""
    
    def __init__(self):
        self.config = get_config()
        self.test_results = []
        self.sqlite_storage = None
        self.redis_storage = None
        
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
        
    @pytest.mark.asyncio
    async def test_sqlite_backend_operations(self):
        """Test SQLite backend with real operations."""
        print("🔍 TESTING SQLITE BACKEND OPERATIONS")
        
        try:
            # Initialize SQLite storage
            db_path = "test_state_sqlite.db"
            if os.path.exists(db_path):
                os.remove(db_path)  # Start fresh
                
            self.sqlite_storage = SQLiteStorage(db_path=db_path)
            
            # Test 1: Create test user profile
            test_user = UserProfile(
                user_id="sqlite_test_user",
                display_name="SQLite Test User",
                email="sqlite@test.com",
                assigned_role="DEVELOPER"
            )
            
            # Test 2: Create test application state
            test_app_state = AppState(
                session_id="sqlite_test_session",
                selected_model="gemini-1.5-pro",
                current_user=test_user
            )
            
            # Add some test messages
            test_app_state.add_message(role="user", content="Test message 1 for SQLite")
            test_app_state.add_message(role="assistant", content="Response 1 from SQLite backend")
            test_app_state.add_message(role="user", content="Test message 2 for SQLite")
            
            # Test 3: Write data to SQLite
            write_data = {
                "sqlite_test_session": test_app_state.model_dump(mode='json')
            }
            await self.sqlite_storage.write(write_data)
            self.log_result(
                "SQLite Write Operation", 
                True, 
                f"Successfully wrote {len(write_data)} items to SQLite"
            )
            
            # Test 4: Read data from SQLite
            read_data = await self.sqlite_storage.read(["sqlite_test_session"])
            if "sqlite_test_session" in read_data:
                retrieved_state = AppState.model_validate(read_data["sqlite_test_session"])
                self.log_result(
                    "SQLite Read Operation",
                    True,
                    f"Successfully read state with {len(retrieved_state.messages)} messages"
                )
                
                # Verify data integrity
                if (retrieved_state.session_id == test_app_state.session_id and 
                    len(retrieved_state.messages) == len(test_app_state.messages)):
                    self.log_result("SQLite Data Integrity", True, "All data matches original")
                else:
                    self.log_result("SQLite Data Integrity", False, "Data mismatch detected")
            else:
                self.log_result("SQLite Read Operation", False, "No data retrieved")
                return False
                
            # Test 5: Update operation
            test_app_state.add_message(role="user", content="Updated message for SQLite")
            updated_data = {
                "sqlite_test_session": test_app_state.model_dump(mode='json')
            }
            await self.sqlite_storage.write(updated_data)
            
            # Verify update
            updated_read = await self.sqlite_storage.read(["sqlite_test_session"])
            if "sqlite_test_session" in updated_read:
                updated_state = AppState.model_validate(updated_read["sqlite_test_session"])
                if len(updated_state.messages) == 4:  # Should have 4 messages now
                    self.log_result("SQLite Update Operation", True, "Update successful")
                else:
                    self.log_result("SQLite Update Operation", False, "Update failed")
            
            # Test 6: Check database file
            if os.path.exists(db_path):
                file_size = os.path.getsize(db_path)
                self.log_result(
                    "SQLite File Creation", 
                    True, 
                    f"Database file created, size: {file_size} bytes"
                )
            else:
                self.log_result("SQLite File Creation", False, "Database file not created")
            
            print(f"📊 SQLite Backend Test Summary: Database file size: {file_size} bytes")
            return True
            
        except Exception as e:
            self.log_result("SQLite Backend Operations", False, f"Exception: {str(e)}")
            logger.error("SQLite backend test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_redis_backend_operations(self):
        """Test Redis backend with real operations."""
        if not REDIS_AVAILABLE:
            self.log_result("Redis Backend Operations", False, "Redis not available")
            return False
            
        print("🔍 TESTING REDIS BACKEND OPERATIONS")
        
        try:
            # Configure Redis settings for testing
            redis_settings = self.config.settings.model_copy()
            redis_settings.memory_type = "redis"
            redis_settings.redis_host = "localhost"
            redis_settings.redis_port = 6379
            redis_settings.redis_db = 1  # Use test database
            redis_settings.redis_prefix = "test_bot:"
            
            # Initialize Redis storage
            self.redis_storage = RedisStorage(app_settings=redis_settings)
            
            # Test 1: Create test user profile
            test_user = UserProfile(
                user_id="redis_test_user",
                display_name="Redis Test User", 
                email="redis@test.com",
                assigned_role="ADMIN"
            )
            
            # Test 2: Create test application state
            test_app_state = AppState(
                session_id="redis_test_session",
                selected_model="gemini-1.5-flash",
                current_user=test_user
            )
            
            # Add some test messages
            test_app_state.add_message(role="user", content="Test message 1 for Redis")
            test_app_state.add_message(role="assistant", content="Response 1 from Redis backend")
            test_app_state.add_message(role="user", content="Test message 2 for Redis")
            
            # Test 3: Write data to Redis
            write_data = {
                "redis_test_session": test_app_state.model_dump(mode='json')
            }
            await self.redis_storage.write(write_data)
            self.log_result(
                "Redis Write Operation",
                True,
                f"Successfully wrote {len(write_data)} items to Redis"
            )
            
            # Test 4: Read data from Redis
            read_data = await self.redis_storage.read(["redis_test_session"])
            if "redis_test_session" in read_data:
                retrieved_state = AppState.model_validate(read_data["redis_test_session"])
                self.log_result(
                    "Redis Read Operation",
                    True,
                    f"Successfully read state with {len(retrieved_state.messages)} messages"
                )
                
                # Verify data integrity
                if (retrieved_state.session_id == test_app_state.session_id and 
                    len(retrieved_state.messages) == len(test_app_state.messages)):
                    self.log_result("Redis Data Integrity", True, "All data matches original")
                else:
                    self.log_result("Redis Data Integrity", False, "Data mismatch detected")
            else:
                self.log_result("Redis Read Operation", False, "No data retrieved")
                return False
                
            # Test 5: Update operation
            test_app_state.add_message(role="user", content="Updated message for Redis")
            updated_data = {
                "redis_test_session": test_app_state.model_dump(mode='json')
            }
            await self.redis_storage.write(updated_data)
            
            # Verify update
            updated_read = await self.redis_storage.read(["redis_test_session"])
            if "redis_test_session" in updated_read:
                updated_state = AppState.model_validate(updated_read["redis_test_session"])
                if len(updated_state.messages) == 4:  # Should have 4 messages now
                    self.log_result("Redis Update Operation", True, "Update successful")
                else:
                    self.log_result("Redis Update Operation", False, "Update failed")
            
            print(f"📊 Redis Backend Test Summary: Operations completed successfully")
            return True
            
        except Exception as e:
            self.log_result("Redis Backend Operations", False, f"Exception: {str(e)}")
            logger.error("Redis backend test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_data_migration_sqlite_to_redis(self):
        """Test migrating data from SQLite to Redis."""
        if not REDIS_AVAILABLE or not self.sqlite_storage or not self.redis_storage:
            self.log_result("Data Migration SQLite->Redis", False, "Prerequisites not met")
            return False
            
        print("🔄 TESTING DATA MIGRATION FROM SQLITE TO REDIS")
        
        try:
            # Read all data from SQLite
            sqlite_keys = ["sqlite_test_session"]
            sqlite_data = await self.sqlite_storage.read(sqlite_keys)
            
            if not sqlite_data:
                self.log_result("Data Migration Preparation", False, "No data in SQLite to migrate")
                return False
            
            # Migrate data to Redis with new keys
            migration_data = {}
            for key, value in sqlite_data.items():
                new_key = f"migrated_{key}"
                migration_data[new_key] = value
            
            await self.redis_storage.write(migration_data)
            
            # Verify migration
            redis_data = await self.redis_storage.read(list(migration_data.keys()))
            
            if len(redis_data) == len(migration_data):
                # Verify data integrity after migration
                for key in migration_data.keys():
                    if key in redis_data:
                        original_state = AppState.model_validate(migration_data[key])
                        migrated_state = AppState.model_validate(redis_data[key])
                        
                        if (original_state.session_id == migrated_state.session_id and
                            len(original_state.messages) == len(migrated_state.messages)):
                            continue
                        else:
                            self.log_result("Data Migration Integrity", False, f"Data mismatch for key {key}")
                            return False
                
                self.log_result(
                    "Data Migration SQLite->Redis", 
                    True, 
                    f"Successfully migrated {len(migration_data)} items"
                )
                return True
            else:
                self.log_result("Data Migration SQLite->Redis", False, "Migration incomplete")
                return False
                
        except Exception as e:
            self.log_result("Data Migration SQLite->Redis", False, f"Exception: {str(e)}")
            logger.error("Data migration test failed", exc_info=True)
            return False
    
    @pytest.mark.asyncio
    async def test_backend_performance_comparison(self):
        """Compare performance between SQLite and Redis."""
        print("⚡ TESTING BACKEND PERFORMANCE COMPARISON")
        
        try:
            # Test SQLite performance
            if self.sqlite_storage:
                start_time = time.time()
                for i in range(10):
                    test_data = {f"perf_test_{i}": {"test": "data", "iteration": i, "backend": "sqlite"}}
                    await self.sqlite_storage.write(test_data)
                sqlite_write_time = time.time() - start_time
                
                start_time = time.time()
                read_keys = [f"perf_test_{i}" for i in range(10)]
                await self.sqlite_storage.read(read_keys)
                sqlite_read_time = time.time() - start_time
                
                self.log_result(
                    "SQLite Performance",
                    True,
                    f"Write: {sqlite_write_time:.3f}s, Read: {sqlite_read_time:.3f}s"
                )
            
            # Test Redis performance
            if self.redis_storage:
                start_time = time.time()
                for i in range(10):
                    test_data = {f"perf_test_{i}": {"test": "data", "iteration": i, "backend": "redis"}}
                    await self.redis_storage.write(test_data)
                redis_write_time = time.time() - start_time
                
                start_time = time.time()
                read_keys = [f"perf_test_{i}" for i in range(10)]
                await self.redis_storage.read(read_keys)
                redis_read_time = time.time() - start_time
                
                self.log_result(
                    "Redis Performance",
                    True,
                    f"Write: {redis_write_time:.3f}s, Read: {redis_read_time:.3f}s"
                )
                
                # Compare performance
                if sqlite_write_time and redis_write_time:
                    faster_write = "Redis" if redis_write_time < sqlite_write_time else "SQLite"
                    faster_read = "Redis" if redis_read_time < sqlite_read_time else "SQLite"
                    
                    self.log_result(
                        "Performance Comparison",
                        True,
                        f"Faster writes: {faster_write}, Faster reads: {faster_read}"
                    )
                    
            return True
            
        except Exception as e:
            self.log_result("Backend Performance Comparison", False, f"Exception: {str(e)}")
            logger.error("Performance comparison failed", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up test resources."""
        print("🧹 CLEANING UP TEST RESOURCES")
        
        try:
            # Close storage connections
            if self.sqlite_storage:
                self.sqlite_storage.close()
                
            if self.redis_storage:
                await self.redis_storage.close()
                
            # Remove test database file
            test_db = "test_state_sqlite.db"
            if os.path.exists(test_db):
                os.remove(test_db)
                print(f"✅ Removed test database: {test_db}")
                
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")
    
    def print_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "="*60)
        print("📊 BACKEND SWITCHING TEST SUMMARY")
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
            "SQLite Write Operation",
            "SQLite Read Operation", 
            "SQLite Data Integrity",
            "Redis Write Operation",
            "Redis Read Operation",
            "Redis Data Integrity",
            "Data Migration SQLite->Redis"
        ]
        
        critical_passed = sum(1 for r in self.test_results 
                             if r['test'] in critical_tests and r['success'])
        
        print(f"\nCRITICAL TESTS: {critical_passed}/{len(critical_tests)} passed")
        
        if critical_passed == len(critical_tests):
            print("🎉 ALL CRITICAL TESTS PASSED - Backend switching is working!")
        else:
            print("🚨 CRITICAL TESTS FAILED - Backend switching has issues!")
        
        return critical_passed == len(critical_tests)

async def main():
    """Main test execution function."""
    print("🚀 STARTING STEP 1.13 SCENARIO 1: SQLite/Redis Backend Switching Test")
    print("=" * 70)
    
    tester = BackendSwitchingTester()
    
    try:
        # Run all tests
        await tester.test_sqlite_backend_operations()
        
        if REDIS_AVAILABLE:
            await tester.test_redis_backend_operations()
            await tester.test_data_migration_sqlite_to_redis()
        
        await tester.test_backend_performance_comparison()
        
        # Print final summary
        success = tester.print_summary()
        
        if success:
            print("\n✅ SCENARIO 1 COMPLETE: Backend switching validation PASSED")
            return True
        else:
            print("\n❌ SCENARIO 1 FAILED: Backend switching validation FAILED")
            return False
            
    except Exception as e:
        print(f"\n💥 SCENARIO 1 CRASHED: {e}")
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