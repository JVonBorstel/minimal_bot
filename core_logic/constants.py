# core_logic/constants.py

"""
This module defines constants used across the core logic of the application,
particularly for chat interactions, tool usage, and workflow management.
"""

# --- Tool and Cycle Limits ---
MAX_TOOL_RESULT_PREVIEW_LEN = 300
"""Maximum length for previewing tool results in logs or UI."""

MAX_TOOL_ARG_PREVIEW_LEN = 100
"""Maximum length for previewing tool arguments in logs or UI."""

MAX_SCRATCHPAD_ITEMS = 10
"""Maximum number of items to keep in the scratchpad memory."""

MAX_GENERAL_TOOL_CYCLES = 5
"""Maximum number of general tool execution cycles allowed in a single turn
before a workflow takes over or the turn ends."""

MAX_TOOL_CYCLES_OUTER = 10
"""
Absolute maximum number of tool execution cycles for the general agent loop
in a single turn.
"""

MAX_STORY_BUILDER_CYCLES_PER_STAGE = 3
"""
Maximum number of LLM calls or retries allowed within a single stage of the
Story Builder workflow.
"""

TOOL_CALL_ID_PREFIX = "call_"
"""Prefix used for generating unique tool call IDs."""


# --- Status Messages ---
# These messages are used to update the UI or logs about the agent's current
# state.
STATUS_THINKING = "🧠 Thinking..."
STATUS_PLANNING = "📝 Planning approach..."
STATUS_CALLING_TOOLS = "🔧 Calling requested tools..."
STATUS_PROCESSING_TOOLS = "⚙️ Processing tool results..."
STATUS_GENERATING_REPLY = "✍️ Generating final reply..."
STATUS_GENERATING_SUMMARY = "📊 Generating final summary..."  # Used for subtask summaries

# Error Status Messages
STATUS_ERROR_LLM = "LLM API Error"
STATUS_ERROR_TOOL = "Tool Execution Error"
STATUS_ERROR_INTERNAL = "Internal Error"
STATUS_MAX_CALLS_REACHED = "Maximum Tool Calls Reached"

# Workflow Specific Status Messages
STATUS_STORY_BUILDER_PREFIX = "Story Builder: "
"""Prefix for status messages related to the Story Builder workflow."""


# --- Agentic Intelligence Constants ---
# Constants related to the agent's decision-making and self-correction
# capabilities.
MAX_SIMILAR_TOOL_CALLS = 3
"""
Maximum number of times a tool can be called with highly similar arguments
before it's considered a potential circular call.
"""

SIMILARITY_THRESHOLD = 0.85
"""
Threshold for determining if two tool argument strings are considered similar
(0.0 to 1.0).
"""

TOOL_RETRY_INITIAL_DELAY = 0.5
"""Initial delay in seconds before retrying a failed tool execution."""

MAX_RETRY_DELAY = 5.0
"""Maximum delay in seconds for tool execution retries."""

MAX_TOOL_EXECUTION_RETRIES = 3
"""Maximum number of retries for a single tool execution attempt."""

LLM_API_RETRY_ATTEMPTS = 3
"""Maximum number of retry attempts for LLM API calls."""

TOOLS_DEGRADED_AFTER_FAILURES = 5
"""
Number of consecutive failures after which a tool might be considered degraded.
"""

SYSTEM_ROLE = "system"
"""Identifier for system-level messages or prompts."""

BREAK_ON_CRITICAL_TOOL_ERROR = False
"""
If True, a critical tool error will immediately break the agent's execution
cycle. If False, the agent will attempt to report the error and let the LLM
respond.
"""


# --- Message Types ---
# Standardized types for internal and external messages within the chat logic.
THOUGHT_MESSAGE_TYPE = "thought"
"""Internal message type for LLM's reasoning or thinking process."""

ACTION_MESSAGE_TYPE = "action"
"""Message type representing a tool call or action to be taken."""

OBSERVATION_MESSAGE_TYPE = "observation"
"""Message type for results or observations from tool executions."""

PLAN_MESSAGE_TYPE = "plan"
"""Internal message type for LLM's proposed plan of action."""

REFLECTION_MESSAGE_TYPE = "reflection"
"""Internal message type for LLM's self-reflection or critique."""

WORKFLOW_STAGE_MESSAGE_TYPE = "workflow_stage"
"""Internal message type to denote the current stage of an active workflow."""


# --- Story Builder Workflow Constants ---
STORY_BUILDER_TRIGGER_TOOL_SCHEMA = {
    "name": "start_story_builder_workflow",
    "description": (
        "Initiates the structured Jira Story Builder workflow when a user "
        "requests to create a Jira ticket, user story, or similar."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "initial_request": {
                "type": "string",
                "description": (
                    "The user's full, original request to build the story or "
                    "ticket."
                )
            }
        },
        "required": ["initial_request"]
    }
}
"""Schema for the tool that triggers the Story Builder workflow."""
