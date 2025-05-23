# user_auth/utils.py
from typing import Optional, Any, List, Dict, Tuple
import threading
import time
import logging
import collections

# Import TurnContext if available and other necessary types
# from botbuilder.core import TurnContext # Example

# Import UserProfile model and DB manager functions
from .models import UserProfile
from .teams_identity import extract_user_identity
from . import db_manager # Use 'from . import db_manager' for clarity
from config import get_config # Added import

# Configure logger for this module
logger = logging.getLogger(__name__) # Using standard logging

# Enhanced caching system with thread safety and limits
_cache_lock = threading.RLock()  # Reentrant lock for thread safety
MAX_CACHE_AGE_SECONDS = 300  # 5 minutes
MAX_CACHE_SIZE = 1000  # Maximum number of profiles to cache
# Cache metrics
_CACHE_STATS = {
    "hits": 0,
    "misses": 0,
    "inserts": 0,
    "updates": 0,
    "stales": 0,
    "evictions": 0,
    "size": 0,
    "db_reads": 0,
    "db_writes": 0,
    "db_time_ms": 0,
    "cache_time_ms": 0,
    "errors": 0
}

# LRU cache with timestamp tracking
class ProfileCache:
    def __init__(self, max_size=MAX_CACHE_SIZE):
        self.max_size = max_size
        self.cache_dict = {}  # {user_id: (profile_data, timestamp, access_count)}
        self.access_order = collections.OrderedDict()  # LRU tracking
    
    def get(self, user_id):
        """Get a profile from cache with LRU tracking."""
        if user_id not in self.cache_dict:
            return None
        
        # Update access order for LRU tracking
        self.access_order.pop(user_id, None)
        self.access_order[user_id] = None
        
        profile_data, timestamp, access_count = self.cache_dict[user_id]
        # Update access count
        self.cache_dict[user_id] = (profile_data, timestamp, access_count + 1)
        
        return profile_data, timestamp
    
    def put(self, user_id, profile_data, timestamp=None):
        """Add or update a profile in cache with timestamp and LRU tracking."""
        if timestamp is None:
            timestamp = time.time()
        
        # Evict least recently used item if at capacity
        if user_id not in self.cache_dict and len(self.cache_dict) >= self.max_size:
            self._evict_lru()
        
        # Update access order for LRU tracking
        self.access_order.pop(user_id, None)
        self.access_order[user_id] = None
        
        # Store with initial or incremented access count
        access_count = 0
        if user_id in self.cache_dict:
            _, _, access_count = self.cache_dict[user_id]
        
        self.cache_dict[user_id] = (profile_data, timestamp, access_count + 1)
        return True
    
    def remove(self, user_id):
        """Remove a profile from cache."""
        if user_id in self.cache_dict:
            del self.cache_dict[user_id]
            self.access_order.pop(user_id, None)
            return True
        return False
    
    def _evict_lru(self):
        """Evict the least recently used item from cache."""
        if not self.access_order:
            return False
        
        lru_key = next(iter(self.access_order))
        self.remove(lru_key)
        _CACHE_STATS["evictions"] += 1
        logger.debug(f"Evicted LRU profile {lru_key} from cache due to size limit")
        return True
    
    def get_all_items(self):
        """Return all items with their metadata for inspection."""
        return self.cache_dict.copy()
    
    def clear(self):
        """Clear the entire cache."""
        count = len(self.cache_dict)
        self.cache_dict = {}
        self.access_order = collections.OrderedDict()
        return count

# Initialize the profile cache
_user_profile_cache = ProfileCache(max_size=MAX_CACHE_SIZE)

