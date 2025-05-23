# --- FILE: config.py ---
import os
import logging
import logging.handlers
from typing import Dict, Any, Optional, List, Literal, Union, cast
import re

from dotenv import load_dotenv, find_dotenv
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    EmailStr,
    ValidationError,
    field_validator,
    model_validator,
)

log = logging.getLogger(__name__)

# --- Custom Logging Filter ---
class DuplicateFilter(logging.Filter):
    """
    Suppresses repeated log messages.
    """
    def __init__(self, name=''):
        super().__init__(name)
        self.last_log = None
        self.last_log_count = 0
        self.max_count = 3  # Show the first 3 occurrences of each message

    def filter(self, record):
        # Get message and compare with last seen
        current_log = record.getMessage()

        if current_log == self.last_log:
            self.last_log_count += 1
            # Only show the first max_count messages
            if self.last_log_count <= self.max_count:
                return True
            
            # For every 50th repeat after max_count, show a summary
            if self.last_log_count % 50 == 0:
                record.msg = f"Previous message repeated {self.last_log_count} times: {record.msg}"
                return True
            return False
        else:
            # If we had repeats before this new message, log a final summary
            if self.last_log and self.last_log_count > self.max_count:
                # Use the same logger as the current record
                logger = logging.getLogger(record.name)
                logger.log(
                    record.levelno,
                    f"Previous message repeated {self.last_log_count-self.max_count} more times: {self.last_log}"
                )

            # Reset for new message
            self.last_log = current_log
            self.last_log_count = 1
            return True

# Load environment variables from .env file first
# This makes them available for Pydantic validation
# Ensures that if this module is imported elsewhere, .env is loaded.
# load_dotenv()  # Actually load the .env file # REMOVED: This should be handled only in app.py

# --- Constants ---

# Define available personas for the bot
# Key: Display Name, Value: Associated internal prompt fragment or identifier (can be expanded later)
# For now, just using names. Logic to use these will be in chat_logic.py
AVAILABLE_PERSONAS: List[str] = [
    "Default", # Standard Augie persona defined by SYSTEM_PROMPT
    "Concise Communicator", # A persona that prioritizes brevity
    "Detailed Explainer", # A persona that elaborates more
    "Code Reviewer", # A persona focused on code analysis tasks
]
DEFAULT_PERSONA: str = "Default"

# Default Gemini model if not specified in .env
DEFAULT_GEMINI_MODEL = "models/gemini-1.5-pro-latest"

# Dynamically get available models if SDK is available, otherwise use hardcoded list
# This list is mainly for reference or potential validation if needed later.
# The actual model availability is checked by the SDK/API.
AVAILABLE_GEMINI_MODELS_REF = [
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash-latest",
    "models/gemini-1.5-pro-latest",
    # Add other known compatible models if necessary
]

AVAILABLE_PERPLEXITY_MODELS_REF = [
    "sonar",
    "sonar-pro",
    "sonar-reasoning",
    "sonar-reasoning-pro",
    "sonar-deep-research",
    "r1-1776"
]

