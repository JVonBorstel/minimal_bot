# File: bot_core/my_bot.py
import sys # Ensure sys is imported at the very top
import json
import random # Add this import
import logging # Added import
import time  # Needed for session duration calculation fallback
from typing import List, Dict, Any, Optional, Union  # Added for type hints
import sqlite3
import os
import threading
import queue
from contextlib import contextmanager # Added for @contextmanager
from importlib import import_module as _import_module_for_early_log
from pydantic import BaseModel # Add this import at the top of the file
import pprint # For pretty printing dicts during debugging
import asyncio
import uuid
import re # Added for regex operations in commands
from datetime import datetime

from botbuilder.core import (  # type: ignore
    ActivityHandler,
    TurnContext,
    MessageFactory,
    ConversationState,
    UserState,
    MemoryStorage,  # For state
)
from botbuilder.schema import (  # type: ignore
    ChannelAccount,
    ActivityTypes,
    Activity,
    SuggestedActions,
    CardAction,
    ActionTypes,  # Added SuggestedActions, CardAction, ActionTypes
    CardFactory,
    CardImage,
)

# Assuming config.py is in the root or a path accessible via PYTHONPATH
from config import Config
from state_models import (
    AppState,
    _migrate_state_if_needed,
)  # Import your Pydantic model and migration
from llm_interface import LLMInterface  # Assuming this path
from tools.tool_executor import ToolExecutor  # Assuming this path
from core_logic import start_streaming_response, HistoryResetRequiredError

# Import enhanced bot handler for safe message processing
from bot_core.enhanced_bot_handler import EnhancedBotHandler

# Import user authentication utilities
from user_auth.utils import get_current_user_profile # Added
from user_auth.models import UserProfile # Added
from user_auth.permissions import Permission # Added for command checking
from workflows.onboarding import OnboardingQuestionType # Added

# Initialize project-light logging FIRST
# This ensures setup_logging and get_logger are available before the RedisStorage import attempt
# Note: Actual setup_logging call with os.getenv is fine here as it uses the imported function.
_my_bot_dir_for_log_setup = os.path.dirname(os.path.abspath(__file__))
_project_root_dir_for_log_setup = os.path.dirname(_my_bot_dir_for_log_setup)
if _project_root_dir_for_log_setup not in sys.path:
    sys.path.insert(0, _project_root_dir_for_log_setup)

# Ensure import_module is available before being used in the try-except block
from importlib import import_module as _import_module_for_early_log

try:
    _logging_module_for_setup = _import_module_for_early_log('utils.logging_config')
    setup_logging_fn = _logging_module_for_setup.setup_logging
    get_logger_fn = _logging_module_for_setup.get_logger
except ModuleNotFoundError as e_log_setup:
    print(f"CRITICAL: Could not import logging utilities from utils.logging_config for initial setup. Path: {sys.path}, Error: {e_log_setup}")
    def setup_logging_fn(level_str="INFO"): logging.basicConfig(level=logging.INFO)
    def get_logger_fn(name): return logging.getLogger(name + "_fallback_early_bot_core")

