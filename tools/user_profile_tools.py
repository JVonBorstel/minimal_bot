"""Tools for managing user profile information and preferences."""

import logging
from typing import Dict, Any, List, Optional

from botbuilder.core import TurnContext

from ._tool_decorator import tool_function
from user_auth.models import UserProfile
from user_auth import db_manager
from user_auth.utils import get_current_user_profile, invalidate_user_profile_cache
from state_models import AppState # Assuming AppState might be needed for context or user_id

log = logging.getLogger(__name__)

# Define which preferences are user-editable and their descriptions
# This helps in providing help text and validating preference names.
EDITABLE_PREFERENCES = {
    "preferred_name": {
        "description": "Your preferred name or nickname.",
        "type": "string"
    },
    "primary_role": {
        "description": "Your primary role in your team (e.g., Developer, QA, DevOps).",
        "type": "string"
    },
    "main_projects": {
        "description": "A list of main projects you are currently working on.",
        "type": "list_of_string" # Special type for validation if needed
    },
    "tool_preferences": {
        "description": "A list of your preferred tools or technologies.",
        "type": "list_of_string"
    },
    "communication_style": {
        "description": "Your preferred communication style (e.g., brief, detailed).",
        "type": "string" 
    },
    "notifications_enabled": {
        "description": "Enable or disable general notifications from the bot (true/false).",
        "type": "boolean"
    }
}

async def _get_user_profile_and_data(app_state: AppState, turn_context: TurnContext) -> tuple[Optional[UserProfile], Optional[dict]]:
    """Helper to get user profile and their profile_data."""
    if not app_state.current_user or not app_state.current_user.user_id:
        log.warning("Attempted to access preferences without a valid user in app_state.")
        # Try to load from turn_context if not in app_state (e.g. first interaction)
        # This might happen if app_state.current_user wasn't populated by on_message_activity prior to tool call
        user_profile = get_current_user_profile(turn_context)
        if not user_profile:
            await turn_context.send_activity("I couldn't identify you to manage preferences. Please try again.")
            return None, None
        # If loaded, ensure it's also set in app_state for consistency in this turn
        app_state.current_user = user_profile 
    else:
        user_profile = app_state.current_user

    if not user_profile.profile_data:
        user_profile.profile_data = {} # Ensure profile_data exists

    return user_profile, user_profile.profile_data

@tool_function(
    name="list_my_preferences",
    description="Show your currently set preferences. This will list all preferences and their current values.",
    parameters_schema={}, # No parameters needed
    categories=["user", "profile", "preferences"],
    tags=["preferences", "settings", "profile", "view", "show", "list"],
    importance=1
)
async def list_my_preferences(app_state: AppState, turn_context: TurnContext) -> Dict[str, Any]:
    """Lists all editable preferences and their current values for the user."""
    user_profile, profile_data = await _get_user_profile_and_data(app_state, turn_context)
    if not user_profile:
        return {"user_facing_message": "Could not identify user to list preferences."}

    current_prefs_display = []
    for key, details in EDITABLE_PREFERENCES.items():
        value = profile_data.get(key)
        if value is None:
            display_value = "Not set"
        elif isinstance(value, list):
            display_value = ", ".join(value) if value else "None specified"
        elif isinstance(value, bool):
            display_value = "Enabled" if value else "Disabled"
        else:
            display_value = str(value)
        current_prefs_display.append(f"- **{details['description']}**: {display_value}")
    
    if not current_prefs_display:
        return {"user_facing_message": "You don't have any preferences set up yet."}

    response_message = "Here are your current preferences:\n" + "\n".join(current_prefs_display)
    response_message += "\n\nYou can change a preference using 'set my preference' or 'update my preference'."
    return {"user_facing_message": response_message}

@tool_function(
    name="get_my_preference",
    description="Get the current value of a specific preference. Use 'list_my_preferences' to see all available ones.",
    parameters_schema={
        "type": "object",
        "properties": {
            "preference_name": {
                "type": "string",
                "description": "The name of the preference to get. Must be one of: " + ", ".join(EDITABLE_PREFERENCES.keys()),
                "enum": list(EDITABLE_PREFERENCES.keys())
            }
        },
        "required": ["preference_name"]
    },
    categories=["user", "profile", "preferences"],
    tags=["preferences", "settings", "profile", "get", "view", "show"],
    importance=2 
)
async def get_my_preference(app_state: AppState, turn_context: TurnContext, preference_name: str) -> Dict[str, Any]:
    """Gets the value of a specific user preference."""
    user_profile, profile_data = await _get_user_profile_and_data(app_state, turn_context)
    if not user_profile:
        return {"user_facing_message": "Could not identify user to get preference."}

    if preference_name not in EDITABLE_PREFERENCES:
        return {"user_facing_message": f"Sorry, '{preference_name}' is not a recognized preference. Available preferences are: {', '.join(EDITABLE_PREFERENCES.keys())}."}

    value = profile_data.get(preference_name)

    if value is None:
        return {"user_facing_message": f"Your preference for '{EDITABLE_PREFERENCES[preference_name]['description']}' is not set."}
    
    display_value = value
    if isinstance(value, list):
        display_value = ", ".join(value) if value else "None specified"
    elif isinstance(value, bool):
        display_value = "Enabled" if value else "Disabled"
        
    return {"user_facing_message": f"Your '{EDITABLE_PREFERENCES[preference_name]['description']}' is currently: {display_value}."}


