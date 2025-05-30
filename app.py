# -- app.py --
"""
Main entry point for the chatbot application (Bot Framework Version).
"""
import os
import sys
import logging
from typing import Dict, Any, cast # Added cast for type hinting
import re

from llm_interface import LLMInterface # Ensure LLMInterface is imported
from tools.tool_executor import ToolExecutor # Keep this, it's used in the shim
from core_logic import start_streaming_response, HistoryResetRequiredError # Keep this
from core_logic.intent_classifier import IntentClassifier # Added import for IntentClassifier
from workflows.workflow_manager import WorkflowManager # Added import for WorkflowManager

# Imports for Bot Framework and Web Server
from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapterSettings,
    TurnContext, # Added for type hinting
)
from botbuilder.schema import Activity, ActivityTypes # Added ActivityTypes for clarity

# Early import for dotenv functionality
from dotenv import load_dotenv, find_dotenv

APP_VERSION = "1.0.0"

# ===== Standard Logging Setup =====
# COLORS and SECTIONS definitions are now primarily for SimpleHumanFormatter in utils.logging_config
# We might still keep COLORS here if other parts of app.py use them directly for prints.
COLORS = {
    "reset": "\033[0m", "bold": "\033[1m", "header": "\033[1;36m", "success": "\033[1;32m",
    "warning": "\033[1;33m", "error": "\033[1;31m", "info": "\033[1;34m", "debug": "\033[0;37m"
}
# SECTIONS dictionary might be removed from here if fully managed by SimpleHumanFormatter
# or kept for reference if app.py still directly uses its keys for logic.
# For now, let's comment it out from app.py as SimpleHumanFormatter will have its own version.
# SECTIONS = {
#     "ENV": {"start": "=== LOADING ENVIRONMENT VARIABLES ===", "title": f"{COLORS['header']}[KEY] Environment Setup{COLORS['reset']}", "end": "=== ENVIRONMENT LOADED SUCCESSFULLY ==="},
#     "CONFIG": {"start": "=== CONFIG VALIDATION RESULTS ===", "title": f"{COLORS['header']}[GEAR] Configuration{COLORS['reset']}", "end": "=== CONFIG VALIDATED ==="},
#     "STARTUP": {"start": "Bot server starting on", "title": f"{COLORS['header']}[ROCKET] Bot Server Startup{COLORS['reset']}", "end": "=== Bot server running ==="}
# }

# The root_logger setup here will be overridden by IntelligentLoggingSystem,
# but we need a basic logger for VERY early messages if any, or for utilities
# that might log before IntelligentLoggingSystem is fully up.
# However, IntelligentLoggingSystem now clears root handlers, so this initial
# setup becomes less critical for console output formatting once utils.logging_config is imported.

# Keep a basic logger instance for app.py itself, but its console output
# will be managed by the handlers set up in utils.logging_config.py
logger = logging.getLogger(__name__)

# Quieten noisy libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING) # httpx is often used by new google libs

def load_environment():
    logger.info("=== LOADING ENVIRONMENT VARIABLES ===")
    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        os.path.join(os.getcwd(), '.env'),
        find_dotenv(usecwd=True)
    ]
    env_loaded = False; env_path_found = "None"
    for dotenv_path in possible_paths:
        if dotenv_path and os.path.exists(dotenv_path):
            env_path_found = dotenv_path
            # logger.info(f"Found .env file at: {env_path_found}") # Quieter
            load_dotenv(dotenv_path, override=True); env_loaded = True; break
    
    env_summary = {}
    env_warnings = []

    if env_loaded:
        logger.info(f"Environment: Loaded .env from {env_path_found}")
        critical_vars = {
            'JIRA_API_URL': True, 'JIRA_API_EMAIL': True, 'JIRA_API_TOKEN': False, # Token value not logged
            'GREPTILE_API_KEY': False, 'PERPLEXITY_API_KEY': False, 'GEMINI_API_KEY': False,
            'MICROSOFT_APP_ID': True, 'MICROSOFT_APP_PASSWORD': False
        }
        
        loaded_vars_summary = []
        for var, log_value in critical_vars.items():
            val = os.environ.get(var)
            if val:
                if log_value:
                    loaded_vars_summary.append(f"{var}: {val[:4]}***")
                else:
                    loaded_vars_summary.append(f"{var}: Present")
            else:
                env_warnings.append(f"{var}: NOT FOUND")
                logger.warning(f"  Environment Variable Missing: {var}") # Keep individual warnings for missing criticals
        
        if loaded_vars_summary:
            env_summary["Loaded Critical Vars"] = ", ".join(loaded_vars_summary)
    else: 
        logger.warning("Environment: No .env file found. Using system environment variables only.")
        env_warnings.append("No .env file loaded")

    # Consolidated summary log
    if env_summary:
        logger.info("Environment Status", extra={"summary_data": env_summary})
    elif not env_loaded and not env_warnings: # No .env, no criticals checked or all were somehow found in sys env without .env (unlikely for all)
        logger.info("Environment: Initialized using system variables (no .env found, critical var status not detailed here).")

    # Explicitly log the end of environment setup for the formatter to catch
    logger.info("=== ENVIRONMENT LOADED SUCCESSFULLY ===") 
    return env_loaded

