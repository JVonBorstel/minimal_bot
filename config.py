# --- FILE: config.py ---
import os
import logging
import logging.handlers
from typing import Dict, Any, Optional, List, Literal, Union, cast
import re
import threading

from dotenv import load_dotenv, find_dotenv
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    EmailStr,
    ValidationError,
    field_validator,
    model_validator,
    ConfigDict,
)

# Try to import BaseSettings, fall back to BaseModel if not available
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    # Fallback for older pydantic versions or missing pydantic-settings
    BaseSettings = BaseModel
    print("Warning: pydantic-settings not found. Environment variable loading may not work properly.")
    # Define a dummy SettingsConfigDict for compatibility if pydantic-settings is missing
    class SettingsConfigDict:
        pass 

log = logging.getLogger(__name__)

# --- Custom Logging Filter ---
# DuplicateFilter remains unchanged, so it's omitted for brevity here but should be kept in your actual file.
class DuplicateFilter(logging.Filter):
    def __init__(self, name=''):
        super().__init__(name)
        self.last_log = None
        self.last_log_count = 0
        self.max_count = 3
    def filter(self, record):
        current_log = record.getMessage()
        if current_log == self.last_log:
            self.last_log_count += 1
            if self.last_log_count <= self.max_count: return True
            if self.last_log_count % 50 == 0:
                record.msg = f"Previous message repeated {self.last_log_count} times: {record.msg}"
                return True
            return False
        else:
            if self.last_log and self.last_log_count > self.max_count:
                logger = logging.getLogger(record.name)
                logger.log(record.levelno, f"Previous message repeated {self.last_log_count-self.max_count} more times: {self.last_log}")
            self.last_log = current_log
            self.last_log_count = 1
            return True

# --- Constants ---
AVAILABLE_PERSONAS: List[str] = ["Default", "Concise Communicator", "Detailed Explainer", "Code Reviewer"]
DEFAULT_PERSONA: str = "Default"
DEFAULT_GEMINI_MODEL = "models/gemini-1.5-flash-latest" # Better free tier limits than pro

AVAILABLE_GEMINI_MODELS_REF = ["models/gemini-1.5-flash-latest", "models/gemini-1.5-pro-latest"] # Updated
AVAILABLE_PERPLEXITY_MODELS_REF = ["sonar", "sonar-pro", "sonar-reasoning", "sonar-reasoning-pro", "sonar-deep-research", "r1-1776"]

