"""
Tool management models for the chatbot.
Contains data classes for tool call requests and results.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolCallRequest:
    """Represents a request to execute a tool."""
    tool_name: str
    parameters: Dict[str, Any]
    tool_call_id: Optional[str] = None
    user_id: Optional[str] = None
    
    def __post_init__(self):
        """Validate the tool call request."""
        if not self.tool_name:
            raise ValueError("tool_name cannot be empty")
        if self.parameters is None:
            self.parameters = {}


@dataclass
class ToolCallResult:
    """Represents the result of a tool execution."""
    tool_name: str
    tool_input: Dict[str, Any]
    status: str
    data: Dict[str, Any]
    summary: str
    tool_call_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    
    def __post_init__(self):
        """Validate the tool call result."""
        if not self.tool_name:
            raise ValueError("tool_name cannot be empty")
        if not self.status:
            raise ValueError("status cannot be empty")
        if self.tool_input is None:
            self.tool_input = {}
        if self.data is None:
            self.data = {}
    
    @property
    def is_success(self) -> bool:
        """Check if the tool execution was successful."""
        return self.status.lower() in ["success", "ok", "mocked_success"]
    
    @property
    def is_error(self) -> bool:
        """Check if the tool execution resulted in an error."""
        return self.status.lower() in ["error", "failed", "failure"] 