load_environment()

try:
    from config import get_config, Config # Config class for type hinting
    from bot_core.adapter_with_error_handler import AdapterWithErrorHandler
    from bot_core.my_bot import MyBot # This is where your core bot logic resides
    from bot_core.intelligent_conversation_orchestrator import IntelligentConversationOrchestrator
    from bot_core.redis_storage import RedisStorage # If you are using Redis
    from health_checks import run_health_checks
except ImportError as e:
    print(f"FATAL: Failed to import core modules: {e}. Dependencies installed? Paths correct?", file=sys.stderr)
    logger.critical(f"Failed to import core modules: {e}. Ensure dependencies are installed and paths are correct.", exc_info=True)
    sys.exit(1)

APP_SETTINGS: Config
try:
    APP_SETTINGS = get_config()
    if hasattr(APP_SETTINGS, 'LOG_LEVEL'):
        # Update root logger level based on validated config
        # This assumes APP_SETTINGS.LOG_LEVEL is a valid logging level string (e.g., "DEBUG")
        try:
            numeric_level = getattr(logging, APP_SETTINGS.LOG_LEVEL.upper(), None)
            if isinstance(numeric_level, int):
                root_logger.setLevel(numeric_level)
                logger.info(f"Root logger level set to {APP_SETTINGS.LOG_LEVEL} from configuration.")
            else:
                logger.warning(f"Invalid LOG_LEVEL '{APP_SETTINGS.LOG_LEVEL}' in config. Using previous level.")
        except Exception as log_level_e:
             logger.error(f"Error setting log level from config: {log_level_e}. Using previous level.")


    logger.info("Configuration loaded successfully (APP_SETTINGS).")
    logger.info("=== CONFIG VALIDATION RESULTS ===")
    tools_to_check = ['github', 'jira', 'greptile', 'perplexity']
    for tool in tools_to_check:
        configured = APP_SETTINGS.is_tool_configured(tool) # Assumes Config has this method
        logger.info(f"Tool '{tool}' properly configured: {configured}")
    logger.info("=== CONFIG VALIDATED ===")
except (ValueError, RuntimeError) as config_e: # More specific Pydantic/config errors
    print(f"FATAL: Configuration error: {config_e}", file=sys.stderr)
    logger.critical(f"Configuration error: {config_e}", exc_info=True)
    sys.exit(1)
except Exception as e: # Catch-all for other init errors
    print(f"FATAL: An unexpected error occurred during initial config: {e}", file=sys.stderr)
    logger.critical(f"An unexpected error occurred during initial config: {e}", exc_info=True)
    sys.exit(1)

BOT_FRAMEWORK_SETTINGS = BotFrameworkAdapterSettings(
    app_id=APP_SETTINGS.settings.MicrosoftAppId or "", # Use validated Pydantic attribute via .settings
    app_password=APP_SETTINGS.settings.MicrosoftAppPassword or "" # Use validated Pydantic attribute via .settings
)
ADAPTER = AdapterWithErrorHandler(BOT_FRAMEWORK_SETTINGS, config=APP_SETTINGS)

BOT: MyBot
ORCHESTRATOR: IntelligentConversationOrchestrator
LLM_INTERFACE_INSTANCE: LLMInterface # Added type hint
INTENT_CLASSIFIER_INSTANCE: IntentClassifier # Added type hint
WORKFLOW_MANAGER_INSTANCE: WorkflowManager # Added type hint
TOOL_EXECUTOR_INSTANCE: ToolExecutor # Added type hint