TOOL_CONFIG_REQUIREMENTS: Dict[str, List[str]] = {
    "jira": ["JIRA_API_URL", "JIRA_API_EMAIL", "JIRA_API_TOKEN"],
    "greptile": ["GREPTILE_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    # GitHub is checked by the presence of GITHUB_ACCOUNT_n_TOKEN and GITHUB_ACCOUNT_n_NAME
}

# --- NEW PROMPTS ---
# ROUTER_SYSTEM_PROMPT and STORY_BUILDER_SYSTEM_PROMPT remain unchanged, omitted for brevity here.
# Ensure they are present in your actual file.
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
# GitHubAccountConfig and AppSettings model definitions remain largely the same.
# Key changes will be in the DEFAULT_SYSTEM_PROMPT and potentially the defaults for AppSettings.
# For brevity, the full Pydantic models are not repeated here but ensure they are in your actual file.

class GitHubAccountConfig(BaseModel):
    name: str = Field(..., description="Unique identifier for this GitHub configuration (e.g., 'personal', 'work').")
    token: str = Field(..., description="GitHub Personal Access Token (PAT) or other token.")
    base_url: Optional[HttpUrl] = Field(None, description="Base URL for GitHub Enterprise instances. Leave None for github.com.")
    model_config = ConfigDict(extra='ignore')

# MODIFIED: Define the new default system prompt with more flexibility
DEFAULT_SYSTEM_PROMPT = """You are Aughie, an intelligent and adaptive ChatOps assistant for development teams. Your core strength is understanding user intent through natural language, not rigid patterns, and making intelligent decisions about how to respond and what actions to take.

**Your Intelligence & Decision-Making Role:**

1. **Intent Understanding**: You excel at understanding what users want from their natural language, regardless of exact phrasing. You don't rely on keywords or exact matches - you understand meaning, context, and subtext.

2. **Context Awareness**: You maintain awareness of:
   - Current conversation state and history
   - Active workflows and processes
   - User permissions and roles
   - Onboarding status and preferences
   - System capabilities and limitations

3. **Adaptive Responses**: You adjust your communication style and responses based on:
   - User preferences and communication style
   - Current context (onboarding, workflows, tasks)
   - Urgency and importance of requests
   - User expertise level and role

4. **Tool Usage Intelligence**: 
   **CRITICAL: When you have tools available that can help answer a user's question or request, YOU MUST USE THEM.**
   - If a user asks about current events, news, or anything requiring real-time information, USE the perplexity_web_search tool
   - If a user asks about code in repositories, USE the github or greptile tools
   - If a user asks about tickets or project management, USE the jira tools
   - NEVER say "I don't have access to real-time information" when you have perplexity tools available
   - NEVER tell users to search elsewhere when you have tools that can do the search for them
   - Analyze the request to understand the underlying goal
   - Determine which tools and approaches are most appropriate
   - Plan multi-step solutions when needed
   - Explain your reasoning and approach
   - Handle errors gracefully with alternative solutions

**Key Behavioral Guidelines:**

**Natural Language Processing:**
- Understand intent from meaning, not exact phrases
- Handle variations, typos, and colloquial language
- Ask clarifying questions when intent is genuinely unclear
- Never require users to use specific command syntax

**Onboarding & User Experience:**
- Recognize when users want to start, skip, postpone, or ask about onboarding
- Understand answers to questions regardless of format
- Adapt onboarding based on user responses and preferences
- Make the experience conversational, not robotic

**Workflow Management:**
- Understand when users want to continue, pause, cancel, or modify workflows
- Recognize when users are answering workflow questions vs. giving new commands
- Handle workflow interruptions gracefully
- Provide helpful context about current state

**Error Handling & Clarification:**
- When tool calls fail due to missing configuration, explain clearly what's needed
- Suggest alternatives when primary approaches aren't available
- Ask targeted questions to gather missing information
- Never assume critical details - always clarify

**Permission-Aware Responses:**
- Understand user roles and adjust capabilities accordingly
- Explain permission limitations helpfully, not defensively
- Suggest appropriate escalation paths when needed
- Maintain security without being obstructive

**Communication Style:**
- Be helpful, professional, and adaptive
- Match user energy and communication preferences
- Use emojis and formatting appropriately for the context
- Be concise when users prefer it, detailed when they need it

**Example Intent Recognition (instead of rigid matching):**

Instead of looking for exact phrases like "start onboarding", understand intent from:
- "Yeah, let's do this setup thing"
- "Sure, I'm ready to get started"
- "OK fine, what do you need to know?"

Instead of exact "skip" commands, understand postponement from:
- "Maybe later, I'm busy right now"
- "Not interested in setup at the moment"
- "Can we do this another time?"

Instead of rigid help commands, understand help requests from:
- "What can you do?"
- "I'm lost, what are my options?"
- "How does this work?"

**Your Goal**: Be an intelligent, adaptive assistant that understands users naturally and helps them accomplish their goals efficiently, regardless of how they express themselves. Use your language understanding capabilities to make conversations feel natural and intelligent, not scripted or robotic. ALWAYS use available tools to answer questions instead of saying you can't access information."""

class AppSettings(BaseSettings):
    app_env: Literal["development", "production"] = Field("development", alias="APP_ENV")
    port: int = Field(3978, alias="PORT", gt=0, lt=65536)
    app_base_url: Optional[HttpUrl] = Field(None, alias="APP_BASE_URL")
    teams_bot_endpoint: Optional[HttpUrl] = Field(None, alias="TEAMS_BOT_ENDPOINT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field("INFO", alias="LOG_LEVEL")
    mock_mode: bool = Field(False, alias="MOCK_MODE")

    # API Endpoints
    bot_api_messages_endpoint: str = Field("/api/messages", alias="BOT_API_MESSAGES_ENDPOINT")
    bot_api_healthcheck_endpoint: str = Field("/api/healthz", alias="BOT_API_HEALTHCHECK_ENDPOINT")

    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    gemini_model: str = Field(DEFAULT_GEMINI_MODEL, alias="GEMINI_MODEL")
    llm_max_history_items: int = Field(50, alias="LLM_MAX_HISTORY_ITEMS", gt=0)

    # MODIFIED: Default system prompt placeholder, will be replaced by the new DEFAULT_SYSTEM_PROMPT constant.
    system_prompt: str = Field(
        DEFAULT_SYSTEM_PROMPT,
        alias="SYSTEM_PROMPT"
    )
    max_consecutive_tool_calls: int = Field(5, alias="MAX_CONSECUTIVE_TOOL_CALLS", gt=0)
    default_api_timeout_seconds: int = Field(90, alias="DEFAULT_API_TIMEOUT_SECONDS", gt=0)
    default_api_max_retries: int = Field(2, alias="DEFAULT_API_MAX_RETRIES", ge=0)
    break_on_critical_tool_error: bool = Field(True, alias="BREAK_ON_CRITICAL_TOOL_ERROR")
    
    MicrosoftAppId: Optional[str] = Field(None, alias="MICROSOFT_APP_ID")
    MicrosoftAppPassword: Optional[str] = Field(None, alias="MICROSOFT_APP_PASSWORD")
    MicrosoftAppType: Optional[str] = Field(None, alias="MICROSOFT_APP_TYPE")

    github_accounts: List[GitHubAccountConfig] = Field(default_factory=list)
    github_default_account_name: Optional[str] = Field(None, alias="GITHUB_DEFAULT_ACCOUNT_NAME")
    
    jira_api_url: Optional[HttpUrl] = Field(None, alias="JIRA_API_URL")
    jira_api_email: Optional[EmailStr] = Field(None, alias="JIRA_API_EMAIL")
    jira_api_token: Optional[str] = Field(None, alias="JIRA_API_TOKEN")
    jira_default_project_key: str = Field("PROJ", alias="JIRA_DEFAULT_PROJECT_KEY")
    jira_default_issue_type: str = Field("Story", alias="JIRA_DEFAULT_ISSUE_TYPE")

    greptile_api_key: Optional[str] = Field(None, alias="GREPTILE_API_KEY")
    greptile_api_url: HttpUrl = Field("https://api.greptile.com/v2", alias="GREPTILE_API_URL") # type: ignore[assignment]
    greptile_default_repo: Optional[str] = Field(None, alias="GREPTILE_DEFAULT_REPO")

    perplexity_api_key: Optional[str] = Field(None, alias="PERPLEXITY_API_KEY")
    perplexity_api_url: HttpUrl = Field("https://api.perplexity.ai", alias="PERPLEXITY_API_URL") # type: ignore[assignment]
    perplexity_model: str = Field("sonar-pro", alias="PERPLEXITY_MODEL")

    # Granular Debug Logging Flags
    log_detailed_appstate: bool = Field(False, alias="LOG_DETAILED_APPSTATE")
    log_llm_interaction: bool = Field(False, alias="LOG_LLM_INTERACTION") # For full prompts/responses
    log_tool_io: bool = Field(False, alias="LOG_TOOL_IO") # For full tool inputs/outputs

    # Tool System configurations (previously constants or hardcoded in Config properties)
    max_function_declarations_for_llm: int = Field(12, alias="MAX_FUNCTION_DECLARATIONS_FOR_LLM", description="Max number of tool function declarations to send to LLM.")
    
    tool_selector_enabled: bool = Field(True, alias="TOOL_SELECTOR_ENABLED")
    tool_selector_similarity_threshold: float = Field(0.1, alias="TOOL_SELECTOR_SIMILARITY_THRESHOLD")
    tool_selector_max_tools: int = Field(15, alias="TOOL_SELECTOR_MAX_TOOLS")
    # tool_selector_always_include_tools: List[str] = Field(default_factory=list, alias="TOOL_SELECTOR_ALWAYS_INCLUDE") # Example if needed
    tool_selector_debug_logging: bool = Field(True, alias="TOOL_SELECTOR_DEBUG_LOGGING")
    tool_selector_default_fallback: bool = Field(True, alias="TOOL_SELECTOR_DEFAULT_FALLBACK")
    tool_selector_embedding_model: str = Field("all-MiniLM-L6-v2", alias="TOOL_SELECTOR_EMBEDDING_MODEL")
    # Cache path might still be constructed, but could be based on a configurable base data directory if needed
    # For now, constructed path is in Config.TOOL_SELECTOR property, which is fine.

    # Validators remain the same, omitted for brevity
    @field_validator('jira_api_token', 'jira_api_email', 'jira_api_url', mode='before')
    def _ensure_jira_fields_not_empty_if_provided(cls, v: Optional[Any], info: Any) -> Optional[Any]:
        if v is not None and isinstance(v, str) and not v.strip(): return None
        return v

    @model_validator(mode='after')
    def _check_jira_config_complete(self) -> 'AppSettings':
        jira_fields_map = {'jira_api_url': self.jira_api_url, 'jira_api_email': self.jira_api_email, 'jira_api_token': self.jira_api_token}
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

    @model_validator(mode='after')
    def check_github_default_account(self) -> 'AppSettings':
        """
        Validates GitHub account configuration.
        More lenient during development to allow testing with expired tokens.
        """
        if self.github_default_account_name and self.github_accounts:
            account_names = {acc.name for acc in self.github_accounts}
            if self.github_default_account_name not in account_names:
                raise ValueError(f"Invalid GITHUB_DEFAULT_ACCOUNT_NAME ('{self.github_default_account_name}'). Does not match: {list(account_names)}")
        elif self.github_default_account_name and not self.github_accounts:
            # Check if we're in a development/testing environment
            is_development = self.app_env == "development" or os.getenv("TESTING") == "true"
            
            if is_development:
                # In development, warn but don't fail - allows testing with expired tokens
                log.warning(f"GITHUB_DEFAULT_ACCOUNT_NAME is set to '{self.github_default_account_name}' but no valid GitHub accounts are configured. This is acceptable in development mode.")
                log.warning("For production deployment, ensure GITHUB_ACCOUNT_1_TOKEN and GITHUB_ACCOUNT_1_NAME are properly set.")
                # Clear the default account name to prevent runtime issues
                self.github_default_account_name = None
            else:
                # In production, this is a real error
                raise ValueError("GITHUB_DEFAULT_ACCOUNT_NAME is set, but no GitHub accounts are configured. Please verify GITHUB_ACCOUNT_1_TOKEN and GITHUB_ACCOUNT_1_NAME environment variables.")
        return self

    state_db_path: str = Field("db/state.sqlite", alias="STATE_DB_PATH")
    security_rbac_enabled: bool = Field(False, alias="SECURITY_RBAC_ENABLED")
    admin_user_id: Optional[str] = Field(None, alias="ADMIN_USER_ID")
    admin_user_name: Optional[str] = Field(None, alias="ADMIN_USER_NAME") 
    admin_user_email: Optional[EmailStr] = Field(None, alias="ADMIN_USER_EMAIL")

    memory_type: Literal["sqlite", "redis"] = Field("sqlite", alias="MEMORY_TYPE")
    redis_url: Optional[str] = Field(None, alias="REDIS_URL")
    redis_host: Optional[str] = Field("localhost", alias="REDIS_HOST")
    redis_port: Optional[int] = Field(6379, alias="REDIS_PORT")
    redis_password: Optional[str] = Field(None, alias="REDIS_PASSWORD")
    redis_db: int = Field(default=0)
    redis_ssl_enabled: bool = Field(default=False)
    redis_prefix: str = Field(default="botstate:")

    # Validators for app_base_url, teams_bot_endpoint, redis_config_if_needed remain unchanged
    # Omitted for brevity.
    @field_validator('app_base_url', mode='before')
    @classmethod
    def derive_app_base_url(cls, v: Optional[str], info: Any) -> str:
        port_field_name = 'port'; port_field_alias = cls.model_fields[port_field_name].alias or port_field_name
        port_val_from_data = info.data.get(port_field_alias)
        if port_val_from_data is None: port_val_from_data = info.data.get(port_field_name)
        actual_port: int
        if port_val_from_data is not None:
            try:
                actual_port = int(port_val_from_data)
                if not (0 < actual_port < 65536): actual_port = 3978
            except (ValueError, TypeError): actual_port = 3978
        else: actual_port = cls.model_fields[port_field_name].default if cls.model_fields[port_field_name].default is not None else 3978
        if v: 
            try:
                parsed_url = HttpUrl(v); current_port_in_url_str = parsed_url.port; expected_port_str = str(actual_port)
                if current_port_in_url_str is None:
                    if not ((parsed_url.scheme == "http" and expected_port_str == "80") or (parsed_url.scheme == "https" and expected_port_str == "443")):
                        return f"{parsed_url.scheme}://{parsed_url.host}:{actual_port}{parsed_url.path or ''}"
                elif current_port_in_url_str != expected_port_str:
                    return f"{parsed_url.scheme}://{parsed_url.host}:{actual_port}{parsed_url.path or ''}"
                return v 
            except Exception: pass
        return f"http://127.0.0.1:{actual_port}"

    @model_validator(mode='after')
    def _ensure_app_base_url_default(self) -> 'AppSettings':
        if self.app_base_url is None:
            actual_port = self.port; default_url_str = f"http://127.0.0.1:{actual_port}"
            try: self.app_base_url = HttpUrl(default_url_str)
            except ValidationError as e: raise ValueError(f"Internal error: Constructed default APP_BASE_URL '{default_url_str}' is invalid.") from e
        return self

    @model_validator(mode='after')
    def derive_teams_bot_endpoint(self) -> 'AppSettings':
        if self.app_base_url:
            base_url_str = str(self.app_base_url); path_segment = "/api/messages"
            if base_url_str.endswith('/') and path_segment.startswith('/'): derived_endpoint = base_url_str + path_segment[1:]
            elif not base_url_str.endswith('/') and not path_segment.startswith('/'): derived_endpoint = base_url_str + "/" + path_segment
            else: derived_endpoint = base_url_str + path_segment
            env_teams_endpoint = os.environ.get("TEAMS_BOT_ENDPOINT")
            if env_teams_endpoint:
                normalized_env = env_teams_endpoint.rstrip('/'); normalized_derived = derived_endpoint.rstrip('/')
                if normalized_env != normalized_derived: log.warning(f"TEAMS_BOT_ENDPOINT from env ('{env_teams_endpoint}') != derived ('{derived_endpoint}'). Using derived.")
            self.teams_bot_endpoint = HttpUrl(derived_endpoint)
        elif os.environ.get("TEAMS_BOT_ENDPOINT"):
            log.warning("APP_BASE_URL not set, but TEAMS_BOT_ENDPOINT is. Using TEAMS_BOT_ENDPOINT directly.")
            self.teams_bot_endpoint = HttpUrl(os.environ.get("TEAMS_BOT_ENDPOINT"))
        else:
            log.error("Could not derive TEAMS_BOT_ENDPOINT as APP_BASE_URL is not available.")
            self.teams_bot_endpoint = None
        return self
    
    @model_validator(mode='after')
    def check_redis_config_if_needed(self) -> 'AppSettings':
        if self.memory_type == "redis":
            if self.redis_url:
                if not str(self.redis_url).strip(): raise ValueError("REDIS_URL is set but empty.")
                log.info(f"Using REDIS_URL for Redis connection: {self.redis_url}")
            elif not self.redis_host: raise ValueError("REDIS_HOST must be set if REDIS_URL is not provided and memory_type is 'redis'.")
        return self

    # Updated model_config for Pydantic V2 BaseSettings
    model_config = SettingsConfigDict(
        env_file=find_dotenv(), # Automatically find and load .env
        env_file_encoding='utf-8',
        extra='ignore',
        # env_prefix='', # No prefix needed if variables are directly named
        case_sensitive=False,
        # validate_default=True, # validate_by_default in Pydantic V2 SettingsConfigDict
        validate_by_default=True,
        use_enum_values=True
    )

    def get_env_value(self, env_name: str) -> Optional[str]:
        # This method is now largely superseded by direct attribute access on the AppSettings instance.
        # Pydantic BaseSettings automatically handles loading from env vars based on field names/aliases.
        # This method could be kept for specific introspection cases or gradually deprecated.
        log.debug(f"AppSettings.get_env_value called for: {env_name}. Consider direct attribute access.")
        
        field_name_to_check = None
        # Check Pydantic field aliases first, then direct attribute names
        for name, field_info in self.model_fields.items():
            if field_info.alias == env_name:
                field_name_to_check = name
                break
        if not field_name_to_check:
            for name in self.model_fields.keys():
                if name.lower() == env_name.lower(): # Case-insensitive check for env_name mapping
                    field_name_to_check = name
                    break
        
        if field_name_to_check and hasattr(self, field_name_to_check):
            setting_value = getattr(self, field_name_to_check)
            if setting_value is not None:
                if isinstance(setting_value, list):
                    return str(len(setting_value)) if setting_value else None 
                elif hasattr(setting_value, '__str__') and isinstance(setting_value, (str, int, float, bool, HttpUrl, EmailStr)):
                     return str(setting_value)
                elif isinstance(setting_value, (str, int, float, bool)):
                    return str(setting_value)
                return "OBJECT_PRESENT"
        
        # Fallback to os.environ.get if not found as a Pydantic field 
        # (should be rare if all settings are modeled).
        direct_value = os.environ.get(env_name)
        if direct_value is not None:
            # log.debug(f"Env var {env_name} found directly in os.environ (value: '{direct_value[:20]}...'), not as a Pydantic field.")
            return direct_value
        return None

    def is_tool_configured(self, tool_name: str, categories: Optional[List[str]] = None) -> bool:
        tool_name_lower = tool_name.lower()
        # Cache should be on the instance of AppSettings
        if not hasattr(self, '_tool_validation_cache_local'): # Use a different cache name to avoid conflict if Config had one
            self._tool_validation_cache_local = {}
        
        cache_key = tool_name_lower 
        if cache_key in self._tool_validation_cache_local:
            return self._tool_validation_cache_local[cache_key]

        # Health status integration (placeholder, assuming health status might be stored elsewhere or passed in)
        # For now, this check is removed as _tool_health_status isn't part of AppSettings directly.
        # if hasattr(self, '_tool_health_status') and self._tool_health_status.get(tool_name_lower) == 'DOWN':
        #     log.warning(f"Tool '{tool_name}' marked DOWN. Considering NOT configured.")
        #     self._tool_validation_cache_local[cache_key] = False
        #     return False

        is_configured = False 
        processed_categories = [cat.lower() for cat in categories] if categories else []

        # 1. GitHub specific check
        if "github" in processed_categories or "github" in tool_name_lower:
            # Access self.github_accounts directly (it's a field in AppSettings)
            is_configured = bool(self.github_accounts and any(acc.token for acc in self.github_accounts))
            log.debug(f"Tool '{tool_name}' (categories: {processed_categories}) GitHub check: configured = {is_configured}, accounts = {len(self.github_accounts)}")
            self._tool_validation_cache_local[cache_key] = is_configured
            return is_configured

        # 2. Check services defined in TOOL_CONFIG_REQUIREMENTS
        service_to_check = None
        for service_key in TOOL_CONFIG_REQUIREMENTS.keys(): 
            if service_key in processed_categories:
                service_to_check = service_key
                break
            if not service_to_check and service_key in tool_name_lower: 
                service_to_check = service_key
        
        if service_to_check:
            required_vars = TOOL_CONFIG_REQUIREMENTS[service_to_check]
            missing_vars = []
            all_found = True
            for var_key_from_global_list in required_vars:
                # Convert VAR_KEY (e.g., JIRA_API_URL) to AppSettings field name (e.g., jira_api_url)
                pydantic_attr_name = var_key_from_global_list.lower()
                if hasattr(self, pydantic_attr_name):
                    if not getattr(self, pydantic_attr_name): # Check if the attribute on self (AppSettings instance) has a value
                        all_found = False
                        missing_vars.append(var_key_from_global_list)
                else: 
                    all_found = False
                    missing_vars.append(f"{var_key_from_global_list} (attribute '{pydantic_attr_name}' not found in AppSettings)")

            if all_found:
                is_configured = True
            else:
                log.warning(f"Tool '{tool_name}' (service: {service_to_check}, categories: {processed_categories}) NOT configured. Missing required Pydantic settings on AppSettings: {missing_vars}")
            
            log.debug(f"Tool '{tool_name}' (service: {service_to_check}) check on AppSettings: configured = {is_configured}")
            self._tool_validation_cache_local[cache_key] = is_configured
            return is_configured

        is_configured = True 
        log.debug(f"Tool '{tool_name}' (categories: {processed_categories}) did not match specific service config checks in AppSettings. Assuming configured. Status: {is_configured}")
        
        self._tool_validation_cache_local[cache_key] = is_configured
        return is_configured


class Config:
    """
    Main configuration class that wraps AppSettings and provides a unified interface
    for accessing all application configuration values.
    """
    
    def __init__(self, env_file: Optional[str] = None): # env_file argument is largely for legacy or specific override cases now
        """
        Initialize Config by loading environment variables and validating settings.
        AppSettings (as BaseSettings) handles .env loading automatically.
        """
        # AppSettings (as BaseSettings with env_file=find_dotenv()) handles .env loading.
        # Explicit load_dotenv here is mostly redundant but kept for _load_github_accounts 
        # which runs before AppSettings is fully initialized if it needs env vars not yet seen by AppSettings.
        # If _load_github_accounts exclusively uses os.getenv, and AppSettings loads .env first,
        # then this explicit load_dotenv might not be strictly needed here.
        # For this pass, we make it more targeted.
        
        # If an explicit env_file is provided for Config, load it with override. 
        # This allows specific test .env files, for example.
        if env_file and os.path.exists(env_file):
            if load_dotenv(env_file, override=True):
                log.info(f"Config explicitly loaded .env file: {env_file}")
        # Otherwise, AppSettings will handle find_dotenv().
        # _load_github_accounts will use os.getenv, which will see vars from .env if AppSettings loaded it,
        # or from the environment if no .env was used by AppSettings.

        github_accounts = self._load_github_accounts()
        
        try:
            self.settings = AppSettings(github_accounts=github_accounts)
            log.info("✅ AppSettings initialized within Config object.")
        except ValidationError as e:
            log.error(f"❌ AppSettings validation failed within Config: {e}")
            raise
        except Exception as e:
            log.error(f"❌ Failed to initialize AppSettings within Config: {e}")
            raise
        
        self._log_config_summary()
    
    def _load_github_accounts(self) -> List[GitHubAccountConfig]:
        """Load GitHub account configurations from environment variables."""
        accounts = []
        account_index = 1
        
        while True:
            # Look for GITHUB_ACCOUNT_n_TOKEN and GITHUB_ACCOUNT_n_NAME
            token_env = f"GITHUB_ACCOUNT_{account_index}_TOKEN"
            name_env = f"GITHUB_ACCOUNT_{account_index}_NAME"
            base_url_env = f"GITHUB_ACCOUNT_{account_index}_BASE_URL"
            
            token = os.getenv(token_env)
            name = os.getenv(name_env)
            
            if not token or not name:
                # No more accounts found
                break
            
            try:
                account_config = GitHubAccountConfig(
                    name=name,
                    token=token,
                    base_url=os.getenv(base_url_env) if os.getenv(base_url_env) else None
                )
                accounts.append(account_config)
                log.debug(f"Loaded GitHub account config: {name}")
            except ValidationError as e:
                log.warning(f"Invalid GitHub account config for {name}: {e}")
            
            account_index += 1
        
        if accounts:
            log.info(f"Loaded {len(accounts)} GitHub account configurations")
        else:
            log.info("No GitHub account configurations found")
        
        return accounts
    
    def _log_config_summary(self):
        """Log a summary of the loaded configuration."""
        log.info("=== Configuration Summary ===")
        log.info(f"Environment: {self.settings.app_env}")
        log.info(f"Port: {self.settings.port}")
        log.info(f"Log Level: {self.settings.log_level}")
        # Access via self.settings for previously direct attributes
        log.info(f"Database: {self.settings.state_db_path}") 
        log.info(f"LLM Model: {self.settings.gemini_model}")
        log.info(f"Memory Type: {self.settings.memory_type}")
        
        # Security
        log.info(f"RBAC Enabled: {self.settings.security_rbac_enabled}")
        if self.settings.admin_user_id:
            log.info(f"Admin User: {self.settings.admin_user_id}")
        
        # Services
        configured_services = []
        if self.settings.github_accounts:
            configured_services.append(f"GitHub ({len(self.settings.github_accounts)} accounts)")
        if self.settings.jira_api_url and self.settings.jira_api_token:
            configured_services.append("Jira")
        if self.settings.greptile_api_key:
            configured_services.append("Greptile")
        if self.settings.perplexity_api_key:
            configured_services.append("Perplexity")
        
        if configured_services:
            log.info(f"Configured Services: {', '.join(configured_services)}")
        else:
            log.info("No external services configured")
        
        log.info("=============================")
    
    @property
    def STATE_DB_PATH(self) -> str:
        return self.settings.state_db_path

    @property
    def GEMINI_API_KEY(self) -> str:
        return self.settings.gemini_api_key

    @property
    def GEMINI_MODEL(self) -> str:
        return self.settings.gemini_model

    @property
    def DEFAULT_SYSTEM_PROMPT(self) -> str:
        return self.settings.system_prompt

    @property
    def DEFAULT_API_TIMEOUT_SECONDS(self) -> int:
        return self.settings.default_api_timeout_seconds

    @property
    def DEFAULT_API_MAX_RETRIES(self) -> int:
        return self.settings.default_api_max_retries

    @property
    def LLM_MAX_HISTORY_ITEMS(self) -> int:
        return self.settings.llm_max_history_items

    @property
    def MAX_CONSECUTIVE_TOOL_CALLS(self) -> int:
        return self.settings.max_consecutive_tool_calls

    @property
    def MOCK_MODE(self) -> bool:
        return self.settings.mock_mode

    @property
    def PERPLEXITY_API_URL(self) -> Optional[HttpUrl]: # Corrected type from AppSettings
        return self.settings.perplexity_api_url

    @property
    def PERPLEXITY_MODEL(self) -> str:
        return self.settings.perplexity_model
    
    @property
    def PERPLEXITY_API_KEY(self) -> Optional[str]: # Added for completeness
        return self.settings.perplexity_api_key

    @property
    def JIRA_API_EMAIL(self) -> Optional[EmailStr]: # Corrected type from AppSettings
        return self.settings.jira_api_email

    @property
    def JIRA_API_URL(self) -> Optional[HttpUrl]: # Added for completeness
        return self.settings.jira_api_url

    @property
    def JIRA_API_TOKEN(self) -> Optional[str]: # Added for completeness
        return self.settings.jira_api_token

    @property
    def AVAILABLE_PERPLEXITY_MODELS_REF(self) -> List[str]:
        return AVAILABLE_PERPLEXITY_MODELS_REF # This is a global constant

    @property
    def MICROSOFT_APP_ID(self) -> Optional[str]:
        return self.settings.MicrosoftAppId

    @property
    def MICROSOFT_APP_PASSWORD(self) -> Optional[str]:
        return self.settings.MicrosoftAppPassword

    @property
    def MICROSOFT_APP_TYPE(self) -> Optional[str]:
        return self.settings.MicrosoftAppType

    @property
    def ADMIN_USER_ID(self) -> Optional[str]:
        return self.settings.admin_user_id

    @property
    def ADMIN_USER_NAME(self) -> Optional[str]:
        return self.settings.admin_user_name

    @property
    def ADMIN_USER_EMAIL(self) -> Optional[EmailStr]:
        return self.settings.admin_user_email

    @property
    def SECURITY_RBAC_ENABLED(self) -> bool:
        return self.settings.security_rbac_enabled

    @property
    def AVAILABLE_PERSONAS(self) -> List[str]:
        return AVAILABLE_PERSONAS # This is a global constant

    @property
    def DEFAULT_PERSONA(self) -> str:
        return DEFAULT_PERSONA # This is a global constant
    
    @property
    def MAX_FUNCTION_DECLARATIONS(self) -> int:
        return self.settings.max_function_declarations_for_llm # Now from AppSettings

    @property
    def SCHEMA_OPTIMIZATION(self) -> Dict[str, Any]:
        return { # Remains hardcoded for now, complex to make fully configurable via env
            "max_tool_schema_properties": 15,
            "max_tool_description_length": 200,
            "max_tool_enum_values": 10,
            "max_nested_object_properties": 8,
            "max_array_item_properties": 6,
            "flatten_nested_objects": False
        }

    @property
    def TOOL_SELECTOR(self) -> Dict[str, Any]:
        # Construct this dict using values from self.settings where appropriate
        cache_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "tool_embeddings.json"
        )
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        return {
            "enabled": self.settings.tool_selector_enabled,
            "similarity_threshold": self.settings.tool_selector_similarity_threshold,
            "max_tools": self.settings.tool_selector_max_tools,
            "always_include_tools": [], # self.settings.tool_selector_always_include_tools if added
            "debug_logging": self.settings.tool_selector_debug_logging,
            "default_fallback": self.settings.tool_selector_default_fallback,
            "cache_path": cache_path, # Constructed path
            "auto_save_interval_seconds": 300, # Could be AppSettings field
            "rebuild_cache_on_startup": False, # Could be AppSettings field
            "embedding_model": self.settings.tool_selector_embedding_model
        }

    @property
    def PERSONA_SYSTEM_PROMPTS(self) -> Dict[str, str]:
        return {
            "Default": self.settings.system_prompt,
            "Concise Communicator": self.settings.system_prompt + "\n\nPlease be concise and direct in your responses.",
            "Detailed Explainer": self.settings.system_prompt + "\n\nPlease provide detailed explanations and context.",
            "Code Reviewer": self.settings.system_prompt + "\n\nFocus on code quality, best practices, and detailed technical analysis."
        }
    
    # --- Methods that operate on or use settings --- 
    def is_tool_configured(self, tool_name: str, categories: Optional[List[str]] = None) -> bool:
        """
        Check if a tool is properly configured.
        Delegates to the AppSettings (self.settings) method.
        """
        if self.settings:
            return self.settings.is_tool_configured(tool_name, categories)
        log.warning("Config.settings not initialized. Cannot check tool configuration.")
        return False
    
    def get_env_value(self, env_name: str) -> Optional[str]:
        """
        Get an environment variable value.
        Delegates to the AppSettings (self.settings) method.
        This is more for introspection; direct access via config.settings.attribute_name is preferred.
        """
        if self.settings:
            return self.settings.get_env_value(env_name)
        log.warning("Config.settings not initialized. Cannot get env value.")
        # Fallback to os.environ as a last resort if settings isn't even there
        return os.environ.get(env_name)
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the configuration.
        Uses self.settings for necessary values.
        """
        try:
            issues = []
            
            # Check critical settings from self.settings
            if not self.settings.gemini_api_key:
                issues.append("GEMINI_API_KEY not configured")
            
            # Check database path accessibility using self.settings.state_db_path
            try:
                db_dir = os.path.dirname(os.path.abspath(self.settings.state_db_path))
                if not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                # Try to create/access the database file
                test_db_path = os.path.join(db_dir, "config_health_test.tmp")
                with open(test_db_path, 'w') as f:
                    f.write("test")
                os.remove(test_db_path)
            except Exception as e:
                issues.append(f"Database path not accessible ({self.settings.state_db_path}): {e}")
            
            if issues:
                return {
                    "status": "WARN",
                    "message": f"Configuration issues: {'; '.join(issues)}",
                    "component": "Config"
                }
            else:
                return {
                    "status": "OK",
                    "message": "Configuration healthy",
                    "component": "Config"
                }
        except Exception as e:
            log.error(f"Error during Config health check: {e}", exc_info=True) # Log the exception
            return {
                "status": "ERROR",
                "message": f"Configuration health check failed: {e}",
                "component": "Config"
            }
    
    def get_system_prompt(self, persona_name: str = "Default") -> str:
        """
        Get the system prompt for the specified persona.
        Uses self.settings.system_prompt and self.PERSONA_SYSTEM_PROMPTS (which itself uses self.settings.system_prompt).
        """
        default_prompt_from_settings = self.settings.system_prompt

        if not persona_name or not isinstance(persona_name, str):
            log.warning(f"Invalid persona name provided: {persona_name}. Using default system prompt from settings.")
            return default_prompt_from_settings
        
        # PERSONA_SYSTEM_PROMPTS is now a property that builds itself using self.settings.system_prompt
        persona_prompts = self.PERSONA_SYSTEM_PROMPTS 
        prompt = persona_prompts.get(persona_name)
        if prompt:
            log.debug(f"Using system prompt for persona: {persona_name}")
            return prompt
        
        log.warning(f"No system prompt found for persona: {persona_name}. Using default from settings.")
        return default_prompt_from_settings

# Global configuration instance
_config_instance: Optional[Config] = None
_config_lock = threading.Lock()


def get_config(env_file: Optional[str] = None, force_reload: bool = False) -> Config:
    """
    Get the global configuration instance (singleton pattern).
    
    Args:
        env_file: Optional path to a .env file to load (only used on first initialization)
        force_reload: Force reloading the configuration (useful for testing)
        
    Returns:
        The global Config instance
    """
    global _config_instance
    
    with _config_lock:
        if _config_instance is None or force_reload:
            try:
                _config_instance = Config(env_file=env_file)
                log.info("✅ Global configuration instance initialized")
            except Exception as e:
                log.error(f"❌ Failed to initialize global configuration: {e}")
                raise
        
        return _config_instance


def reload_config(env_file: Optional[str] = None) -> Config:
    """
    Force reload the global configuration instance.
    Useful when environment variables have changed.
    
    Args:
        env_file: Optional path to a .env file to load
        
    Returns:
        The newly reloaded Config instance
    """
    return get_config(env_file=env_file, force_reload=True)

