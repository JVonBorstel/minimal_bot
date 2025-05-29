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
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions or missing pydantic-settings
    BaseSettings = BaseModel
    print("Warning: pydantic-settings not found. Environment variable loading may not work properly.")

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

4. **Tool Usage Intelligence**: When users need help with tasks:
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

**Your Goal**: Be an intelligent, adaptive assistant that understands users naturally and helps them accomplish their goals efficiently, regardless of how they express themselves. Use your language understanding capabilities to make conversations feel natural and intelligent, not scripted or robotic."""

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
        if self.github_default_account_name and self.github_accounts:
            account_names = {acc.name for acc in self.github_accounts}
            if self.github_default_account_name not in account_names:
                raise ValueError(f"Invalid GITHUB_DEFAULT_ACCOUNT_NAME ('{self.github_default_account_name}'). Does not match: {list(account_names)}")
        elif self.github_default_account_name and not self.github_accounts:
             raise ValueError("GITHUB_DEFAULT_ACCOUNT_NAME is set, but no GitHub accounts are configured.")
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

    model_config = ConfigDict(
        env_file_encoding='utf-8',
        extra='ignore',
        # Enable environment variable loading for BaseSettings
        env_prefix='',
        case_sensitive=False,
        validate_default=True,
        use_enum_values=True
    )

    def get_env_value(self, env_name: str) -> Optional[str]:
        # Ensure settings are loaded if accessed directly before full __init__ (less common)
        if not hasattr(self, 'settings') and hasattr(self, '_config_instance') and self._config_instance is not None and hasattr(self._config_instance, 'settings'):
             self.settings = self._config_instance.settings
        
        if hasattr(self, 'settings'):
            field_name = None
            # Check Pydantic field aliases first
            for name, field_info in self.settings.model_fields.items():
                if hasattr(field_info, 'alias') and field_info.alias == env_name:
                    field_name = name
                    break
            
            # If not found by alias, check direct attribute name (case-insensitive for env var style)
            if not field_name:
                for name in self.settings.model_fields.keys():
                    if name.lower() == env_name.lower():
                        field_name = name
                        break
            
            if field_name and hasattr(self.settings, field_name):
                setting_value = getattr(self.settings, field_name)
                if setting_value is not None:
                    # For lists (like github_accounts), consider it "set" if the list is not empty
                    if isinstance(setting_value, list):
                        return str(len(setting_value)) if setting_value else None 
                    # For Pydantic models or other complex types, __str__ might be too verbose or not indicative of "set"
                    # For HttpUrl etc., str(setting_value) is fine.
                    elif hasattr(setting_value, '__str__') and isinstance(setting_value, (str, int, float, bool, HttpUrl, EmailStr)):
                         return str(setting_value)
                    elif isinstance(setting_value, (str, int, float, bool)): # Basic types already covered but good fallback
                        return str(setting_value)
                    # If it's a complex object not covered above, and we just need to check existence,
                    # its presence means it's "set". Returning a placeholder.
                    return "OBJECT_PRESENT" 
        
        # Fallback to direct os.environ.get if not found in Pydantic settings
        # This is less common if all configs are routed via AppSettings
        direct_value = os.environ.get(env_name)
        if direct_value is not None:
            log.debug(f"Env var {env_name} found directly in os.environ (value: '{direct_value[:20]}...').")
            return direct_value
        
        # log.debug(f"Env var or Pydantic setting {env_name} not found or has no value.")
        return None

    def is_tool_configured(self, tool_name: str, categories: Optional[List[str]] = None) -> bool:
        tool_name_lower = tool_name.lower()
        if not hasattr(self, '_tool_validation_cache'):
            self._tool_validation_cache = {}
        
        cache_key = tool_name_lower # Simple cache key for now
        if cache_key in self._tool_validation_cache:
            return self._tool_validation_cache[cache_key]

        if not hasattr(self, '_tool_health_status'):
            self._tool_health_status = {}

        if tool_name_lower in self._tool_health_status and self._tool_health_status[tool_name_lower] == 'DOWN':
            log.warning(f"Tool '{tool_name}' marked DOWN by health check. Considering NOT configured.")
            self._tool_validation_cache[cache_key] = False
            return False

        is_configured = False # Default to False
        processed_categories = [cat.lower() for cat in categories] if categories else []

        # 1. GitHub specific check (due to complex structure of github_accounts)
        if "github" in processed_categories or "github" in tool_name_lower:
            # Check if github_accounts is properly loaded and has valid tokens
            github_accounts = getattr(self, 'github_accounts', [])
            is_configured = bool(github_accounts and any(acc.token for acc in github_accounts))
            log.debug(f"Tool '{tool_name}' (categories: {processed_categories}) GitHub check: configured = {is_configured}, accounts = {len(github_accounts)}")
            self._tool_validation_cache[cache_key] = is_configured
            return is_configured

        # 2. Check services defined in TOOL_CONFIG_REQUIREMENTS based on categories or tool name
        service_to_check = None
        for service_key in TOOL_CONFIG_REQUIREMENTS.keys(): # Access global directly
            if service_key in processed_categories:
                service_to_check = service_key
                break
            if not service_to_check and service_key in tool_name_lower: # Fallback if category not specific
                service_to_check = service_key
        
        if service_to_check:
            required_vars = TOOL_CONFIG_REQUIREMENTS[service_to_check] # Access global directly
            missing_vars = []
            all_found = True
            for var_key in required_vars:
                pydantic_attr_name = var_key.lower() # Simple conversion
                # Assuming self.settings is the loaded AppSettings instance
                if hasattr(self, pydantic_attr_name): # Check directly on self (AppSettings instance)
                    if not getattr(self, pydantic_attr_name):
                        all_found = False
                        missing_vars.append(var_key)
                else: 
                    all_found = False
                    missing_vars.append(f"{var_key} (attribute not found in AppSettings)")

            if all_found:
                is_configured = True
            else:
                log.warning(f"Tool '{tool_name}' (service: {service_to_check}, categories: {processed_categories}) NOT configured. Missing Pydantic settings: {missing_vars}")
            
            log.debug(f"Tool '{tool_name}' (service: {service_to_check}) check: configured = {is_configured}")
            self._tool_validation_cache[cache_key] = is_configured
            return is_configured

        # 3. If no specific service category requiring config matched, assume it's a core/dependency-free tool.
        is_configured = True 
        log.debug(f"Tool '{tool_name}' (categories: {processed_categories}) did not match specific service config checks. Assuming configured (e.g., core tool). Status: {is_configured}")
        
        self._tool_validation_cache[cache_key] = is_configured
        return is_configured


class Config:
    """
    Main configuration class that wraps AppSettings and provides a unified interface
    for accessing all application configuration values.
    """
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize Config by loading environment variables and validating settings.
        
        Args:
            env_file: Optional path to a .env file to load
        """
        # Load environment variables from .env file if provided or found
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to find a .env file in common locations
            env_path = find_dotenv()
            if env_path:
                load_dotenv(env_path)
                log.info(f"Loaded environment variables from: {env_path}")
            else:
                log.info("No .env file found, using system environment variables only")
        
        # Load GitHub account configurations from environment variables
        github_accounts = self._load_github_accounts()
        
        # Initialize the Pydantic settings model
        try:
            # Create a temporary dict to pass github_accounts to the model
            # while still allowing BaseSettings to read from environment
            extra_data = {"github_accounts": github_accounts}
            self.settings = AppSettings(**extra_data)
            log.info("✅ Configuration loaded successfully")
        except ValidationError as e:
            log.error(f"❌ Configuration validation failed: {e}")
            raise
        except Exception as e:
            log.error(f"❌ Failed to initialize configuration: {e}")
            raise
        
        # Set up computed properties
        self._setup_computed_properties()
        
        # Log configuration summary
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
    
    def _setup_computed_properties(self):
        """Set up computed properties and convenience attributes."""
        # Database path property
        self.STATE_DB_PATH = self.settings.state_db_path
        
        # Core API settings
        self.GEMINI_API_KEY = self.settings.gemini_api_key
        self.GEMINI_MODEL = self.settings.gemini_model
        self.DEFAULT_SYSTEM_PROMPT = self.settings.system_prompt
        self.DEFAULT_API_TIMEOUT_SECONDS = self.settings.default_api_timeout_seconds
        self.DEFAULT_API_MAX_RETRIES = self.settings.default_api_max_retries
        
        # LLM settings
        self.LLM_MAX_HISTORY_ITEMS = self.settings.llm_max_history_items
        self.MAX_CONSECUTIVE_TOOL_CALLS = self.settings.max_consecutive_tool_calls
        
        # Backward compatibility alias for MAX_HISTORY_MESSAGES
        self.MAX_HISTORY_MESSAGES = self.settings.llm_max_history_items
        
        # Application settings
        self.MOCK_MODE = self.settings.mock_mode
        
        # Service API settings
        self.PERPLEXITY_API_URL = self.settings.perplexity_api_url
        self.PERPLEXITY_MODEL = self.settings.perplexity_model
        self.JIRA_API_EMAIL = self.settings.jira_api_email
        
        # Available models reference
        self.AVAILABLE_PERPLEXITY_MODELS_REF = AVAILABLE_PERPLEXITY_MODELS_REF
        
        # Tool executor instance (will be set later during initialization)
        self.tool_executor_instance = None
        
        # Bot Framework settings
        self.MICROSOFT_APP_ID = self.settings.MicrosoftAppId
        self.MICROSOFT_APP_PASSWORD = self.settings.MicrosoftAppPassword
        self.MICROSOFT_APP_TYPE = self.settings.MicrosoftAppType
        
        # Admin settings
        self.ADMIN_USER_ID = self.settings.admin_user_id
        self.ADMIN_USER_NAME = self.settings.admin_user_name
        self.ADMIN_USER_EMAIL = self.settings.admin_user_email
        
        # Security settings
        self.SECURITY_RBAC_ENABLED = self.settings.security_rbac_enabled
        
        # Persona settings (compatibility with existing code)
        self.AVAILABLE_PERSONAS = AVAILABLE_PERSONAS
        self.DEFAULT_PERSONA = DEFAULT_PERSONA
        
        # Tool configuration limits and optimizations
        self.MAX_FUNCTION_DECLARATIONS = 12  # Reasonable default for LLM tool limits
        self.SCHEMA_OPTIMIZATION = {
            "max_tool_schema_properties": 15,
            "max_tool_description_length": 200,
            "max_tool_enum_values": 10,
            "max_nested_object_properties": 8,
            "max_array_item_properties": 6,
            "flatten_nested_objects": False
        }
        
        # Tool Selector configuration
        self.TOOL_SELECTOR = {
            "enabled": True,
            "similarity_threshold": 0.1,  # Lower threshold for better tool selection
            "max_tools": 15,
            "always_include_tools": [],
            "debug_logging": True,  # Enable debug logging to help diagnose issues
            "default_fallback": True,
            "cache_path": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "tool_embeddings.json"
            ),
            "auto_save_interval_seconds": 300,
            "rebuild_cache_on_startup": False,
            "embedding_model": "all-MiniLM-L6-v2"
        }
        
        # Persona system prompts (if needed in the future)
        self.PERSONA_SYSTEM_PROMPTS = {
            "Default": self.DEFAULT_SYSTEM_PROMPT,
            "Concise Communicator": self.DEFAULT_SYSTEM_PROMPT + "\n\nPlease be concise and direct in your responses.",
            "Detailed Explainer": self.DEFAULT_SYSTEM_PROMPT + "\n\nPlease provide detailed explanations and context.",
            "Code Reviewer": self.DEFAULT_SYSTEM_PROMPT + "\n\nFocus on code quality, best practices, and detailed technical analysis."
        }
    
    def _log_config_summary(self):
        """Log a summary of the loaded configuration."""
        log.info("=== Configuration Summary ===")
        log.info(f"Environment: {self.settings.app_env}")
        log.info(f"Port: {self.settings.port}")
        log.info(f"Log Level: {self.settings.log_level}")
        log.info(f"Database: {self.STATE_DB_PATH}")
        log.info(f"LLM Model: {self.GEMINI_MODEL}")
        log.info(f"Memory Type: {self.settings.memory_type}")
        
        # Security
        log.info(f"RBAC Enabled: {self.SECURITY_RBAC_ENABLED}")
        if self.ADMIN_USER_ID:
            log.info(f"Admin User: {self.ADMIN_USER_ID}")
        
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
    
    def is_tool_configured(self, tool_name: str, categories: Optional[List[str]] = None) -> bool:
        """
        Check if a tool is properly configured.
        Delegates to the AppSettings method.
        """
        return self.settings.is_tool_configured(tool_name, categories)
    
    def get_env_value(self, env_name: str) -> Optional[str]:
        """
        Get an environment variable value.
        Delegates to the AppSettings method.
        """
        return self.settings.get_env_value(env_name)
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the configuration.
        """
        try:
            issues = []
            
            # Check critical settings
            if not self.GEMINI_API_KEY:
                issues.append("GEMINI_API_KEY not configured")
            
            # Check database path accessibility
            try:
                db_dir = os.path.dirname(os.path.abspath(self.STATE_DB_PATH))
                if not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                # Try to create/access the database file
                test_db_path = os.path.join(db_dir, "config_health_test.tmp")
                with open(test_db_path, 'w') as f:
                    f.write("test")
                os.remove(test_db_path)
            except Exception as e:
                issues.append(f"Database path not accessible: {e}")
            
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
            return {
                "status": "ERROR",
                "message": f"Configuration health check failed: {e}",
                "component": "Config"
            }
    
    def get_system_prompt(self, persona_name: str = "Default") -> str:
        """
        Get the system prompt for the specified persona.
        
        Args:
            persona_name: The name of the persona to get the system prompt for.
            
        Returns:
            The system prompt for the specified persona.
        """
        if not persona_name or not isinstance(persona_name, str):
            log.warning(f"Invalid persona name provided: {persona_name}. Using default system prompt.")
            return self.DEFAULT_SYSTEM_PROMPT
        
        if hasattr(self, 'PERSONA_SYSTEM_PROMPTS') and isinstance(self.PERSONA_SYSTEM_PROMPTS, dict):
            prompt = self.PERSONA_SYSTEM_PROMPTS.get(persona_name)
            if prompt:
                log.debug(f"Using system prompt for persona: {persona_name}")
                return prompt
        
        log.warning(f"No system prompt found for persona: {persona_name}. Using default.")
        return self.DEFAULT_SYSTEM_PROMPT
    
    @property
    def MAX_HISTORY_MESSAGES(self) -> int:
        """Alias for LLM_MAX_HISTORY_ITEMS, used for backward compatibility."""
        return self.settings.llm_max_history_items
    
    @MAX_HISTORY_MESSAGES.setter
    def MAX_HISTORY_MESSAGES(self, value: int) -> None:
        """Setter for MAX_HISTORY_MESSAGES to support testing."""
        self.settings.llm_max_history_items = value


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