@tool_function(
    name="set_my_preference",
    description="Set or update one of your personal preferences. For list-based preferences like 'main_projects' or 'tool_preferences', provide the new list as a comma-separated string. For 'notifications_enabled', use 'true' or 'false'.",
    parameters_schema={
        "type": "object",
        "properties": {
            "preference_name": {
                "type": "string",
                "description": "The name of the preference to set. Must be one of: " + ", ".join(EDITABLE_PREFERENCES.keys()),
                "enum": list(EDITABLE_PREFERENCES.keys())
            },
            "value": {
                "type": "string", # Keep as string, convert in function
                "description": "The new value for the preference. For lists, use comma-separated values (e.g., 'projectA, projectB'). For booleans, use 'true' or 'false'."
            }
        },
        "required": ["preference_name", "value"]
    },
    categories=["user", "profile", "preferences"],
    tags=["preferences", "settings", "profile", "set", "update", "change"],
    importance=3
)
async def set_my_preference(app_state: AppState, turn_context: TurnContext, preference_name: str, value: str) -> Dict[str, Any]:
    """Sets or updates a specific user preference."""
    user_profile, profile_data = await _get_user_profile_and_data(app_state, turn_context)
    if not user_profile:
        return {"user_facing_message": "Could not identify user to set preference."}

    if preference_name not in EDITABLE_PREFERENCES:
        return {"user_facing_message": f"Sorry, '{preference_name}' is not a recognized preference. Available preferences are: {', '.join(EDITABLE_PREFERENCES.keys())}."}

    pref_details = EDITABLE_PREFERENCES[preference_name]
    original_value_for_log = profile_data.get(preference_name)
    new_value: Any = value # Keep it as Any for now

    try:
        if pref_details["type"] == "list_of_string":
            if isinstance(value, str):
                new_value = [item.strip() for item in value.split(',') if item.strip()]
            elif isinstance(value, list): # LLM might directly provide a list
                new_value = [str(item).strip() for item in value if str(item).strip()]
            else:
                return {"user_facing_message": f"For '{preference_name}', please provide a comma-separated list of items."}
        elif pref_details["type"] == "boolean":
            if value.lower() == 'true':
                new_value = True
            elif value.lower() == 'false':
                new_value = False
            else:
                return {"user_facing_message": f"For '{preference_name}', please use 'true' or 'false'."}
        elif pref_details["type"] == "string":
            new_value = str(value) # Ensure it's a string
        # Add other type conversions if necessary, e.g., int
    except Exception as e:
        log.error(f"Error converting value for preference {preference_name}: {e}", exc_info=True)
        return {"user_facing_message": f"There was an issue processing the value for '{preference_name}'. Please check the format."}

    profile_data[preference_name] = new_value
    user_profile.profile_data = profile_data # Re-assign, as profile_data might have been a copy or new dict
    user_profile.update_last_active()

    # Save updated profile
    profile_dict_to_save = user_profile.model_dump()

    # db_manager.save_user_profile expects a dict, not a UserProfile object directly.
    if db_manager.save_user_profile(profile_dict_to_save):
        log.info(f"User {user_profile.user_id} updated preference '{preference_name}' from '{original_value_for_log}' to '{new_value}'.")
        # Invalidate cache
        invalidate_user_profile_cache(user_profile.user_id)
        
        # Confirm back to user
        display_new_value = new_value
        if isinstance(new_value, list):
            display_new_value = ", ".join(new_value) if new_value else "empty"
        elif isinstance(new_value, bool):
            display_new_value = "Enabled" if new_value else "Disabled"
            
        return {"user_facing_message": f"Okay, I've updated your '{pref_details['description']}' to: {display_new_value}."}
    else:
        log.error(f"Failed to save updated preferences for user {user_profile.user_id} to database.")
        # Revert in-memory change if save fails? For now, it's optimistic.
        # If reverting: profile_data[preference_name] = original_value_for_log 
        return {"user_facing_message": "Sorry, I couldn't save your updated preference. Please try again."} 