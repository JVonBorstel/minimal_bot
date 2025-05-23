from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import time

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

    class Config:
        # Example for Pydantic V2 if you were using it for ORM-like features
        # from_attributes = True 
        # For Pydantic V1, or basic model usage, this is often not needed or `orm_mode = True`
        pass

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