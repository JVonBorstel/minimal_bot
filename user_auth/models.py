from typing import Optional, Dict, Any, List  # Added List
from pydantic import BaseModel, Field, ConfigDict
import time
# Removed: from state_models import ToolSelectionMetrics

class ToolSelectionRecord(BaseModel):
    """
    Record of a tool selection event for analytics and learning.
    """
    timestamp: float = Field(default_factory=time.time)
    query: str
    selected_tools: List[str]  # List of tool names that were selected
    used_tools: List[str] = []  # List of tools that were actually used
    success_rate: Optional[float] = None  # Success rate if calculated


class ToolSelectionMetrics(BaseModel):
    """
    Metrics for the tool selection system.
    """
    total_selections: int = 0
    # Selection where at least one tool was used
    successful_selections: int = 0
    selection_records: List[ToolSelectionRecord] = Field(default_factory=list)


class UserProfile(BaseModel):
    """
    Model for storing user profile information.
    """
    user_id: str = Field(..., description="Primary key, unique ID for the user (e.g., from Teams).")
    display_name: str = Field(..., description="Display name of the user.")
    email: Optional[str] = Field(None, description="Email address of the user (if available).")
    aad_object_id: Optional[str] = Field(None, description="Azure Active Directory Object ID for the user.")
    tenant_id: Optional[str] = Field(None, description="Azure Active Directory Tenant ID associated with the user.")
    
    assigned_role: str = Field("DEFAULT", description="The role assigned to this user (e.g., ADMIN, DEVELOPER, STAKEHOLDER, DEFAULT).")
    
    first_seen_timestamp: int = Field(default_factory=lambda: int(time.time()), description="Unix timestamp of when the user was first seen.")
    last_active_timestamp: int = Field(default_factory=lambda: int(time.time()), description="Unix timestamp of when the user was last active.")
    
    profile_data: Optional[Dict[str, Any]] = Field(None, description="JSON blob for additional, extensible attributes.")
    profile_version: int = Field(1, description="Version number for the profile schema.")

    # Field for user-global tool adapter learning
    tool_adapter_metrics: ToolSelectionMetrics = Field(default_factory=ToolSelectionMetrics, description="User-specific metrics for tool adapter learning.")

    model_config = ConfigDict()

    def update_last_active(self) -> None:
        """Updates the last_active_timestamp to the current time."""
        self.last_active_timestamp = int(time.time())

    # Placeholder for database interaction methods.
    # Actual DB interaction will be handled by a separate manager/utility
    # that uses these Pydantic models for validation and serialization.

    # @classmethod
    # def get_by_id(cls, user_id: str) -> Optional["UserProfile"]:
    #     # This would involve a database call
    #     # Example: db_data = db.get_user(user_id)
    #     # if db_data: return cls(**db_data)
    #     return None

    # def save(self) -> None:
    #     # This would involve a database call
    #     # Example: db.save_user(self.model_dump())
    #     pass 