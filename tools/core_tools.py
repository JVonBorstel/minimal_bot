"""Core tools that are always available to users."""

import logging
from typing import Dict, Any, List, Optional
from ._tool_decorator import tool_function
from config import Config
from datetime import datetime
from user_auth.permissions import Permission
from workflows.onboarding import OnboardingWorkflow
from user_auth import db_manager
import time

log = logging.getLogger(__name__)


@tool_function(
    name="help",
    description="Get help and show available commands. Use this when users ask for help, what you can do, or how to use the bot.",
    parameters_schema={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string", 
                "description": "Optional specific topic to get help about"
            }
        },
        "required": []
    },
    categories=["assistance", "documentation"],
    tags=["help", "support", "guide", "commands", "usage", "what can you do", "available", "tools"],
    importance=4  # Reduced importance from 10
)
async def help(topic: str = None, config: Config = None) -> Dict[str, Any]:
    """
    Provides help and shows available commands to the user.
    
    Args:
        topic: Optional specific topic to get help about
        config: Configuration object (injected)
        
    Returns:
        Dict containing help information
    """
    log.info(f"Help tool called with topic: {topic}")
    
    help_response = {
        "title": "🤖 Augie ChatOps Bot - Help & Commands",
        "description": "I'm here to help you with development tasks, project management, and information retrieval!",
        "sections": []
    }
    
    # General help
    general_section = {
        "name": "🌟 Getting Started",
        "content": [
            "Just type naturally! I understand context and can help with:",
            "• Creating and managing GitHub issues and pull requests",
            "• Working with Jira tickets and project planning",
            "• Searching code and repositories",
            "• Finding information online",
            "• And much more!"
        ]
    }
    help_response["sections"].append(general_section)
    
    # Command examples
    examples_section = {
        "name": "💡 Example Commands",
        "content": [
            "**GitHub:**",
            "• 'Create a GitHub issue for the login bug'",
            "• 'Show my open pull requests'",
            "• 'Search for authentication code in the repository'",
            "",
            "**Jira:**",
            "• 'Create a new Jira ticket for the API feature'",
            "• 'Show my assigned Jira issues'",
            "• 'What's in the current sprint?'",
            "",
            "**Code & Search:**",
            "• 'Find all Python files with database queries'",
            "• 'Search the web for React best practices'",
            "• 'Analyze the codebase structure'"
        ]
    }
    help_response["sections"].append(examples_section)
    
    # Tool categories - Now dynamically generated
    categories_section_content = ["An overview of my capabilities by category:"]
    if config and hasattr(config, 'tool_executor_instance') and config.tool_executor_instance:
        try:
            tool_defs = config.tool_executor_instance.get_available_tool_definitions()
            categorized_tools: Dict[str, List[str]] = {}
            for tool_def in tool_defs:
                tool_name = tool_def.get('name', 'Unnamed Tool')
                # Use metadata.categories if available, otherwise infer from tool name or use a default
                metadata = tool_def.get('metadata', {})
                categories = metadata.get('categories', [])
                
                if not categories and '_' in tool_name: # Infer from tool name like 'github_list_repos' -> 'github'
                    category_inferred = tool_name.split('_')[0].capitalize()
                    categories = [category_inferred]
                elif not categories:
                    categories = ["General"] # Default category

                for category in categories:
                    display_category = category.replace("_", " ").title()
                    if display_category not in categorized_tools:
                        categorized_tools[display_category] = []
                    
                    # Add tool name with a brief description if available
                    tool_desc = tool_def.get('description', 'No description available.')
                    # Keep description brief for this list
                    brief_desc = (tool_desc[:50] + '...') if len(tool_desc) > 50 else tool_desc
                    categorized_tools[display_category].append(f"• **{tool_name}**: _{brief_desc}_")

            if categorized_tools:
                for category, tool_list_formatted in sorted(categorized_tools.items()):
                    categories_section_content.append(f"\\n**{category} Tools:**")
                    categories_section_content.extend(tool_list_formatted)
            else:
                categories_section_content.append("No tools seem to be available or configured at the moment.")

        except Exception as e:
            log.error(f"Error dynamically generating tool categories for help: {e}", exc_info=True)
            categories_section_content.append("Could not retrieve dynamic tool list. Showing generic categories.")
            # Fallback to original hardcoded content if dynamic generation fails
            categories_section_content.extend([
                "**GitHub Tools**: Repository management, issues, PRs, code search",
                "**Jira Tools**: Project management, tickets, sprints, workflows",
                "**Greptile Tools**: Semantic code search and analysis",
                "**Perplexity Tools**: Web search and current information",
                "**Core Tools**: Help, status, and basic utilities"
            ])
    else:
        log.warning("Tool executor instance not found in config. Falling back to static help categories.")
        # Fallback to original hardcoded content if config or executor is missing
        categories_section_content.extend([
            "**GitHub Tools**: Repository management, issues, PRs, code search",
            "**Jira Tools**: Project management, tickets, sprints, workflows",
            "**Greptile Tools**: Semantic code search and analysis",
            "**Perplexity Tools**: Web search and current information",
            "**Core Tools**: Help, status, and basic utilities"
        ])

    categories_section = {
        "name": "🛠️ Available Tool Categories & Tools", # Updated name
        "content": categories_section_content
    }
    help_response["sections"].append(categories_section)
    
    # Tips
    tips_section = {
        "name": "💡 Pro Tips",
        "content": [
            "• Be specific about what you want to do",
            "• I maintain context, so you can have natural conversations",
            "• For complex tasks, I'll guide you through the process",
            "• Just ask if you need clarification on anything!"
        ]
    }
    help_response["sections"].append(tips_section)
    
    # Topic-specific help
    if topic:
        topic_lower = topic.lower()
        if "github" in topic_lower:
            topic_section = {
                "name": f"📚 Help: GitHub",
                "content": [
                    "**GitHub capabilities:**",
                    "• Create, update, and close issues",
                    "• Manage pull requests and reviews",
                    "• Search code across repositories",
                    "• List and analyze repositories",
                    "• Work with commits and branches",
                    "• Manage GitHub Actions workflows"
                ]
            }
            help_response["sections"].append(topic_section)
        elif "jira" in topic_lower:
            topic_section = {
                "name": f"📚 Help: Jira",
                "content": [
                    "**Jira capabilities:**",
                    "• Create and update tickets",
                    "• Manage sprints and boards",
                    "• Search and filter issues",
                    "• Work with projects and epics",
                    "• Track progress and generate reports",
                    "• Handle workflows and transitions"
                ]
            }
            help_response["sections"].append(topic_section)
    
    # Return just the help_response data - the decorator will wrap it
    return help_response


