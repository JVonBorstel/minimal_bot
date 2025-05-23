# user_auth/db_manager.py
import json
import time
import os
from typing import Optional, Dict, Any, List, Generator
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, select, update, delete, exc as sqlalchemy_exc
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession # Renamed to avoid conflict

from config import get_config
from .orm_models import UserProfile, Base as UserAuthBase # Import Base for potential use, UserProfile for CRUD

# Configure logger for this module
logger = logging.getLogger(__name__)

# --- SQLAlchemy Engine and Session Setup ---
_engine = None
_SessionLocal: Optional[sessionmaker[SQLAlchemySession]] = None

def _get_engine():
    """Initializes and returns the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        app_config = get_config()
        # Ensure forward slashes for URL, especially on Windows
        normalized_db_path = app_config.STATE_DB_PATH.replace('\\', '/')
        db_url = f"sqlite:///{normalized_db_path}"
        _engine = create_engine(db_url, echo=False) # echo=True for debugging SQL, False for production
        # Optional: Could call Base.metadata.create_all(_engine) here IF NOT USING ALEMBIC
        # But since we are using Alembic, Alembic handles table creation.
        logger.info(f"SQLAlchemy engine initialized for database: {db_url}")
    return _engine

def _get_session_local() -> sessionmaker[SQLAlchemySession]:
    """Initializes and returns the SQLAlchemy sessionmaker."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _SessionLocal 

@contextmanager
def get_session() -> Generator[SQLAlchemySession, None, None]:
    """Provide a transactional scope around a series of operations."""
    session_factory = _get_session_local()
    db_session = session_factory()
    try:
        yield db_session
        db_session.commit() # Commit on successful block execution
    except sqlalchemy_exc.SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error occurred: {e}", exc_info=True)
        db_session.rollback() # Rollback on error
        raise # Re-raise the exception after rollback
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_session: {e}", exc_info=True)
        db_session.rollback()
        raise
    finally:
        db_session.close()

# --- Table Schema and Initialization (Handled by Alembic) ---
# The create_user_profiles_table_if_not_exists function is no longer needed.
# Alembic is responsible for schema creation and migrations.
# Ensure Alembic migrations are run at application startup or during deployment.
# Example: `alembic upgrade head`

# --- CRUD Operations for UserProfile (Refactored) ---

