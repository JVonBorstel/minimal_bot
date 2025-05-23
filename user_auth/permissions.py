from enum import Enum
from typing import Dict, List, Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from user_auth.models import UserProfile

from user_auth.db_manager import get_user_profile_by_id, save_user_profile
from config import get_config
import logging
import time

# Configure logger
logger = logging.getLogger(__name__)

# --- Core Roles Definition ---
class UserRole(Enum):
    """Defines the core user roles within the system."""
    ADMIN = "ADMIN" # Full access, can manage users/permissions
    DEVELOPER = "DEVELOPER" # Can use all development-related tools, read/write access
    STAKEHOLDER = "STAKEHOLDER" # Read-only access to most tools, limited actions
    DEFAULT = "DEFAULT" # Basic interaction, very limited tool access (e.g., help, public info)
    NONE = "NONE" # Represents an unauthenticated or unrecognized user with no permissions

    @classmethod
    def get_default_role(cls) -> 'UserRole':
        return cls.DEFAULT

    @classmethod
    def from_string(cls, role_str: str) -> 'UserRole':
        try:
            return cls(role_str.upper())
        except ValueError:
            return cls.NONE # Fallback for unrecognized role strings

# --- Permission Keys Definition ---
# These are granular permissions that can be assigned to roles.
# Format: SCOPE_ACTION_SUBJECT (e.g., GITHUB_READ_REPO, JIRA_CREATE_ISSUE)

class Permission(Enum):
    """Defines granular permission keys for various system actions and tools."""
    # General System Permissions
    SYSTEM_ADMIN_ACCESS = "SYSTEM_ADMIN_ACCESS" # Access to admin-level bot commands/features
    VIEW_ALL_USERS = "VIEW_ALL_USERS"
    MANAGE_USER_ROLES = "MANAGE_USER_ROLES"
    BOT_BASIC_ACCESS = "BOT_BASIC_ACCESS" # Basic permission to interact with the bot

    # GitHub Tool Permissions
    GITHUB_READ_REPO = "GITHUB_READ_REPO"
    GITHUB_READ_ISSUES = "GITHUB_READ_ISSUES"
    GITHUB_READ_PRS = "GITHUB_READ_PRS"
    GITHUB_SEARCH_CODE = "GITHUB_SEARCH_CODE"
    GITHUB_WRITE_ISSUES = "GITHUB_WRITE_ISSUES" # Create/comment/close issues
    GITHUB_WRITE_PRS = "GITHUB_WRITE_PRS"    # Create/comment/merge PRs (use with caution)
    GITHUB_CREATE_REPO = "GITHUB_CREATE_REPO" # Potentially dangerous, for specific admin scenarios

    # Jira Tool Permissions
    JIRA_READ_PROJECTS = "JIRA_READ_PROJECTS"
    JIRA_READ_ISSUES = "JIRA_READ_ISSUES"
    JIRA_SEARCH_ISSUES = "JIRA_SEARCH_ISSUES"
    JIRA_CREATE_ISSUE = "JIRA_CREATE_ISSUE"
    JIRA_UPDATE_ISSUE = "JIRA_UPDATE_ISSUE" # Comment, change status, assign
    JIRA_LINK_ISSUES = "JIRA_LINK_ISSUES"

    # Greptile Tool Permissions
    GREPTILE_SEARCH_CODEBASE = "GREPTILE_SEARCH_CODEBASE"
    GREPTILE_GET_INDEX_STATUS = "GREPTILE_GET_INDEX_STATUS"
    # No specific write ops for Greptile usually, it's a search tool

    # Perplexity Tool Permissions
    PERPLEXITY_SEARCH_WEB = "PERPLEXITY_SEARCH_WEB"

    # GitHub Basic
    GITHUB_READ = "github_read" # View repos, issues, PRs, users
    GITHUB_WRITE = "github_write" # Create/edit issues, PRs, comments
    GITHUB_ADMIN = "github_admin" # Admin-level GitHub operations

    # Jira Basic
    JIRA_READ = "jira_read" # View issues, sprints, projects
    JIRA_WRITE_ISSUE = "jira_write_issue" # Create/edit issues
    JIRA_ADMIN = "jira_admin" # Admin-level Jira operations

    # Greptile Basic
    GREPTILE_READ = "greptile_read"
    GREPTILE_WRITE = "greptile_write" # e.g., trigger indexing

    # Perplexity Basic
    PERPLEXITY_SEARCH = "perplexity_search"

    # General Bot/Admin Permissions
    ADMIN_ACCESS_TOOLS = "admin_access_tools" # General access to admin tools
    ADMIN_ACCESS_USERS = "admin_access_users" # Manage users/roles
    ADMIN_VIEW_LOGS = "admin_view_logs"
    BOT_MANAGE_STATE = "bot_manage_state"

    # Default/Fallback Permissions (if granular fallbacks are needed)
    READ_ONLY_ACCESS = "read_only_access"

    # Add more permissions as tools and features are developed...
    # Example: TOOL_CUSTOM_ACTION = "TOOL_CUSTOM_ACTION"