# You can add more core tools here in the future
# For example: status, ping, feedback, etc. 

@tool_function(
    name="preferences",
    description="Manage user preferences and onboarding settings.",
    parameters_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform - 'view', 'restart_onboarding', 'reset'"
            }
        },
        "required": ["action"]
    },
    categories=["assistance", "onboarding"],
    tags=["preferences", "onboarding", "settings"],
    importance=4
)
async def preferences(action: str = "view", app_state: Any = None) -> Dict[str, Any]:
    """
    Manage user preferences and onboarding settings.
    
    Args:
        action: Action to perform - 'view', 'restart_onboarding', 'reset'
        app_state: Application state (injected by tool framework)
        
    Returns:
        Dictionary containing preference information or update results
    """
    try:
        # Get current user from app state
        if not app_state or not hasattr(app_state, 'current_user') or not app_state.current_user:
            return {
                "status": "ERROR",
                "error_type": "UserProfileNotFound",
                "user_facing_message": "I couldn't find your user profile. Please contact an administrator if this issue persists.",
                "technical_details": "User profile not found in app_state or app_state.current_user is None."
            }
        
        user_profile = app_state.current_user
        profile_data = user_profile.profile_data or {}
        preferences = profile_data.get("preferences", {})
        
        action_lower = action.lower() # Case-insensitive action

        if action_lower == "view":
            # Show current preferences
            if not profile_data.get("onboarding_completed"):
                return {
                    "status": "INFO", 
                    "message": "You haven't completed onboarding yet. Your onboarding will start automatically on your next interaction, or you can use the restart option.",
                    "onboarding_status": "incomplete"
                }
            
            pref_summary = f"**Your Preferences for {preferences.get('preferred_name', user_profile.display_name)}:**\\n\\n"
            
            if preferences.get('primary_role'):
                pref_summary += f"👤 **Role**: {preferences['primary_role']}\n"
            
            if preferences.get('main_projects'):
                projects = preferences['main_projects']
                if projects:
                    pref_summary += f"📂 **Main Projects**: {', '.join(projects)}\n"
            
            if preferences.get('tool_preferences'):
                tools = preferences['tool_preferences']
                if tools:
                    pref_summary += f"🛠️ **Preferred Tools**: {', '.join(tools)}\n"
            
            if preferences.get('communication_style'):
                pref_summary += f"💬 **Communication Style**: {preferences['communication_style']}\n"
            
            notifications = "Enabled" if preferences.get('notifications_enabled') else "Disabled"
            pref_summary += f"🔔 **Notifications**: {notifications}\n"
            
            # Show personal credentials status
            has_personal_creds = bool(profile_data.get("personal_credentials"))
            cred_status = "Configured" if has_personal_creds else "Using shared access"
            pref_summary += f"🔑 **API Access**: {cred_status}\n\n"
            
            pref_summary += "**Update Options:**\n"
            pref_summary += "• Use 'restart onboarding' to go through setup again\n"
            pref_summary += "• Individual preferences can be updated through conversation"
            
            return {
                "status": "SUCCESS",
                "message": pref_summary,
                "onboarding_status": "completed"
            }
        
        elif action_lower == "restart_onboarding":
            # Allow user to restart onboarding
            try:
                # Clear existing onboarding completion
                profile_data["onboarding_completed"] = False
                if "onboarding_completed_at" in profile_data:
                    del profile_data["onboarding_completed_at"]
                
                # Clear any active onboarding workflows
                workflows_to_remove = []
                for wf_id, workflow in app_state.active_workflows.items():
                    if (workflow.workflow_type == "onboarding" and 
                        workflow.data.get("user_id") == user_profile.user_id):
                        workflows_to_remove.append(wf_id)
                
                for wf_id in workflows_to_remove:
                    app_state.completed_workflows.append(
                        app_state.active_workflows.pop(wf_id)
                    )
                
                # Start new onboarding
                onboarding = OnboardingWorkflow(user_profile, app_state)
                workflow = onboarding.start_workflow()
                
                # Get first question
                first_question_response = onboarding._format_question_response(
                    onboarding.ONBOARDING_QUESTIONS[0], 
                    workflow
                )
                
                # Update user profile
                user_profile.profile_data = profile_data
                profile_dict = user_profile.model_dump()
                db_manager.save_user_profile(profile_dict)
                
                welcome_message = (
                    f"🔄 **Restarting Onboarding for {user_profile.display_name}**\n\n"
                    f"Let's update your preferences with a fresh onboarding process.\n\n"
                    f"**{first_question_response['progress']}** {first_question_response['message']}"
                )
                
                return {
                    "status": "SUCCESS",
                    "message": welcome_message,
                    "workflow_started": True,
                    "workflow_id": workflow.workflow_id
                }
            
            except Exception as e:
                log.error(f"Error restarting onboarding: {e}", exc_info=True)
                return {
                    "status": "ERROR",
                    "error_type": "OnboardingRestartFailed",
                    "user_facing_message": "I ran into a problem trying to restart the onboarding process. Please try again in a moment.",
                    "technical_details": f"Failed to restart onboarding: {e.__class__.__name__}: {str(e)}"
                }
        
        elif action_lower == "reset":
            # Admin function to reset user preferences
            if not app_state.has_permission(Permission.ADMIN_ACCESS_USERS):
                return {
                    "status": "ERROR",
                    "error_type": "PermissionDenied",
                    "user_facing_message": "Sorry, you don't have the necessary permissions to perform this action.",
                    "technical_details": "User lacks ADMIN_ACCESS_USERS permission for 'reset' action in preferences tool."
                }
            
            # Reset all preferences
            user_profile.profile_data = {
                "onboarding_completed": False,
                "preferences": {},
                "reset_at": datetime.utcnow().isoformat(),
                "reset_by": user_profile.user_id
            }
            
            profile_dict = user_profile.model_dump()
            db_manager.save_user_profile(profile_dict)
            
            return {
                "status": "SUCCESS",
                "message": f"✅ Reset preferences for {user_profile.display_name}. They will go through onboarding on next interaction."
            }
        
        else:
            return {
                "status": "ERROR", 
                "error_type": "InvalidAction",
                "user_facing_message": f"Sorry, I don't know how to '{action}'. You can ask to 'view', 'restart onboarding', or (for admins) 'reset' preferences.",
                "technical_details": f"Unknown action '{action}' in preferences tool. Valid actions: 'view', 'restart_onboarding', 'reset'."
            }
            
    except Exception as e:
        log.error(f"Error in preferences tool: {e}", exc_info=True)
        return {
            "status": "ERROR",
            "error_type": "PreferencesToolError",
            "user_facing_message": "I encountered an unexpected issue while managing preferences. Please try again.",
            "technical_details": f"Error in preferences tool: {e.__class__.__name__}: {str(e)}"
        }

