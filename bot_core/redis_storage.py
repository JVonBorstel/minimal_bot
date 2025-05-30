import json
import logging
from typing import List, Dict, Any, Optional
import pprint 
import redis 
import asyncio

import redis.asyncio as aioredis
from botbuilder.core import Storage, StoreItem
from pydantic import BaseModel # GOTTTTAAA make sure this is imported

from config import AppSettings 

log = logging.getLogger(__name__)

class RedisStorageError(Exception):
    """Custom exception for RedisStorage errors."""
    pass

class RedisStorage(Storage):
    """
    A Storage provider that uses an asynchronous Redis client for state persistence.
    It stores bot state data as JSON strings in Redis.
    """

    def __init__(self, app_settings: AppSettings):
        """
        Initializes a new instance of the RedisStorage class.

        Args:
            app_settings: The application settings containing Redis configuration.
        """
        super().__init__()
        self._app_settings = app_settings
        self._redis_client: Optional[aioredis.Redis] = None
        self._is_initializing = False # Flag to prevent re-entrant initialization
        self._redis_prefix = self._app_settings.redis_prefix # Storing prefix for convenience

    # --- START: Interface Adapter Methods for ToolCallAdapter ---
    async def get_app_state(self, session_id: str) -> Optional['AppState']:
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
        from state_models import AppState  # Import here to avoid circular imports
        
        log.debug(f"RedisStorage.get_app_state called for session_id: {session_id}")
        try:
            # Read data using the standard read method - only fetch the session we need
            data_dict = await self.read([session_id])
            if not data_dict or session_id not in data_dict or data_dict[session_id] is None:
                log.warning(f"No state found for session_id: {session_id}")
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
                log.error(f"Error validating state data for session_id {session_id}: {e}", exc_info=True)
                return None
                
        except Exception as e:
            log.error(f"Error in get_app_state for session_id {session_id}: {e}", exc_info=True)
            return None
            
    async def save_app_state(self, session_id: str, app_state: 'AppState') -> bool:
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
        log.debug(f"RedisStorage.save_app_state called for session_id: {session_id}")
        try:
            # Convert AppState to a serializable format with mode='json' to handle all data types
            state_data = app_state.model_dump(mode='json')
            
            # Write data using the standard write method
            await self.write({session_id: state_data})
            return True
        except Exception as e:
            log.error(f"Error in save_app_state for session_id {session_id}: {e}", exc_info=True)
            return False
    # --- END: Interface Adapter Methods for ToolCallAdapter ---

    async def _ensure_client_initialized(self):
        """Ensures the Redis client is initialized before use."""
        if self._redis_client is None:
            if self._is_initializing:
                # Another task is already initializing, wait or raise if needed
                # For now, simple prevention, could add a lock/event if true concurrency is expected here
                log.warning("Redis client initialization already in progress.")
                # Potentially wait for an event or timeout
                # For simplicity, we'll let subsequent calls attempt initialization
                # if the first one fails or this check becomes a bottleneck.
                # However, if _initialize_client is always awaited properly on first use,
                # this re-entrancy might be less of an issue.
                return 

            self._is_initializing = True
            try:
                await self._initialize_client()
            finally:
                self._is_initializing = False

    async def _initialize_client(self):
        """
        Establishes a connection to the Redis server using settings from AppSettings.
        """
        if self._redis_client:
            return

        log.info("Initializing Redis client...")
        settings = self._app_settings

        try:
            if settings.redis_url:
                log.info(f"Connecting to Redis using URL: {settings.redis_url}")
                # If from_url is patched with new_callable=AsyncMock, the call itself needs to be awaited.
                self._redis_client = await aioredis.from_url(
                    str(settings.redis_url),
                    encoding="utf-8",
                    decode_responses=True 
                )
            else:
                log.info(f"Connecting to Redis using host: {settings.redis_host}, port: {settings.redis_port}, DB: {settings.redis_db}")
                # If Redis class is patched with new_callable=AsyncMock, the instantiation call needs to be awaited.
                self._redis_client = await aioredis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port or 6379,
                    password=settings.redis_password,
                    db=settings.redis_db or 0,
                    ssl=settings.redis_ssl_enabled or False,
                    encoding="utf-8",
                    decode_responses=True
                )
            
            # Now self._redis_client should be the actual client object (or mock client object)
            await self._redis_client.ping()
            log.info("Successfully connected to Redis and pinged server.")
            log.info(f"Redis client type after initialization: {type(self._redis_client)}")

        except redis.exceptions.ConnectionError as e:
            log.error(f"Redis connection failed: {e}", exc_info=True)
            self._redis_client = None # Ensure client is None if connection fails
            raise RedisStorageError(f"Failed to connect to Redis: {e}") from e
        except Exception as e: # Catch other potential errors during client creation
            log.error(f"An unexpected error occurred during Redis client initialization: {e}", exc_info=True)
            self._redis_client = None
            raise RedisStorageError(f"Unexpected error initializing Redis client: {e}") from e

    async def read(self, keys: List[str]) -> Dict[str, Any]:
        """
        Reads specific StoreItems from Redis.

        Args:
            keys: A list of keys for the StoreItems to read.

        Returns:
            A dictionary of StoreItems, with keys matching the input.
        """
        if not keys:
            return {}

        await self._ensure_client_initialized()
        if not self._redis_client:
            raise RedisStorageError("Redis client not available for read operation.")

        state: Dict[str, Any] = {}
        prefixed_keys = [self._redis_prefix + key for key in keys]
        try:
            log.debug(f"Reading prefixed keys from Redis: {prefixed_keys}")
            values = await self._redis_client.mget(prefixed_keys)
            
            for i, original_key in enumerate(keys):
                value = values[i]
                if value is not None:
                    try:
                        log.debug(f"RedisRead: Raw value for key '{original_key}' (prefixed: {prefixed_keys[i]}): {value}")
                        deserialized_item = json.loads(value)
                        log.debug(f"RedisRead: Loaded data for key '{original_key}': {pprint.pformat(deserialized_item)}")
                        if not isinstance(deserialized_item, dict):
                            log.warning(f"Deserialized item for key '{original_key}' is not a dict, skipping. Value: {value[:200]}")
                            continue
                        state[original_key] = deserialized_item
                    except json.JSONDecodeError as e:
                        log.error(f"Failed to deserialize JSON for key '{original_key}' (prefixed: {prefixed_keys[i]}). Value: '{value[:500]}'. Error: {e}")
                        continue
                    except Exception as e:
                        log.error(f"Unexpected error processing key '{original_key}' (prefixed: {prefixed_keys[i]}). Value: {value[:500]}. Error: {e}")
                        continue
                else:
                    log.debug(f"Key '{original_key}' (prefixed: {prefixed_keys[i]}) not found in Redis.")
            log.debug(f"Successfully read {len(state)} items from Redis.")
            return state
        except redis.exceptions.RedisError as e:
            log.error(f"Redis read operation failed: {e}", exc_info=True)
            raise RedisStorageError(f"Redis read failed: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error during Redis read: {e}", exc_info=True)
            raise RedisStorageError(f"Unexpected error during Redis read: {e}") from e

    async def write(self, changes: Dict[str, Any]):
        """
        Writes StoreItems to Redis.

        Args:
            changes: A dictionary of StoreItems to write, with their keys.
                     The value should be a dict representing the StoreItem.
        """
        if not changes:
            return

        await self._ensure_client_initialized()
        if not self._redis_client:
            raise RedisStorageError("Redis client not available for write operation.")

        try:
            log.debug(f"Writing {len(changes)} items to Redis.")
            # For Bot Framework, StoreItem has an eTag. Redis doesn't inherently use eTags
            # like CosmosDB or Table Storage. If optimistic locking is needed, it must be
            # implemented using WATCH/MULTI/EXEC or Lua scripts.
            # For basic storage, we just serialize the whole StoreItem (or dict).

            # Using a pipeline for atomic writes if multiple changes
            async with self._redis_client.pipeline(transaction=True) as pipe:
                for key, store_item_data in changes.items():
                    if not isinstance(store_item_data, dict) and not isinstance(store_item_data, BaseModel):
                        log.warning(f"Item for key '{key}' is not a dict or Pydantic BaseModel, skipping write. Type: {type(store_item_data)}")
                        continue
                    
                    temp_store_item_dict = {}
                    if isinstance(store_item_data, dict):
                        for item_key, item_val in store_item_data.items():
                            if isinstance(item_val, BaseModel):
                                temp_store_item_dict[item_key] = item_val.model_dump(mode='json')
                            else:
                                temp_store_item_dict[item_key] = item_val
                        data_to_serialize = temp_store_item_dict
                    else: 
                        data_to_serialize = store_item_data
                        if isinstance(store_item_data, BaseModel):
                             data_to_serialize = store_item_data.model_dump(mode='json')
                    
                    prefixed_key = self._redis_prefix + key
                    try:
                        log.debug(f"RedisWrite: Key: {key} (prefixed: {prefixed_key}), Type of store_item_data: {type(store_item_data)}")
                        
                        log.debug(f"RedisWrite: Type of data_to_serialize: {type(data_to_serialize)}")
                        if isinstance(data_to_serialize, dict):
                            log.debug(f"RedisWrite: data_to_serialize (dict): {pprint.pformat(data_to_serialize)}")
                        else:
                            log.debug(f"RedisWrite: data_to_serialize (str): {str(data_to_serialize)[:500]}")

                        serialized_value = json.dumps(data_to_serialize)
                        log.debug(f"RedisWrite: JSON data to write for key {key} (prefixed: {prefixed_key}): {serialized_value[:500]}")
                        await pipe.set(prefixed_key, serialized_value)
                        log.debug(f"Queued SET for key: {key} (prefixed: {prefixed_key})")
                    except TypeError as e:
                        log.error(f"Failed to serialize item for key '{key}' (prefixed: {prefixed_key}) to JSON. Object type: {type(data_to_serialize)}. Error: {e}", exc_info=True)
                        raise RedisStorageError(f"Serialization failed for key '{key}': {e}") from e
                await pipe.execute()
            log.info(f"Successfully wrote {len(changes)} items to Redis.")

        except redis.exceptions.RedisError as e:
            log.error(f"Redis write operation failed: {e}", exc_info=True)
            raise RedisStorageError(f"Redis write failed: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error during Redis write: {e}", exc_info=True)
            raise RedisStorageError(f"Unexpected error during Redis write: {e}") from e


    async def delete(self, keys: List[str]):
        """
        Deletes StoreItems from Redis.

        Args:
            keys: A list of keys for the StoreItems to delete.
        """
        if not keys:
            return

        await self._ensure_client_initialized()
        if not self._redis_client:
            raise RedisStorageError("Redis client not available for delete operation.")
        
        prefixed_keys = [self._redis_prefix + key for key in keys]
        try:
            log.debug(f"Deleting prefixed keys from Redis: {prefixed_keys}")
            deleted_count = await self._redis_client.delete(*prefixed_keys)
            log.info(f"Successfully deleted {deleted_count} keys from Redis (based on prefixed keys: {prefixed_keys}).")
        except redis.exceptions.RedisError as e:
            log.error(f"Redis delete operation failed: {e}", exc_info=True)
            raise RedisStorageError(f"Redis delete failed: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error during Redis delete: {e}", exc_info=True)
            raise RedisStorageError(f"Unexpected error during Redis delete: {e}") from e

    async def close(self):
        """
        Closes the Redis client connection if it's open.
        """
        if self._redis_client:
            log.info("Closing Redis client connection...")
            try:
                await self._redis_client.close()
                # await self._redis_client.connection_pool.disconnect() # For older redis-py versions
                log.info("Redis client connection closed successfully.")
            except redis.exceptions.RedisError as e:
                log.error(f"Error closing Redis connection: {e}", exc_info=True)
            except Exception as e:
                log.error(f"Unexpected error during Redis client close: {e}", exc_info=True)
            finally:
                self._redis_client = None