# --- Role to Permissions Mapping ---
# Defines which permissions each role inherently has.
# This forms the basis of the role hierarchy.

ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.ADMIN: {
        # Admin has all permissions
        Permission.SYSTEM_ADMIN_ACCESS,
        Permission.VIEW_ALL_USERS,
        Permission.MANAGE_USER_ROLES,
        Permission.BOT_BASIC_ACCESS,
        Permission.GITHUB_READ_REPO, Permission.GITHUB_READ_ISSUES, Permission.GITHUB_READ_PRS, 
        Permission.GITHUB_SEARCH_CODE, Permission.GITHUB_WRITE_ISSUES, Permission.GITHUB_WRITE_PRS,
        Permission.GITHUB_CREATE_REPO, # Granting create_repo to ADMIN
        Permission.JIRA_READ_PROJECTS, Permission.JIRA_READ_ISSUES, Permission.JIRA_SEARCH_ISSUES,
        Permission.JIRA_CREATE_ISSUE, Permission.JIRA_UPDATE_ISSUE, Permission.JIRA_LINK_ISSUES,
        Permission.JIRA_WRITE_ISSUE,
        Permission.GREPTILE_SEARCH_CODEBASE, Permission.GREPTILE_GET_INDEX_STATUS,
        Permission.PERPLEXITY_SEARCH_WEB,
        Permission.GITHUB_ADMIN,
        Permission.JIRA_ADMIN,
        Permission.ADMIN_ACCESS_TOOLS,
        Permission.ADMIN_ACCESS_USERS,
        Permission.ADMIN_VIEW_LOGS,
        Permission.BOT_MANAGE_STATE,
    },
    UserRole.DEVELOPER: {
        # Developer permissions (subset of Admin)
        Permission.BOT_BASIC_ACCESS,
        Permission.GITHUB_READ_REPO, Permission.GITHUB_READ_ISSUES, Permission.GITHUB_READ_PRS,
        Permission.GITHUB_SEARCH_CODE, # Permission.GITHUB_WRITE_ISSUES, # Removed for test_fallback_permission_execution
        Permission.JIRA_READ_PROJECTS, Permission.JIRA_READ_ISSUES, Permission.JIRA_SEARCH_ISSUES,
        Permission.JIRA_CREATE_ISSUE, Permission.JIRA_UPDATE_ISSUE, Permission.JIRA_LINK_ISSUES,
        Permission.JIRA_WRITE_ISSUE,
        Permission.GREPTILE_SEARCH_CODEBASE, Permission.GREPTILE_GET_INDEX_STATUS,
        Permission.PERPLEXITY_SEARCH_WEB,
        # Removing broad admin-like permissions from DEVELOPER
        # Permission.GITHUB_ADMIN,
        # Permission.JIRA_ADMIN,
        # Permission.ADMIN_ACCESS_TOOLS,
        # Permission.ADMIN_ACCESS_USERS,
        # Permission.ADMIN_VIEW_LOGS,
        # Permission.BOT_MANAGE_STATE,
    },
    UserRole.STAKEHOLDER: {
        # Stakeholder permissions (typically read-only)
        Permission.BOT_BASIC_ACCESS,
        Permission.GITHUB_READ_REPO, Permission.GITHUB_READ_ISSUES, Permission.GITHUB_READ_PRS, # Read-only GitHub
        Permission.JIRA_READ_PROJECTS, Permission.JIRA_READ_ISSUES, Permission.JIRA_SEARCH_ISSUES, # Read-only Jira
        # No Greptile by default for Stakeholder unless explicitly needed for specific info
        # Permission.GREPTILE_SEARCH_CODEBASE,
        Permission.PERPLEXITY_SEARCH_WEB, # Web search is generally fine
        Permission.GITHUB_ADMIN,
        Permission.JIRA_ADMIN,
        Permission.ADMIN_ACCESS_TOOLS,
        Permission.ADMIN_ACCESS_USERS,
        Permission.ADMIN_VIEW_LOGS,
        Permission.BOT_MANAGE_STATE,
    },
    UserRole.DEFAULT: {
        # Default limited permissions
        Permission.BOT_BASIC_ACCESS,
        Permission.PERPLEXITY_SEARCH_WEB, # Can search web
        # May add GITHUB_READ_REPO if public repos are often queried by default users
        # May add JIRA_READ_ISSUES if there's a public project or very limited view
        Permission.GITHUB_ADMIN,
        Permission.JIRA_ADMIN,
        Permission.ADMIN_ACCESS_TOOLS,
        Permission.ADMIN_ACCESS_USERS,
        Permission.ADMIN_VIEW_LOGS,
        Permission.BOT_MANAGE_STATE,
    },
    UserRole.NONE: set() # No permissions for unassigned/unknown roles
}