@tool_function(
    name="onboarding_admin", 
    description="Admin functions for managing user onboarding.",
    parameters_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Admin action - 'list_incomplete', 'force_complete', 'view_user', 'reset_user'"
            },
            "user_identifier": {
                "type": "string",
                "description": "User ID or email for user-specific actions"
            }
        },
        "required": ["action"]
    },
    categories=["assistance", "admin"],
    tags=["onboarding", "admin", "management"],
    importance=4
)
async def onboarding_admin(action: str, user_identifier: str = None, app_state: Any = None) -> Dict[str, Any]:
    """
    Admin functions for managing user onboarding.
    
    Args:
        action: Admin action - 'list_incomplete', 'force_complete', 'view_user', 'reset_user'
        user_identifier: User ID or email for user-specific actions
        app_state: Application state (injected by tool framework)
        
    Returns:
        Dictionary containing admin operation results
    """
    try:
        # Check admin permissions
        if not app_state or not app_state.has_permission(Permission.ADMIN_ACCESS_USERS):
            return {
                "status": "ERROR",
                "error_type": "PermissionDenied",
                "user_facing_message": "Sorry, you don't have the necessary permissions for this admin operation.",
                "technical_details": "User lacks ADMIN_ACCESS_USERS permission for onboarding_admin tool."
            }
        
        action_lower = action.lower() # Case-insensitive action

        if action_lower == "list_incomplete":
            # List users who haven't completed onboarding
            all_profiles = db_manager.get_all_user_profiles()
            incomplete_users = []
            
            for profile_data in all_profiles:
                profile_prefs = (profile_data.get("profile_data") or {})
                if not profile_prefs.get("onboarding_completed", False):
                    incomplete_users.append({
                        "user_id": profile_data["user_id"],
                        "display_name": profile_data["display_name"],
                        "email": profile_data.get("email"),
                        "first_seen": profile_data["first_seen_timestamp"],
                        "role": profile_data["assigned_role"]
                    })
            
            if not incomplete_users:
                return {
                    "status": "SUCCESS",
                    "message": "✅ All users have completed onboarding!"
                }
            
            # Format the list
            incomplete_list = "**Users who haven't completed onboarding:**\n\n"
            for user in incomplete_users:
                time_ago = int(time.time()) - user["first_seen"]
                days_ago = time_ago // 86400
                
                incomplete_list += f"• **{user['display_name']}** ({user['role']})\n"
                incomplete_list += f"  - Email: {user['email'] or 'N/A'}\n"
                incomplete_list += f"  - First seen: {days_ago} days ago\n"
                incomplete_list += f"  - User ID: `{user['user_id']}`\n\n"
            
            incomplete_list += f"**Total: {len(incomplete_users)} users**\n\n"
            incomplete_list += "**Available Actions:**\n"
            incomplete_list += "• Force complete: 'force complete onboarding for [user_id]'\n"
            incomplete_list += "• Reset user: 'reset onboarding for [user_id]'"
            
            return {
                "status": "SUCCESS", 
                "message": incomplete_list,
                "incomplete_count": len(incomplete_users)
            }
        
        elif action_lower == "view_user":
            if not user_identifier:
                return {
                    "status": "ERROR",
                    "error_type": "MissingParameter",
                    "user_facing_message": "Please specify which user you'd like to view. You can use their ID or email.",
                    "technical_details": "user_identifier not provided for view_user action in onboarding_admin."
                }
            
            # Find user by ID or email
            user_profile_data = None
            if "@" in user_identifier:
                # Search by email
                all_profiles = db_manager.get_all_user_profiles()
                for profile in all_profiles:
                    if profile.get("email") == user_identifier:
                        user_profile_data = profile
                        break
            else:
                # Search by user ID
                user_profile_data = db_manager.get_user_profile_by_id(user_identifier)
            
            if not user_profile_data:
                return {
                    "status": "ERROR",
                    "error_type": "UserNotFound",
                    "user_facing_message": f"I couldn't find a user with the identifier '{user_identifier}'.",
                    "technical_details": f"User not found: {user_identifier} in onboarding_admin/view_user."
                }
            
            profile_data = user_profile_data.get("profile_data") or {}
            preferences = profile_data.get("preferences", {})
            
            user_summary = f"**User Profile: {user_profile_data['display_name']}**\n\n"
            user_summary += f"👤 **User ID**: `{user_profile_data['user_id']}`\n"
            user_summary += f"📧 **Email**: {user_profile_data.get('email', 'N/A')}\n"
            user_summary += f"🎭 **Role**: {user_profile_data['assigned_role']}\n"
            
            # Onboarding status
            onboarding_completed = profile_data.get("onboarding_completed", False)
            status_emoji = "✅" if onboarding_completed else "⏳"
            user_summary += f"{status_emoji} **Onboarding**: {'Completed' if onboarding_completed else 'Incomplete'}\n"
            
            if onboarding_completed and profile_data.get("onboarding_completed_at"):
                completed_at = profile_data["onboarding_completed_at"]
                user_summary += f"📅 **Completed**: {completed_at}\n"
            
            # Preferences if available
            if preferences:
                user_summary += "\n**Preferences:**\n"
                if preferences.get('preferred_name'):
                    user_summary += f"• **Preferred Name**: {preferences['preferred_name']}\n"
                if preferences.get('primary_role'):
                    user_summary += f"• **Primary Role**: {preferences['primary_role']}\n"
                if preferences.get('main_projects'):
                    user_summary += f"• **Projects**: {', '.join(preferences['main_projects'])}\n"
                if preferences.get('communication_style'):
                    user_summary += f"• **Communication**: {preferences['communication_style']}\n"
            
            # Personal credentials
            has_creds = bool(profile_data.get("personal_credentials"))
            user_summary += f"\n🔑 **Personal Credentials**: {'Yes' if has_creds else 'No'}\n"
            
            # Activity
            first_seen = datetime.fromtimestamp(user_profile_data["first_seen_timestamp"])
            last_active = datetime.fromtimestamp(user_profile_data["last_active_timestamp"])
            user_summary += f"\n📊 **Activity:**\n"
            user_summary += f"• **First Seen**: {first_seen.strftime('%Y-%m-%d %H:%M')}\n"
            user_summary += f"• **Last Active**: {last_active.strftime('%Y-%m-%d %H:%M')}\n"
            
            return {
                "status": "SUCCESS",
                "message": user_summary,
                "onboarding_completed": onboarding_completed
            }
        
        elif action_lower == "force_complete":
            if not user_identifier:
                return {
                    "status": "ERROR", 
                    "error_type": "MissingParameter",
                    "user_facing_message": "Please specify which user you'd like to force complete onboarding for. You can use their ID.",
                    "technical_details": "user_identifier not provided for force_complete action in onboarding_admin."
                }
            
            # Find and update user
            user_profile_data = db_manager.get_user_profile_by_id(user_identifier)
            if not user_profile_data:
                return {
                    "status": "ERROR",
                    "error_type": "UserNotFound",
                    "user_facing_message": f"I couldn't find a user with the ID '{user_identifier}'.",
                    "technical_details": f"User not found: {user_identifier} in onboarding_admin/force_complete."
                }
            
            # Mark onboarding as complete
            profile_data = user_profile_data.get("profile_data") or {}
            profile_data["onboarding_completed"] = True
            profile_data["onboarding_completed_at"] = datetime.utcnow().isoformat()
            profile_data["force_completed_by"] = app_state.current_user.user_id
            
            # Update the profile data
            user_profile_data["profile_data"] = profile_data
            
            # Save to database
            if db_manager.save_user_profile(user_profile_data):
                return {
                    "status": "SUCCESS",
                    "message": f"✅ Marked onboarding as complete for {user_profile_data['display_name']}",
                    "user_updated": user_profile_data['display_name']
                }
            else:
                log.error(f"Failed to save user profile for {user_identifier} during force_complete.") # Added log
                return {
                    "status": "ERROR",
                    "error_type": "ProfileUpdateFailed",
                    "user_facing_message": f"I tried to mark onboarding as complete for {user_identifier}, but couldn't save the changes. Please check the logs.",
                    "technical_details": f"db_manager.save_user_profile returned False for {user_identifier} in onboarding_admin/force_complete."
                }
        
        elif action_lower == "reset_user":
            if not user_identifier:
                return {
                    "status": "ERROR",
                    "error_type": "MissingParameter",
                    "user_facing_message": "Please specify which user you'd like to reset. You can use their ID.",
                    "technical_details": "user_identifier not provided for reset_user action in onboarding_admin."
                }
            
            # Find and reset user
            user_profile_data = db_manager.get_user_profile_by_id(user_identifier)
            if not user_profile_data:
                return {
                    "status": "ERROR",
                    "error_type": "UserNotFound",
                    "user_facing_message": f"I couldn't find a user with the ID '{user_identifier}'.",
                    "technical_details": f"User not found: {user_identifier} in onboarding_admin/reset_user."
                }
            
            # Reset onboarding
            user_profile_data["profile_data"] = {
                "onboarding_completed": False,
                "preferences": {},
                "reset_at": datetime.utcnow().isoformat(),
                "reset_by": app_state.current_user.user_id
            }
            
            # Save to database
            if db_manager.save_user_profile(user_profile_data):
                return {
                    "status": "SUCCESS",
                    "message": f"✅ Reset onboarding for {user_profile_data['display_name']}. They will go through onboarding on next interaction.",
                    "user_reset": user_profile_data['display_name']
                }
            else:
                log.error(f"Failed to save user profile for {user_identifier} during reset_user.") # Added log
                return {
                    "status": "ERROR",
                    "error_type": "ProfileUpdateFailed",
                    "user_facing_message": f"I tried to reset onboarding for {user_identifier}, but couldn't save the changes. Please check the logs.",
                    "technical_details": f"db_manager.save_user_profile returned False for {user_identifier} in onboarding_admin/reset_user."
                }
        
        else:
            return {
                "status": "ERROR",
                "error_type": "InvalidAction",
                "user_facing_message": f"Sorry, I don't know how to perform the admin action '{action}'. Valid actions are 'list_incomplete', 'view_user', 'force_complete', or 'reset_user'.",
                "technical_details": f"Unknown admin action '{action}' in onboarding_admin tool."
            }
            
    except Exception as e:
        log.error(f"Error in onboarding admin tool: {e}", exc_info=True)
        return {
            "status": "ERROR",
            "error_type": "OnboardingAdminToolError",
            "user_facing_message": "I encountered an unexpected issue while performing that admin action. Please try again.",
            "technical_details": f"Error in onboarding_admin tool: {e.__class__.__name__}: {str(e)}"
        } 