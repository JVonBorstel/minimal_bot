import time
import logging
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple, Literal, Union
from datetime import datetime

# Use Pydantic for state management
from pydantic import BaseModel, Field, field_validator, ValidationError, ConfigDict
from pydantic_core import PydanticCustomError  # For custom validation errors

# Get logger for state management
log = logging.getLogger("state")

from user_auth.models import UserProfile # Added import
from user_auth.permissions import Permission, PermissionManager # Added imports
from config import get_config # Added for RBAC check

# Import our new safe message handler
from bot_core.message_handler import SafeMessage, MessageProcessor, SafeTextPart

# === Standard Library ===
import asyncio
import copy
import json
import logging
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Literal, Tuple, Callable

# === Third Party ===
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from pydantic.main import create_model

# --- Define Message Part Models (as per guide's implication) ---
class TextPart(BaseModel):
    text: str
    type: Literal["text"] = "text"

class FunctionCallData(BaseModel):
    name: str
    args: Dict[str, Any]

class FunctionCallPart(BaseModel):
    function_call: FunctionCallData
    type: Literal["function_call"] = "function_call"

class FunctionResponseDataContent(BaseModel):
    content: Any # Tool output, can be string, dict, etc.

class FunctionResponseData(BaseModel):
    name: str
    response: FunctionResponseDataContent

class FunctionResponsePart(BaseModel):
    function_response: FunctionResponseData
    type: Literal["function_response"] = "function_response"

MessagePart = Union[TextPart, FunctionCallPart, FunctionResponsePart]

class Message(BaseModel):
    """Enhanced Message model with safe validation"""
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    
    role: str = Field(description="Role of the message sender")
    parts: List[MessagePart] = Field(default_factory=list, description="Message content parts")
    raw_text: Optional[str] = Field(default=None, description="Original raw text")
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional message metadata")
    
    # Add missing fields that history processing expects
    is_internal: bool = Field(default=False, description="Whether this is an internal message")
    is_error: bool = Field(default=False, description="Whether this message represents an error")
    message_type: Optional[str] = Field(default=None, description="Type of message for workflow context")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tool calls if this is a model message with tools")
    tool_call_id: Optional[str] = Field(default=None, description="Tool call ID if this is a tool response")
    
    @model_validator(mode='before')
    @classmethod
    def safe_message_validation(cls, value: Any) -> Dict[str, Any]:
        """Safely handle various message input formats"""
        from bot_core.message_handler import MessageProcessor
        try:
            # Use our enhanced message processor
            safe_msg = MessageProcessor.safe_parse_message(value)
            # Convert SafeTextPart to proper TextPart
            text_parts = []
            for part in safe_msg.parts:
                text_parts.append(TextPart(text=part.content, type="text"))
            
            return {
                "role": safe_msg.role,
                "parts": text_parts,
                "raw_text": safe_msg.raw_text,
                "timestamp": datetime.now(),
                "metadata": {},
                "is_internal": False,
                "is_error": False,
                "message_type": None,
                "tool_calls": None,
                "tool_call_id": None
            }
        except Exception as e:
            log.warning(f"Message validation fallback triggered: {e}")
            # Ultimate fallback
            text_content = str(value) if value is not None else ""
            return {
                "role": "user",
                "parts": [TextPart(text=text_content, type="text")],
                "raw_text": text_content,
                "timestamp": datetime.now(),
                "metadata": {},
                "is_internal": False,
                "is_error": False,
                "message_type": None,
                "tool_calls": None,
                "tool_call_id": None
            }
    
    @property
    def text(self) -> str:
        """Get the message text content safely"""
        if self.raw_text:
            return self.raw_text
        text_parts = []
        for part in self.parts:
            if hasattr(part, 'type') and part.type == "text":
                text_parts.append(part.text)
        return "".join(text_parts)
    
    def get_text_content(self) -> str:
        """Alternative method to get text content"""
        return self.text

# --- END: Message Part Models ---

# --- Pydantic Models for Statistics ---

class ToolUsageStats(BaseModel):
    """Tracks usage statistics for a specific tool using Pydantic."""
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_execution_ms: int = 0
    consecutive_failures: int = 0
    is_degraded: bool = False
    last_call_timestamp: float = 0.0