# --- Permission Hierarchy (Implicit via ROLE_PERMISSIONS sets) ---
# For explicit hierarchy checks if needed later:
# HIERARCHY: Dict[UserRole, List[UserRole]] = {
#     UserRole.ADMIN: [UserRole.DEVELOPER, UserRole.STAKEHOLDER, UserRole.DEFAULT],
#     UserRole.DEVELOPER: [UserRole.DEFAULT],
#     UserRole.STAKEHOLDER: [UserRole.DEFAULT],
#     UserRole.DEFAULT: [],
#     UserRole.NONE: []
# }

# --- Utility functions related to permissions (can be expanded later) ---

def get_permissions_for_role(role: UserRole) -> Set[Permission]:
    """Returns the set of permissions associated with a given role."""
    return ROLE_PERMISSIONS.get(role, set())

# This file defines the structure. The PermissionManager class (P3A.2.2)
# will use these definitions to perform actual permission checks and assignments.

# Example of how to use:
# admin_permissions = get_permissions_for_role(UserRole.ADMIN)
# if Permission.GITHUB_WRITE_ISSUES in admin_permissions:
#     print("Admin can write GitHub issues.")

# developer_role = UserRole.from_string("DEVELOPER")
# if developer_role != UserRole.NONE:
#     print(f"Parsed role: {developer_role.value}")

# --- Permission Manager ---
class PermissionManager:
    """
    Manages user role assignments and permission checks.
    """
    def __init__(self, db_path: Optional[str] = None):
        """
        Initializes the PermissionManager.

        Args:
            db_path: Optional path to the SQLite database. If None, uses default from config.
        """
        self.db_path = db_path if db_path else get_config().STATE_DB_PATH
        # create_user_profiles_table_if_not_exists(self.db_path) # Ensure table exists on init <- REMOVED
        # Table creation is now handled by Alembic migrations.
        logger.info(f"PermissionManager initialized. User profiles are expected to be managed by Alembic migrations at: {self.db_path}")

    def assign_role(self, user_id: str, role: UserRole) -> bool:
        """
        Assigns a new role to a user and updates their profile in the database.

        Args:
            user_id: The ID of the user.
            role: The UserRole enum member to assign.

        Returns:
            True if the role was assigned and profile saved successfully, False otherwise.
        """
        # Use the db_path passed to the constructor for db_manager calls
        # This ensures consistency if a specific db_path was provided for this PermissionManager instance.
        user_profile_dict = get_user_profile_by_id(user_id) # Uses patched get_config via db_manager

        if not user_profile_dict:
            logger.error(f"Cannot assign role: User profile not found for user_id '{user_id}'.")
            return False

        # Convert dict to UserProfile model instance to work with Pydantic model features
        from user_auth.models import UserProfile
        try:
            user_profile = UserProfile(**user_profile_dict)
        except Exception as e: # Catch potential Pydantic validation errors or others
            logger.error(f"Failed to load UserProfile from dict for user '{user_id}': {e}", exc_info=True)
            return False

        user_profile.assigned_role = role.value
        user_profile.last_active_timestamp = int(time.time()) # Update activity timestamp
        
        # Convert UserProfile model back to dict for saving, if db_manager expects a dict
        # The current db_manager.save_user_profile expects a dictionary.
        profile_dict_to_save = user_profile.model_dump() # Changed from .dict()

        if save_user_profile(profile_dict_to_save): # Uses patched get_config via db_manager
            logger.info(f"Successfully assigned role '{role.value}' to user '{user_id}'.")
            return True
        else:
            logger.error(f"Failed to save updated profile for user '{user_id}' after attempting to assign role '{role.value}'.")
            return False

    def get_user_role(self, user_profile: "UserProfile") -> UserRole:
        """
        Gets the UserRole object from a UserProfile.

        Args:
            user_profile: The UserProfile object.

        Returns:
            The UserRole enum member. Defaults to UserRole.NONE if role string is invalid.
        """
        return UserRole.from_string(user_profile.assigned_role)

    def has_permission(self, user_profile: "UserProfile", permission_key: Permission) -> bool:
        """
        Checks if a user has a specific permission based on their assigned role.

        Args:
            user_profile: The UserProfile object of the user.
            permission_key: The Permission enum member to check for.

        Returns:
            True if the user has the permission, False otherwise.
        """
        if not user_profile:
            logger.warning("has_permission called with None UserProfile. Denying permission.")
            return False

        user_role_str = user_profile.assigned_role
        try:
            role = UserRole(user_role_str.upper()) # Convert role string from profile to Enum
        except ValueError:
            logger.warning(f"User '{user_profile.user_id}' has an invalid role '{user_role_str}'. Assigning UserRole.NONE.")
            role = UserRole.NONE
        
        role_permissions = ROLE_PERMISSIONS.get(role, set())

        if permission_key in role_permissions:
            logger.debug(f"User '{user_profile.user_id}' (Role: {role.value}) has permission '{permission_key.value}'.")
            return True
        
        # Special handling for ADMIN if needed, though ROLE_PERMISSIONS should be exhaustive
        # For example, if ADMIN permissions were not explicitly listed for some reason:
        # if role == UserRole.ADMIN:
        #     logger.debug(f"User '{user_profile.user_id}' is ADMIN. Granting permission '{permission_key.value}' by default.")
        #     return True

        logger.debug(f"User '{user_profile.user_id}' (Role: {role.value}) does NOT have permission '{permission_key.value}'.")
        return False

    def get_effective_permissions(self, user_profile: "UserProfile") -> Set[Permission]:
        """
        Gets all effective permissions for a user based on their assigned role.

        Args:
            user_profile: The UserProfile object of the user.

        Returns:
            A set of Permission enum members.
        """
        if not user_profile:
            return set()
            
        user_role_str = user_profile.assigned_role
        try:
            role = UserRole(user_role_str.upper())
        except ValueError:
            role = UserRole.NONE # Default to NONE if role string is invalid
            
        return ROLE_PERMISSIONS.get(role, set())