setup_logging_fn(level_str=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger_fn("bot_core.my_bot")  # Define logger a bit earlier

# Import new RedisStorage if available
try:
    from .redis_storage import RedisStorage
except ImportError:
    RedisStorage = None # Allows conditional logic if file/class isn't there yet
    logger.info("RedisStorage not found or importable from .redis_storage. Redis will not be available.") # Now logger is defined

# --- Start: Robust import of root utils.py and logging_config ---
_my_bot_dir = os.path.dirname(os.path.abspath(__file__))
_project_root_dir = os.path.dirname(_my_bot_dir) # This should be Light-MVP root

# Add project root to sys.path to ensure correct module resolution
if _project_root_dir not in sys.path:
    sys.path.insert(0, _project_root_dir)

# Explicitly load sanitize_message_content etc. from the root utils.py
_root_utils_py_path = os.path.join(_project_root_dir, "utils.py")
_root_utils_spec_loader = _import_module_for_early_log('importlib.util') # Get spec_from_file_location from importlib.util
_root_utils_spec = _root_utils_spec_loader.spec_from_file_location("root_utils_module", _root_utils_py_path)

if not (_root_utils_spec and _root_utils_spec.loader):
    raise ImportError(
        f"Could not create module spec for root utils.py at {_root_utils_py_path}. "
        "Ensure the file exists and is accessible."
    )
_root_utils_module_obj = _root_utils_spec_loader.module_from_spec(_root_utils_spec)
_root_utils_spec.loader.exec_module(_root_utils_module_obj)

# Import the correct sanitize_message_content from utils/utils.py that returns an integer
try:
    from utils.utils import (
        sanitize_message_content,
        log_session_summary_adapted,
        cleanup_messages,
        optimize_tool_usage_stats
    )
    logger.info("Successfully imported primary utilities (sanitize_message_content, log_session_summary_adapted, cleanup_messages, optimize_tool_usage_stats) from utils.utils package.")

    # For any functions that are ONLY in the root utils.py and are still needed,
    # they would need to be explicitly imported or accessed via _root_utils_module_obj.
    # Example: if format_error_message and truncate_text from root utils.py are used by MyBot
    # and not defined in utils/utils.py, they would be shadowed if not explicitly re-assigned here
    # from _root_utils_module_obj. We need to verify their usage in MyBot.
    # For now, assuming the four above are the primary ones with conflicting names.
    if hasattr(_root_utils_module_obj, 'format_error_message'):
        format_error_message = _root_utils_module_obj.format_error_message
    if hasattr(_root_utils_module_obj, 'truncate_text'):
        truncate_text = _root_utils_module_obj.truncate_text

except ImportError as e:
    logger.warning(f"Could not import one or more primary utilities from utils.utils, falling back to root utils.py for all: {e}")
    # Fallback to root utils.py functions if utils/utils.py or specific functions are not available
    sanitize_message_content = _root_utils_module_obj.sanitize_message_content
    cleanup_messages = _root_utils_module_obj.cleanup_messages
    optimize_tool_usage_stats = _root_utils_module_obj.optimize_tool_usage_stats
    log_session_summary_adapted = _root_utils_module_obj.log_session_summary_adapted
    
    # And also for any unique root functions if they were intended to be primary
    if hasattr(_root_utils_module_obj, 'format_error_message'):
        format_error_message = _root_utils_module_obj.format_error_message
    if hasattr(_root_utils_module_obj, 'truncate_text'):
        truncate_text = _root_utils_module_obj.truncate_text
# --- End: Robust import ---

# Import logging utilities using absolute path from the project's utils package
try:
    _logging_module = _import_module_for_early_log('utils.logging_config')
    setup_logging = _logging_module.setup_logging
    get_logger = _logging_module.get_logger
    start_new_turn = _logging_module.start_new_turn
    clear_turn_ids = _logging_module.clear_turn_ids
except ModuleNotFoundError as e:
    print(f"CRITICAL: Could not import logging utilities from utils.logging_config. Path: {sys.path}, Error: {e}")
    # Define dummy loggers/functions if all else fails to prevent crashes
    def setup_logging(level_str="INFO"): pass
    def get_logger(name):
        import logging
        return logging.getLogger(name + "_fallback_bot_core")
    def start_new_turn(): return "fallback_turn_id"
    def clear_turn_ids(): pass


class SQLiteStorage:
    """
    Robust SQLite-backed storage for Bot Framework state.
    Stores state as JSON blobs keyed by (namespace, id).
    Includes connection pooling and enhanced error handling.
    """
    # SQLite error codes that might be transient and benefit from retries
    TRANSIENT_ERROR_CODES = {
        5,   # SQLITE_BUSY: Database file is locked
        6,   # SQLITE_LOCKED: A table in the database is locked
        261, # SQLITE_BUSY_SNAPSHOT
        262, # SQLITE_BUSY_RECOVERY
        513, # SQLITE_BUSY_TIMEOUT
        520, # SQLITE_READONLY_RECOVERY
        1026, # SQLITE_CANTOPEN_CONVPATH
        1027, # SQLITE_CANTOPEN_FULLPATH
        1032, # SQLITE_IOERR_LOCKED
        1033, # SQLITE_IOERR_NOMEM
        1034, # SQLITE_IOERR_RDONLY
        1035, # SQLITE_IOERR_SHORT_READ
        1051, # SQLITE_IOERR_LOCK
        1052, # SQLITE_IOERR_UNLOCK
        1053, # SQLITE_IOERR_RDLOCK
    }
    
    def __init__(self, db_path: str, pool_size: int = 5, max_retries: int = 3):
        """
        Initialize SQLiteStorage with connection pooling.
        
        Args:
            db_path: Path to the SQLite database file
            pool_size: Size of the connection pool
            max_retries: Maximum number of retry attempts for transient errors
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_retries = max_retries
        self._pool_lock = threading.RLock()
        self._conn_pool = queue.Queue(maxsize=pool_size)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        # Initialize the connection pool
        self._init_pool()
        
        # Ensure the table exists
        self._ensure_table()

    # --- START: Interface Adapter Methods for ToolCallAdapter ---
    async def get_app_state(self, session_id: str) -> Optional[AppState]:
        """
        Get an AppState for a specific session. Adapter method for ToolCallAdapter.
        
        This method bridges between the low-level key-value storage interface (read/write)
        and the higher-level AppState object used by ToolCallAdapter. It ensures proper
        validation and typing of the state data.
        
        Args:
            session_id: The session ID to get the state for
            
        Returns:
            An AppState instance or None if not found
        """
        logger.debug(f"SQLiteStorage.get_app_state called for session_id: {session_id}")
        try:
            # Read data using the standard read method - only fetch the session we need
            data_dict = await self.read([session_id])
            if not data_dict or session_id not in data_dict or data_dict[session_id] is None:
                logger.warning(f"No state found for session_id: {session_id}")
                return None
                
            # Parse the state data
            state_data = data_dict[session_id]
            
            # If it's already an AppState instance, return it directly
            if isinstance(state_data, AppState):
                return state_data
                
            # Otherwise, validate and convert to AppState
            try:
                app_state = AppState.model_validate(state_data)
                return app_state
            except Exception as e:
                logger.error(f"Error validating state data for session_id {session_id}: {e}", exc_info=True)
                return None
                
        except Exception as e:
            logger.error(f"Error in get_app_state for session_id {session_id}: {e}", exc_info=True)
            return None
            
    async def save_app_state(self, session_id: str, app_state: AppState) -> bool:
        """
        Save an AppState for a specific session. Adapter method for ToolCallAdapter.
        
        This method bridges between the ToolCallAdapter's expected interface and the
        underlying storage system. It handles serialization of the AppState object
        to a format suitable for storage.
        
        Args:
            session_id: The session ID to save the state for
            app_state: The AppState to save
            
        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"SQLiteStorage.save_app_state called for session_id: {session_id}")
        try:
            # Convert AppState to a serializable format with mode='json' to handle all data types
            state_data = app_state.model_dump(mode='json')
            
            # Write data using the standard write method
            await self.write({session_id: state_data})
            return True
        except Exception as e:
            logger.error(f"Error in save_app_state for session_id {session_id}: {e}", exc_info=True)
            return False
    # --- END: Interface Adapter Methods for ToolCallAdapter ---

    def _init_pool(self):
        """Initialize the connection pool with connections."""
        for _ in range(self.pool_size):
            try:
                conn = self._create_connection()
                self._conn_pool.put(conn)
            except Exception as e:
                logger.error(f"Error initializing connection pool: {e}")
                # Continue even if we couldn't initialize all connections

    def _create_connection(self):
        """Create a new SQLite connection with optimized settings."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # Timeout for acquiring a lock (seconds)
            isolation_level=None,  # Use autocommit mode
            check_same_thread=False  # Allow connections to be used across threads
        )
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Set busy timeout to wait for locks to be released
        conn.execute("PRAGMA busy_timeout=5000")  # 5 seconds
        
        # Other performance optimizations
        conn.execute("PRAGMA synchronous=NORMAL")  # Less durability, more speed
        conn.execute("PRAGMA cache_size=2000")  # Use more memory for caching
        
        return conn

    @contextmanager
    def _get_conn(self):
        """Get a connection from the pool with automatic return."""
        conn = None
        conn_id_for_log = "None"
        logger.debug(f"_get_conn: Attempting to get connection. Current pool qsize: {self._conn_pool.qsize()}")
        try:
            # Get a connection from the pool or create a new one if pool is empty
            try:
                conn = self._conn_pool.get(block=False)
                conn_id_for_log = id(conn)
                logger.debug(f"_get_conn: Got connection {conn_id_for_log} from pool. Pool qsize after get: {self._conn_pool.qsize()}")
            except queue.Empty:
                logger.debug("_get_conn: Connection pool empty, creating new connection.")
                conn = self._create_connection()
                conn_id_for_log = id(conn)
                logger.debug(f"_get_conn: Created new connection {conn_id_for_log}.")
            
            # Begin transaction explicitly
            logger.debug(f"_get_conn: Beginning IMMEDIATE transaction for connection {conn_id_for_log}.")
            conn.execute("BEGIN IMMEDIATE")
            
            logger.debug(f"_get_conn: Yielding connection {conn_id_for_log}.")
            yield conn
            
            # Commit transaction
            logger.debug(f"_get_conn: Committing transaction for connection {conn_id_for_log}.")
            conn.execute("COMMIT")
            
        except sqlite3.Error as e:
            # Rollback transaction on error
            if conn:
                logger.error(f"_get_conn: SQLite error with connection {conn_id_for_log}. Attempting rollback. Error: {e}")
                try:
                    conn.execute("ROLLBACK")
                    logger.debug(f"_get_conn: Rollback successful for connection {conn_id_for_log}.")
                except Exception as rollback_error:
                    logger.error(f"_get_conn: Error rolling back transaction for connection {conn_id_for_log}: {rollback_error}")
            else:
                logger.error(f"_get_conn: SQLite error (conn is None): {e}")
            raise
        except Exception as e:
            # Handle other exceptions
            logger.error(f"_get_conn: Unexpected error with connection {conn_id_for_log if conn else 'None'}: {e}", exc_info=True)
            raise
        finally:
            logger.debug(f"_get_conn: Entering finally block for connection {conn_id_for_log if conn else 'None'}. Pool qsize: {self._conn_pool.qsize()}")
            # Return connection to pool if it's still usable
            if conn:
                try:
                    # Check if connection is still usable
                    conn.execute("SELECT 1")
                    logger.debug(f"_get_conn: Connection {conn_id_for_log} is usable.")
                    # Put back in the pool if it has room
                    try:
                        self._conn_pool.put(conn, block=False)
                        logger.debug(f"_get_conn: Returned connection {conn_id_for_log} to pool. Pool qsize after put: {self._conn_pool.qsize()}")
                    except queue.Full:
                        # Pool is full, close this extra connection
                        logger.debug(f"_get_conn: Pool full, closing extra connection {conn_id_for_log}.")
                        conn.close()
                        logger.debug(f"_get_conn: Closed extra connection {conn_id_for_log}. Pool qsize: {self._conn_pool.qsize()}")
                except Exception as ex_check_usable:
                    logger.warning(f"_get_conn: Connection {conn_id_for_log} is not usable (Error: {ex_check_usable}). Closing it.")
                    # Connection is not usable anymore, close it and create a new one
                    try:
                        conn.close()
                        logger.debug(f"_get_conn: Closed bad connection {conn_id_for_log}.")
                    except Exception as ex_close_bad:
                        logger.error(f"_get_conn: Error closing bad connection {conn_id_for_log}: {ex_close_bad}")
                    
                    # Try to replace it in the pool
                    try:
                        logger.debug(f"_get_conn: Attempting to replace bad connection {conn_id_for_log} in pool.")
                        new_conn = self._create_connection()
                        new_conn_id = id(new_conn)
                        self._conn_pool.put(new_conn, block=False)
                        logger.debug(f"_get_conn: Replaced bad connection {conn_id_for_log} with new connection {new_conn_id} in pool. Pool qsize: {self._conn_pool.qsize()}")
                    except Exception as replace_error:
                        logger.error(f"_get_conn: Failed to replace connection {conn_id_for_log} in pool: {replace_error}. Pool qsize: {self._conn_pool.qsize()}")
            else:
                logger.debug("_get_conn: Finally block, conn is None.")

    def _ensure_table(self):
        """Ensure the bot_state table exists."""
        with self._get_conn() as conn:
            # Check if table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'"
            )
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Table doesn't exist, create it with timestamp columns
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_state (
                        namespace TEXT NOT NULL,
                        id TEXT NOT NULL,
                        data TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now')),
                        PRIMARY KEY (namespace, id)
                    )
                    """
                )
            else:
                # Table exists, check if it has the timestamp columns
                try:
                    conn.execute("SELECT created_at FROM bot_state LIMIT 1")
                except sqlite3.OperationalError:
                    # created_at column doesn't exist, add it without default
                    conn.execute("ALTER TABLE bot_state ADD COLUMN created_at TEXT")
                    # Update all existing rows with current timestamp
                    conn.execute("UPDATE bot_state SET created_at = datetime('now')")
                
                try:
                    conn.execute("SELECT updated_at FROM bot_state LIMIT 1")
                except sqlite3.OperationalError:
                    # updated_at column doesn't exist, add it without default
                    conn.execute("ALTER TABLE bot_state ADD COLUMN updated_at TEXT")
                    # Update all existing rows with current timestamp
                    conn.execute("UPDATE bot_state SET updated_at = datetime('now')")

    async def read(self, keys):
        """
        Read items from storage with retry logic for transient errors.

        Args:
            keys: List of str keys or dicts with 'namespace' and 'id'

        Returns:
            A dictionary of StoreItems, with keys matching the input.
        """
        if not keys:
            return {}

        # Prepare keys for database query, handling both string and dict formats
        processed_keys = []
        original_key_map = {} # To map processed keys back to original keys if format differs
        for idx, key_input in enumerate(keys):
            if isinstance(key_input, dict) and 'namespace' in key_input and 'id' in key_input:
                p_key = key_input
                original_key_map[f"{p_key['namespace']}/{p_key['id']}"] = key_input # Store original dict key
            elif isinstance(key_input, str):
                parts = key_input.split('/')
                if len(parts) > 1:
                    namespace = parts[0]
                    id_ = "/".join(parts[1:])
                    if '|' in id_:
                         id_ = id_.split('|')[0]
                else:
                    namespace = "default"
                    id_ = key_input
                p_key = {'namespace': namespace, 'id': id_}
                original_key_map[f"{namespace}/{id_}"] = key_input # Store original string key
            else:
                logger.warning(f"Unsupported key format during read: {key_input}")
                # For unsupported formats, we'll effectively return None for this key later
                continue
            processed_keys.append(p_key)

        if not processed_keys:
             # Bot Framework expects a dict. If all keys were invalid, return dict with original keys mapping to None.
            return {k: None for k in keys}

        # This will store results fetched from DB, keyed by "namespace/id"
        db_results_dict = {}
        retries_left = self.max_retries
        success = False

        while retries_left >= 0:
            try:
                with self._get_conn() as conn:
                    where_clauses = []
                    params = []
                    for p_key_dict in processed_keys:
                         where_clauses.append("(namespace=? AND id=?)")
                         params.extend([p_key_dict['namespace'], p_key_dict['id']])

                    if not where_clauses:
                        success = True # No valid keys to query, so technically successful
                        break 

                    sql = f"SELECT namespace, id, data FROM bot_state WHERE {' OR '.join(where_clauses)}"
                    cur = conn.execute(sql, params)

                    for row in cur.fetchall():
                        namespace, id_, data_str = row
                        db_key = f"{namespace}/{id_}"
                        logger.debug(f"SQLiteRead: Raw data_str for {db_key}: {data_str}")
                        try:
                            loaded_data = json.loads(data_str)
                            logger.debug(f"SQLiteRead: Loaded data for {db_key}: {pprint.pformat(loaded_data)}")
                            db_results_dict[db_key] = loaded_data
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Error decoding JSON data for {db_key}: {json_err}. Data: {data_str[:500]}") # Log part of the data
                            db_results_dict[db_key] = None # Store None if data is corrupted
                success = True
                break # Break from while loop on success
            except sqlite3.Error as e:
                error_code = getattr(e, 'sqlite_errorcode', None)
                if error_code in self.TRANSIENT_ERROR_CODES and retries_left > 0:
                    retries_left -= 1
                    wait_time = 0.1 * (2 ** (self.max_retries - retries_left))
                    logger.warning(f"Transient SQLite error {error_code}, retrying in {wait_time:.2f}s. {retries_left} retries left.")
                    await asyncio.sleep(wait_time) # Fixed: Use async sleep in async method
                else:
                    logger.error(f"SQLite error during read: {e}")
                    raise 
            except Exception as e:
                logger.error(f"Unexpected error during read: {e}")
                raise
        
        if not success:
            # This case should ideally be covered by the re-raise in except blocks
            # If somehow reached, it means all retries failed without re-raising.
            logger.error("SQLite read operation failed after all retries.")
            # Return dict with all original keys mapping to None as a fallback
            return {k: None for k in keys}

        # Construct final result dictionary mapping original keys to their found items (or None)
        final_dict_result = {}
        for original_key_input in keys: # Iterate through original keys to maintain order and include all
            # Reconstruct the processed key string format used for db_results_dict and original_key_map
            processed_key_str_for_lookup = None
            if isinstance(original_key_input, dict) and 'namespace' in original_key_input and 'id' in original_key_input:
                processed_key_str_for_lookup = f"{original_key_input['namespace']}/{original_key_input['id']}"
            elif isinstance(original_key_input, str):
                 parts = original_key_input.split('/')
                 if len(parts) > 1:
                     namespace = parts[0]
                     id_ = "/".join(parts[1:])
                     if '|' in id_:
                          id_ = id_.split('|')[0]
                     processed_key_str_for_lookup = f"{namespace}/{id_}"
                 else:
                     processed_key_str_for_lookup = f"default/{original_key_input}"
            
            if processed_key_str_for_lookup in db_results_dict:
                final_dict_result[original_key_input] = db_results_dict[processed_key_str_for_lookup]
            else:
                final_dict_result[original_key_input] = None

        return final_dict_result

    async def write(self, changes):
        """
        Write items to storage with retry logic.
        
        Args:
            changes: Dict of document IDs to state objects, or a pair of lists [keys], [values]
        """
        if not changes:
            return
            
        # Handle both dict format and Bot Framework format (which could be two lists)
        if isinstance(changes, list):
            # This should not happen now, but this was the older interface
            logger.warning("Deprecated list format passed to write(). Please update to use dictionary.")
            return
            
        retries_left = self.max_retries
        
        while retries_left >= 0:
            try:
                with self._get_conn() as conn:
                    for key, value in changes.items():
                        try:
                            if isinstance(key, dict) and 'namespace' in key and 'id' in key:
                                # Handle the case where key is a dict with namespace/id
                                namespace = key['namespace']
                                id_ = key['id']
                            elif isinstance(key, str):
                                # Standard Bot Framework format: key is a string ID, split on '/'
                                parts = key.split('/')
                                if len(parts) > 1:
                                    namespace = parts[0]
                                    id_ = "/".join(parts[1:]) # Corrected: join remaining parts for id
                                else:
                                    namespace = "default"
                                    id_ = key
                            else:
                                err_msg = f"Unsupported key format: {key}. Key must be a string (namespace/id) or a dict {{'namespace': ..., 'id': ...}}."
                                logger.error(err_msg)
                                raise TypeError(err_msg) # Raise an exception
                           
                           # Serialize data
                            logger.debug(f"SQLiteWrite: Key: {key}, Type of value: {type(value)}")
                            if hasattr(value, '__dict__'):
                                logger.debug(f"SQLiteWrite: value.__dict__: {pprint.pformat(value.__dict__)}")
                                if 'AugieConversationState' in value.__dict__:
                                     logger.debug(f"SQLiteWrite: Type of value.AugieConversationState: {type(value.__dict__['AugieConversationState'])}")
                            
                            # data_to_serialize = value # Original problematic line
                            # The 'value' here is the StoreItem dict, e.g., {'AugieConversationState': AppState(...), 'eTag': '...'}
                            # We need to serialize the AppState model *within* this dict.
                            
                            temp_store_item_dict = {}
                            if isinstance(value, dict):
                                for item_key, item_val in value.items():
                                    if isinstance(item_val, BaseModel): # Check if nested item is Pydantic
                                        temp_store_item_dict[item_key] = item_val.model_dump(mode='json')
                                    else:
                                        temp_store_item_dict[item_key] = item_val
                                data_to_serialize = temp_store_item_dict
                            else: # Should not happen if Bot Framework sends StoreItem dicts
                                data_to_serialize = value
                                if isinstance(value, BaseModel):
                                     data_to_serialize = value.model_dump(mode='json')

                            if isinstance(data_to_serialize, dict):
                                logger.debug(f"SQLiteWrite: data_to_serialize (dict): {pprint.pformat(data_to_serialize)}")
                            else:
                                logger.debug(f"SQLiteWrite: data_to_serialize (str): {str(data_to_serialize)[:500]}")

                            try:
                                data = json.dumps(data_to_serialize)
                                logger.debug(f"SQLiteWrite: JSON data to write for key {key}: {data[:500]}") # Log first 500 chars
                            except TypeError as json_err:
                                logger.error(f"Error serializing data for {key}: {json_err}. Object type: {type(data_to_serialize)}", exc_info=True)
                                # If model_dump was used, this error is less likely for Pydantic types
                                # but could still occur for complex nested non-Pydantic types within the model.
                                raise # Re-raise the TypeError to make the failure explicit
                                
                            # Update or insert the data with updated timestamp
                            conn.execute(
                                """
                                REPLACE INTO bot_state (namespace, id, data, updated_at) 
                                VALUES (?, ?, ?, datetime('now'))
                                """,
                                (namespace, id_, data)
                            )
                        except sqlite3.Error as e:
                            logger.error(f"Error writing key {key}: {e}")
                            # Continue with other keys
                # If we got here, the operation was successful
                break
            except sqlite3.Error as e:
                error_code = getattr(e, 'sqlite_errorcode', None)
                if error_code in self.TRANSIENT_ERROR_CODES and retries_left > 0:
                    retries_left -= 1
                    wait_time = 0.1 * (2 ** (self.max_retries - retries_left)) * (0.5 + random.random())
                    logger.warning(f"Transient SQLite error {error_code}, retrying in {wait_time:.2f}s. {retries_left} retries left.")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"SQLite error during write: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error during write: {e}")
                raise

    async def delete(self, keys):
        """
        Delete items from storage with retry logic.
        
        Args:
            keys: List of dicts with 'namespace' and 'id'
        """
        if not keys:
            return
            
        if not isinstance(keys, list):
            keys = [keys]  # Convert single key to list for consistency
            
        retries_left = self.max_retries
        
        while retries_left >= 0:
            try:
                with self._get_conn() as conn:
                    for key in keys:
                        try:
                            if not isinstance(key, dict) or 'namespace' not in key or 'id' not in key:
                                logger.warning(f"Invalid key format for delete: {key}")
                                continue
                                
                            conn.execute(
                                "DELETE FROM bot_state WHERE namespace=? AND id=?",
                                (key['namespace'], key['id'])
                            )
                        except sqlite3.Error as e:
                            logger.error(f"Error deleting key {key}: {e}")
                            # Continue with other keys
                # If we got here, the operation was successful
                break
            except sqlite3.Error as e:
                error_code = getattr(e, 'sqlite_errorcode', None)
                if error_code in self.TRANSIENT_ERROR_CODES and retries_left > 0:
                    retries_left -= 1
                    wait_time = 0.1 * (2 ** (self.max_retries - retries_left)) * (0.5 + random.random())
                    logger.warning(f"Transient SQLite error {error_code}, retrying in {wait_time:.2f}s. {retries_left} retries left.")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"SQLite error during delete: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error during delete: {e}")
                raise

    def close(self):
        """Close all connections in the pool."""
        try:
            while not self._conn_pool.empty():
                conn = self._conn_pool.get(block=False)
                if conn:
                    try:
                        conn.close()
                    except Exception as e:
                        logger.error(f"Error closing connection: {e}")
        except Exception as e:
            logger.error(f"Error during close: {e}")