def get_user_profile_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a user profile from the database by user_id using SQLAlchemy ORM.

    Returns:
        A dictionary representing the user profile if found, else None.
    """
    try:
        with get_session() as session:
            # Using session.get() is efficient for fetching by primary key
            user_profile = session.get(UserProfile, user_id)
            
            if user_profile:
                # Convert ORM object to dictionary
                # This ensures compatibility with previous interface. Future refactor could return ORM object.
                profile_dict = {
                    column.name: getattr(user_profile, column.name) 
                    for column in user_profile.__table__.columns
                }
                # Deserialize profile_data if it exists and is a string
                if profile_dict.get('profile_data') and isinstance(profile_dict['profile_data'], str):
                    try:
                        profile_dict['profile_data'] = json.loads(profile_dict['profile_data'])
                    except json.JSONDecodeError:
                        logger.warning(f"Could not decode profile_data JSON for user {user_id} from ORM. Returning as raw string.")
                return profile_dict
            return None
    except sqlalchemy_exc.SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error getting user profile for {user_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting user profile for {user_id}: {e}", exc_info=True)
        return None

def save_user_profile(user_profile_dict: Dict[str, Any]) -> bool:
    """
    Saves (inserts or updates) a user profile in the database using SQLAlchemy ORM.
    The input is a dictionary, expected to conform to UserProfile model fields.
    
    Returns:
        True if save was successful, False otherwise.
    """
    if not user_profile_dict.get('user_id') or not user_profile_dict.get('display_name'):
        logger.error("Cannot save user profile: missing user_id or display_name.")
        return False

    try:
        with get_session() as session:
            user_id = user_profile_dict['user_id']
            user_profile = session.get(UserProfile, user_id)

            # Prepare data, especially serializing profile_data if it's a dict
            data_to_save = user_profile_dict.copy()
            if 'profile_data' in data_to_save and isinstance(data_to_save['profile_data'], dict):
                try:
                    data_to_save['profile_data'] = json.dumps(data_to_save['profile_data'])
                except TypeError:
                    logger.error(f"Could not serialize profile_data for user {user_id}. Saving as None/not updating.")
                    # Decide handling: either remove or save as is if it was already a string/None
                    if isinstance(user_profile_dict['profile_data'], dict): # only pop if it was the problematic dict
                        data_to_save.pop('profile_data', None) 
            
            current_time = int(time.time())

            if user_profile: # Update existing profile
                logger.debug(f"Updating existing user profile: {user_id}")
                for key, value in data_to_save.items():
                    if hasattr(user_profile, key):
                        setattr(user_profile, key, value)
                    else:
                        logger.warning(f"Key {key} not found in UserProfile model, skipping for update.")
                # Ensure last_active_timestamp is updated
                if 'last_active_timestamp' not in data_to_save:
                    user_profile.last_active_timestamp = current_time
            else: # Insert new profile
                logger.debug(f"Creating new user profile: {user_id}")
                # Ensure required timestamps if not provided
                if 'first_seen_timestamp' not in data_to_save:
                    data_to_save['first_seen_timestamp'] = current_time
                if 'last_active_timestamp' not in data_to_save:
                    data_to_save['last_active_timestamp'] = current_time
                
                # Filter data_to_save to only include keys that are actual columns in UserProfile
                valid_columns = {column.name for column in UserProfile.__table__.columns}
                filtered_data = {k: v for k, v in data_to_save.items() if k in valid_columns}
                
                user_profile = UserProfile(**filtered_data)
                session.add(user_profile)
            
            # Session commit is handled by the get_session context manager
            logger.info(f"User profile for '{user_id}' processed successfully.")
            return True
            
    except sqlalchemy_exc.SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error saving user profile for {user_profile_dict.get('user_id')}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error saving user profile for {user_profile_dict.get('user_id')}: {e}", exc_info=True)
        return False

def get_all_user_profiles() -> List[Dict[str, Any]]:
    """Retrieves all user profiles from the database using SQLAlchemy ORM."""
    profiles_list = []
    try:
        with get_session() as session:
            stmt = select(UserProfile).order_by(UserProfile.last_active_timestamp.desc())
            user_profiles = session.execute(stmt).scalars().all()

            for user_profile in user_profiles:
                profile_dict = {
                    column.name: getattr(user_profile, column.name) 
                    for column in user_profile.__table__.columns
                }
                if profile_dict.get('profile_data') and isinstance(profile_dict['profile_data'], str):
                    try:
                        profile_dict['profile_data'] = json.loads(profile_dict['profile_data'])
                    except json.JSONDecodeError:
                        logger.warning(f"Could not decode profile_data JSON for user {user_profile.user_id} in get_all_user_profiles. Returning as raw string.")
                profiles_list.append(profile_dict)
        return profiles_list
    except sqlalchemy_exc.SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error getting all user profiles: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting all user profiles: {e}", exc_info=True)
        return []

# Example of how it might be called (e.g. in user_auth/__init__.py or app startup):
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO)
#     # Initialize engine (usually done once at app startup)
#     # _get_engine()
#     # The old create_user_profiles_table_if_not_exists() is replaced by Alembic migrations.
#     # print(f"Ensuring database and table via Alembic migrations (run separately).")
#     # Test save (example using new structure - to be fully implemented)
#     # test_profile_data = {
#     #     "user_id": "test_orm_user_123",
#     #     "display_name": "Test ORM User",
#     #     "email": "test_orm@example.com",
#     #     "assigned_role": "ADMIN",
#     #     "first_seen_timestamp": int(time.time()),
#     #     "last_active_timestamp": int(time.time()),
#     #     "profile_version": 1
#     # }
#     # if save_user_profile(test_profile_data):
#     #     print(f"Saved ORM profile: {test_profile_data['user_id']}")
#     #     loaded_profile = get_user_profile_by_id(test_profile_data['user_id'])
#     #     if loaded_profile:
#     #         print(f"Loaded ORM profile: {loaded_profile}")
#     #     else:
#     #         print(f"Failed to load ORM profile: {test_profile_data['user_id']}")
#     # else:
#     #     print(f"Failed to save ORM profile: {test_profile_data['user_id']}") 