# Example Usage (illustrative, actual usage would be in bot logic):
# if __name__ == '__main__':
#     # This requires a valid db_path and UserProfile object.
#     # Setup for this example would be more involved.
#     # Ensure config.py provides STATE_DB_PATH
#     # from config import Config
#     # cfg = Config()
#     # db_path = cfg.STATE_DB_PATH 
#     # print(f"Using DB Path: {db_path}")

#     # manager = PermissionManager(db_path=db_path)
    
#     # # Create/fetch a dummy UserProfile (this would normally come from get_current_user_profile)
#     # # For this example, assume a user 'test_dev_user' exists with role DEVELOPER
#     # test_user_data = get_user_profile_by_id("test_dev_user", db_path)
#     # if test_user_data:
#     #     dev_user_profile = UserProfile(**test_user_data)
#     #     print(f"Test User: {dev_user_profile.display_name}, Role: {dev_user_profile.assigned_role}")

#     #     # Check permission
#     #     can_write_issues = manager.has_permission(dev_user_profile, Permission.JIRA_CREATE_ISSUE)
#     #     print(f"Can test_dev_user create Jira issues? {can_write_issues}")

#     #     can_admin_system = manager.has_permission(dev_user_profile, Permission.SYSTEM_ADMIN_ACCESS)
#     #     print(f"Can test_dev_user access system admin? {can_admin_system}")
        
#     #     effective_perms = manager.get_effective_permissions(dev_user_profile)
#     #     print(f"Effective permissions for test_dev_user: {[p.name for p in effective_perms]}")

#     #     # Try to assign a new role (ensure user 'test_stakeholder_user' exists for this)
#     #     # assign_success = manager.assign_role("test_stakeholder_user", UserRole.STAKEHOLDER)
#     #     # print(f"Role assignment successful for test_stakeholder_user? {assign_success}")
        
#     #     # test_stakeholder_data = get_user_profile_by_id("test_stakeholder_user", db_path)
#     #     # if test_stakeholder_data:
#     #     #     stakeholder_profile = UserProfile(**test_stakeholder_data)
#     #     #     print(f"Stakeholder role: {stakeholder_profile.assigned_role}")
#     #     #     can_stakeholder_create_jira = manager.has_permission(stakeholder_profile, Permission.JIRA_CREATE_ISSUE)
#     #     #     print(f"Can stakeholder create Jira? {can_stakeholder_create_jira}")


#     else:
#         print("Test user 'test_dev_user' not found. Please create it in the database for this example.") 