class SessionDebugStats(BaseModel):
    """Tracks cumulative debug statistics for the current session."""
    llm_tokens_used: int = 0
    llm_calls: int = 0
    llm_api_call_duration_ms: int = 0  # Cumulative duration of API calls
    tool_calls: int = 0
    tool_execution_ms: int = 0  # Cumulative duration of tool executions
    planning_ms: int = 0  # Time spent in initial planning phase
    total_duration_ms: int = 0  # Total duration of user prompt processing
    failed_tool_calls: int = 0
    retry_count: int = 0
    tool_usage: Dict[str, ToolUsageStats] = Field(default_factory=dict)
    total_agent_turn_ms: int = Field(
        0, description="Cumulative time spent in all agent turns"
    )

    @field_validator('tool_usage')
    @classmethod
    def check_tool_usage_structure(cls, v: Dict) -> Dict:
        """Validates the structure of the tool_usage dictionary."""
        if not v:
            return v
        if not isinstance(v, dict):
            raise PydanticCustomError(
                "value_error", "tool_usage must be a dictionary", {"value": v}
            )
        for tool_name, stats in v.items():
            if not isinstance(tool_name, str):
                raise PydanticCustomError(
                    "value_error",
                    "Tool name must be a string",
                    {"value": tool_name}
                )
            if not isinstance(stats, ToolUsageStats):
                try:
                    if isinstance(stats, dict):
                        ToolUsageStats.model_validate(stats)
                    elif not isinstance(stats, ToolUsageStats):
                        # Break long line
                        raise ValueError(
                            f"Expected ToolUsageStats or dict, "
                            f"got {type(stats)}"
                        )
                except (ValidationError, ValueError) as e:
                    error_msg = (  # Provide a more specific error message
                        f"Tool stats for '{tool_name}' is not a valid "
                        f"ToolUsageStats object or dict: {e}"
                    )
                    raise PydanticCustomError(
                        "value_error",
                        error_msg,  # type: ignore[arg-type]
                        {"tool_name": tool_name, "stats": stats}
                    ) from e
            if isinstance(stats, ToolUsageStats):
                if stats.calls < stats.successes + stats.failures:
                    raise PydanticCustomError(
                        "value_error",
                        (
                            f"Tool stats for {tool_name} has "
                            f"inconsistent counts"
                        ),  # type: ignore[arg-type]
                        {
                            "calls": stats.calls,
                            "successes": stats.successes,
                            "failures": stats.failures
                        }
                    )
        return v

    @field_validator(
        'llm_tokens_used',
        'llm_calls',
        'llm_api_call_duration_ms',
        'tool_calls',
        'tool_execution_ms',
        'planning_ms',
        'total_duration_ms',
        'failed_tool_calls',
        'retry_count',
        'total_agent_turn_ms'
    )
    @classmethod
    def check_non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Statistic value cannot be negative")
        return v


# --- Pydantic Model for Scratchpad ---
class ScratchpadEntry(BaseModel):
    """Represents a single entry in the short-term scratchpad memory."""
    tool_name: str
    summary: str
    tool_input: str  # Added to store the input to the tool
    result: str      # Added to store the result of the tool call
    is_error: bool   # Added to indicate if the tool call resulted in an error
    timestamp: float = Field(default_factory=time.time)