try:
    # CRITICAL: The MyBot class likely holds ConversationState, UserState,
    # and the logic to build the history for the LLM.
    # Ensure MyBot's constructor correctly initializes storage (e.g., RedisStorage if configured)
    # and any state accessors (e.g., for conversation history).
    
    # Instantiate ToolExecutor - Initialize only once
    TOOL_EXECUTOR_INSTANCE = ToolExecutor(config=APP_SETTINGS)
    logger.info("ToolExecutor initialized successfully.")
    
    # Instantiate LLMInterface - Initialize only once (required by both MyBot and IntentClassifier)
    LLM_INTERFACE_INSTANCE = LLMInterface(config=APP_SETTINGS) 
    logger.info("LLMInterface initialized successfully.")
    
    # Pass the shared instances to MyBot to prevent double initialization
    BOT = MyBot(APP_SETTINGS, tool_executor=TOOL_EXECUTOR_INSTANCE, llm_interface=LLM_INTERFACE_INSTANCE)
    logger.info("MyBot initialized successfully.")

    # Create an AppState instance for WorkflowManager and Orchestrator
    from state_models import AppState
    SHARED_APP_STATE = AppState()
    logger.info("Shared AppState initialized successfully.")

    # Instantiate IntentClassifier
    INTENT_CLASSIFIER_INSTANCE = IntentClassifier(llm_interface=LLM_INTERFACE_INSTANCE)
    logger.info("IntentClassifier initialized successfully.")

    # Instantiate WorkflowManager
    WORKFLOW_MANAGER_INSTANCE = WorkflowManager(
        app_state=SHARED_APP_STATE,  # Use the shared app state
        llm_interface=LLM_INTERFACE_INSTANCE, 
        config=APP_SETTINGS
    )
    logger.info("WorkflowManager initialized successfully.")

    # Instantiate the Orchestrator - pass the already instantiated components
    # to prevent redundant initialization
    ORCHESTRATOR = IntelligentConversationOrchestrator(
        app_state=SHARED_APP_STATE,  
        config=APP_SETTINGS,  
        llm_interface=LLM_INTERFACE_INSTANCE, 
        intent_classifier=INTENT_CLASSIFIER_INSTANCE, 
        workflow_manager=WORKFLOW_MANAGER_INSTANCE, 
        tool_executor=TOOL_EXECUTOR_INSTANCE, 
        conversation_state=BOT.conversation_state, 
        user_state=BOT.user_state                 
    )
    logger.info("IntelligentConversationOrchestrator initialized successfully.")

except Exception as e:
    logger.critical(f"Failed to initialize MyBot or Orchestrator: {e}", exc_info=True)
    sys.exit(1)

try:
    from user_auth.utils import ensure_admin_user_exists
    if ensure_admin_user_exists(): logger.info("Admin user setup completed successfully.")
    else: logger.warning("Admin user setup failed, but continuing with startup.")
except Exception as e:
    logger.error(f"Error during admin user setup: {e}", exc_info=True)
    logger.warning("Continuing with startup despite admin user setup error.")

async def on_bot_startup(app: web.Application):
    """Called when the bot server has started successfully"""
    logger.info("=== BOT SERVER RUNNING ===")  # Matches the end trigger in formatter

async def on_bot_shutdown(app: web.Application):
    logger.info("Bot application shutting down. Cleaning up resources...")
    # BOT should have been initialized.
    # The `storage` attribute on BOT is assumed to be set by MyBot's constructor.
    if hasattr(BOT, 'storage') and BOT.storage: # Check if BOT and BOT.storage exist
        if isinstance(BOT.storage, RedisStorage): # Check if it's RedisStorage specifically
            try:
                logger.info("Closing Redis bot storage connection...")
                await BOT.storage.close() # Assuming RedisStorage has an async close
                logger.info("Redis bot storage connection closed.")
            except Exception as e:
                logger.error(f"Error closing Redis bot storage: {e}", exc_info=True)
        elif hasattr(BOT.storage, 'aclose'): # For other async storage types
            try:
                logger.info("Closing other type of bot storage connection (aclose)...")
                await BOT.storage.aclose()
                logger.info("Other bot storage connection closed.")
            except Exception as e:
                logger.error(f"Error closing other bot storage (aclose): {e}", exc_info=True)
        else:
            logger.info("Bot storage does not have a recognized close/aclose method or is not RedisStorage.")
    else:
        logger.info("No bot storage found on BOT object or BOT.storage is None. Skipping storage cleanup.")