class MyBot(ActivityHandler):
    def __init__(self, app_config: Config):
        logger.info("Initializing MyBot...")
        self.app_config = app_config
        self.llm_interface = LLMInterface(app_config)
        self.tool_executor = ToolExecutor(app_config) # Initialize ToolExecutor
        
        # Initialize enhanced bot handler for safe message processing
        self.enhanced_handler = EnhancedBotHandler()
        logger.info("Enhanced bot handler initialized for safe message processing")

        # --- Storage Initialization based on memory_type --- 
        if app_config.settings.memory_type == "redis" and RedisStorage:
            logger.info(f"Using Redis for bot state. Configured URL: {app_config.settings.redis_url}, Host: {app_config.settings.redis_host}, Port: {app_config.settings.redis_port}")
            try:
                self.storage = RedisStorage(app_settings=app_config.settings)
                logger.info("RedisStorage instantiated successfully.")
                # It's good practice to have a way to test the connection early if desired,
                # but _ensure_client_initialized will handle it on first use.
            except Exception as e:
                logger.error(f"Failed to initialize RedisStorage: {e}. Falling back to SQLite.", exc_info=True)
                # Fallback to SQLite if Redis initialization fails
                db_path = self.app_config.STATE_DB_PATH
                logger.info(f"Using SQLite database for bot state at: {db_path} (fallback from Redis)")
                self.storage = SQLiteStorage(db_path=db_path)
        else:
            if app_config.settings.memory_type == "redis" and not RedisStorage:
                logger.warning("MEMORY_TYPE is 'redis' but RedisStorage adapter is not available. Falling back to SQLite.")
            
            db_path = self.app_config.STATE_DB_PATH # Uses the property from Config
            logger.info(f"Using SQLite database for bot state at: {db_path}")
            self.storage = SQLiteStorage(db_path=db_path) 
        # --- End Storage Initialization ---

        # Define state properties
        self.conversation_state = ConversationState(self.storage)
        self.user_state = UserState(self.storage)  # For user-specific state

        # Create property accessor for conversation data.
        # This will store our main application state
        # (like your Pydantic AppState model).
        # For now, it can be a simple dictionary.
        self.convo_state_accessor = self.conversation_state.create_property(
            "AugieConversationState"
        )

        # Store Pydantic model class for easy instantiation and validation
        self.AppStateModel = AppState
        logger.info("MyBot initialized.") # Simplified log

    async def _get_conversation_data(
        self, turn_context: TurnContext
    ) -> AppState:
        """Gets, migrates, and validates conversation data as AppState."""
        # AppState_dict will be the raw dictionary from storage
        # For Bot Framework, the accessor manages the raw dict <-> object internally to some extent
        # but we want to ensure we get our Pydantic model instance.
        app_state_raw_from_storage = await self.convo_state_accessor.get(
            turn_context, lambda: {} # Return empty dict if not found, AppState will initialize
        )

        # logger.debug(f"_get_conversation_data: Raw data from accessor for conv {turn_context.activity.conversation.id}: {pprint.pformat(app_state_raw_from_storage)}")
        logger.debug(
            f"Raw data from accessor for conv {turn_context.activity.conversation.id}",
            extra={
                "event_type": "raw_state_accessor_data",
                "conversation_id": turn_context.activity.conversation.id,
                "raw_data_type": str(type(app_state_raw_from_storage)),
                # Avoid dumping potentially huge raw_app_state_raw_from_storage unless specifically needed
                # "raw_data_preview": pprint.pformat(app_state_raw_from_storage)[:500] + "..." if app_state_raw_from_storage else "None"
            }
        )
        # logger.debug(f"_get_conversation_data: Type of raw_data: {type(app_state_raw_from_storage)}") # Covered by above

        app_state_instance: AppState

        if not app_state_raw_from_storage: # Handles None or empty dict
            logger.info(
                "No existing conversation state found or state is empty. "
                f"Initializing fresh AppState for conv {turn_context.activity.conversation.id}."
            )
            app_state_instance = self.AppStateModel(
                session_id=turn_context.activity.conversation.id, # Ensure session_id is set
                # Initialize with defaults from app_config
                selected_model=self.app_config.GEMINI_MODEL,
                available_personas=getattr(
                    self.app_config, "AVAILABLE_PERSONAS", ["Default"]
                ),
                selected_persona=getattr(
                    self.app_config, "DEFAULT_PERSONA", "Default"
                ),
                selected_perplexity_model=getattr(
                    self.app_config, "PERPLEXITY_MODEL", "sonar-pro"
                ),
            )
        elif isinstance(app_state_raw_from_storage, AppState):
            logger.info(f"Accessor returned AppState instance directly for conv {turn_context.activity.conversation.id}. Performing checks and updates.")
            app_state_instance = app_state_raw_from_storage
        elif isinstance(app_state_raw_from_storage, dict):
            logger.info(
                f"Existing conversation state (dict) found for conv {turn_context.activity.conversation.id}. "
                f"Attempting migration/validation."
            )
            try:
                # Pass raw_data directly, _migrate_state_if_needed now handles dicts and can return AppState
                migrated_data_or_app_state = _migrate_state_if_needed(app_state_raw_from_storage)

                if isinstance(migrated_data_or_app_state, AppState):
                    app_state_instance = migrated_data_or_app_state
                elif isinstance(migrated_data_or_app_state, dict): # if migration returned a dict
                    app_state_instance = self.AppStateModel(**migrated_data_or_app_state)
                else: # Should not happen
                    logger.error(f"Migration returned unexpected type {type(migrated_data_or_app_state)}. Re-initializing AppState for conv {turn_context.activity.conversation.id}.")
                    app_state_instance = self.AppStateModel(session_id=turn_context.activity.conversation.id)

            except Exception as e:
                logger.error(f"Error migrating/validating state for conv {turn_context.activity.conversation.id}: {e}. Re-initializing AppState.", exc_info=True)
                app_state_instance = self.AppStateModel(session_id=turn_context.activity.conversation.id)
        else:
            logger.error(f"Loaded state is neither dict nor AppState (type: {type(app_state_raw_from_storage)}). Re-initializing AppState for conv {turn_context.activity.conversation.id}.")
            app_state_instance = self.AppStateModel(session_id=turn_context.activity.conversation.id)

        # Ensure session_id is correctly set from turn_context if not already
        if not app_state_instance.session_id and turn_context.activity and turn_context.activity.conversation:
            app_state_instance.session_id = turn_context.activity.conversation.id
            logger.debug(f"Set session_id from turn_context: {app_state_instance.session_id}")
        elif not app_state_instance.session_id:
            # Fallback if turn_context also doesn't have it (highly unlikely for message activity)
            app_state_instance.session_id = f"unknown_session_{uuid.uuid4()}"
            logger.warning(f"Assigned fallback session_id: {app_state_instance.session_id}")


        # Log loaded state (once, after all initialization/migration attempts)
        # logger.debug(f"Loaded AppState for conv {turn_context.activity.conversation.id}: {app_state_instance.model_dump_json(indent=2)}")
        log_extra_details = {
            "event_type": "appstate_loaded_summary",
            "session_id": app_state_instance.session_id,
            "user_id": app_state_instance.current_user.user_id if app_state_instance.current_user else None,
            "message_count": len(app_state_instance.messages),
            "active_workflows_count": len(app_state_instance.active_workflows),
            "version": app_state_instance.version,
            "last_interaction_status": app_state_instance.last_interaction_status,
        }
        # Optionally add full dump only if a specific debug flag is on
        if self.app_config.settings.log_detailed_appstate:
            log_extra_details["full_appstate_dump"] = app_state_instance.model_dump(mode='json')

        logger.debug(
            f"Loaded AppState for conv {app_state_instance.session_id}. Messages: {len(app_state_instance.messages)}, Workflows: {len(app_state_instance.active_workflows)}",
            extra=log_extra_details
        )

        # Ensure essential config-dependent fields are current if state loaded/initialized
        if not app_state_instance.selected_model:
            app_state_instance.selected_model = self.app_config.GEMINI_MODEL
            logger.debug("Default selected_model applied to AppState.")
        # If available_personas is not present in the loaded state (e.g., older state version)
        # or if it's an empty list, it will be refreshed from the application configuration.
        # If the loaded state had a non-empty list (e.g., from a previous session or if Pydantic
        # applied its default_factory=["Default"] because the field was missing entirely from raw_data),
        # that existing non-empty list will be preserved unless it was an empty list.
        if (
            not hasattr(app_state_instance, "available_personas")
            or not app_state_instance.available_personas
        ):
            app_state_instance.available_personas = getattr(
                self.app_config, "AVAILABLE_PERSONAS", ["Default"]
            )
            logger.debug("Default available_personas applied to AppState.")
        if (
            not hasattr(app_state_instance, "selected_persona")
            or not app_state_instance.selected_persona
        ):
            app_state_instance.selected_persona = getattr(
                self.app_config, "DEFAULT_PERSONA", "Default"
            )
            logger.debug("Default selected_persona applied to AppState.")
        if (
            not hasattr(app_state_instance, "selected_perplexity_model")
            or not app_state_instance.selected_perplexity_model
        ):
            app_state_instance.selected_perplexity_model = getattr(
                self.app_config, "PERPLEXITY_MODEL", "sonar-pro"
            )
            logger.debug("Default selected_perplexity_model applied.")

        # Set displayed_model to the actual selected_model
        app_state_instance.displayed_model = app_state_instance.selected_model
 
        # Use utils to validate and repair the state
        # is_valid, repairs = validate_and_repair_state(app_state_instance) # Removed: Functionality likely moved to core_logic.history_utils
        # if repairs:
        #     logger.info(
        #         f"State validation and repair performed: {len(repairs)} repairs made"
        #     )
        # Check if message history needs cleanup (over 100 messages)
        if len(app_state_instance.messages) > 100:
            removed = cleanup_messages(app_state_instance, keep_last_n=100)
            logger.info(
                f"Cleaned up message history: removed {removed} old messages"
            )

        # Check if tool usage stats need optimization
        if hasattr(app_state_instance, "session_stats") and hasattr(
            app_state_instance.session_stats, "tool_usage"
        ):
            if (
                len(app_state_instance.session_stats.tool_usage) > 20
            ):  # If tracking too many tools
                optimize_tool_usage_stats(app_state_instance, keep_top_n=15)
                logger.debug("Optimized tool usage statistics")

        # Ensure the turn context has this version of the state after creation/migration
        await self.convo_state_accessor.set(turn_context, app_state_instance)
        logger.debug(f"_get_conversation_data: Set AppState instance (session_id: {app_state_instance.session_id}) back on turn_context via accessor.")

        logger.info(
            f"AppState ready for turn (version: {getattr(app_state_instance, 'version', 'unknown')}, "
            f"session_id: {app_state_instance.session_id})."
        )
        return app_state_instance

    async def on_turn(self, turn_context: TurnContext):
        # This is called for every activity.
        # It's crucial to call super().on_turn() to ensure the ActivityHandler
        # routes events.
        await super().on_turn(turn_context)

        # Save any state changes that might have occurred during the turn.
        app_state_to_save = await self.convo_state_accessor.get(turn_context) # Get the latest state object to log before saving
        if app_state_to_save and isinstance(app_state_to_save, AppState): # Or your AppState model
             logger.debug(f"Attempting to save AppState for conv {turn_context.activity.conversation.id} at end of on_turn.")
             # The accessor expects the raw object to be set, Bot Framework handles serialization for supported storage.
             # If using Pydantic model directly with accessor, it should be fine.
             await self.convo_state_accessor.set(turn_context, app_state_to_save)
        elif app_state_to_save: # It's some other dict, set it
             logger.debug(f"Attempting to save raw dict state for conv {turn_context.activity.conversation.id} at end of on_turn.")
             await self.convo_state_accessor.set(turn_context, app_state_to_save)


        # Forcing save can be useful but also hide issues if state wasn't actually changed.
        # Sticking to force=False unless explicitly needed.
        await self.conversation_state.save_changes(turn_context, force=False)
        await self.user_state.save_changes(turn_context, force=False) # If you use user state

        if app_state_to_save and isinstance(app_state_to_save, AppState):
            # logger.debug(f"Saved AppState for conv {turn_context.activity.conversation.id} (version: {app_state_to_save.version}, messages: {len(app_state_to_save.messages)})")
            logger.debug(
                f"Saved AppState for conv {turn_context.activity.conversation.id}. Version: {app_state_to_save.version}, Messages: {len(app_state_to_save.messages)}",
                extra={
                    "event_type": "appstate_saved_summary",
                    "conversation_id": turn_context.activity.conversation.id,
                    "appstate_version": app_state_to_save.version,
                    "message_count": len(app_state_to_save.messages),
                    "full_appstate_dump_on_save": app_state_to_save.model_dump(mode='json') if self.app_config.settings.log_detailed_appstate else "not_logged"
                }
            )
        elif app_state_to_save: # It was a dict
             logger.debug(f"Saved raw dict state for conv {turn_context.activity.conversation.id}. Keys: {list(app_state_to_save.keys()) if isinstance(app_state_to_save, dict) else 'N/A'}")
        else:
            logger.debug(f"No app_state found on accessor to save at end of on_turn for conv {turn_context.activity.conversation.id}")

        logger.debug(f"Saved state for turn: {turn_context.activity.id}")

    async def on_members_added_activity(
        self, members_added: List[ChannelAccount], turn_context: TurnContext
    ):
        logger.info("on_members_added_activity called.")
        app_state: AppState = await self._get_conversation_data(
            turn_context
        )  # Load state to ensure it's initialized

        for member in members_added:
            # Greet anyone that was actually added to the conversation
            # (not the bot itself).
            if (
                member
                and member.id is not None
                and turn_context.activity
                and turn_context.activity.recipient
                and member.id != turn_context.activity.recipient.id
                and member.name.lower() != "bot" # Add check for bot name
            ):
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"Hello {member.name}! Welcome to the Augie Bot "
                        f"(Bot Framework Edition v.{app_state.version})."
                    )
                )
                await turn_context.send_activity(
                    "I'm your AI assistant for development and "
                    "operations tasks. How can I help you today?"
                )
                # Optionally add system message to app_state about welcome
                app_state.add_message(
                    role="system",
                    content=f"Welcomed new member: {member.name}"
                )
                logger.info("Welcomed new member", extra={"event_type": "member_added", "details": {"member_name": member.name, "activity_id": turn_context.activity.id}})

    async def on_message_activity(self, turn_context: TurnContext):
        current_turn_id = start_new_turn()
        logger_msg_activity = get_logger("bot_core.my_bot.on_message_activity") # Use namespaced logger
        
        logger_msg_activity.info(
            "Processing user message",
            extra={
                "event_type": "user_message_received",
                "details": {
                    "text": turn_context.activity.text,
                    "activity_id": turn_context.activity.id,
                    "conversation_id": turn_context.activity.conversation.id,
                    "user_id": turn_context.activity.from_property.id if turn_context.activity.from_property else "unknown",
                    "channel_id": turn_context.activity.channel_id,
                }
            }
        )
        interaction_start_time = time.monotonic()  # Record start
        app_state: AppState = await self._get_conversation_data(turn_context)

        # --- Start: Integrate User Authentication (P3A.4.1) ---
        try:
            # Attempt to load user profile from turn context
            user_profile = get_current_user_profile(turn_context, db_path=self.app_config.STATE_DB_PATH)
            
            if user_profile:
                # Store the user profile in app state for later access
                app_state.current_user = user_profile
                
                logger_msg_activity.debug(
                    f"User profile loaded for user {user_profile.user_id} with role {user_profile.assigned_role}",
                    extra={
                        "event_type": "user_profile_loaded",
                        "details": {
                            "user_id": user_profile.user_id,
                            "assigned_role": user_profile.assigned_role,
                            "display_name": user_profile.display_name,
                            "email": user_profile.email,  # May be None
                            "first_seen": user_profile.first_seen_timestamp,
                            "last_active": user_profile.last_active_timestamp
                        }
                    }
                )
                
                # --- Start Onboarding Logic Block ---
                try:
                    from workflows.onboarding import OnboardingWorkflow, get_active_onboarding_workflow, ONBOARDING_QUESTIONS
                    
                    user_text_lower = turn_context.activity.text.lower().strip() if turn_context.activity.text else ""
                    current_active_onboarding_workflow = get_active_onboarding_workflow(app_state, user_profile.user_id)
                    onboarding_handler = OnboardingWorkflow(user_profile, app_state)
                    
                    onboarding_was_skipped_this_turn = False

                    if current_active_onboarding_workflow and user_text_lower == "help":
                        help_message = (
                            "You're currently in the onboarding process. You can:\\n"
                            "- Answer the current question above.\\n"
                            "- Type 'skip onboarding' to exit this setup at any time."
                        )
                        await turn_context.send_activity(MessageFactory.text(help_message))
                        logger_msg_activity.info(f"Provided onboarding-specific help to user {user_profile.user_id}.",
                                                 extra={"event_type": "onboarding_contextual_help_sent"})
                        return

                    if current_active_onboarding_workflow:
                        skip_phrases = ["skip onboarding", "@bot skip onboarding", "skip", "i want to skip", "don't onboard me", "no thanks onboarding"]
                        explicit_skip_requested = any(phrase == user_text_lower for phrase in skip_phrases)
                        
                        llm_inferred_skip = False
                        if not explicit_skip_requested and user_text_lower:
                            negative_onboarding_phrases = [
                                "i don't want to do this", "i dont want to do this", "stop this process", 
                                "exit onboarding", "cancel this setup", "no more questions please",
                                "let's not do this", "enough questions"
                            ]
                            if any(phrase in user_text_lower for phrase in negative_onboarding_phrases):
                                llm_inferred_skip = True
                                logger_msg_activity.info(f"LLM-simulated: detected intent to skip onboarding for user {user_profile.user_id} from: '{user_text_lower}'.", extra={"event_type": "onboarding_skip_inferred_simulated_llm"})

                        if explicit_skip_requested or llm_inferred_skip:
                            event_source = "explicit_command" if explicit_skip_requested else "llm_inference"
                            logger_msg_activity.info(f"User {user_profile.user_id} requested to skip onboarding ({event_source}). WF: {current_active_onboarding_workflow.workflow_id}.",
                                                     extra={"event_type": "onboarding_skip_initiated", "source": event_source})
                            skip_result = onboarding_handler.skip_onboarding(current_active_onboarding_workflow.workflow_id)
                            
                            if skip_result.get("success"):
                                await turn_context.send_activity(MessageFactory.text(skip_result["message"]))
                                from user_auth import db_manager
                                from user_auth.utils import invalidate_user_profile_cache
                                profile_dict = onboarding_handler.user_profile.model_dump()
                                db_manager.save_user_profile(profile_dict)
                                # Invalidate cache to ensure fresh profile data is loaded next time
                                invalidate_user_profile_cache(user_profile.user_id)
                                logger_msg_activity.info(f"Onboarding successfully skipped ({event_source}) for user {user_profile.user_id}. WF: {current_active_onboarding_workflow.workflow_id}.",
                                                         extra={"event_type": "onboarding_skipped_successfully", "source": event_source})
                                current_active_onboarding_workflow = None 
                                onboarding_was_skipped_this_turn = True
                                # Save state and return early - don't process "skip" as a regular message
                                await self.conversation_state.save_changes(turn_context)
                                await self.user_state.save_changes(turn_context)
                                return
                            else:
                                await turn_context.send_activity(MessageFactory.text(skip_result.get("error", "Could not skip onboarding.")))
                    
                    if not onboarding_was_skipped_this_turn:
                        if current_active_onboarding_workflow:
                            # New: Check for "why" questions before processing as an answer
                            meta_question_phrases = ["why?", "why", "why do you need this?", "why do you need this", "what for?", "what for", "what is this for?", "what is this for"]
                            if user_text_lower in meta_question_phrases:
                                current_q_index = current_active_onboarding_workflow.data.get("current_question_index", 0)
                                # Adjust for follow-up questions if necessary
                                if current_active_onboarding_workflow.data.get("processing_follow_ups"):
                                    follow_up_qs = current_active_onboarding_workflow.data.get("follow_up_questions", [])
                                    follow_up_idx = current_active_onboarding_workflow.data.get("follow_up_index", 0)
                                    if follow_up_idx < len(follow_up_qs):
                                        current_onboarding_question_details = follow_up_qs[follow_up_idx]
                                    else: # Should not happen if state is consistent
                                        current_onboarding_question_details = None
                                elif 0 <= current_q_index < len(ONBOARDING_QUESTIONS):
                                    current_onboarding_question_details = ONBOARDING_QUESTIONS[current_q_index]
                                else:
                                    current_onboarding_question_details = None

                                if current_onboarding_question_details:
                                    explanation = current_onboarding_question_details.help_text
                                    original_question_text = current_onboarding_question_details.question
                                    
                                    if explanation:
                                        reply_text = f"💡 Good question! I'm asking because: {explanation}"
                                    else:
                                        reply_text = "This information helps me tailor my assistance to you better."
                                    
                                    await turn_context.send_activity(MessageFactory.text(reply_text))
                                    
                                    # Re-format and send the original question again
                                    current_progress_val = current_active_onboarding_workflow.data.get("current_question_index", 0)
                                    # If processing follow-ups, progress might refer to the main question's index
                                    if not current_active_onboarding_workflow.data.get("processing_follow_ups"):
                                        current_progress_val += 1 # Display 1-based index
                                    else: # For follow-ups, keep main question's index for progress display
                                        current_progress_val = current_active_onboarding_workflow.data.get("current_question_index", 0) +1 

                                    total_questions_val = current_active_onboarding_workflow.data.get('questions_total', len(ONBOARDING_QUESTIONS))
                                    current_progress = f"**{current_progress_val}/{total_questions_val}**"
                                    question_display_text = f"{current_progress} {original_question_text}"
                                    if current_onboarding_question_details.choices:
                                        formatted_choices = "\n".join(f"{i+1}. {choice}" for i, choice in enumerate(current_onboarding_question_details.choices))
                                        question_display_text += f"\n\n{formatted_choices}"
                                        if current_onboarding_question_details.question_type == OnboardingQuestionType.MULTI_CHOICE:
                                            question_display_text += "\n\n*You can select multiple options by number (e.g., '1,3,5') or text*"
                                    if not current_onboarding_question_details.required:
                                        question_display_text += "\n\n*Optional - type 'skip' to skip*"

                                    await turn_context.send_activity(MessageFactory.text(question_display_text))
                                    
                                    logger_msg_activity.info(f"Provided explanation for onboarding question '{current_onboarding_question_details.key}' to user {user_profile.user_id}.",
                                                             extra={"event_type": "onboarding_meta_question_answered"})
                                    return # End turn, user can now answer with context
                                else:
                                    logger_msg_activity.warning(f"Could not retrieve current question details for meta-question. WF state: {current_active_onboarding_workflow.data}")
                                    # Fallback if question details not found, just process answer

                            result = onboarding_handler.process_answer(current_active_onboarding_workflow.workflow_id, user_text_lower)
                            
                            # Import db_manager and invalidate_user_profile_cache here as they are used in multiple branches
                            from user_auth import db_manager
                            from user_auth.utils import invalidate_user_profile_cache

                            if result.get("error"):
                                await turn_context.send_activity(MessageFactory.text(f"❌ {result['error']}"))
                                return
                            if result.get("retry_question"):
                                await turn_context.send_activity(MessageFactory.text(f"❌ {result['message']}"))
                                return
                            
                            # --- Start: New logic for incremental save and confirmation ---
                            profile_dict_for_save = onboarding_handler.user_profile.model_dump()
                            save_successful = db_manager.save_user_profile(profile_dict_for_save)
                            
                            if save_successful:
                                invalidate_user_profile_cache(user_profile.user_id)
                                logger_msg_activity.info(f"Successfully saved UserProfile for {user_profile.user_id} after onboarding answer/skip.", extra={"event_type": "onboarding_profile_increment_save"})
                                
                                saved_key = result.get("answer_saved_key")
                                saved_value = result.get("answer_saved_value")
                                was_skipped = result.get("question_skipped")

                                if not result.get("completed"): # Don't send intermediate confirmations if onboarding just completed
                                    if was_skipped:
                                        # User skipped a non-required question
                                        summary_of_saved = onboarding_handler.get_accumulated_answers_summary()
                                        await turn_context.send_activity(MessageFactory.text(f"Okay, we'll skip that one. {summary_of_saved}"))
                                        logger_msg_activity.info(f"User skipped non-required question '{saved_key}'. Summary sent.", extra={"event_type": "onboarding_question_skipped_ack"})
                                    elif saved_key and saved_value is not None:
                                        # User provided an answer, and it wasn't an empty skip for an optional question
                                        # Map common keys to more readable versions for the message
                                        readable_key_map = {
                                            "welcome_name": "your preferred name",
                                            "primary_role": "your primary role",
                                            "main_projects": "your main projects",
                                            "tool_preferences": "your tool preferences",
                                            "communication_style": "your communication style",
                                            "notifications": "your notification preference",
                                            "personal_credentials": "your choice for personal credentials setup",
                                            "github_token": "your GitHub token",
                                            "jira_email": "your Jira email",
                                            "jira_token": "your Jira API token"
                                        }
                                        display_key = readable_key_map.get(saved_key, f"your answer for '{saved_key}'")
                                        
                                        # For multi-choice, saved_value might be a list
                                        display_value = saved_value
                                        if isinstance(saved_value, list):
                                            display_value = ", ".join(str(v) for v in saved_value)
                                        elif isinstance(saved_value, bool): # For notifications_enabled being true/false
                                            display_value = "enabled" if saved_value else "disabled"
                                        elif saved_key == "notifications": # Original answer was yes/no
                                            display_value = f"'{saved_value}' (notifications will be {'enabled' if saved_value == 'yes' else 'disabled'})"
                                        elif saved_key == "personal_credentials":
                                            display_value = f"'{saved_value}' (we'll ask for details if you said yes)"
                                        else:
                                            display_value = f"'{saved_value}'"

                                        confirmation_msg = f"Thanks! I've noted {display_key} as {display_value}."
                                        await turn_context.send_activity(MessageFactory.text(confirmation_msg))
                                        logger_msg_activity.info(f"Sent confirmation for onboarding answer: key='{saved_key}'.", extra={"event_type": "onboarding_answer_confirmed"})
                            else:
                                logger_msg_activity.error(f"Failed to save UserProfile for {user_profile.user_id} after onboarding answer/skip.", extra={"event_type": "onboarding_profile_increment_save_failed"})
                                # Inform user about save failure? Or rely on next operation failing?
                                # For now, log and proceed. The state in memory is updated, but DB is stale.
                            # --- End: New logic for incremental save and confirmation ---

                            if result.get("completed"):
                                # Message is now a card payload
                                completion_card_payload = result["message"]
                                completion_activity = MessageFactory.attachment(completion_card_payload)
                                await turn_context.send_activity(completion_activity)
                                
                                # Profile is already saved by the incremental save block above
                                if result.get("suggested_role"):
                                    admin_message = (f"\n\n🔒 **Admin Note**: User {user_profile.display_name} "
                                                     f"completed onboarding and was suggested role **{result['suggested_role']}**. "
                                                     f"Use `@augie assign role {user_profile.email or user_profile.user_id} {result['suggested_role']}` to update.")
                                    await turn_context.send_activity(MessageFactory.text(admin_message))
                                logger_msg_activity.info(f"Completed onboarding for user {user_profile.user_id}",
                                                         extra={"event_type": "onboarding_completed", "suggested_role": result.get("suggested_role")})
                            else: 
                                # Send next question, potentially with suggested actions
                                next_question_text = f"**{result['progress']}** {result['message']}"
                                next_question_activity = MessageFactory.text(next_question_text)
                                if result.get("suggested_actions"):
                                    next_question_activity.suggested_actions = SuggestedActions(
                                        actions=result["suggested_actions"]
                                    )
                                await turn_context.send_activity(next_question_activity)
                                
                                logger_msg_activity.debug(f"Sent next onboarding question to user {user_profile.user_id}",
                                                          extra={"event_type": "onboarding_question_sent", "progress": result.get("progress")})
                                return
                        elif OnboardingWorkflow.should_trigger_onboarding(user_profile, app_state):
                            logger_msg_activity.info(f"Triggering onboarding workflow for new user {user_profile.user_id}", extra={"event_type": "onboarding_workflow_triggered"})
                            workflow = onboarding_handler.start_workflow()
                            
                            # --- Create Welcome Hero Card ---
                            welcome_card = CardFactory.hero_card(
                                title="👋 Welcome to Augie!",
                                text=f"Hi {user_profile.display_name}! I'm your AI assistant. A quick setup will help me tailor my responses and tools for you. You can type 'skip onboarding' at any time to bypass this.",
                                images=[CardImage(url=self.app_config.settings.get("AUGIE_LOGO_URL", "https://raw.githubusercontent.com/Aughie/augie_images/main/logos_various_formats/logo_circle_transparent_256.png"))], # Optional: Add a logo if configured
                                # No buttons on the welcome card to prevent misinterpretation of the button click as an answer to the first question.
                                # The first question will be sent immediately after this card.
                            )
                            welcome_activity = MessageFactory.attachment(welcome_card)
                            await turn_context.send_activity(welcome_activity)
                            
                            # --- Send First Actual Question (as a separate activity) ---
                            first_question_response = onboarding_handler._format_question_response(ONBOARDING_QUESTIONS[0], workflow)
                            
                            first_question_activity = MessageFactory.text(
                                f"**{first_question_response['progress']}** {first_question_response['message']}"
                            )
                            if first_question_response.get("suggested_actions"):
                                first_question_activity.suggested_actions = SuggestedActions(actions=first_question_response["suggested_actions"])
                            
                            await turn_context.send_activity(first_question_activity)
                            
                            from user_auth import db_manager
                            profile_dict = user_profile.model_dump()
                            db_manager.save_user_profile(profile_dict)
                            logger_msg_activity.info(f"Started onboarding workflow {workflow.workflow_id} for user {user_profile.user_id}", extra={"event_type": "onboarding_workflow_started", "workflow_id": workflow.workflow_id})
                            return 

                except Exception as e_onboarding: # Correctly scoped except for onboarding block
                    logger_msg_activity.error(f"Error in ONBOARDING LOGIC block: {e_onboarding}", exc_info=True, extra={"event_type": "onboarding_block_error"})
                
                # --- END Onboarding Logic Block --- 
                
                # --- Permission-Aware Bot Responses (after onboarding attempt) ---
                if not app_state.has_permission(Permission.BOT_BASIC_ACCESS): # Moved this check outside onboarding try-except
                    await turn_context.send_activity(MessageFactory.text(
                        "Sorry, you don't have permission to use this bot. Please contact your administrator for access."
                    ))
                    logger_msg_activity.warning(
                        f"Blocked unauthorized access attempt from user {user_profile.user_id}",
                        extra={"event_type": "unauthorized_access_attempt"}
                    )
                    return
            
            else: # user_profile is None
                logger_msg_activity.warning(
                    "Could not load or create user profile for the current turn. Using restricted permissions.",
                    extra={
                        "event_type": "user_profile_load_failed",
                        "details": {
                            "activity_id": turn_context.activity.id,
                            "user_id": turn_context.activity.from_property.id if turn_context.activity.from_property else "unknown"
                        }
                    }
                )
                app_state.current_user = None # Ensure app_state reflects no user

        except Exception as e_user_profile: # Correctly scoped except for the main user profile try block
            logger_msg_activity.error(
                f"Error loading/creating user profile: {e_user_profile}",
                exc_info=True,
                extra={
                    "event_type": "user_profile_error",
                    "details": {
                        "activity_id": turn_context.activity.id,
                        "error": str(e_user_profile),
                        "user_id": turn_context.activity.from_property.id if turn_context.activity.from_property else "unknown"
                    }
                }
            )
            app_state.current_user = None # Ensure app_state reflects no user
        # --- End: Integrate User Authentication (P3A.4.1) ---

        # --- Command Handling / Main LLM Interaction ---
        # (Ensure this part is not reached if a 'return' happened in onboarding)

        activity_text_lower = turn_context.activity.text.lower().strip() if turn_context.activity.text else "" 
        command_handled = False

        # --- Helper function for P3A.5.1: Get available tools based on user permissions (already defined above) ---
        # def get_available_tools_for_user() -> Dict[str, List[Dict[str, str]]]: ...

        # Command 0: @bot help / @bot what can you do / @bot commands
        # (This is general help, onboarding help is handled above)
        # Ensure user_profile is available for the get_active_onboarding_workflow check
        user_is_onboarding = False
        if app_state.current_user: # Check if current_user is not None
            # Corrected: Need to import get_active_onboarding_workflow from workflows.onboarding
            from workflows.onboarding import get_active_onboarding_workflow
            user_is_onboarding = get_active_onboarding_workflow(app_state, app_state.current_user.user_id) is not None
        
        # Placeholder for get_available_tools_for_user
        def get_available_tools_for_user() -> Dict[str, List[Dict[str, str]]]:
            logger_msg_activity.warning("Placeholder get_available_tools_for_user called. Returning empty dict.")
            return {}

        if not user_is_onboarding: # Only show general help if not in active onboarding
            if activity_text_lower in ["help", "@bot help", "@bot what can you do", "@bot commands"]:
                command_handled = True
                available_tools = get_available_tools_for_user() # Ensure this function is accessible or defined earlier
                help_text_lines = [
                    "I'm your ChatOps assistant. Here's what I can help with based on your access level:",
                    "",
                    "Basic Commands:",
                    "- `@bot help` or `@bot what can you do` - Display this help message.",
                    "- `@bot my role` or `@bot my permissions` - See your current role and permissions.",
                ]
                if available_tools:
                    help_text_lines.append("")
                    help_text_lines.append("Available Tool Categories & Commands:")
                    for category, tools_in_category in available_tools.items():
                        help_text_lines.append(f"\n**{category}**:")
                        for tool_info in tools_in_category:
                            help_text_lines.append(f"- `{tool_info['name']}`: {tool_info['description']}")
                else:
                    help_text_lines.append("\nCurrently, I don't have specific tools available to list for your role, or tool loading failed.")

                if app_state.current_user and app_state.has_permission(Permission.MANAGE_USER_ROLES):
                    help_text_lines.append("")
                    help_text_lines.append("**Admin Commands:**")
                    help_text_lines.append("- `@bot admin view permissions for <user_id>` - View another user's permissions.")
                
                await turn_context.send_activity(MessageFactory.text("\n".join(help_text_lines)))
                logger_msg_activity.info(
                    f"User requested help. Displayed help with {len(available_tools)} tool categories.",
                    extra={
                        "event_type": "command_executed",
                        "details": {
                            "command": "help",
                            "user_id": app_state.current_user.user_id if app_state.current_user else "unknown",
                            "role": app_state.current_user.assigned_role if app_state.current_user else "none",
                            "tool_categories": list(available_tools.keys()) if available_tools else []
                        }
                    }
                )
                
            # Command 1: @Bot my permissions / @Bot my role
            if activity_text_lower == "@bot my permissions" or activity_text_lower == "@bot my role":
                command_handled = True
                if app_state.current_user:
                    role_name = app_state.current_user.assigned_role
                    # Use app_state.permission_manager to get effective permissions
                    effective_permissions = app_state.permission_manager.get_effective_permissions(app_state.current_user)
                    perm_names = sorted([p.name for p in effective_permissions])
                    
                    response_md = f"Your assigned role is: **{role_name}**.\n\n"
                    if perm_names:
                        response_md += "Your effective permissions include:\n"
                        for p_name in perm_names:
                            response_md += f"- `{p_name}`\n"
                    else:
                        response_md += "You have the basic permissions associated with your role."
                    
                    await turn_context.send_activity(MessageFactory.text(response_md))
                    logger_msg_activity.info(
                        f"User '{app_state.current_user.user_id}' executed 'my permissions' command.",
                        extra={"event_type": "command_executed", "details": {"command": "my_permissions"}}
                    )
                else:
                    await turn_context.send_activity(MessageFactory.text("Sorry, I couldn't identify you to check your permissions."))
                    logger_msg_activity.warning(
                        "User tried 'my permissions' command but current_user is None.",
                        extra={"event_type": "command_failed", "details": {"command": "my_permissions", "reason": "User not identified"}}
                    )
            
            # Command 2: @Bot admin view role for <user_id> / @Bot admin view permissions for <user_id>
            # Using a simple regex to capture the user_id
            admin_view_match = re.match(r"@bot admin view (?:role|permissions) for (\S+)", activity_text_lower)
            if admin_view_match:
                command_handled = True
                target_user_id = admin_view_match.group(1)

                if not app_state.current_user:
                    await turn_context.send_activity(MessageFactory.text("Sorry, I couldn't identify you to perform this admin command."))
                    logger_msg_activity.warning(
                        "Admin command 'view role for user' failed: Requesting user not identified.",
                        extra={"event_type": "admin_command_failed", "details": {"command": "admin_view_role", "reason": "Requesting user not identified"}}
                    )
                elif not app_state.has_permission(Permission.MANAGE_USER_ROLES): # Using MANAGE_USER_ROLES for this
                    await turn_context.send_activity(MessageFactory.text("Sorry, you don't have permission to view other users' roles/permissions."))
                    logger_msg_activity.warning(
                        f"User '{app_state.current_user.user_id}' denied access to 'admin view role for {target_user_id}' command.",
                        extra={"event_type": "admin_command_denied", "details": {"command": "admin_view_role", "requesting_user": app_state.current_user.user_id, "target_user": target_user_id}}
                    )
                else:
                    # Admin is authorized, proceed to fetch target user
                    from user_auth.db_manager import get_user_profile_by_id # Local import
                    target_user_profile_dict = get_user_profile_by_id(target_user_id)

                    if not target_user_profile_dict:
                        await turn_context.send_activity(MessageFactory.text(f"User '{target_user_id}' not found."))
                    else:
                        target_user = UserProfile(**target_user_profile_dict)
                        role_name = target_user.assigned_role
                        # Use app_state.permission_manager as it's already instantiated
                        effective_permissions = app_state.permission_manager.get_effective_permissions(target_user)
                        perm_names = sorted([p.name for p in effective_permissions])

                        response_md = f"User **{target_user.user_id}** (Display: {target_user.display_name}) has role: **{role_name}**.\n\n"
                        if perm_names:
                            response_md += "Their effective permissions include:\n"
                            for p_name in perm_names:
                                response_md += f"- `{p_name}`\n"
                        else:
                            response_md += f"They have the basic permissions associated with the {role_name} role."
                        
                        await turn_context.send_activity(MessageFactory.text(response_md))
                        logger_msg_activity.info(
                            f"Admin '{app_state.current_user.user_id}' executed 'admin view role for {target_user_id}'.",
                            extra={"event_type": "admin_command_executed", "details": {"command": "admin_view_role", "target_user": target_user_id}}
                        )

        # NEW Command: @bot my preferences / @bot my data
        my_prefs_commands = [
            "@bot my preferences", "@bot show my preferences", "@bot my data", 
            "@bot my settings", "@bot view my preferences", "@bot summarize my preferences"
        ]
        if activity_text_lower in my_prefs_commands:
            command_handled = True
            if app_state.current_user and app_state.current_user.profile_data:
                prefs = app_state.current_user.profile_data.get("preferences", {})
                onboarding_status = app_state.current_user.profile_data.get("onboarding_status", "unknown")
                completed_at = app_state.current_user.profile_data.get("onboarding_completed_at")
                skipped_at = app_state.current_user.profile_data.get("onboarding_skipped_at")

                summary_lines = ["Here's a summary of your current preferences:", ""]

                if onboarding_status == "skipped" and skipped_at:
                    summary_lines.insert(1, f"(Onboarding was skipped on {datetime.fromisoformat(skipped_at).strftime('%Y-%m-%d %H:%M')} UTC)")
                elif onboarding_status != "skipped" and completed_at: # completed or other status but has completion time
                    summary_lines.insert(1, f"(Onboarding completed on {datetime.fromisoformat(completed_at).strftime('%Y-%m-%d %H:%M')} UTC)")
                
                summary_lines.append(f"👤 Preferred Name: {prefs.get('preferred_name', 'Not set')}")
                summary_lines.append(f"🎯 Primary Role: {prefs.get('primary_role', 'Not set')}")
                
                projects = prefs.get('main_projects', [])
                summary_lines.append(f"📂 Main Projects: {(', '.join(projects) if projects else 'None specified')}")
                
                tools = prefs.get('tool_preferences', [])
                summary_lines.append(f"🛠️ Tool Preferences: {(', '.join(tools) if tools else 'None specified')}")
                
                summary_lines.append(f"💬 Communication Style: {prefs.get('communication_style', 'Default / Not set')}")
                
                notifications_enabled = prefs.get('notifications_enabled')
                notifications_text = "Enabled" if notifications_enabled else ("Disabled" if notifications_enabled is False else "Default (Disabled)")
                summary_lines.append(f"🔔 Notifications: {notifications_text}")
                
                summary_lines.append("\nYou can update these by using the `@augie preferences` command (if available) or by asking to change specific settings.")
                # Future: "...or by re-running onboarding (this would reset them to defaults before asking)."

                await turn_context.send_activity(MessageFactory.text("\n".join(summary_lines)))
                logger_msg_activity.info(
                    f"User '{app_state.current_user.user_id}' executed 'my preferences' command.",
                    extra={"event_type": "command_executed", "details": {"command": "my_preferences"}}
                )
            elif app_state.current_user: # Has profile, but no profile_data or no preferences
                 await turn_context.send_activity(MessageFactory.text("It seems your preferences haven't been set up yet. You can go through onboarding to set them."))
                 logger_msg_activity.info(
                    f"User '{app_state.current_user.user_id}' tried 'my preferences' but no preference data found.",
                    extra={"event_type": "command_executed_no_data", "details": {"command": "my_preferences"}}
                )            
            else: # No current_user
                await turn_context.send_activity(MessageFactory.text("Sorry, I couldn't identify you to show your preferences."))
                logger_msg_activity.warning(
                    "User tried 'my preferences' command but current_user is None.",
                    extra={"event_type": "command_failed", "details": {"command": "my_preferences", "reason": "User not identified"}}
                )

        if command_handled:
            # If a command was handled, we might not want to proceed to the main LLM logic.
            # Save state and return.
            # The session summary will be logged in on_turn as usual.
            await self.conversation_state.save_changes(turn_context) # Ensure state is saved
            await self.user_state.save_changes(turn_context)
            logger_msg_activity.info(f"Command handled: '{activity_text_lower}'. Bypassing main LLM interaction for this turn.", extra={"event_type": "command_bypass_llm"})
            # We should also ensure total_duration_ms is set if we bypass the main loop.
            if hasattr(app_state, "session_stats") and app_state.session_stats is not None:
                 interaction_end_time = time.monotonic()
                 app_state.session_stats.total_duration_ms = int((interaction_end_time - interaction_start_time) * 1000)
            return 
        # --- End: P3A.5.2 Permission Management Commands ---

        # Use enhanced handler for safe message processing instead of direct add_message
        logger_msg_activity.debug("Processing user input with enhanced handler for safety")
        success, result = self.enhanced_handler.safe_process_user_input(
            turn_context.activity.text, 
            app_state
        )
        
        if not success:
            # Enhanced handler detected an issue with the message
            logger_msg_activity.error(f"Enhanced handler rejected user input: {result}")
            await turn_context.send_activity(MessageFactory.text(
                f"I'm sorry, but I encountered an issue processing your message: {result}"
            ))
            # Save state and return early
            await self.conversation_state.save_changes(turn_context)
            await self.user_state.save_changes(turn_context)
            return
        
        logger_msg_activity.info(f"Enhanced handler successfully processed user input: '{result[:50]}{'...' if len(result) > 50 else ''}'")

        # Reset turn-specific state if method exists
        if hasattr(app_state, "reset_turn_state") and callable(
            app_state.reset_turn_state
        ):
            app_state.reset_turn_state()
            logger_msg_activity.debug("Called app_state.reset_turn_state()", extra={"event_type": "state_reset_turn"})
        else:
            logger_msg_activity.debug(
                "AppState missing callable 'reset_turn_state' method.",
                extra={"event_type": "state_warning", "details": {"missing_method": "reset_turn_state"}}
            )

        # Send an initial "thinking" or typing activity
        typing_activity = Activity(type=ActivityTypes.typing)
        sent_typing_activity_resource_response = (
            await turn_context.send_activity(typing_activity)
        )
        last_activity_id_to_update = (
            sent_typing_activity_resource_response.id
            if sent_typing_activity_resource_response
            else None
        )
        logger_msg_activity.debug(f"Initial last_activity_id_to_update: {last_activity_id_to_update}", extra={"event_type": "debug_internal_state", "details": {"last_activity_id": last_activity_id_to_update}})

        accumulated_text_response: List[str] = []
        final_bot_message_sent = False
     
        # Check if the bot is already processing a request for this session
        if app_state.is_streaming:
            logger_msg_activity.warning(
                "Attempt to start new response while already streaming for session.",
                extra={
                    "event_type": "concurrent_message_blocked",
                    "details": {
                        "session_id": app_state.session_id,
                        "user_message": turn_context.activity.text
                    }
                }
            )
            await turn_context.send_activity(
                MessageFactory.text("I'm still working on your previous request. Please wait a moment before sending a new one.")
            )
            # Do not proceed with processing this new message
            # State will be saved in on_turn, including the user message that was just added.
            # The next time the user sends a message (after streaming is false), that new message will be processed.
            return
     
        try:
            stream = start_streaming_response(  # Async generator
                app_state=app_state,
                llm=self.llm_interface,
                tool_executor=self.tool_executor,
                config=self.app_config,
            )
            logger_msg_activity.debug("Stream object obtained.", extra={"event_type": "stream_initiated", "details": {"stream_type": str(type(stream))}})
            async for event in stream:
                event_type = event.get("type")
                event_content = event.get("content")
                logger_msg_activity.debug(
                    "Bot received event from stream.",
                    extra={
                        "event_type": "stream_event_received",
                        "details": {
                            "session_id": app_state.session_id, # Added for clarity
                            "event_type_from_stream": event_type,
                            "event_content_preview": str(event_content)[:100],
                            "last_activity_id": last_activity_id_to_update,
                            "accumulated_text_len": len(''.join(accumulated_text_response))
                        }
                    }
                )

                if event_type == "text_chunk":
                    if event_content is not None:
                        accumulated_text_response.append(str(event_content))
                    
                    if last_activity_id_to_update:
                        updated_text = "".join(accumulated_text_response).strip()
                        if updated_text:
                            activity_to_update = Activity(
                                id=last_activity_id_to_update,
                                type=ActivityTypes.message,
                                text=updated_text,
                            )
                            try:
                                await turn_context.update_activity(activity_to_update)
                                final_bot_message_sent = True
                                logger_msg_activity.debug("Updated activity with text_chunk.", extra={"event_type": "activity_updated", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "update_type": "text_chunk"}})
                            except Exception as update_error:
                                logger_msg_activity.warning(
                                    "Failed to update activity with text_chunk, falling back to new message.",
                                    exc_info=True,
                                    extra={"event_type": "activity_update_failed", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "error": str(update_error)}}
                                )
                                # Fallback: send as new message if update failed
                                new_activity_sent_response = await turn_context.send_activity(Activity(type=ActivityTypes.message, text=updated_text))
                                last_activity_id_to_update = new_activity_sent_response.id if new_activity_sent_response else None
                                final_bot_message_sent = True
                                accumulated_text_response = [updated_text] # Reset accumulated for next potential update
                elif event_type == "status":
                    status_message = f"⏳ Status: {event_content}"
                    if last_activity_id_to_update and not "".join(accumulated_text_response).strip():
                        activity_to_update = Activity(
                            id=last_activity_id_to_update,
                            type=ActivityTypes.message, # Ensure it's a message type
                            text=status_message,
                        )
                        try:
                            await turn_context.update_activity(activity_to_update)
                            final_bot_message_sent = True # Consider this a message sent
                            logger_msg_activity.debug("Updated activity with status.", extra={"event_type": "activity_updated", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "update_type": "status", "status_content": event_content}})
                        except Exception as update_error:
                            logger_msg_activity.warning(
                                "Failed to update status activity, sending new.",
                                exc_info=True,
                                extra={"event_type": "activity_update_failed", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "error": str(update_error)}}
                            )
                            # Fallback: send as new message
                            new_activity_sent_response = await turn_context.send_activity(status_message)
                            last_activity_id_to_update = new_activity_sent_response.id if new_activity_sent_response else None
                            final_bot_message_sent = True
                            # Since status is ephemeral, don't add to accumulated_text_response
                    else: # If there's already text or no activity to update, send new or log
                        logger_msg_activity.info(f"Status update: {event_content}", extra={"event_type": "status_update_logged", "details": {"session_id": app_state.session_id, "status_content": event_content}})
                        # Optionally send as a new message if important enough and not just for logs
                        # await turn_context.send_activity(MessageFactory.text(status_message))
                        # For now, just logging if it can't be an update of the placeholder

                elif event_type == "tool_calls":
                    tool_names = [tc.get("function", {}).get("name", "N/A") for tc in (event_content or []) if isinstance(tc, dict)]
                    tool_call_msg = f"🔧 Using tools: {', '.join(tool_names)}"
                    logger_msg_activity.info("Tool calls initiated.", extra={"event_type": "tool_calls_initiated", "details": {"tool_names": tool_names, "raw_tool_calls": event_content}})
                    
                    # --- P3A.5.3 Access Auditing: Permission check for tool access ---
                    if app_state.current_user:
                        # Log tool usage attempt for audit purposes
                        logger_msg_activity.info(
                            f"User {app_state.current_user.user_id} with role {app_state.current_user.assigned_role} attempting to use tools: {', '.join(tool_names)}",
                            extra={
                                "event_type": "tool_access_attempt",
                                "details": {
                                    "user_id": app_state.current_user.user_id,
                                    "user_role": app_state.current_user.assigned_role,
                                    "tools_attempted": tool_names,
                                    "conversation_id": turn_context.activity.conversation.id
                                }
                            }
                        )
                    
                    if last_activity_id_to_update and not "".join(accumulated_text_response).strip():
                        try:
                            await turn_context.update_activity(
                                Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=tool_call_msg)
                            )
                            final_bot_message_sent = True
                        except Exception as update_error:
                            logger_msg_activity.warning("Failed to update tool calls activity, sending new.", exc_info=True, extra={"event_type": "activity_update_failed", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "error": str(update_error)}})
                            await turn_context.send_activity(tool_call_msg)
                            final_bot_message_sent = True
                    else:
                        await turn_context.send_activity(tool_call_msg)
                        final_bot_message_sent = True
                    last_activity_id_to_update = None

                elif event_type == "tool_results":
                    logger_msg_activity.info(
                        "Received 'tool_results' event. This will be processed by the LLM.",
                        extra={"event_type": "tool_results_received_internal", "details": {"content_preview": str(event_content)[:200]}}
                    )
                    
                    # --- P3A.5.3 Access Auditing: Check for permission denied responses ---
                    if isinstance(event_content, list): # Corrected: event_content is a list of tool result message dicts
                        for tool_result_msg_dict in event_content: # Corrected: iterate over the list
                            if isinstance(tool_result_msg_dict, dict):
                                content_str = tool_result_msg_dict.get("content")
                                tool_name_from_msg = tool_result_msg_dict.get("name", "unknown tool") # Get tool name from the message itself
                                
                                if content_str and isinstance(content_str, str):
                                    try:
                                        parsed_content_data = json.loads(content_str)
                                        if isinstance(parsed_content_data, dict) and \
                                           parsed_content_data.get("status") == "PERMISSION_DENIED":
                                            
                                            permission_msg = parsed_content_data.get("message", f"Permission denied for {tool_name_from_msg}")
                                            
                                            # Log the permission denial for audit purposes
                                            logger_msg_activity.warning(
                                                f"Permission denied: {permission_msg}",
                                                extra={
                                                    "event_type": "permission_denied_explicit_message", # Changed event_type slightly
                                                    "details": {
                                                        "tool_name": tool_name_from_msg,
                                                        "user_id": app_state.current_user.user_id if app_state.current_user else "unknown",
                                                        "role": app_state.current_user.assigned_role if app_state.current_user else "none",
                                                        "conversation_id": turn_context.activity.conversation.id,
                                                        "permission_message": permission_msg
                                                    }
                                                }
                                            )
                                            
                                            await turn_context.send_activity(
                                                f"⚠️ {permission_msg}. If you need this capability, please contact your administrator."
                                            )
                                    except json.JSONDecodeError:
                                        logger_msg_activity.warning(
                                            f"Could not parse tool result content as JSON for tool '{tool_name_from_msg}' while checking for PERMISSION_DENIED.",
                                            extra={"event_type": "tool_result_parse_error_permission_check", "details": {"tool_name": tool_name_from_msg, "content_preview": content_str[:100]}}
                                        )
                    
                    pass # Explicitly do nothing more for tool_results here, LLM will handle them

                elif event_type == "workflow_pause":
                    pause_event_content = event.get("content", {})
                    pause_msg = pause_event_content.get("message", "Workflow paused, awaiting your input.")
                    raw_draft = pause_event_content.get("raw_draft_for_display")
                    logger_msg_activity.info("Workflow paused.", extra={"event_type": "workflow_paused", "details": pause_event_content})

                    if raw_draft:
                        await turn_context.send_activity(MessageFactory.text(f"```markdown\n{raw_draft}\n```"))

                    activity_to_send = MessageFactory.text(pause_msg)
                    suggested_bot_actions = []
                    if "actions" in pause_event_content and pause_event_content["actions"]:
                        for action_def in pause_event_content["actions"]:
                            if isinstance(action_def, dict):
                                suggested_bot_actions.append(
                                    CardAction(
                                        type=action_def.get("type", ActionTypes.im_back),
                                        title=action_def.get("title") or "",
                                        value=action_def.get("value") or "",
                                        text=(action_def.get("text", action_def.get("value") or "") or ""),
                                        display_text=(action_def.get("display_text", action_def.get("title") or "") or ""),
                                    )
                                )
                            else:
                                logger_msg_activity.warning("Skipping invalid action definition in workflow_pause event.", extra={"event_type": "invalid_action_definition", "details": {"action_def": action_def}})
                        if suggested_bot_actions:
                            activity_to_send.suggested_actions = SuggestedActions(actions=suggested_bot_actions)
                    
                    await turn_context.send_activity(activity_to_send)
                    final_bot_message_sent = True
                    last_activity_id_to_update = None
                    if hasattr(app_state, "last_interaction_status"):
                        app_state.last_interaction_status = "WAITING_USER_INPUT"
                
                elif event_type == "workflow_transition":
                    next_stage_name = event_content.get("next_stage", "next stage") if isinstance(event_content, dict) else "next stage"
                    transition_msg = f"Workflow progressing to {next_stage_name}..."
                    logger_msg_activity.info("Workflow transitioning.", extra={"event_type": "workflow_transitioning", "details": {"next_stage": next_stage_name, "content": event_content}})
                    await turn_context.send_activity(transition_msg)
                    final_bot_message_sent = True
                    last_activity_id_to_update = None

                elif event_type == "error":
                    error_display_msg = f"🚨 Error: {event_content}"
                    logger_msg_activity.error("Error event received from stream.", extra={"event_type": "stream_error_event", "details": {"error_content": event_content}})
                    
                    # CRITICAL FIX: Reset is_streaming on error to prevent getting stuck
                    if hasattr(app_state, "is_streaming"):
                        app_state.is_streaming = False
                        logger_msg_activity.debug("Reset is_streaming to False on error.", extra={"event_type": "is_streaming_reset_error"})
                    
                    if last_activity_id_to_update and not "".join(accumulated_text_response).strip():
                        try:
                            await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=error_display_msg))
                            final_bot_message_sent = True
                        except Exception as update_error:
                            logger_msg_activity.warning("Failed to update error activity, sending new.", exc_info=True, extra={"event_type": "activity_update_failed", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "error": str(update_error)}})
                            await turn_context.send_activity(error_display_msg)
                            final_bot_message_sent = True
                    else:
                        await turn_context.send_activity(error_display_msg)
                    final_bot_message_sent = True
                    last_activity_id_to_update = None
                    if hasattr(app_state, "last_interaction_status"):
                        app_state.last_interaction_status = "ERROR"
                    break

                elif event_type == "completed":
                    final_status_val = event_content.get("status", "COMPLETED_OK") if isinstance(event_content, dict) else "COMPLETED_OK"
                    if hasattr(app_state, "last_interaction_status"):
                        app_state.last_interaction_status = final_status_val
                    
                    # CRITICAL FIX: Reset is_streaming here to ensure state is saved correctly
                    # This prevents the bot from getting stuck in streaming mode
                    if hasattr(app_state, "is_streaming"):
                        app_state.is_streaming = False
                        logger_msg_activity.debug("Reset is_streaming to False on completion.", extra={"event_type": "is_streaming_reset"})
                    
                    logger_msg_activity.info("Chat logic completed.", extra={"event_type": "stream_completed", "details": {"status": final_status_val}})
                    break
        
        except HistoryResetRequiredError as e:
            logger_msg_activity.warning(
                "HistoryResetRequiredError caught in on_message_activity.",
                exc_info=True,
                extra={"event_type": "history_reset_required_error", "details": {"error_message": str(e)}}
            )
            reset_message = (
                "🔄 My apologies, I had a problem with our conversation "
                "history and had to reset it. Please try your request "
                f"again. (Details: {e})"
            )
            await turn_context.send_activity(MessageFactory.text(reset_message))
            final_bot_message_sent = True
            if hasattr(app_state, "last_interaction_status"):
                app_state.last_interaction_status = "HISTORY_RESET"

        except Exception as e:
            logger_msg_activity.error(
                "Unhandled error in on_message_activity's streaming loop.",
                exc_info=True,
                extra={"event_type": "unhandled_stream_exception"}
            )
            error_message = "Sorry, an unexpected error occurred while I was processing your request."
            try:
                if last_activity_id_to_update and not "".join(accumulated_text_response).strip():
                    try:
                        await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=f"🚨 {error_message}"))
                        final_bot_message_sent = True
                    except Exception as update_error:
                        logger_msg_activity.warning("Failed to update activity with unhandled error message, sending new.", exc_info=True, extra={"event_type": "activity_update_failed", "details": {"session_id": app_state.session_id, "activity_id": last_activity_id_to_update, "error": str(update_error)}})
                        await turn_context.send_activity(f"🚨 {error_message}")
                        final_bot_message_sent = True
                    last_activity_id_to_update = None
                else:
                    await turn_context.send_activity(f"🚨 {error_message}")
                    final_bot_message_sent = True
            except Exception as send_err:
                logger_msg_activity.error("Failed to send unhandled error message to user.", exc_info=True, extra={"event_type": "send_error_message_failed"})
            final_bot_message_sent = True # Ensure this is true if an error message was attempted
            if hasattr(app_state, "last_interaction_status"):
                app_state.last_interaction_status = "FATAL_ERROR"
        finally:
            if "app_state" in locals() and isinstance(app_state, AppState):
                sanitized_count = sanitize_message_content(app_state)
                if sanitized_count > 0:
                    logger_msg_activity.debug(f"Sanitized {sanitized_count} messages before saving state.", extra={"event_type": "state_sanitized", "details": {"count": sanitized_count}})

                if hasattr(app_state, "session_stats") and app_state.session_stats is not None and app_state.session_stats.total_duration_ms == 0:
                    interaction_end_time = time.monotonic()
                    app_state.session_stats.total_duration_ms = int((interaction_end_time - interaction_start_time) * 1000)
                    logger_msg_activity.debug(
                        "Calculated interaction duration in finally block.",
                        extra={"event_type": "duration_calculated", "details": {"duration_ms": app_state.session_stats.total_duration_ms}}
                    )
                try:
                    log_session_summary_adapted(
                        app_state=app_state,
                        final_status=getattr(app_state, "last_interaction_status", "UNKNOWN"),
                        error_details=getattr(app_state, "current_step_error", None),
                    )
                except Exception as log_e:
                    logger_msg_activity.error("Failed to log session summary.", exc_info=True, extra={"event_type": "session_summary_log_failed"})
            else:
                logger_msg_activity.error(
                    "Could not log session summary: app_state not available or invalid.",
                    extra={"event_type": "session_summary_log_skipped_no_state"}
                )
            
            clear_turn_ids() # Clear all correlation IDs at the end of the turn
            logger_msg_activity.info("Turn processing finished.", extra={"event_type": "turn_end", "details": {"activity_id": turn_context.activity.id, "final_status": getattr(app_state, "last_interaction_status", "UNKNOWN") if 'app_state' in locals() else "UNKNOWN_NO_APP_STATE"}})

        final_text_to_send = "".join(accumulated_text_response).strip()
        placeholder_updated = final_bot_message_sent and last_activity_id_to_update is not None

        if final_text_to_send and not placeholder_updated:
            await turn_context.send_activity(MessageFactory.text(final_text_to_send))
            final_bot_message_sent = True
            logger_msg_activity.info("Sent final text response as a new message activity.", extra={"event_type": "final_text_sent_new_message"})
        elif not final_text_to_send and not final_bot_message_sent:
            current_status = getattr(app_state, "last_interaction_status", "")
            if current_status not in ["ERROR", "FATAL_ERROR", "HISTORY_RESET", "WAITING_USER_INPUT"]:
                await turn_context.send_activity(MessageFactory.text("✅ Processed."))
                logger_msg_activity.info("Sent generic completion message.", extra={"event_type": "generic_completion_sent"})
                final_bot_message_sent = True

        if final_text_to_send and placeholder_updated and last_activity_id_to_update is not None:
            await turn_context.send_activity(MessageFactory.text(final_text_to_send))
            logger_msg_activity.info("Force-sent final response as a new message activity (bugfix).", extra={"event_type": "final_text_force_sent_new_message"})
            final_bot_message_sent = True

        if hasattr(app_state, "session_stats") and app_state.session_stats is not None:
            logger.info( # This is the existing summary log, keep it as is or integrate with JSON if preferred
                "Turn completed. Session: %s, Duration: %sms, LLM Calls: %s, Status: %s",
                app_state.session_id,
                app_state.session_stats.total_duration_ms,
                app_state.session_stats.llm_calls,
                getattr(app_state, "last_interaction_status", "N/A"),
            )
        else:
            logger.info(
                "Turn completed. Session: %s, Status: %s (Session stats missing)",
                app_state.session_id,
                getattr(app_state, "last_interaction_status", "N/A"),
            )