# --- START: ADDED WorkflowContext DEFINITION ---
# --- Pydantic Models for Workflow State Management ---
class WorkflowContext(BaseModel):
    """Represents the state and history of a single complex workflow."""
    workflow_id: str = Field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    workflow_type: str
    status: str = "active"  # e.g., active, completed, failed, cancelled
    current_stage: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list) # Log of actions/stage changes
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Pydantic v2 style model config
    model_config = {
        "validate_assignment": True,
        "arbitrary_types_allowed": True
    }

    @field_validator('updated_at', 'created_at', mode='before')
    @classmethod
    def ensure_datetime_obj(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                # Handle ISO format, especially if it includes Z for UTC
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                pass # If not ISO, try timestamp
        if isinstance(v, (float, int)):
            try:
                return datetime.utcfromtimestamp(float(v)) # Assume UTC if it's a timestamp
            except (ValueError, TypeError):
                pass # If not a valid timestamp
        log.warning(f"Could not parse datetime from value: {v} of type {type(v)}, defaulting to utcnow().")
        return datetime.utcnow()

    def update_timestamp(self) -> None:
        """Updates the 'updated_at' timestamp to the current UTC time."""
        self.updated_at = datetime.utcnow()

    def add_history_event(self, event_type: str, message: str, stage: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """Adds a structured event to the workflow's history."""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z", # Ensure UTC ISO format
            "event_type": event_type, # e.g., "STAGE_CHANGE", "DATA_UPDATE", "ERROR", "INFO"
            "message": message,
            "stage_at_event": stage if stage else self.current_stage,
            "details": details if details else {}
        }
        self.history.append(event)
        self.update_timestamp()
# --- END: ADDED WorkflowContext DEFINITION ---

# --- Pydantic Models for Tool Selection Analytics ---
# ToolSelectionRecord and ToolSelectionMetrics are now defined in user_auth.models to avoid circular imports.

class AppState(BaseModel):
    """Enhanced AppState with better message handling"""
    model_config = ConfigDict(extra='allow', validate_assignment=True)
    
    # Core fields
    version: str = Field(default="v4_bot", description="State schema version")
    messages: List[Message] = Field(default_factory=list)
    current_user_id: Optional[str] = None
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: Any) -> None:
        """Safely add a message with enhanced validation"""
        try:
            # Handle various content formats
            if isinstance(content, str):
                message_data = {"role": role, "text": content}
            elif isinstance(content, dict):
                message_data = content.copy()
                message_data["role"] = role
            else:
                # Convert any other type to string
                message_data = {"role": role, "text": str(content)}
            
            # Validate text integrity before adding
            text_content = MessageProcessor.safe_get_text(message_data)
            if not MessageProcessor.validate_text_integrity(text_content):
                log.warning(f"Text integrity issue detected, attempting repair")
                # Try to fix common issues
                if len(text_content) > 100 and ' ' not in text_content:
                    # Might be a long string without spaces - this could be the character splitting issue
                    log.error(f"Detected possible character splitting: '{text_content[:50]}...'")
                    return  # Skip adding this malformed message
            
            message = Message.model_validate(message_data)
            self.messages.append(message)
            self.updated_at = datetime.now()
            
            log.debug(f"Successfully added message: role={role}, content_length={len(text_content)}")
            
        except Exception as e:
            log.error(f"Failed to add message: {e}")
            # Create a safe fallback message
            try:
                fallback_text = f"[Message processing error: {str(content)[:100]}]"
                fallback_message = Message(
                    role=role,
                    parts=[TextPart(text=fallback_text, type="text")],
                    raw_text=fallback_text
                )
                self.messages.append(fallback_message)
                log.info("Added fallback message due to processing error")
            except Exception as fallback_error:
                log.error(f"Even fallback message creation failed: {fallback_error}")
    
    def get_last_user_message(self) -> Optional[str]:
        """Safely get the last user message"""
        try:
            for message in reversed(self.messages):
                if message.role == "user":
                    return message.text
            return None
        except Exception as e:
            log.error(f"Error getting last user message: {e}")
            return None
    
    def get_message_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get message history in a safe format"""
        try:
            recent_messages = self.messages[-limit:] if limit > 0 else self.messages
            history = []
            
            for msg in recent_messages:
                try:
                    history.append({
                        "role": msg.role,
                        "content": msg.text,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
                    })
                except Exception as e:
                    log.warning(f"Error processing message in history: {e}")
                    # Add a safe fallback entry
                    history.append({
                        "role": "system",
                        "content": f"[Error processing message: {str(e)}]",
                        "timestamp": datetime.now().isoformat()
                    })
            
            return history
        except Exception as e:
            log.error(f"Error getting message history: {e}")
            return []

    # Add current_user field
    current_user: Optional[UserProfile] = Field(default=None, description="The UserProfile of the current user.")

    # UI Related State
    selected_model: Optional[str] = None  # Set during init from config
    displayed_model: Optional[str] = None  # Actual model displayed/used
    model_recently_changed: bool = False
    model_change_count: int = 0  # Track changes to avoid loops/stale state
    selected_perplexity_model: Optional[str] = None  # Track Perplexity model

    # Health Check State
    health_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    health_prev_results: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )
    health_last_checked: float = 0.0
    health_force_refresh: bool = True  # Force initial check

    # Session Management State
    current_session_name: Optional[str] = "default"
    available_sessions: List[str] = Field(
        default_factory=lambda: ["default"]
    )

    # Tool Details (populated by ToolExecutor)
    available_tool_details: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )

    # Logging State
    startup_logged: bool = False
    startup_summary_lines: List[str] = Field(
        default_factory=list
    )  # For UI display

    # --- NEW FIELDS for Orchestration & Polish ---

    # Session Statistics (Cumulative)
    session_stats: SessionDebugStats = Field(
        default_factory=lambda: SessionDebugStats(total_agent_turn_ms=0)
    )
    # Status of the last completed user interaction cycle
    last_interaction_status: str = "COMPLETED"  # Default to success

    # Developer Visibility Toggles
    show_internal_steps: bool = False  # Toggle for planning/thought messages
    show_full_trace: bool = False  # Toggle for even more verbose trace logging

    # Multi-Agent Readiness (Future-Proofing)
    selected_persona: Optional[str] = "Default"  # Default persona
    available_personas: List[str] = Field(
        default_factory=lambda: ["Default"]
    )  # Loaded from config later
    persona_recently_changed: bool = False

    # --- NEW FIELDS for UI Decoupling ---
    # These fields are updated by chat_logic.py and read by my_bot.py

    # Current status message displayed to the user
    # (e.g., "Thinking...", "Executing tool X...")
    current_status_message: Optional[str] = None

    # Detailed feedback from the current tool execution cycle
    current_tool_execution_feedback: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Details of tool execution attempts in the last batch"
    )

    # Stores the specific error message from the *last failed step*
    # (LLM or tool call) in an interaction.
    current_step_error: Optional[str] = None

    # Stores the structured results from the *last* call to _execute_tool_calls
    # This includes role='tool' messages and internal reflection messages.
    last_tool_results: Optional[List[Dict[str, Any]]] = None

    # --- NEW Field for Streaming ---
    streaming_placeholder_content: Optional[str] = None
    is_streaming: bool = False

    # --- NEW Field for Scratchpad Memory ---
    scratchpad: List[ScratchpadEntry] = Field(
        default_factory=list,
        description="Short-term memory of recent tool result summaries"
    )

    # --- Tool Execution History ---
    previous_tool_calls: List[Tuple[str, str, str, str]] = Field(
        default_factory=list,
        description="Tracks previous tool calls to detect circular patterns (id, name, args_str, hash)"
    )

    # --- NEW Workflow State Fields ---
    active_workflows: Dict[str, WorkflowContext] = Field(
        default_factory=dict,
        description="Dictionary of active workflows, keyed by workflow_id."
    )
    completed_workflows: List[WorkflowContext] = Field(
        default_factory=list,
        description="List of completed or terminated workflows."
    )

    # --- Permission Manager Instance (cached) ---
    # _permission_manager_instance: Optional[PermissionManager] = Field(default=None, exclude=True) # Old way
    # Declare as a regular instance variable, not a Pydantic Field, for internal caching.
    # It will be initialized to None by default Python object behavior or in __init__ if we had one.
    # For Pydantic models, if not assigned in __init__ or as a Field, it might not be automatically present.
    # A common pattern is to initialize such private, cached attributes in the model's __init__ or
    # rely on the @property to create it on first access if it's None.

    # Let's initialize it to None explicitly if not using a custom __init__ for AppState.
    # Pydantic V2 handles instance variables not defined as Fields differently.
    # The most straightforward way for a cached property is to ensure it's set to None initially.
    # We can assign it directly in the class body for Pydantic models if it is not a Field.
    _permission_manager_instance: Optional[PermissionManager] = None

    @property
    def permission_manager(self) -> PermissionManager:
        """Provides a cached instance of PermissionManager."""
        if self._permission_manager_instance is None:
            # Assuming get_config().STATE_DB_PATH is accessible here
            # If not, AppState init might need to pass the db_path or config
            # For now, using get_config() as PermissionManager does.
            self._permission_manager_instance = PermissionManager(db_path=get_config().STATE_DB_PATH)
        return self._permission_manager_instance

    def has_permission(self, permission_key: Permission) -> bool:
        """
        Checks if the current user (from app_state.current_user) has the specified permission.
        Uses the PermissionManager for the actual check.
        Logs permission check attempts.
        If RBAC is disabled via config, this check will always return True.
        
        Args:
            permission_key: The Permission enum member to check for.
            
        Returns:
            True if the user has the permission (or RBAC is disabled), False otherwise.
        """
        app_config = get_config()
        if not app_config.settings.security_rbac_enabled:
            log.debug(
                f"RBAC is disabled. Granting permission '{permission_key.value}' by default. "
                f"(User: {self.current_user.user_id if self.current_user else 'N/A'}, Session: {self.session_id})"
            )
            return True

        # Check for missing user profile first
        if not self.current_user:
            log.warning(
                f"has_permission check for '{permission_key.value}' failed: No current_user in AppState. (Session: {self.session_id})"
            )
            return False

        # Use the cached PermissionManager instance
        manager = self.permission_manager
        
        # Track permission check metrics (could be expanded for analytics)
        # This could be used to identify most-used permissions and optimize roles
        log_start_time = time.time()
        
        # Perform the check
        try:
            user_has_perm = manager.has_permission(self.current_user, permission_key)
        except Exception as e:
            log.error(
                f"Error checking permission '{permission_key.value}' for user '{self.current_user.user_id}': {e}",
                exc_info=True
            )
            return False  # Fail closed (deny access) on errors
        
        # Calculate time spent on permission check
        check_duration_ms = int((time.time() - log_start_time) * 1000)
        
        # Enhanced logging with more context
        log_level = logging.DEBUG if user_has_perm else logging.INFO
        log.log(
            log_level,
            f"Permission check for User '{self.current_user.user_id}' (Role: {self.current_user.assigned_role}) "
            f"on Permission '{permission_key.value}': {'GRANTED' if user_has_perm else 'DENIED'}. "
            f"(Session: {self.session_id}, Duration: {check_duration_ms}ms)"
        )
        
        return user_has_perm

    # --- Model Configuration ---
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra="allow"
    )

    # --- Methods for Core State Management ---
    def add_message(
        self,
        role: Literal["user", "model", "function", "system"],
        parts: Optional[List[MessagePart]] = None, # Expect parts directly
        # Deprecate old direct content/tool_calls parameters in favor of parts
        content: Optional[str] = None, # Kept for backward compatibility during transition
        tool_calls: Optional[List[Dict]] = None, # Kept for backward compatibility
        function_name: Optional[str] = None, # For role='function' backward compatibility
        tool_call_id_for_response: Optional[str] = None, # For role='function' backward compatibility
        **kwargs
    ) -> None:
        """Adds a message to the chat history using the new Message and Part structure."""
        
        processed_parts: List[MessagePart] = []

        if parts:
            processed_parts.extend(parts)
        elif role == "user" and content:
            processed_parts.append(TextPart(text=content))
        elif (role == "model" or role == "assistant") and content and not tool_calls: # Handle simple text for model/assistant
            processed_parts.append(TextPart(text=content))
        elif (role == "model" or role == "assistant") and tool_calls: # Handle tool_calls for model/assistant
            if content: # If there's also text content with tool calls
                processed_parts.append(TextPart(text=content))
            for tc_data in tool_calls:
                # Check for the more detailed structure first (e.g., from LLM response)
                if (isinstance(tc_data, dict) and
                    isinstance(tc_data.get("function"), dict) and
                    tc_data.get("function").get("name") and
                    isinstance(tc_data.get("function").get("arguments"), dict)):
                    processed_parts.append(FunctionCallPart(function_call=FunctionCallData(
                        name=tc_data["function"]["name"],
                        args=tc_data["function"]["arguments"] # Corrected: was tc_data["function"]["args"]
                    )))
                # Check for a simpler direct structure (e.g. internal representation)
                elif (isinstance(tc_data, dict) and 
                      tc_data.get("name") and 
                      isinstance(tc_data.get("args"), dict)):
                    processed_parts.append(FunctionCallPart(function_call=FunctionCallData(
                        name=tc_data["name"],
                        args=tc_data["args"]
                    )))
                else:
                    log.warning(f"Unsupported tool_call structure in add_message for role '{role}': {tc_data}")
        elif role == "function" and function_name and content: # content is tool output here
            # tool_call_id_for_response is the ID of the call this is a response to.
            # The guide's `prepare_messages_for_llm_from_appstate` expects the `FunctionResponsePart` to contain the `name` of the function.
            # The `tool_call_id` isn't directly part of the `FunctionResponsePart` model in the guide, but it's vital for linking.
            # We will store it in metadata if provided.
            actual_tool_output_content: Any
            try:
                actual_tool_output_content = json.loads(content)
            except json.JSONDecodeError:
                actual_tool_output_content = content # Store as string if not JSON

            processed_parts.append(FunctionResponsePart(function_response=FunctionResponseData(
                name=function_name,
                response=FunctionResponseDataContent(content=actual_tool_output_content)
            )))
            if tool_call_id_for_response and "metadata" not in kwargs:
                kwargs["metadata"] = {}
            if tool_call_id_for_response:
                kwargs["metadata"]["tool_call_id"] = tool_call_id_for_response
        elif role == "system" and content:
            processed_parts.append(TextPart(text=content))
        
        if not processed_parts:
            log.warning(
                f"Attempted to add message for role '{role}' but no parts could be processed/created. "
                f"Original content: '{str(content)[:50]}...', Original tool_calls: {tool_calls}. Skipping."
            )
            return

        message_obj = Message(
            role=role,
            parts=processed_parts,
            is_error=kwargs.pop("is_error", False),
            is_internal=kwargs.pop("is_internal", False),
            message_type=kwargs.pop("message_type", None),
            tool_calls=tool_calls if tool_calls else None,
            tool_call_id=tool_call_id_for_response,
            metadata=kwargs.pop("metadata", {})
        )
        
        # Merge any remaining kwargs into metadata if they weren't standard Message fields
        message_obj.metadata.update(kwargs)

        try:
            self.messages.append(message_obj)
            log.debug(
                f"Added message - Role: {role}, Parts: {len(message_obj.parts)}, "
                f"Internal: {message_obj.is_internal if hasattr(message_obj, 'is_internal') else 'N/A'}, Type: {message_obj.message_type if hasattr(message_obj, 'message_type') else 'N/A'}"
            )
        except ValidationError as e:
            log.error(f"Pydantic validation error adding message: {e}")
        except Exception as e:
            log.error(f"Unexpected error adding message: {e}", exc_info=True)

    def clear_chat(self) -> None:
        """Clears chat, resets stats and transient status fields."""
        try:
            self.messages = []
            # Reset stats on clear
            self.session_stats = SessionDebugStats(total_agent_turn_ms=0)
            # Reset transient status fields as well
            self.current_status_message = None
            self.current_tool_execution_feedback = []
            self.current_step_error = None
            self.last_tool_results = None
            self.reset_turn_state()  # Clear other transient fields
            self.last_interaction_status = "CLEARED"
            log.info(
                "Chat history, session statistics, workflow, and "
                "transient status fields cleared."
            )
        except ValidationError as e:
            log.error(f"Pydantic validation error during clear_chat: {e}")
        except Exception as e:
            log.error(
                f"Unexpected error during clear_chat: {e}", exc_info=True
            )

    def update_tool_usage(
        self, function_name: str, duration_ms: int, is_success: bool
    ) -> None:
        """Safely updates tool usage statistics."""
        try:
            if not isinstance(self.session_stats.tool_usage, dict):
                # Break long line
                log.error(
                    "Tool usage is not a dict, cannot update. Resetting."
                )
                self.session_stats.tool_usage = {}  # Attempt recovery

            tool_stats = self.session_stats.tool_usage.get(function_name)
            if tool_stats is None:
                tool_stats = ToolUsageStats()
                # IMPORTANT: Assign the new stats object back to the dictionary
                self.session_stats.tool_usage[function_name] = tool_stats

            tool_stats.calls += 1
            tool_stats.total_execution_ms += duration_ms
            tool_stats.last_call_timestamp = time.time()

            if is_success:
                tool_stats.successes += 1
                tool_stats.consecutive_failures = 0
            else:
                tool_stats.failures += 1
                tool_stats.consecutive_failures += 1
                # Check if tool should be marked as degraded
                TOOLS_DEGRADED_AFTER_FAILURES = 5  # Could be from config
                if (tool_stats.consecutive_failures >=
                        TOOLS_DEGRADED_AFTER_FAILURES):
                    tool_stats.is_degraded = True
                    log.warning(
                        f"Tool '{function_name}' marked as degraded after "
                        f"{tool_stats.consecutive_failures} consecutive "
                        f"failures"
                    )
            # Trigger validation by assigning the modified dictionary back
            self.session_stats.tool_usage = self.session_stats.tool_usage

        except ValidationError as e:
            log.error(
                f"Pydantic validation error updating tool usage for "
                f"'{function_name}': {e}"
            )
        except Exception as e:
            log.error(
                f"Unexpected error updating tool usage for "
                f"\'{function_name}\': {e}",
                exc_info=True
            )

    def reset_turn_state(self) -> None:
        """Resets transient state fields for a new user prompt."""
        self.current_status_message = None
        self.current_tool_execution_feedback = []
        self.current_step_error = None
        self.last_tool_results = None
        # Set initial status for the new turn
        self.last_interaction_status = "PROCESSING"
        # Break long line
        log.debug(
            "Turn-specific state fields reset (workflow state preserved)."
        )

    def add_scratchpad_entry(self, entry: ScratchpadEntry) -> None:
        """Adds an entry to the scratchpad, maintaining size limit."""
        # Define limit locally or import from config if centralized later
        MAX_SCRATCHPAD_ITEMS = 10  # Keep consistent with chat_logic

        if not isinstance(entry, ScratchpadEntry):
            # Break long line
            log.warning(
                f"Attempted to add invalid entry type to scratchpad: "
                f"{type(entry)}"
            )
            return
        try:
            # Prepend to keep most recent entries easily accessible
            self.scratchpad.insert(0, entry)
            # Trim the list if it exceeds the maximum size
            if len(self.scratchpad) > MAX_SCRATCHPAD_ITEMS:
                self.scratchpad = self.scratchpad[:MAX_SCRATCHPAD_ITEMS]
            log.debug(
                f"Added scratchpad entry for tool: {entry.tool_name}. "
                f"New size: {len(self.scratchpad)}"
            )
        except ValidationError as e:
            log.error(
                f"Pydantic validation error adding scratchpad entry: {e}"
            )
        except Exception as e:
            log.error(
                f"Unexpected error adding scratchpad entry: {e}",
                exc_info=True
            )

    def get_full_context_for_llm(self) -> List[Dict[str, Any]]:
        """Constructs the full message list for the LLM, including system prompt if needed."""
        # Implementation here

    def end_workflow(self, workflow_id: str, end_status: Literal["completed", "failed", "cancelled", "terminated"] = "completed") -> bool:
        """
        Ends a specific active workflow by its ID and moves it to completed_workflows.

        Args:
            workflow_id: The ID of the workflow to end.
            end_status: The status to set for the ended workflow.
                        Defaults to "completed".
        
        Returns:
            True if the workflow was found and ended, False otherwise.
        """
        if workflow_id in self.active_workflows:
            workflow_to_end = self.active_workflows.pop(workflow_id)
            
            workflow_to_end.status = end_status
            workflow_to_end.update_timestamp()
            
            event_type_str = "WORKFLOW_COMPLETED"
            if end_status == "failed":
                event_type_str = "WORKFLOW_FAILED"
            elif end_status == "cancelled":
                event_type_str = "WORKFLOW_CANCELLED"
            elif end_status == "terminated":
                event_type_str = "WORKFLOW_TERMINATED_BY_SYSTEM"

            workflow_to_end.add_history_event(
                event_type=event_type_str,
                message=f"Workflow '{workflow_to_end.workflow_type}' (ID: {workflow_id}) ended with status: {end_status}.",
                details={"final_status": end_status, "ended_by": "AppState.end_workflow"}
            )
            
            self.completed_workflows.append(workflow_to_end)
            log.info(f"Workflow '{workflow_id}' (Type: {workflow_to_end.workflow_type}) ended with status '{end_status}' and moved to completed_workflows.")
            return True
        else:
            log.warning(f"Attempted to end workflow ID '{workflow_id}', but it was not found in active_workflows.")
            return False

# State migration function
def _migrate_state_if_needed(old_state_data: Union[Dict, AppState]) -> AppState: # Allow AppState as input
    """Handles versioned state migration when schema changes."""

    # Handle if old_state_data is already an AppState instance
    if isinstance(old_state_data, AppState):
        if old_state_data.version == "v4_bot":
            log.debug("Received AppState instance is already latest version (v4_bot). No migration needed.")
            return old_state_data
        else:
            log.info(f"Received AppState instance version {old_state_data.version}. Converting to dict for migration.")
            # Convert to dict to proceed with dictionary-based migration logic
            old_state_data_dict = old_state_data.model_dump(mode='json')
    elif isinstance(old_state_data, dict):
        old_state_data_dict = old_state_data
    else: # Should not happen if type hints are respected
        log.error(f"Unexpected type for old_state_data: {type(old_state_data)}. Attempting to treat as empty.")
        old_state_data_dict = {}

    if not old_state_data_dict: # Check if the dictionary is empty
        log.warning(
            "Empty old_state_data (or failed conversion) received for migration, creating fresh AppState."
        )
        return AppState(
            session_id=f"conv_{uuid.uuid4().hex[:8]}",
            version="v4_bot"
        )

    current_version = old_state_data_dict.get('version', 'v1')
    # Ensure migrated_data starts as a copy of the dictionary form
    migrated_data = old_state_data_dict.copy()
    target_v_for_error_log = migrated_data.get('version')

    try:
        if current_version == "v1":
            log.info("Migrating state from v1 to v2 (Bot context)...")
            migrated_data = {
                'version': 'v2',
                'session_id': old_state_data.get(  # Break long line
                    'session_id', f"conv_{uuid.uuid4().hex[:8]}"
                ),
                'messages': old_state_data.get('messages', []),
                'selected_model': old_state_data.get('selected_model'),
            }
            current_version = "v2"

        if current_version == "v2":
            log.info("Migrating state from v2 to v3 (Bot context)...")
            migrated_data = (
                old_state_data.copy() if current_version != 'v1'
                else migrated_data
            )
            migrated_data['version'] = "v3"
            # Note: v2 to v3 migration currently involves no data transformation, only a version bump.
            # This might have been a placeholder or a schema version increment without structural change.
            current_version = "v3"

        if current_version == "v3":
            log.info("Migrating state from v3 to v4 (Bot context)...")
            migrated_data = (
                old_state_data.copy() if current_version not in ['v1', 'v2']
                else migrated_data
            )
            migrated_data.setdefault('current_workflow', None)
            migrated_data.setdefault('workflow_stage', None)
            migrated_data['version'] = "v4"
            current_version = "v4"

        if current_version == "v4":
            log.info("Migrating state from v4 to v4_bot (transforming old workflow fields)...")
            migrated_data = (
                old_state_data.copy() if current_version not in ['v1', 'v2', 'v3']
                else migrated_data
            )
            # Migration from v4 to v4_bot:
            # - Key change: 'current_workflow' and 'workflow_stage' are transformed into 'active_workflows'.
            # - New fields: 'active_workflows', 'completed_workflows' (default to empty).
            # - 'current_user' field added (defaults to None).
            # - 'version' becomes 'v4_bot'.
            migrated_data["version"] = "v4_bot"
            
            old_current_workflow_type = migrated_data.pop("current_workflow", None)
            old_workflow_stage = migrated_data.pop("workflow_stage", None)

            if old_current_workflow_type: # If there was an active workflow
                # Initialize active_workflows if it's not already a dict (e.g., from earlier migration steps if any)
                if "active_workflows" not in migrated_data or not isinstance(migrated_data.get("active_workflows"), dict):
                    migrated_data["active_workflows"] = {}
                
                # Create a new WorkflowContext for the migrated workflow
                # workflow_id will be auto-generated by its default_factory
                migrated_workflow = WorkflowContext(
                    workflow_type=str(old_current_workflow_type), # Ensure it's a string
                    current_stage=str(old_workflow_stage) if old_workflow_stage is not None else None,
                    status="active", # Assume it was active
                    data={}, # Start with empty data for the migrated workflow
                    history=[{ # Add a history event for traceability
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "event_type": "MIGRATION",
                        "message": f"Workflow migrated from v4 state. Original type: {old_current_workflow_type}, stage: {old_workflow_stage}",
                        "stage_at_event": str(old_workflow_stage) if old_workflow_stage is not None else None,
                        "details": {"source_version": "v4"}
                    }],
                    created_at=datetime.utcnow(), # Set creation to migration time
                    updated_at=datetime.utcnow()  # Set update to migration time
                )
                # Add to active_workflows, keyed by its new workflow_id
                migrated_data["active_workflows"][migrated_workflow.workflow_id] = migrated_workflow.model_dump()
                log.info(f"Migrated v4 workflow '{old_current_workflow_type}' (stage: {old_workflow_stage}) to new WorkflowContext with ID {migrated_workflow.workflow_id}")
            
            # active_workflows and completed_workflows will get their Pydantic defaults (empty dict/list)
            # if not already populated by the migration step above.
            # current_user will get its Pydantic default (None)
            current_version = migrated_data["version"] # Ensure current_version is updated for the loop/final check
        
        if current_version == "v4_bot":
            log.debug(
                "State is v4_bot or migrated to v4_bot. "
                "Validating final structure."
            )
            return AppState(**migrated_data)  # Validate against current model
        else:
            log.error(
                f"Unknown state version '{current_version}' after "
                f"migration process. Resetting state."
            )
            return AppState(
                session_id=f"conv_{uuid.uuid4().hex[:8]}", version="v4_bot"
            )

    except ValidationError as e:
        log.error(  # Break long line
            f"State validation/migration failed for v '{current_version}'"
            f"processing data for v_target='{target_v_for_error_log}': {e}"
        )
        # Fix: Create dictionary first, then use in f-string
        partial_data_str = str(
            {k: v for k, v in old_state_data.items() if k != 'messages'}
        )
        log.error(f"Failed state data (partial): {partial_data_str}...",
                  exc_info=True)
        return AppState(
            session_id=f"conv_{uuid.uuid4().hex[:8]}", version="v4_bot"
        )
    except Exception as e:
        log.error(
            f"Unexpected error during state migration "
            f"(current_version processing: '{current_version}'): {e}",
            exc_info=True
        )
        return AppState(
            session_id=f"conv_{uuid.uuid4().hex[:8]}", version="v4_bot"
        )