async def messages(req: web.BaseRequest) -> web.Response:
    if "application/json" not in req.headers.get("Content-Type", ""):
        logger.warning("Request received with non-JSON content type.")
        return web.Response(status=415)

    try:
        body = await req.json()
    except Exception as json_e:
        logger.error(f"Failed to parse request body as JSON: {json_e}", exc_info=True)
        return web.Response(status=400, text="Invalid JSON body") # Bad Request

    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    # Enhanced logging for incoming activity
    activity_type = activity.type
    user_id = activity.from_property.id if activity.from_property else "N/A"
    conversation_id = activity.conversation.id if activity.conversation else "N/A"
    
    logger.info(
        f"Received activity: Type='{activity_type}', From='{user_id}', ConvID='{conversation_id}'"
    )
    if activity.type == ActivityTypes.message and activity.text:
        logger.debug(f"  Message Text: '{activity.text[:100]}{'...' if len(activity.text) > 100 else ''}'") # Log snippet of message
        
        # Enhanced monitoring: Check for potential character splitting patterns in incoming messages
        if len(activity.text) > 50 and ' ' not in activity.text:
            logger.warning(f"Potential character splitting detected in incoming message from {user_id}: '{activity.text[:50]}...'")
        
        # Enhanced monitoring: Check for text integrity issues
        from bot_core.message_handler import MessageProcessor
        processor = MessageProcessor()
        if not processor.validate_text_integrity(activity.text):
            logger.warning(f"Text integrity validation failed for incoming message from {user_id}")

    try:
        # IMPORTANT: We're only using ORCHESTRATOR.process_activity as the handler
        # The BOT instance is initialized for storage/state management but should not be 
        # handling activities directly to prevent duplicate message handling
        response = await ADAPTER.process_activity(activity, auth_header, ORCHESTRATOR.process_activity)
        if response:
            logger.debug(f"Sending response with status: {response.status}")
            return web.json_response(response.body, status=response.status)
        
        logger.debug("No explicit response body to send (activity processed by ORCHESTRATOR.process_activity), responding with 201 Accepted.")
        return web.Response(status=201)
    except Exception as exception:
        logger.error(f"Error processing activity in messages handler: {exception}", exc_info=True)
        
        # Enhanced error handling: Check if this is related to character splitting or validation
        error_msg = str(exception).lower()
        if any(indicator in error_msg for indicator in ['character', 'validation', 'input should be', 'splitting']):
            logger.error(f"Possible character splitting or validation error detected: {exception}")
            
        # AdapterWithErrorHandler should handle sending error messages to the user.
        # This ensures a 500 is returned if something goes wrong at this top level.
        # The user-facing message is ideally sent by AdapterWithErrorHandler or MyBot's error handling.
        return web.Response(status=500, text=f"Internal Server Error: {str(exception)}")


async def healthz(req: web.BaseRequest) -> web.Response:
    logger.info("Health check endpoint (/healthz) requested.")
    try:
        # BOT.llm_interface and BOT.app_config are assumed to be attributes of MyBot instance
        if not hasattr(BOT, 'llm_interface') or not BOT.llm_interface:
            logger.error("BOT object is missing 'llm_interface' for health check.")
            return web.json_response({"status": "ERROR", "message": "Bot's LLM interface not configured."}, status=503)
        if not hasattr(BOT, 'app_config') or not BOT.app_config: # app_config is likely APP_SETTINGS passed to MyBot
            logger.error("BOT object is missing 'app_config' (application settings) for health check.")
            return web.json_response({"status": "ERROR", "message": "Bot's application config not available."}, status=503)

        # Type casting for clarity if MyBot attributes are generically typed
        llm_interface_instance = cast(LLMInterface, BOT.llm_interface)
        config_instance = cast(Config, BOT.app_config) # Assuming MyBot stores the Config instance as app_config

        health_results = run_health_checks(llm_interface_instance, config_instance)
        overall_status = "OK"; http_status_code = 200; critical_down = False

        for component, result in health_results.items():
            component_status = result.get("status", "UNKNOWN")
            if component_status not in ["OK", "NOT CONFIGURED", "DEGRADED_OPERATIONAL"]:
                if component_status in ["ERROR", "DOWN"] and component == "LLM API": # Example critical component
                    critical_down = True; overall_status = "ERROR"; break
                overall_status = "DEGRADED"
        
        if critical_down: http_status_code = 503
        # else if overall_status == "DEGRADED": http_status_code = 200 # Or 503 if degraded is severe

        logger.info(f"Health check completed. Overall status: {overall_status}")
        return web.json_response(
            {"overall_status": overall_status, "components": health_results, "version": APP_VERSION},
            status=http_status_code
        )
    except Exception as e:
        logger.error(f"Error during health check execution: {e}", exc_info=True)
        return web.json_response({"overall_status": "ERROR", "message": f"Health check failed: {str(e)}"}, status=500)