def get_current_user_profile(turn_context_or_app_state: Any, db_path: Optional[str] = None) -> Optional[UserProfile]:
    """
    Retrieves the current UserProfile based on the turn context or app state.
    Implements efficient thread-safe caching with LRU eviction and uses db_manager for persistence.
    
    Args:
        turn_context_or_app_state: The TurnContext or AppState object for the current turn.
                                   This needs to provide a way to get the user_id.
        db_path: Optional path to the SQLite database. If None, db_manager.DB_NAME is used.

    Returns:
        The UserProfile for the current user, or None if not found/identifiable.
    """
    user_id: Optional[str] = None
    activity_obj: Optional[Any] = None # Renamed to avoid conflict with activity var name in some contexts
    cache_status = "UNKNOWN"
    
    # Start precise timing for performance tracking
    start_time = time.time()

    # Determine database path to use
    effective_db_path = db_path
    if effective_db_path is None:
        app_config = get_config()
        effective_db_path = app_config.STATE_DB_PATH

    # Try to get activity_obj if the context object has it
    if hasattr(turn_context_or_app_state, 'activity'):
        activity_obj = turn_context_or_app_state.activity

    # Extract user_id using a prioritized hierarchy of sources
    
    # 1. First priority: activity.from_property.id (standard Bot Framework)
    if activity_obj and hasattr(activity_obj, 'from_property') and activity_obj.from_property and \
       hasattr(activity_obj.from_property, 'id'):
        potential_id_from_activity = getattr(activity_obj.from_property, 'id', None)
        if isinstance(potential_id_from_activity, str) and potential_id_from_activity:
            user_id = potential_id_from_activity
            logger.debug(f"User ID '{user_id}' extracted from activity.from_property.id")
    
    # 2. Second priority: current_user_id attribute (for custom contexts)
    if not user_id and hasattr(turn_context_or_app_state, 'current_user_id'):
        potential_user_id_attr = getattr(turn_context_or_app_state, 'current_user_id', None)
        if isinstance(potential_user_id_attr, str) and potential_user_id_attr:
            user_id = potential_user_id_attr
            logger.debug(f"User ID '{user_id}' extracted from context.current_user_id")
    
    # 3. Third priority: session metadata (for contexts with session managers)
    if not user_id and hasattr(turn_context_or_app_state, 'get_session_metadata'):
        try:
            # Ensure get_session_metadata is callable if it's a MagicMock from tests
            if callable(turn_context_or_app_state.get_session_metadata):
                metadata_user_id = turn_context_or_app_state.get_session_metadata('user_id')
                if isinstance(metadata_user_id, str) and metadata_user_id:
                    user_id = metadata_user_id
                    logger.debug(f"User ID '{user_id}' extracted from session metadata")
            else:
                logger.debug("Context object has 'get_session_metadata' but it's not callable.")
        except Exception as e:
            logger.debug(f"Error calling get_session_metadata: {e}")
            pass # Catch if get_session_metadata is not callable or errors

    # 4. Final check: ensure we have a valid user ID
    if not user_id:
        logger.warning("Could not determine user_id from the provided context.")
        return None

    # Check for short-circuit case: if user profile is already in AppState
    if hasattr(turn_context_or_app_state, 'current_user') and turn_context_or_app_state.current_user:
        current_user = turn_context_or_app_state.current_user
        if hasattr(current_user, 'user_id') and current_user.user_id == user_id:
            # The user profile is already loaded in app_state and matches the current user_id
            # Update last_active and return
            if hasattr(current_user, 'update_last_active'):
                current_user.update_last_active()
            logger.debug(f"User profile for '{user_id}' already present in AppState, returning directly")
            return current_user

    # Try to get from cache first (memory efficiency) - thread-safe access
    with _cache_lock:
        # Look up the profile in our cache
        cache_result = _user_profile_cache.get(user_id)
        
        if cache_result:
            cached_profile_data, timestamp = cache_result
            age = time.time() - timestamp
            
            if age < MAX_CACHE_AGE_SECONDS:
                # Cache hit - profile is fresh
                logger.debug(f"Cache HIT for user_id: {user_id} (age: {age:.1f}s)")
                _CACHE_STATS["hits"] += 1
                cache_status = "HIT"
                
                # Create UserProfile from cached data
                try:
                    profile = UserProfile(**cached_profile_data)
                    profile.update_last_active()  # Update last active timestamp
                    
                    # Record cache access duration
                    cache_time_ms = (time.time() - start_time) * 1000
                    _CACHE_STATS["cache_time_ms"] += cache_time_ms
                    
                    # Optional: Every N hits, update the database with the new last_active
                    # This reduces DB writes while still periodically recording activity
                    # Use access count from cache for smarter update policy
                    cache_entry = _user_profile_cache.cache_dict.get(user_id)
                    if cache_entry:
                        _, _, access_count = cache_entry
                        
                        # Update DB increasingly less frequently based on access count
                        # Frequent users get updated less often to reduce DB load
                        update_frequency = min(20, max(5, access_count // 10 * 5))
                        
                        if access_count % update_frequency == 0:
                            try:
                                # We won't await this or worry too much if it fails
                                # as it's just a periodic refresh
                                profile_dict = profile.model_dump()
                                db_manager.save_user_profile(profile_dict)
                                _CACHE_STATS["db_writes"] += 1
                                logger.debug(f"Updated last_active in DB for user {user_id} (periodic)")
                            except Exception as e:
                                logger.debug(f"Non-critical error updating last_active in DB: {e}")
                                _CACHE_STATS["errors"] += 1
                    
                    elapsed = time.time() - start_time
                    logger.debug(f"get_current_user_profile elapsed time: {elapsed*1000:.2f}ms (cache {cache_status})")
                    return profile
                except Exception as e:
                    logger.warning(f"Error creating UserProfile from cache for {user_id}: {e}")
                    _CACHE_STATS["errors"] += 1
                    # Don't return here, continue to try loading from DB
            else:
                # Cache is stale, remove and load from DB
                logger.debug(f"Cache STALE for user_id: {user_id} (age: {age:.1f}s)")
                _CACHE_STATS["stales"] += 1
                _CACHE_STATS["evictions"] += 1
                cache_status = "STALE"
                _user_profile_cache.remove(user_id)  # Remove stale entry

    # Cache miss or stale - load from database
    logger.debug(f"Cache {cache_status if cache_status != 'UNKNOWN' else 'MISS'} for user_id: {user_id}. Loading from DB: {effective_db_path}")
    if cache_status == "UNKNOWN":
        _CACHE_STATS["misses"] += 1
    
    db_start_time = time.time()
    db_profile_data = db_manager.get_user_profile_by_id(user_id)
    db_time_ms = (time.time() - db_start_time) * 1000
    _CACHE_STATS["db_time_ms"] += db_time_ms
    _CACHE_STATS["db_reads"] += 1

    if db_profile_data:
        # DB hit - create profile and update cache
        try:
            profile = UserProfile(**db_profile_data)
            profile.update_last_active()  # Update last active time
            logger.debug(f"Loaded profile from DB for user_id: {user_id}. Role: {profile.assigned_role}")
            
            # Save updated last_active time back to DB
            try:
                profile_dict = profile.model_dump()
                if not db_manager.save_user_profile(profile_dict):
                    logger.error(f"Failed to save updated last_active for user {user_id} to DB.")
                    _CACHE_STATS["errors"] += 1
                else:
                    _CACHE_STATS["db_writes"] += 1
            except Exception as save_err:
                logger.error(f"Error saving profile with updated last_active: {save_err}")
                _CACHE_STATS["errors"] += 1
            
            # Update cache - thread-safe access
            with _cache_lock:
                _user_profile_cache.put(
                    user_id, 
                    profile.model_dump(), 
                    time.time()
                )
            
            elapsed = time.time() - start_time
            logger.debug(f"get_current_user_profile elapsed time: {elapsed*1000:.2f}ms (DB hit)")
            return profile
        except Exception as e:  # Catch Pydantic validation errors or others
            logger.error(f"Error instantiating UserProfile from DB data for {user_id}: {e}", exc_info=True)
            _CACHE_STATS["errors"] += 1
            return None
    elif activity_obj:
        # DB miss with activity - try to create new profile
        try:
            identity_info = extract_user_identity(activity_obj)
            if identity_info and identity_info.get('user_id') == user_id:  # Ensure extracted ID matches
                logger.info(f"Creating NEW profile for user_id: {user_id} from activity.")
                
                # Create new profile
                new_profile = UserProfile(
                    user_id=identity_info['user_id'],
                    display_name=identity_info.get('name', 'Unknown User'),  # Ensure a default for display_name
                    email=identity_info.get('email'),
                    aad_object_id=identity_info.get('aad_object_id'),
                    tenant_id=identity_info.get('tenant_id')
                    # assigned_role will use the default from UserProfile model ("DEFAULT")
                )
                
                # Save to DB
                profile_dict = new_profile.model_dump()
                db_save_successful = db_manager.save_user_profile(profile_dict)
                if db_save_successful:
                    _CACHE_STATS["db_writes"] += 1
                
                if not db_save_successful:
                    logger.error(f"Failed to save new profile for user {user_id} to DB.")
                    _CACHE_STATS["errors"] += 1
                    return None  # Failed to save, so don't return a profile that isn't persisted
                
                # Update cache - thread-safe access
                with _cache_lock:
                    _user_profile_cache.put(user_id, profile_dict, time.time())
                
                elapsed = time.time() - start_time
                logger.debug(f"get_current_user_profile elapsed time: {elapsed*1000:.2f}ms (new profile created)")
                return new_profile
            else:
                logger.warning(
                    f"Could not extract valid identity from activity to create new profile for user_id: {user_id}. "
                    f"Identity info: {identity_info}"
                )
                _CACHE_STATS["errors"] += 1
                return None
        except Exception as e:
            logger.error(f"Error creating new UserProfile for {user_id}: {e}", exc_info=True)
            _CACHE_STATS["errors"] += 1
            return None
    else:
        logger.warning(f"User profile for {user_id} not found in DB and no activity provided to create a new one.")
        _CACHE_STATS["errors"] += 1
        return None

def get_cache_stats() -> dict:
    """Returns detailed statistics about the user profile cache performance."""
    with _cache_lock:
        stats = _CACHE_STATS.copy()  # Return a copy to prevent external modification
        
        # Add derived metrics
        total_lookups = stats["hits"] + stats["misses"]
        if total_lookups > 0:
            stats["hit_rate"] = stats["hits"] / total_lookups
            stats["avg_cache_time_ms"] = stats["cache_time_ms"] / total_lookups if stats["cache_time_ms"] > 0 else 0
        else:
            stats["hit_rate"] = 0.0
            stats["avg_cache_time_ms"] = 0.0
        
        total_db_ops = stats["db_reads"] + stats["db_writes"]
        if total_db_ops > 0:
            stats["avg_db_time_ms"] = stats["db_time_ms"] / total_db_ops if stats["db_time_ms"] > 0 else 0
        else:
            stats["avg_db_time_ms"] = 0.0
            
        all_cache_entries = _user_profile_cache.get_all_items()
        
        stats["cache_size"] = len(all_cache_entries)
        stats["cache_size_limit"] = MAX_CACHE_SIZE
        stats["cache_limit_seconds"] = MAX_CACHE_AGE_SECONDS
        
        # Add cache health metrics
        if all_cache_entries:
            now = time.time()
            age_sum = sum(now - timestamp for _, timestamp, _ in all_cache_entries.values())
            stats["avg_entry_age_seconds"] = age_sum / len(all_cache_entries)
            
            total_access_count = sum(access_count for _, _, access_count in all_cache_entries.values())
            stats["avg_access_count"] = total_access_count / len(all_cache_entries)
            
            # Calculate how many entries are about to expire
            near_expiry_count = sum(1 for _, timestamp, _ in all_cache_entries.values() 
                                     if now - timestamp > (MAX_CACHE_AGE_SECONDS * 0.8))
            stats["entries_near_expiry"] = near_expiry_count
        else:
            stats["avg_entry_age_seconds"] = 0
            stats["avg_access_count"] = 0
            stats["entries_near_expiry"] = 0
        
        return stats

def clear_user_profile_cache() -> None:
    """
    Clears the user profile cache. Useful for testing or when configuration changes.
    Thread-safe operation.
    """
    with _cache_lock:
        cache_size = _user_profile_cache.clear()
        logger.info(f"User profile cache cleared. {cache_size} entries removed.")

def get_cache_entry_details(user_id: str) -> Optional[Dict]:
    """
    Gets detailed information about a specific cache entry for diagnostics.
    """
    with _cache_lock:
        if user_id not in _user_profile_cache.cache_dict:
            return None
            
        profile_data, timestamp, access_count = _user_profile_cache.cache_dict[user_id]
        
        return {
            "user_id": user_id,
            "profile_data": profile_data,  # The actual cached UserProfile data
            "cache_age_seconds": time.time() - timestamp,
            "cached_at": timestamp,
            "access_count": access_count,
            "expires_at": timestamp + MAX_CACHE_AGE_SECONDS,
            "expires_in_seconds": (timestamp + MAX_CACHE_AGE_SECONDS) - time.time(),
            "is_expired": (time.time() - timestamp) > MAX_CACHE_AGE_SECONDS
        }

def preload_user_profiles(user_ids: List[str], db_path: Optional[str] = None) -> int:
    """
    Preloads multiple user profiles into the cache for expected high-traffic users.
    
    Args:
        user_ids: List of user IDs to preload
        db_path: Optional path to the SQLite database
        
    Returns:
        Number of profiles successfully preloaded
    """
    if not user_ids:
        return 0
        
    success_count = 0
    effective_db_path = db_path
    if effective_db_path is None:
        app_config = get_config()
        effective_db_path = app_config.STATE_DB_PATH
    
    for user_id in user_ids:
        try:
            # Load from DB
            profile_data = db_manager.get_user_profile_by_id(user_id)
            if profile_data:
                # Add to cache
                with _cache_lock:
                    _user_profile_cache.put(user_id, profile_data, time.time())
                success_count += 1
        except Exception as e:
            logger.error(f"Error preloading profile for user {user_id}: {e}")
            
    logger.info(f"Preloaded {success_count}/{len(user_ids)} user profiles into cache")
    return success_count

# Placeholder for tracking conversation participants - P3A.1.3
# def get_conversation_participants(turn_context_or_app_state: Any, db_path: Optional[str] = None) -> List[UserProfile]:
#     """
#     Retrieves UserProfile objects for all participants in the current conversation.
#     This is a complex task that might involve calls to `adapter.get_conversation_members()`.
#     """
#     # effective_db_path = db_path or db_manager.DB_NAME
#     # 1. Get conversation ID from context
#     # 2. Call adapter.get_conversation_members(conversation_id)
#     # 3. For each member, try to get_current_user_profile (or a similar lookup using effective_db_path)
#     return []

# It's crucial to initialize the database table at application startup.
# This can be done by calling db_manager.create_user_profiles_table_if_not_exists()
# from your main application entry point (e.g., app.py or where Config is first loaded). 