# Define which env vars are needed for each logical tool/service
# Used by Config.is_tool_configured
TOOL_CONFIG_REQUIREMENTS: Dict[str, List[str]] = {
    "jira": ["JIRA_API_URL", "JIRA_API_EMAIL", "JIRA_API_TOKEN"],
    "greptile": ["GREPTILE_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
}

# --- NEW PROMPTS ---
# Using constants directly, simplifies AppSettings model
ROUTER_SYSTEM_PROMPT = """You are Augie, a helpful and versatile ChatOps assistant. Your primary goal is to understand the user's request and determine the best course of action.

Available Actions:
1.  **General Conversation:** Engage in normal conversation, answer questions based on your knowledge.
2.  **Direct Tool Use:** If the user asks for specific information or action that matches one of your tools (GitHub, Jira, Perplexity, Greptile), plan and execute the tool call(s) directly. Ask for clarification if needed.
3.  **Story Building:** If the user explicitly asks to 'create a Jira ticket', 'build a user story', 'draft an issue', or similar, you MUST initiate the specialized 'Story Builder' workflow by calling the `start_story_builder_workflow` function. Do NOT attempt to create the ticket directly using other tools in this case.

Analyze the user's latest message and decide which action is appropriate. If unsure, ask clarifying questions. If initiating story building, call the function `start_story_builder_workflow` with the user's full request as the `initial_request` parameter."""

STORY_BUILDER_SYSTEM_PROMPT = """Your name is Augie, the Jira Story Builder. You assist users in creating Jira tickets by strictly adhering to a detailed, predefined structure suitable for direct integration into Jira systems. It guides users to fill out the template below.

**Current Task:** You are in a specific stage of building the story. Follow the instructions for your current stage provided in the conversation history (e.g., 'Current Stage: detailing', 'Current Stage: draft1_review').

<rules>
*   Ensure all detail provided *throughout the conversation history* is used, leave nothing out.
*   When filling out sections during the 'collecting_info' stage and you do not have the information, ASK ONE QUESTION AT A TIME.
*   When asking clarifying questions, provide suggestions (use Perplexity tool if needed for web info) BEFORE finalizing a section.
*   Search online using the Perplexity tool to fill in gaps *where appropriate and requested* or to provide suggestions.
</rules>

<design_steps> (These outline the overall flow managed by the system)
*   System will manage stages: collecting_info -> detailing -> draft1_review -> draft2_review -> final_draft -> awaiting_confirmation -> create_ticket.
*   'detailing' stage: Generate a detailed, line-by-line requirement list based on *all* user input gathered so far. Be extremely verbose.
*   'drafting' stages: Use the detailed list and the template to generate the story.
*   'review' stages: Present the draft to the user for feedback (system handles this pause).
*   'awaiting_confirmation': Present the final draft for approval before creation (system handles this pause).
</design_steps>

<critical_steps>
*   If requirements involve database tables during the 'detailing' or 'drafting' stages, GENERATE the full T-SQL script within a code block.
*   You MUST ALWAYS use ALL user-provided data. THIS IS NOT OPTIONAL.
</critical_steps>

<products>
*   LoanMAPS: Loan Origination System, CRM, Borrower Portal.
*   Rule Tool: Agency/Investor Search engine.
*   Tech: ASP.NET/C#, MSSQL.
</products>

<technology> (Your knowledge includes these)
ElasticSearch/OpenSearch, Twilio, Redis, Entity Framework Core, Dapper, FluentResults, FluentValidation, ASP.NET Core Blazor, MediatR, MassTransit, Hangfire, RestSharp, Amazon QLDB, Snowflake DB, Audit.NET, AWS Services, OpenAI, DbUp, EPPlus, Handlebars.Net, Hashids.net, Humanizer, Ical.Net, ImageResizer, iTextSharp, JSReport, Knockout.js, CSS/LESS, HTML, JavaScript, SignalR, Moment.js, MySQL, Polly, Postmark, QRCoder
</technology>

<template>
<<<JIRA_STORY_START>>>
# Project: [Project Name]

## Summary:
[Provide a concise overview of the project or task, including key goals and technologies involved.]

## Description:
This ticket provides a detailed outline of the requirements and expected functionalities for the [Project or Feature Name]. It specifies the tasks, objectives, and any special considerations necessary for the development team to understand and execute the requirements effectively.

## General Requirements:
- **Technology Stack:** [Specify primary technologies - USER PROVIDED ONLY or ask/suggest]
- **Key Resources:**
  - [Resource 1 Name/Link]
  - [Resource 2 Name/Link]
  - [Resource 3 Name/Link]

## Detailed Specifications:

### [Component or Feature 1]:
- **Objective:** [Define the goal]
- **Functional Requirements:**
  - [Detail 1]
  - [Detail 2]
- **Technical Specifications:**
  - [Detail 1]
  - [Code examples/T-SQL if applicable]
- **Exhibits:** [Placeholder for user to add links/references]

### [Component or Feature 2]:
- **Objective:** [Define the goal]
- **Functional Requirements:**
  - [Detail 1]
  - [Detail 2]
- **Technical Specifications:**
  - [Detail 1]
  - [Code examples/T-SQL if applicable]
- **Exhibits:** [Placeholder for user to add links/references]

[...repeat component sections as needed...]

## Potential Impacted Areas:
- **[Area 1]:** [Describe impact]
- **[Area 2]:** [Describe impact]

## Testing Instructions:
- **[Feature 1]:** [Testing steps/checklist]
- **[Feature 2]:** [Testing steps/checklist]

## Post-Deployment Actions:
- **[Action 1]:** [Example: Update permissions]
- **[Action 2]:** [Example: Configure credentials]

## Documentation and Training:
- [Details on documentation/training needs]

## Development Guidelines:
- **Best Practices:** [Mention specific standards if known]
- **Security:** [Mention specific requirements if known]
- **Performance Optimization:** [Mention specific goals if known]

## Expected Outcome:
[Describe successful completion and how to measure it]
<<<JIRA_STORY_END>>>
"""

# --- Pydantic Models for Settings Validation ---

class GitHubAccountConfig(BaseModel):
    """Configuration for a single GitHub account/instance."""
    name: str = Field(..., description="Unique identifier for this GitHub configuration (e.g., 'personal', 'work').")
    token: str = Field(..., description="GitHub Personal Access Token (PAT) or other token.")
    base_url: Optional[HttpUrl] = Field(None, description="Base URL for GitHub Enterprise instances. Leave None for github.com.")

    class Config:
        extra = 'ignore'

class AppSettings(BaseModel):
    """Pydantic model defining and validating ALL application settings."""
    # Core App Settings
    app_env: Literal["development", "production"] = Field("development", alias="APP_ENV")
    port: int = Field(3978, alias="PORT", gt=0, lt=65536) # Default Bot Framework port
    app_base_url: Optional[HttpUrl] = Field(None, alias="APP_BASE_URL")
    teams_bot_endpoint: Optional[HttpUrl] = Field(None, alias="TEAMS_BOT_ENDPOINT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field("INFO", alias="LOG_LEVEL")
    mock_mode: bool = Field(False, alias="MOCK_MODE")

    # LLM Settings
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    gemini_model: str = Field(DEFAULT_GEMINI_MODEL, alias="GEMINI_MODEL")
    llm_max_history_items: int = Field(50, alias="LLM_MAX_HISTORY_ITEMS", gt=0)

    # Agent Behavior Settings
    system_prompt: str = Field(
        "DEFAULT_SYSTEM_PROMPT_PLACEHOLDER",
        alias="SYSTEM_PROMPT"
    )
    max_consecutive_tool_calls: int = Field(5, alias="MAX_CONSECUTIVE_TOOL_CALLS", gt=0)
    default_api_timeout_seconds: int = Field(90, alias="DEFAULT_API_TIMEOUT_SECONDS", gt=0)
    default_api_max_retries: int = Field(2, alias="DEFAULT_API_MAX_RETRIES", ge=0)
    break_on_critical_tool_error: bool = Field(True, alias="BREAK_ON_CRITICAL_TOOL_ERROR")
    
    # --- Bot Framework Specific Settings ---
    MicrosoftAppId: Optional[str] = Field(None, alias="MICROSOFT_APP_ID")
    MicrosoftAppPassword: Optional[str] = Field(None, alias="MICROSOFT_APP_PASSWORD")

    # --- Tool-Specific Settings (Flattened) ---
    # GitHub (Multiple Accounts)
    github_accounts: List[GitHubAccountConfig] = Field(
        default_factory=list,
        description="List of configured GitHub accounts/instances."
    )
    github_default_account_name: Optional[str] = Field(
        None,
        alias="GITHUB_DEFAULT_ACCOUNT_NAME",
        description="The 'name' of the GitHub account to use by default if not specified."
    )
    # Jira
    jira_api_url: Optional[HttpUrl] = Field(None, alias="JIRA_API_URL")
    jira_api_email: Optional[EmailStr] = Field(None, alias="JIRA_API_EMAIL")
    jira_api_token: Optional[str] = Field(None, alias="JIRA_API_TOKEN")
    jira_default_project_key: str = Field("PROJ", alias="JIRA_DEFAULT_PROJECT_KEY")
    jira_default_issue_type: str = Field("Story", alias="JIRA_DEFAULT_ISSUE_TYPE")
    # Greptile
    greptile_api_key: Optional[str] = Field(None, alias="GREPTILE_API_KEY")
    greptile_api_url: HttpUrl = Field("https://api.greptile.com/v2", alias="GREPTILE_API_URL") # type: ignore[assignment]
    greptile_default_repo: Optional[str] = Field(None, alias="GREPTILE_DEFAULT_REPO")
    # Perplexity
    perplexity_api_key: Optional[str] = Field(None, alias="PERPLEXITY_API_KEY")
    perplexity_api_url: HttpUrl = Field("https://api.perplexity.ai", alias="PERPLEXITY_API_URL") # type: ignore[assignment]
    perplexity_model: str = Field("sonar-pro", alias="PERPLEXITY_MODEL")

    @field_validator('jira_api_token', 'jira_api_email', 'jira_api_url', mode='before')
    def _ensure_jira_fields_not_empty_if_provided(cls, v: Optional[Any], info: Any) -> Optional[Any]:
        if v is not None and isinstance(v, str) and not v.strip():
            # If a string is provided but it's empty, treat it as None for further validation.
            return None
        return v

    @model_validator(mode='after')
    def _check_jira_config_complete(self) -> 'AppSettings':
        jira_fields_map = {
            'jira_api_url': self.jira_api_url,
            'jira_api_email': self.jira_api_email,
            'jira_api_token': self.jira_api_token
        }
        
        set_fields = {field for field, value in jira_fields_map.items() if value is not None and str(value).strip()}
        
        if 0 < len(set_fields) < len(jira_fields_map):
            missing_fields = []
            for field_name, value in jira_fields_map.items():
                if value is None or (isinstance(value, str) and not str(value).strip()):
                    pydantic_field = self.model_fields.get(field_name)
                    env_var_name = pydantic_field.alias if pydantic_field and pydantic_field.alias else field_name.upper()
                    missing_fields.append(f"{field_name} (env var: {env_var_name})")
            
            if missing_fields:
                error_message = f"Jira configuration incomplete: If any Jira setting is provided, all are required. Missing values for: {', '.join(missing_fields)}."
                log.error(error_message)
                raise ValueError(error_message)
        return self

    # GitHub cross-field validation (ensure default account exists if specified)
    @model_validator(mode='after')
    def check_github_default_account(self) -> 'AppSettings':
        if self.github_default_account_name and self.github_accounts:
            account_names = {acc.name for acc in self.github_accounts}
            if self.github_default_account_name not in account_names:
                raise ValueError(
                    f"Invalid GITHUB_DEFAULT_ACCOUNT_NAME ('{self.github_default_account_name}'). "
                    f"It does not match any configured account name: {list(account_names)}"
                )
        elif self.github_default_account_name and not self.github_accounts:
             raise ValueError(
                 "GITHUB_DEFAULT_ACCOUNT_NAME is set, but no GitHub accounts are configured (GITHUB_ACCOUNT_n_... variables)."
             )
        return self

    state_db_path: str = Field("db/state.sqlite", alias="STATE_DB_PATH")

    # Security Settings
    security_rbac_enabled: bool = Field(False, alias="SECURITY_RBAC_ENABLED")

    # Storage Settings
    memory_type: Literal["sqlite", "redis"] = Field("sqlite", alias="MEMORY_TYPE")
    # Redis Specific Settings (optional, only used if memory_type is 'redis')
    redis_url: Optional[str] = Field(None, alias="REDIS_URL", description="Full Redis connection URL (e.g., redis://user:pass@host:port/db). Overrides individual host/port/db/ssl settings if provided.")
    redis_host: Optional[str] = Field("localhost", alias="REDIS_HOST")
    redis_port: Optional[int] = Field(6379, alias="REDIS_PORT")
    redis_password: Optional[str] = Field(None, alias="REDIS_PASSWORD")
    redis_db: int = Field(default=0, description="Redis database number.")
    redis_ssl_enabled: bool = Field(default=False, description="Enable SSL for Redis connection.")
    redis_prefix: str = Field(default="botstate:", description="Prefix for all keys stored in Redis by this bot instance.")

    @field_validator('app_base_url', mode='before')
    @classmethod
    def derive_app_base_url(cls, v: Optional[str], info: Any) -> str:
        """Derives app_base_url from PORT if not explicitly set or ensures port consistency."""
        
        port_field_name = 'port'
        port_field_alias = cls.model_fields[port_field_name].alias or port_field_name # Alias is 'PORT'
        
        port_val_from_data = info.data.get(port_field_alias) # Try alias 'PORT' first
        if port_val_from_data is None:
            port_val_from_data = info.data.get(port_field_name) # Then try field name 'port'

        actual_port: int
        if port_val_from_data is not None:
            try:
                actual_port = int(port_val_from_data)
                if not (0 < actual_port < 65536):
                    log.warning(f"Port value '{port_val_from_data}' (from key '{port_field_alias if info.data.get(port_field_alias) else port_field_name}') is out of valid range. Defaulting to 3978.")
                    actual_port = 3978
            except (ValueError, TypeError):
                log.warning(f"Invalid port value '{port_val_from_data}' (from key '{port_field_alias if info.data.get(port_field_alias) else port_field_name}'). Defaulting to 3978.")
                actual_port = 3978
        else:
            log.warning(f"Port not found in raw input (keys '{port_field_alias}', '{port_field_name}'). Using default from field: {cls.model_fields[port_field_name].default}")
            actual_port = cls.model_fields[port_field_name].default 
            if actual_port is None: 
                actual_port = 3978

        if v: 
            try:
                parsed_url = HttpUrl(v) 
                current_port_in_url_str = parsed_url.port
                expected_port_str = str(actual_port)

                if current_port_in_url_str is None:
                    if not ((parsed_url.scheme == "http" and expected_port_str == "80") or \
                            (parsed_url.scheme == "https" and expected_port_str == "443")):
                        new_url_str = f"{parsed_url.scheme}://{parsed_url.host}:{actual_port}{parsed_url.path or ''}"
                        log.info(f"APP_BASE_URL '{v}' had no explicit port, adjusted to: '{new_url_str}'")
                        return new_url_str
                elif current_port_in_url_str != expected_port_str:
                    log.warning(
                        f"Port in APP_BASE_URL ('{current_port_in_url_str}') "
                        f"does not match target PORT ('{actual_port}'). Overriding APP_BASE_URL port."
                    )
                    new_url_str = f"{parsed_url.scheme}://{parsed_url.host}:{actual_port}{parsed_url.path or ''}"
                    return new_url_str
                return v 
            except Exception as e: 
                log.error(f"Error parsing or adjusting provided APP_BASE_URL '{v}': {e}. Falling back to default.")
        
        default_url_str = f"http://127.0.0.1:{actual_port}"
        log.info(f"APP_BASE_URL not provided or adjustment failed, defaulting to: {default_url_str}")
        return default_url_str

    @model_validator(mode='after')
    def _ensure_app_base_url_default(self) -> 'AppSettings':
        """Ensures app_base_url has a default if it wasn't provided or resolved to None."""
        if self.app_base_url is None:
            # self.port is already validated and available as an int
            actual_port = self.port
            default_url_str = f"http://127.0.0.1:{actual_port}"
            log.info(
                f"APP_BASE_URL was not set or resulted in None after field processing, "
                f"applying default in model_validator: {default_url_str}"
            )
            try:
                # Directly assign the parsed HttpUrl object
                self.app_base_url = HttpUrl(default_url_str)
            except ValidationError as e:
                # This case should ideally not be reached if default_url_str is always valid.
                log.critical(f"CRITICAL: Failed to parse internally constructed default APP_BASE_URL '{default_url_str}': {e}")
                # Raising a ValueError here will make the model validation fail, which is appropriate.
                raise ValueError(f"Internal error: Constructed default APP_BASE_URL '{default_url_str}' is invalid.") from e
        return self

    @model_validator(mode='after')
    def derive_teams_bot_endpoint(self) -> 'AppSettings':
        """Derives teams_bot_endpoint from app_base_url."""
        if self.app_base_url:
            # Ensure app_base_url is a string before joining path
            base_url_str = str(self.app_base_url)
            # Ensure no double slashes if base_url_str ends with / and path starts with /
            path_segment = "/api/messages"
            if base_url_str.endswith('/') and path_segment.startswith('/'):
                derived_endpoint = base_url_str + path_segment[1:]
            elif not base_url_str.endswith('/') and not path_segment.startswith('/'):
                 derived_endpoint = base_url_str + "/" + path_segment
            else:
                derived_endpoint = base_url_str + path_segment
            
            # If TEAMS_BOT_ENDPOINT was set in env, check if it matches derived one (ignoring minor diffs like trailing slash)
            env_teams_endpoint = os.environ.get("TEAMS_BOT_ENDPOINT")
            if env_teams_endpoint:
                # Normalize both for comparison (e.g. remove trailing slashes)
                normalized_env = env_teams_endpoint.rstrip('/')
                normalized_derived = derived_endpoint.rstrip('/')
                if normalized_env != normalized_derived:
                    log.warning(
                        f"TEAMS_BOT_ENDPOINT from environment ('{env_teams_endpoint}') does not match derived endpoint "
                        f"('{derived_endpoint}') based on APP_BASE_URL and PORT. Using derived endpoint."
                    )
            self.teams_bot_endpoint = HttpUrl(derived_endpoint) # Validate and assign
        elif os.environ.get("TEAMS_BOT_ENDPOINT"): # if app_base_url was somehow None, but TEAMS_BOT_ENDPOINT is set
            log.warning("APP_BASE_URL is not set, but TEAMS_BOT_ENDPOINT is. Attempting to use TEAMS_BOT_ENDPOINT directly. This may lead to inconsistencies.")
            self.teams_bot_endpoint = HttpUrl(os.environ.get("TEAMS_BOT_ENDPOINT"))
        else:
            log.error("Could not derive TEAMS_BOT_ENDPOINT as APP_BASE_URL is not available.")
            self.teams_bot_endpoint = None # Or raise an error if it's critical
        return self

    @model_validator(mode='after')
    def check_redis_config_if_needed(self) -> 'AppSettings':
        """Checks Redis configuration if memory_type is 'redis'."""
        if self.memory_type == "redis":
            if self.redis_url:
                # If redis_url is provided, it takes precedence.
                # Basic check to ensure it's not just an empty string if provided.
                if not str(self.redis_url).strip():
                    raise ValueError("REDIS_URL is set but empty. Please provide a valid Redis connection URL or unset it to use individual host/port settings.")
                # Further validation of the URL could be done here if needed,
                # but pydantic's HttpUrl (or a custom regex) might be too strict for redis URLs.
                # For now, we assume if it's set, it's intended to be used as is.
                log.info(f"Using REDIS_URL for Redis connection: {self.redis_url}")
            elif not self.redis_host: # redis_host has a default, so this check is mainly for explicit None/empty
                raise ValueError("REDIS_HOST must be set if REDIS_URL is not provided and memory_type is 'redis'.")
        return self

    class Config:
        env_file_encoding = 'utf-8'
        extra = 'ignore'

# Define the default system prompt separately for readability
DEFAULT_SYSTEM_PROMPT = """You are a versatile and helpful AI assistant designed for development teams. You can engage in natural conversation and utilize specialized tools when appropriate.

**Core Objective:** Accurately understand the user's intent and respond in the most effective way.

**CRITICAL: When you need to use tools, make function calls directly. Do NOT output planning text, pseudo-code, or "tool_code" blocks. Use the actual function calling capability.**

**Interaction Flow:**
1.  **Analyze Intent:** First, determine if the user's message is primarily conversational (e.g., a greeting, simple question, comment, expressing gratitude) or if it clearly implies a task requiring specific information or action that necessitates a tool.
    *   Messages like "Show me PR #123 in the Light-MVP repository", "What are my open Jira tickets?", or "Search for code that implements the login feature" indicate a need for tools.
    *   Messages like "Hi", "Thanks", "How are you?", "What\'s the best practice for code reviews?", or "Tell me about RESTful APIs" can be answered conversationally.
2.  **Prioritize Conversation:** For simple inputs or general conversation, respond directly without using tools. Do NOT invoke tools unless the user\'s intent strongly indicates a need for external information or specific actions. If a request is ambiguous but could be a general question, answer conversationally first.
3.  **Tool Usage Guidelines:**
    *   **GitHub:** Use for repository information, PRs, issues, code search, and repository analysis.
    *   **Jira:** Use for ticket queries, project information, and issue management.
    *   **Greptile:** Use for semantic code search, code understanding, and codebase analysis.
    *   **Perplexity:** Use selectively for web searches when the user explicitly asks for recent/external information or when answering factual questions outside your knowledge.
4.  **Pattern Recognition:**
    *   If you see patterns like "PR #123", "JIRA-456", or repository names like "username/repo", route to the appropriate tool.
    *   For queries like "list my jira tickets", "show my open issues", "what are my Jira tickets?", or similar requests for personalized Jira information about the **current user**:
        *   Your primary goal is to use the `jira_get_issues_by_user` tool.
        *   This tool requires a `user_email` parameter.
        *   **First, check if the user's email is already known from their profile. If so, use it directly.**
        *   **If the user's email is not known or you are unsure, you MUST ask the user for their email address.**
        *   **Once you have the user's email (either from their profile or after asking them), you MUST then immediately call the `jira_get_issues_by_user` tool with that email.** Do not ask what to do next; proceed with the tool call.
        *   You can optionally use the `status_category` parameter (e.g., "to do", "in progress", "done"). If the user doesn\'t specify, default to "to do" or ask if they want a specific status (this clarification can happen before or after getting the email).
    *   For queries like "list my repos", "show my github repositories", or similar requests for personalized GitHub repository lists, use the `github_list_repositories` tool (again, inferring the user context if needed).
    *   For queries containing words like "weather", "latest news", or "current", consider using Perplexity for web search.
    *   For code-related queries like "find function that implements..." use Greptile or GitHub search tools.
5.  **Direct Tool Execution:** When you need to use tools, call them immediately without explaining your plan. Let the tool results inform your response to the user.
6.  **Ask for Clarification:** When a task-oriented request lacks necessary details (e.g., missing repository name or issue key), ask for clarification before proceeding.
7.  **Effective Tool Parameters:**
    *   Pass complete, properly formatted parameters to tools.
    *   Use specific search terms when querying code or repositories.
    *   Use proper boolean values (true/false) rather than strings.
    *   Structure array parameters as proper arrays, not comma-separated strings.

**Critical Decision Points:**
1.  **When NOT to use tools:**
    *   For greetings, thanks, and simple conversations
    *   For general knowledge questions within your capabilities
    *   When the user is asking about your capabilities or how you work
    *   For conceptual explanations or best practices discussions
2.  **When to DEFINITELY use tools:**
    *   When the user explicitly requests external information ("search for", "find online")
    *   When referring to specific resources by ID (PR numbers, Jira tickets)
    *   When requesting recent information (news, weather, current events)
    *   When asking for specific code or repository details

**Parameter Decision Guide:**
*   GitHub tools: Require repository names, issue/PR numbers, or search queries
*   Jira tools: Require issue keys, project IDs, or search terms
*   Greptile tools: Require repository URLs/names and search queries
*   Perplexity tools: Require clear, focused search terms

**REMEMBER: Use function calls directly. Do not describe what you plan to do or output pseudo-code. Execute the function calls and then provide a helpful response based on the results.**"""

# Replace placeholder in the model definition
AppSettings.model_fields['system_prompt'].default = DEFAULT_SYSTEM_PROMPT

# --- Main Configuration Class ---
class Config:
    """Configuration class holding validated application settings."""
    settings: AppSettings
    AVAILABLE_PERSONAS: List[str] = AVAILABLE_PERSONAS
    DEFAULT_PERSONA: str = DEFAULT_PERSONA
    TOOL_CONFIG_REQUIREMENTS: Dict[str, List[str]] = TOOL_CONFIG_REQUIREMENTS
    AVAILABLE_GEMINI_MODELS_REF: List[str] = AVAILABLE_GEMINI_MODELS_REF
    AVAILABLE_PERPLEXITY_MODELS_REF: List[str] = AVAILABLE_PERPLEXITY_MODELS_REF
    # Expose prompts as class attributes or properties
    ROUTER_PROMPT: str = ROUTER_SYSTEM_PROMPT
    STORY_BUILDER_PROMPT: str = STORY_BUILDER_SYSTEM_PROMPT
    # Default system prompt as class attribute
    DEFAULT_SYSTEM_PROMPT: str = DEFAULT_SYSTEM_PROMPT
    
    # Tool Integration Configuration
    MAX_SERVICE_SCHEMA_PROPERTIES: int = 12  # Maximum properties to include in a service's parameter schema
    MAX_TOOLS_BEFORE_FILTERING: int = 20    # Threshold above which to apply category filtering
    MAX_FUNCTION_DECLARATIONS: int = 6      # Maximum number of services/function declarations to send to LLM
    
    # Define persona-specific system prompts
    PERSONA_SYSTEM_PROMPTS: Dict[str, str] = {
        "Default": DEFAULT_SYSTEM_PROMPT,
        "Concise Communicator": """You are a concise AI assistant. Provide brief, direct answers without unnecessary explanations or introductions. Focus on giving just the essential information needed to answer the user's question. When using tools, explain your actions minimally.""",
        "Detailed Explainer": """You are a thorough AI assistant that provides comprehensive explanations. Break down complex topics into clear, detailed explanations with examples when helpful. When using tools, explain your reasoning process, methodology, and how each step contributes to the solution.""",
        "Code Reviewer": """You are a code review specialist. Focus on analyzing code for bugs, security issues, performance concerns, and adherence to best practices. Provide specific, actionable feedback with code examples to demonstrate improvements. When reviewing, consider readability, maintainability, edge cases, and potential optimizations."""
    }
    
    # Tool Selector Configuration
    TOOL_SELECTOR: Dict[str, Any] = {
        "enabled": True,                           # Whether to use dynamic tool selection
        "embedding_model": "all-MiniLM-L6-v2",     # SentenceTransformer model to use
        "cache_path": "data/tool_embeddings.json", # Path to store the tool embeddings cache
        "similarity_threshold": 0.45,              # Minimum similarity score to consider a tool relevant (Increased from 0.3)
        "max_tools": 6,                           # Maximum number of tools to select for each query
        "always_include_tools": ["help", "search_web"],  # Tools to always include regardless of relevance
        "debug_logging": True,                    # Enable detailed logging of selection process
        "default_fallback": False,                 # Fall back to all tools if selection fails (Changed from True to be more conservative)
        "rebuild_cache_on_startup": False,         # Whether to rebuild the tool embeddings cache on startup
    }
    
    # Schema Optimization Configuration
    SCHEMA_OPTIMIZATION: Dict[str, Any] = {
        "enabled": True,                     # Whether to optimize schemas
        "max_tool_description_length": 150,  # Max length for individual tool parameter descriptions
        "max_tool_enum_values": 8,           # Max enum values for individual tool parameters
        "max_tool_schema_properties": 12,    # Max properties for a single tool's schema (before service consolidation)
        "max_nested_object_properties": 5,   # Max properties in a nested object before simplification
        "max_array_item_properties": 4,      # Max properties for an object within an array before simplification
        "simplify_complex_types": True,      # Existing: Whether to simplify oneOf/anyOf constructs
        "flatten_nested_objects": False,     # Existing (but changed default): Whether to flatten deeply nested objects to string
        "truncate_long_names": False,        # Existing (but changed default): Whether to truncate long property names
        "max_name_length": 30,               # Existing: Maximum length for property names if truncation is enabled (if truncate_long_names is True)
        # Deprecating or re-evaluating old keys if they were for different scope
        # "max_description_length": 100,    # Old key, effectively replaced by max_tool_description_length
        # "max_enum_values": 5,             # Old key, effectively replaced by max_tool_enum_values
    }

    # Internal state
    _initial_log_level_set: bool = False
    _tool_validation_cache: Dict[str, bool]
    _tool_health_status: Dict[str, str]

    def __init__(self):
        """Loads and validates configuration from environment variables using Pydantic."""
        try:
            # 1. Initial basic logging (before full validation) - REMOVED
            # initial_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
            # self._setup_initial_logging(initial_log_level)

            # 2. Load environment variables from .env files
            log.debug("Config.__init__: Loading .env files (if present)...")
            load_dotenv(find_dotenv(usecwd=True), verbose=True, override=False) # Load .env, don't override existing os.environ

            # 3. Prepare env vars for Pydantic validation
            log.debug("Preparing environment variables for Pydantic validation...")
            env_dict = dict(os.environ) # Use current environment
            cleaned_env_dict: Dict[str, Any] = {} # Dict to pass to Pydantic
            temp_github_accounts: Dict[int, Dict[str, str]] = {}
            github_accounts_data: List[Dict[str, Optional[str]]] = []
            github_var_pattern = re.compile(r"^GITHUB_ACCOUNT_(\d+)_(NAME|TOKEN|BASE_URL)$", re.IGNORECASE)

            # Simplified GitHub account extraction without sanitization
            # Iterates through all environment variables, looking for keys matching the
            # GITHUB_ACCOUNT_n_NAME/TOKEN/BASE_URL pattern. It stores these temporarily
            # by index number (n).
            github_account_raw_keys_to_remove = set()
            for key, value in env_dict.items():
                match = github_var_pattern.match(key)
                if match:
                    index = int(match.group(1))
                    field = match.group(2).lower() # 'name', 'token', 'base_url'
                    if index not in temp_github_accounts:
                        temp_github_accounts[index] = {}
                    temp_github_accounts[index][field] = value # Use raw value
                    log.debug(f"  Parsed GitHub var: Index={index}, Field='{field}'")
                    github_account_raw_keys_to_remove.add(key) # Mark raw key for removal
                else:
                    # Store other variables directly for Pydantic
                    cleaned_env_dict[key] = value

            # Remove the raw GITHUB_ACCOUNT_n_... keys to avoid confusing Pydantic
            if github_account_raw_keys_to_remove:
                log.debug(f"Removing {len(github_account_raw_keys_to_remove)} raw GitHub account keys before validation.")
                # No need to remove from cleaned_env_dict as they were never added there
                # for key_to_remove in github_account_raw_keys_to_remove:
                #     cleaned_env_dict.pop(key_to_remove, None) # Remove if present

            # --- Construct GitHub Account List ---
            log.debug("Constructing GitHub account list from parsed variables...")
            for index in sorted(temp_github_accounts.keys()):
                account_data = temp_github_accounts[index]

                # Add debug logging as per Step 1, Mod 1
                log.debug(f"Processing Account Index {index}:")
                log.debug(f"  Raw account data keys: {list(account_data.keys())}") # Log keys for clarity
                name_check_value = account_data.get('name')
                token_check_value = account_data.get('token')
                base_url_value = account_data.get('base_url') # Get base_url for logging

                log.debug(f"  Name value from env: '{name_check_value}' (Type: {type(name_check_value)})")
                log.debug(f"  Token value from env (first 5 chars): '{str(token_check_value)[:5] if token_check_value else None}' (Type: {type(token_check_value)}, IsSet: {token_check_value is not None})")
                log.debug(f"  Base URL value from env: '{base_url_value}' (Type: {type(base_url_value)})")
                log.debug(f"  Condition check: bool(name_check_value) -> {bool(name_check_value)}, bool(token_check_value) -> {bool(token_check_value)}")

                # Basic check for required fields (name and token must exist and be non-empty)
                if name_check_value and token_check_value:
                    github_accounts_data.append({
                        'name': name_check_value,
                        'token': token_check_value,
                        'base_url': base_url_value # Pass raw value or None
                    })
                    log.debug(f"  SUCCESS: Added GitHub account for validation: Name='{name_check_value}'")
                else:
                    log.warning(f"  SKIPPED: GitHub account at index {index} due to missing or empty 'NAME' or 'TOKEN'. Name_IsSet: {bool(name_check_value)}, Token_IsSet: {bool(token_check_value)}. Found keys: {list(account_data.keys())}")

            # Add debug logging as per Step 1, Mod 2
            log.debug(f"Final github_accounts_data list prepared for Pydantic: {len(github_accounts_data)} item(s)")
            for i, account_dict_item in enumerate(github_accounts_data):
                 _acc_token_val_l473 = account_dict_item.get('token') # account_dict_item is a dict here, token could be None
                 _acc_token_for_log_len_l473 = _acc_token_val_l473 if isinstance(_acc_token_val_l473, str) else ""
                 log.debug(f"  Account {i+1} data: name='{account_dict_item.get('name')}', token_length={len(_acc_token_for_log_len_l473)}, base_url='{account_dict_item.get('base_url')}'")

            # Add the constructed list to the dictionary Pydantic will validate
            # Use the CLASS FIELD NAME ('github_accounts'), not the alias, for assignment before validation
            # This list of dictionaries is passed to Pydantic's AppSettings.model_validate
            # where each dictionary will be validated against the GitHubAccountConfig model.
            cleaned_env_dict['github_accounts'] = github_accounts_data
            log.debug(f"Assigned github_accounts key to cleaned_env_dict. Type: {type(cleaned_env_dict['github_accounts'])}, Count: {len(cleaned_env_dict['github_accounts'])}")


            # Add assertion as per Step 1, Testing
            # Note: This might fail if no GitHub accounts are configured, which is valid.
            # Consider if this assertion should only run if GITHUB_DEFAULT_ACCOUNT_NAME is set.
            # For now, keeping it simple as per the report.
            if os.environ.get("GITHUB_DEFAULT_ACCOUNT_NAME"):
                 # Only assert if a default is expected to exist
                 assert len(github_accounts_data) > 0, "GITHUB_DEFAULT_ACCOUNT_NAME is set, but no GitHub accounts were successfully extracted from environment variables"

            # --- Pydantic Validation ---
            # Pydantic now loads and validates settings from the prepared dictionary
            log.info("Starting Pydantic validation with prepared dictionary...")
            log.debug(f"Keys in cleaned_env_dict for Pydantic: {list(cleaned_env_dict.keys())}")
            log.debug(f"MICROSOFT_APP_ID in cleaned_env_dict: {'MICROSOFT_APP_ID' in cleaned_env_dict}")
            log.debug(f"Value of MICROSOFT_APP_ID if present: {cleaned_env_dict.get('MICROSOFT_APP_ID')}")
            
            # CRITICAL DEBUG: Log github_accounts data before validation
            log.debug(f"CRITICAL DEBUG - github_accounts before validation: {cleaned_env_dict.get('github_accounts')}")
            log.debug(f"CRITICAL DEBUG - github_accounts type: {type(cleaned_env_dict.get('github_accounts'))}")
            log.debug(f"CRITICAL DEBUG - github_accounts count: {len(cleaned_env_dict.get('github_accounts', []))}")
            
            self.settings = AppSettings.model_validate(cleaned_env_dict)
            log.info("Pydantic settings loaded and validated successfully.")
            
            # CRITICAL DEBUG: Log github_accounts after validation  
            log.debug(f"CRITICAL DEBUG - github_accounts after validation: {self.settings.github_accounts}")
            log.debug(f"CRITICAL DEBUG - github_accounts count after validation: {len(self.settings.github_accounts)}")

            # Add assertion as per Step 1, Testing
            if os.environ.get("GITHUB_DEFAULT_ACCOUNT_NAME"):
                # Assert that after validation, accounts exist if a default is specified
                assert len(self.settings.github_accounts) > 0, "GITHUB_DEFAULT_ACCOUNT_NAME is set, but GitHub accounts list is empty after Pydantic validation"


            # Debug logs to check values loaded by Pydantic
            log.debug(f"Pydantic loaded settings:")
            log.debug(f"CRITICAL DEBUG - Debug logging check: github_accounts = {self.settings.github_accounts}")
            log.debug(f"CRITICAL DEBUG - Debug logging check: len(github_accounts) = {len(self.settings.github_accounts)}")
            log.debug(f"CRITICAL DEBUG - Debug logging check: bool(github_accounts) = {bool(self.settings.github_accounts)}")
            log.debug(f"CRITICAL DEBUG - Debug logging check: type(github_accounts) = {type(self.settings.github_accounts)}")
            if self.settings.github_accounts:
                 log.debug(f"  settings.github_accounts:")
                 for i, raw_account_config in enumerate(self.settings.github_accounts):
                     typed_account_config: GitHubAccountConfig = cast(GitHubAccountConfig, raw_account_config)
                     log.debug(f"    [{i}] Name: {typed_account_config.name}, Token: {'***' if typed_account_config.token else 'None'}, Base URL: {typed_account_config.base_url}")
                 log.debug(f"  settings.github_default_account_name: {self.settings.github_default_account_name}")
            else:
                 log.debug(f"  github_accounts is falsy: {self.settings.github_accounts}")

            # Now that validation is done, setup logging properly based on the validated setting - REMOVED
            # self._setup_logging() # Re-run with validated settings

            log.info("Configuration loaded and validated successfully (config.py).")
            log.info(f"App Environment: {self.settings.app_env}")
            log.info(f"Log Level: {self.settings.log_level}") # Should now reflect validated level
            log.info(f"Default Gemini Model: {self.settings.gemini_model}")
            log.info(f"Available Personas: {self.AVAILABLE_PERSONAS}")
            log.info(f"Default Persona: {self.DEFAULT_PERSONA}")
        except ValidationError as e:
            log.critical(f"CRITICAL: Configuration validation failed:\n{e}", exc_info=False)
            if "gemini_api_key" in str(e).lower():
                 log.critical("Ensure GEMINI_API_KEY is set correctly in your .env file.")
            # Exit if critical config is missing
            raise ValueError(f"Configuration errors: {e}") from e
        except Exception as e:
            log.critical(f"CRITICAL: An unexpected error occurred during configuration loading: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize configuration: {e}") from e

    def get_env_value(self, env_name: str) -> Optional[str]:
        """
        Retrieves environment variables preferentially from validated Pydantic settings.
        Falls back to os.environ for variables not explicitly in the model.
        Handles potential parsing of complex types back to string.
        """
        # Prioritize validated Pydantic settings
        if hasattr(self, 'settings'):
            # Find the field name corresponding to the alias (env_name)
            field_name = None
            for name, field_info in self.settings.model_fields.items():
                # Handle potential alias difference (e.g., GITHUB_TOKEN vs github_token field)
                # Check both alias and direct field name match (prefer alias)
                if field_info.alias == env_name:
                    field_name = name
                    break
                elif name == env_name.lower(): # Fallback for direct match if no alias found
                     field_name = name
                     # Don't break here, alias match is preferred

            if field_name and hasattr(self.settings, field_name):
                setting_value = getattr(self.settings, field_name)
                if setting_value is not None:
                    # Handle lists (like github_accounts) - maybe return count or specific value?
                    # For now, just indicate presence for simple checks (is_tool_configured)
                    if isinstance(setting_value, list):
                         log.debug(f"Found list setting '{field_name}' for ENV var '{env_name}' (Count: {len(setting_value)})")
                         # Return something truthy if non-empty, or None if empty?
                         # This function is often used for boolean checks (is_tool_configured)
                         return str(len(setting_value)) if setting_value else None # Indicate presence/count
                    # Convert complex types like HttpUrl to string
                    elif hasattr(setting_value, '__str__') and not isinstance(setting_value, str):
                         log.debug(f"Found setting '{field_name}' for ENV var '{env_name}', returning string representation.")
                         return str(setting_value)
                    else:
                         log.debug(f"Found setting '{field_name}' for ENV var '{env_name}'")
                         return setting_value # Return primitive types directly

        # Fallback to raw os.environ if not found in validated settings
        # (Useful for vars not modeled in AppSettings but needed elsewhere)
        direct_value = os.environ.get(env_name)
        if direct_value is not None: # Check for None explicitly, empty string is valid value
            log.debug(f"Found environment variable {env_name} directly in os.environ (not via settings model).")
            # Return the raw value - assume downstream handles cleaning if needed
            return direct_value

        log.warning(f"Environment variable {env_name} not found in Pydantic settings or os.environ.")
        return None
        
    def is_tool_configured(self, tool_key: str) -> bool:
        """
        Check if a tool has its required configuration available.
        Special handling for 'github'.
        """
        tool_key_lower = tool_key.lower()

        # Initialize cache if it doesn't exist
        if not hasattr(self, '_tool_validation_cache'):
            self._tool_validation_cache = {}
        if tool_key_lower in self._tool_validation_cache:
            return self._tool_validation_cache[tool_key_lower]

        # Initialize health status cache if it doesn't exist
        if not hasattr(self, '_tool_health_status'):
            self._tool_health_status = {}

        is_configured = False # Default to False

        # Check for health status override
        if tool_key_lower in self._tool_health_status:
            health_status = self._tool_health_status[tool_key_lower]
            if health_status == 'DOWN':
                log.warning(f"Tool '{tool_key}' is marked as DOWN by health check. Considering as not configured.")
                is_configured = False
                self._tool_validation_cache[tool_key_lower] = is_configured
                return is_configured

        # --- Special handling for GitHub ---
        if tool_key_lower == 'github':
            if self.settings.github_accounts:
                 log.info("Tool 'github' is configured: Found at least one account in settings.github_accounts.")
                 is_configured = True
            else:
                 log.warning("Tool 'github' is NOT configured: settings.github_accounts is empty.")
                 is_configured = False

        # --- Standard handling for other tools ---
        elif tool_key_lower in self.TOOL_CONFIG_REQUIREMENTS:
            required_vars = self.TOOL_CONFIG_REQUIREMENTS[tool_key_lower]
            log.debug(f"Validating config for tool '{tool_key}'. Required ENV vars: {required_vars}")

            all_found = True
            missing_vars = []
            for env_var_name in required_vars:
                val = self.get_env_value(env_var_name)
                if not val: # Checks for None or empty string
                    all_found = False
                    missing_vars.append(env_var_name)
                    log.warning(f"Tool '{tool_key}': Missing required variable: {env_var_name}")
                else:
                    log.debug(f"Tool '{tool_key}': Found required variable: {env_var_name}")

            if all_found:
                log.info(f"Tool '{tool_key}' is properly configured.")
                is_configured = True
            else:
                log.warning(f"Tool '{tool_key}' is NOT configured correctly. Missing: {missing_vars}")
                is_configured = False
        
        # --- Tool not in requirements ---
        else:
            log.warning(f"Tool '{tool_key}' has no defined configuration requirements in TOOL_CONFIG_REQUIREMENTS. Assuming NOT configured.")
            is_configured = False # Safer default if requirements aren't listed

        # Cache and return the result
        self._tool_validation_cache[tool_key_lower] = is_configured
        return is_configured

    def update_tool_health_status(self, tool_key: str, status: str) -> None:
        """
        Update the health status for a tool.
        This allows health check results to influence the is_tool_configured method.
        
        Args:
            tool_key: The tool key (e.g., 'github', 'greptile')
            status: The health status ('OK', 'DOWN', etc.)
        """
        if not hasattr(self, '_tool_health_status'):
            self._tool_health_status = {}
            
        tool_key_lower = tool_key.lower()
        self._tool_health_status[tool_key_lower] = status
        
        # Clear validation cache for this tool
        if hasattr(self, '_tool_validation_cache') and tool_key_lower in self._tool_validation_cache:
            del self._tool_validation_cache[tool_key_lower]
            
        log.info(f"Updated health status for tool '{tool_key}': {status}")
        
    def get_configuration_summary(self) -> Dict[str, bool]:
        """
        Returns a dictionary of critical tools and their configuration status.
        """
        summary = {}
        for tool_key in self.TOOL_CONFIG_REQUIREMENTS.keys():
            summary[tool_key] = self.is_tool_configured(tool_key)
        return summary

    @property
    def APP_ENV(self) -> Literal["development", "production"]:
        return self.settings.app_env

    @property
    def PORT(self) -> int:
        return self.settings.port

    @property
    def LOG_LEVEL(self) -> str:
        return self.settings.log_level

    @property
    def GEMINI_API_KEY(self) -> str:
        if not self.settings.gemini_api_key:
             raise ValueError("GEMINI_API_KEY is not set in the configuration.")
        return self.settings.gemini_api_key

    @property
    def GEMINI_MODEL(self) -> str:
        return self.settings.gemini_model

    @property
    def JIRA_API_URL(self) -> Optional[HttpUrl]:
        return self.settings.jira_api_url

    @property
    def JIRA_API_EMAIL(self) -> Optional[EmailStr]:
        return self.settings.jira_api_email

    @property
    def JIRA_API_TOKEN(self) -> Optional[str]:
        return self.settings.jira_api_token

    @property
    def JIRA_DEFAULT_PROJECT_KEY(self) -> str:
        return self.settings.jira_default_project_key
    
    @property
    def JIRA_DEFAULT_ISSUE_TYPE(self) -> str:
        return self.settings.jira_default_issue_type

    @property
    def GREPTILE_API_KEY(self) -> Optional[str]:
        return self.settings.greptile_api_key

    @property
    def GREPTILE_API_URL(self) -> HttpUrl:
        return self.settings.greptile_api_url

    @property
    def GREPTILE_DEFAULT_REPO(self) -> Optional[str]:
        return self.settings.greptile_default_repo

    @property
    def PERPLEXITY_API_KEY(self) -> Optional[str]:
        return self.settings.perplexity_api_key

    @property
    def PERPLEXITY_API_URL(self) -> HttpUrl:
        return self.settings.perplexity_api_url

    @property
    def PERPLEXITY_MODEL(self) -> str:
        return self.settings.perplexity_model

    @property
    def SYSTEM_PROMPT(self) -> str:
        return self.settings.system_prompt if self.settings.system_prompt != "DEFAULT_SYSTEM_PROMPT_PLACEHOLDER" else DEFAULT_SYSTEM_PROMPT

    @property
    def MAX_CONSECUTIVE_TOOL_CALLS(self) -> int:
        return self.settings.max_consecutive_tool_calls

    @property
    def DEFAULT_API_TIMEOUT_SECONDS(self) -> int:
        return self.settings.default_api_timeout_seconds

    @property
    def DEFAULT_API_MAX_RETRIES(self) -> int:
        return self.settings.default_api_max_retries

    @property
    def BREAK_ON_CRITICAL_TOOL_ERROR(self) -> bool:
        return self.settings.break_on_critical_tool_error

    @property
    def LLM_MAX_HISTORY_ITEMS(self) -> int:
        return self.settings.llm_max_history_items

    @property
    def TOOLS(self) -> Dict[str, Any]:
        """Fallback for tools configuration used in test/demo contexts."""
        return {} # Empty dict as a safe fallback

    @property
    def MOCK_MODE(self) -> bool:
        """Whether mock mode is enabled for API responses."""
        return self.settings.mock_mode

    @property
    def GENERAL_SYSTEM_PROMPT(self) -> str:
        """Returns the default system prompt for testing compatibility."""
        return self.DEFAULT_SYSTEM_PROMPT
        
    @GENERAL_SYSTEM_PROMPT.setter
    def GENERAL_SYSTEM_PROMPT(self, value: str) -> None:
        """Set the default system prompt. Used primarily for testing."""
        self.DEFAULT_SYSTEM_PROMPT = value

    @property
    def MAX_HISTORY_MESSAGES(self) -> int:
        """Alias for LLM_MAX_HISTORY_ITEMS, used for backward compatibility."""
        return self.settings.llm_max_history_items
        
    @MAX_HISTORY_MESSAGES.setter
    def MAX_HISTORY_MESSAGES(self, value: int) -> None:
        """Setter for MAX_HISTORY_MESSAGES to support testing."""
        self.settings.llm_max_history_items = value

    def get_system_prompt(self, persona_name: str = "Default") -> str:
        """
        Returns the appropriate system prompt for the given persona.
        
        Args:
            persona_name: The name of the requested persona (e.g., "Default", "Concise Communicator")
            
        Returns:
            str: The system prompt for the requested persona.
        """
        # If specific personas are defined, use those
        if persona_name and persona_name in self.AVAILABLE_PERSONAS:
            # Get persona-specific prompt if it exists, else use default
            persona_key = f"SYSTEM_PROMPT_{persona_name.upper().replace(' ', '_')}"
            if hasattr(self, persona_key):
                return getattr(self, persona_key)
        
        # Default to the standard system prompt
        return self.SYSTEM_PROMPT

    def get_github_config(self, name: Optional[str] = None) -> Optional[GitHubAccountConfig]:
        """
        Retrieves a specific GitHub account configuration by name, or the default one.

        Args:
            name: The name of the GitHub account config to retrieve.
                  If None, retrieves the default account specified by
                  GITHUB_DEFAULT_ACCOUNT_NAME, or the first account if no
                  default is set but accounts exist.

        Returns:
            The matching GitHubAccountConfig object, or None if not found.
        """
        if not self.settings.github_accounts:
            log.warning("get_github_config called, but no GitHub accounts are configured.")
            return None

        target_name = name or self.settings.github_default_account_name

        if target_name:
            for account in self.settings.github_accounts:
                if account.name == target_name:
                    log.debug(f"Found GitHub config for name: '{target_name}'")
                    return account
            log.warning(f"GitHub config requested for name '{target_name}', but not found.")
            # If a specific name was requested and not found, return None
            if name:
                 return None
            # If default was requested but not found, fall through to grabbing the first one

        # If no specific name requested AND default name wasn't found or wasn't set, return the first account
        if not target_name and self.settings.github_accounts:
             log.debug("No specific or default GitHub name specified/found, returning the first configured account.")
             return self.settings.github_accounts[0]

        # If we get here, a default name was specified but not found
        log.error(f"Default GitHub account '{self.settings.github_default_account_name}' not found in configured accounts.")
        return None # Or raise an error? Let's return None for now.

    @property
    def STATE_DB_PATH(self) -> str:
        return self.settings.state_db_path

# --- Initialize and Export Singleton Instance ---
# This ensures the configuration is loaded and validated once when the module is imported.

# Global singleton instance
_config_instance: Optional[Config] = None

def get_config() -> Config:
    """
    Returns the singleton Config instance, initializing it if necessary.
    This prevents duplicate initialization across imports.
    """
    global _config_instance
    if _config_instance is None:
        log.info("Initializing singleton Config instance...")
        _config_instance = Config()
        log.info("Singleton Config instance created.")
    return _config_instance

# For backward compatibility with direct imports
# CONFIG = get_config()