SERVER_APP = web.Application()
SERVER_APP.router.add_post(APP_SETTINGS.settings.bot_api_messages_endpoint or "/api/messages", messages) # Use validated config via .settings
SERVER_APP.router.add_get(APP_SETTINGS.settings.bot_api_healthcheck_endpoint or "/healthz", healthz) # Use validated config via .settings
SERVER_APP.on_startup.append(on_bot_startup)
SERVER_APP.on_cleanup.append(on_bot_shutdown)

if __name__ == "__main__":
    port_to_use = 3978 # Default Bot Framework port
    try:
        # Use PORT from APP_SETTINGS (validated Pydantic model)
        if APP_SETTINGS.settings.port and isinstance(APP_SETTINGS.settings.port, int):
            port_to_use = APP_SETTINGS.settings.port
            logger.info(f"Using port {port_to_use} from configuration.")
        else:
            logger.warning(f"APP_SETTINGS.port not found or invalid ('{APP_SETTINGS.settings.port}'). Using default port {port_to_use}.")
        
        logger.info(f"Bot server starting on http://0.0.0.0:{port_to_use}") # Matches SECTIONS["STARTUP"]["start"]
        
        # Start the server
        web.run_app(SERVER_APP, host="0.0.0.0", port=port_to_use) # Changed from localhost to 0.0.0.0
        
    except Exception as error:
        logger.critical(f"Failed to start bot server: {error}", exc_info=True)
        sys.exit(1)

# Shim for e2e tests (remains largely unchanged, ensure it uses the BOT instance if needed)
# This function is a shim to allow e2e tests to run.
# It attempts to replicate the previous behavior of process_user_interaction.
async def process_user_interaction(
    user_query: Dict[str, Any],
    app_state: Any, # Should be AppState, but using Any for broader compatibility
    llm_interface: LLMInterface, # This would be BOT.llm_interface in a real scenario
    tool_executor: ToolExecutor, # This would be BOT.tool_executor
    config: Config # This would be BOT.app_config
) -> Any:
    logger.info("Shim process_user_interaction called with query: %s", user_query.get('content'))

    if not hasattr(app_state, 'add_message') or not callable(app_state.add_message):
        logger.error("Shim: app_state is missing 'add_message' method.")
        return app_state # Indicate failure or return modified state

    app_state.add_message(role="user", content=user_query.get("content", ""))
    if hasattr(app_state, 'reset_turn_state') and callable(app_state.reset_turn_state):
        app_state.reset_turn_state()

    try:
        # Ensure that start_streaming_response correctly uses app_state to derive history
        # and passes it to the llm_interface.
        stream = start_streaming_response(
            app_state=app_state, # This app_state needs to contain the history
            llm=llm_interface,   # Which in turn is passed to llm.generate_content_stream
            tool_executor=tool_executor,
            config=config
        )
        async for event in stream:
            if event.get("type") == "completed":
                if hasattr(app_state, 'last_interaction_status'):
                    app_state.last_interaction_status = event.get("content", {}).get("status", "COMPLETED_OK")
                break
            elif event.get("type") == "error":
                if hasattr(app_state, 'last_interaction_status'): app_state.last_interaction_status = "ERROR"
                app_state.add_message(role="assistant", content=f"Error: {event.get('content')}")
                break
        return app_state
    except HistoryResetRequiredError as e:
        logger.warning(f"Shim: HistoryResetRequiredError: {e}")
        if hasattr(app_state, 'last_interaction_status'): app_state.last_interaction_status = "HISTORY_RESET"
        app_state.add_message(role="assistant", content=f"History reset: {e}")
        return app_state
    except Exception as e:
        logger.error(f"Shim: Unhandled error in process_user_interaction: {e}", exc_info=True)
        if hasattr(app_state, 'last_interaction_status'): app_state.last_interaction_status = "FATAL_ERROR"
        app_state.add_message(role="assistant", content="An unexpected error occurred in the shim.")
        return app_state