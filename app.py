# -- app.py --
"""
Main entry point for the chatbot application (Bot Framework Version).
"""
import os
import sys
import logging
from typing import Dict, Any
from llm_interface import LLMInterface
from tools.tool_executor import ToolExecutor
from core_logic import start_streaming_response, HistoryResetRequiredError

# Imports for Bot Framework and Web Server
from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapterSettings,
)  # type: ignore
from botbuilder.schema import Activity  # type: ignore

# Early import for dotenv functionality
from dotenv import load_dotenv, find_dotenv

APP_VERSION = "1.0.0"  # Define APP_VERSION

# ===== Standard Logging Setup =====
# ANSI color codes for colorful logging output
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "header": "\033[1;36m",  # Bold Cyan
    "success": "\033[1;32m",  # Bold Green
    "warning": "\033[1;33m",  # Bold Yellow
    "error": "\033[1;31m",    # Bold Red
    "info": "\033[1;34m",     # Bold Blue
    "debug": "\033[0;37m"     # Light Gray
}

# Section markers and their pretty display formats
SECTIONS = {
    "ENV": {
        "start": "=== LOADING ENVIRONMENT VARIABLES ===",
        "title": f"{COLORS['header']}[KEY] Environment Setup{COLORS['reset']}",
        "end": "=== ENVIRONMENT LOADED SUCCESSFULLY ===",
        # Adjusted end marker
    },
    "CONFIG": {
        "start": "=== CONFIG VALIDATION RESULTS ===",
        # Adjusted from app_config.is_tool_configured
        "title": f"{COLORS['header']}[GEAR] Configuration{COLORS['reset']}",
        "end": "=== CONFIG VALIDATED ===",  # Generic end
    },
    # TOOLS and HEALTH sections were specific to the old Streamlit startup,
    # their logging would now happen within MyBot/health_checks.py
    "STARTUP": {  # This STARTUP is for the Bot Server
        "start": "Bot server starting on",
        "title": (
            f"{COLORS['header']}[ROCKET] Bot Server Startup"
            f"{COLORS['reset']}"
        ),
        "end": "=== Bot server running ===",  # Generic end
    }
}


# Custom formatter that adds color and handles section markers
class ColoredFormatter(logging.Formatter):
    """Custom log formatter that adds colors and handles section markers"""

    def __init__(self, fmt=None, datefmt=None, use_colors=True):
        if fmt is None:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            # More standard default
        super().__init__(fmt, datefmt, style='%')
        self.use_colors = use_colors
        # Allow disabling colors (e.g., for file logging)

    def format(self, record):
        # Get the handler's stream to write section headers/footers directly,
        # ensuring they appear in the correct order relative to other log
        # messages.
        handler_stream = None
        # Only attempt for INFO and above for sections
        if record.levelno >= logging.INFO:
            # This is a bit of a hack to find the stream. In a complex setup
            # with many handlers, one might need a more robust way or pass
            # the stream to the formatter.
            for h in logging.getLogger().handlers:
                if hasattr(h, 'stream'):
                    handler_stream = h.stream
                    break

        # Check if this is a section marker message
        for section_name, section_details in SECTIONS.items():
            if isinstance(record.msg, str):  # Ensure msg is a string
                if section_details["start"] in record.msg or \
                   (section_details["start"].endswith("v") and
                        record.msg.startswith(section_details["start"])):
                    if handler_stream and self.use_colors:
                        handler_stream.write(f"\n{'=' * 50}\n")
                        handler_stream.write(f"{section_details['title']}\n")
                        handler_stream.write(f"{'-' * 50}\n\n")
                        handler_stream.flush()
                    # Let the original message pass through for logging too
                    break
                elif section_details["end"] in record.msg:
                    if handler_stream and self.use_colors:
                        handler_stream.write(f"\n{'-' * 50}\n")
                        handler_stream.write(
                            f"{COLORS['info']}Section {section_name} "
                            f"completed{COLORS['reset']}\n"
                        )
                        handler_stream.write(f"{'=' * 50}\n\n")
                        handler_stream.flush()
                    # Let the original message pass through
                    break

        # Apply colors for log level and message if colors are enabled
        log_record = logging.makeLogRecord(record.__dict__)  # Make a copy

        if self.use_colors:
            # Skip if already colored
            if any(color in str(log_record.msg) for color in COLORS.values()):
                pass  # Let super().format handle it
            elif record.levelno >= logging.ERROR:
                log_record.levelname = (
                    f"{COLORS['error']}{record.levelname}{COLORS['reset']}"
                )
                log_record.msg = (
                    f"{COLORS['error']}{record.msg}{COLORS['reset']}"
                )
            elif record.levelno >= logging.WARNING:
                log_record.levelname = (
                    f"{COLORS['warning']}{record.levelname}{COLORS['reset']}"
                )
                if isinstance(record.msg, str) and \
                   record.msg.startswith("Warning:"):
                    log_record.msg = (
                        f"{COLORS['warning']}{record.msg}{COLORS['reset']}"
                    )
            elif record.levelno >= logging.INFO:
                log_record.levelname = (
                    f"{COLORS['info']}{record.levelname}{COLORS['reset']}"
                )
                if isinstance(record.msg, str) and \
                   record.msg.startswith("Success:"):
                    log_record.msg = (
                        f"{COLORS['success']}{record.msg}{COLORS['reset']}"
                    )
            else:  # DEBUG and below
                log_record.levelname = (
                    f"{COLORS['debug']}{record.levelname}{COLORS['reset']}"
                )
                # Optionally color debug messages too
                # log_record.msg = (
                #     f"{COLORS['debug']}{record.msg}{COLORS['reset']}"
                # )

        return super().format(log_record)


# Set up the root logger before any other imports that might log
root_logger = logging.getLogger()
console_handler = logging.StreamHandler(sys.stdout)
# Use stdout for general logs
console_handler.setFormatter(ColoredFormatter())
root_logger.addHandler(console_handler)
# Initial log level, can be overridden by config later if needed
# However, for BotFramework, APP_SETTINGS.LOG_LEVEL is typically used after
# config load.
# We set INFO here so startup messages are visible.
root_logger.setLevel(logging.INFO)

# Create a named logger for this module
logger = logging.getLogger(__name__)
# summary_logger would be defined and used within MyBot or utils


# --- ONE-TIME ENVIRONMENT VARIABLE LOADING ---
# This must be the FIRST thing that happens in the app for config loading
def load_environment():
    """Load environment variables with detailed logging."""
    logger.info("=== LOADING ENVIRONMENT VARIABLES ===")
    # Matches SECTIONS["ENV"]["start"]

    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        os.path.join(os.getcwd(), '.env'),
        find_dotenv(usecwd=True)
        # find_dotenv checks current and parent dirs
    ]

    env_loaded = False
    env_path_found = "None"
    for dotenv_path in possible_paths:
        # Ensure dotenv_path is not None
        if dotenv_path and os.path.exists(dotenv_path):
            env_path_found = dotenv_path
            logger.info(f"Found .env file at: {env_path_found}")
            load_dotenv(dotenv_path, override=True)
            env_loaded = True
            break

    if env_loaded:
        logger.info(f"SUCCESS: Loaded .env file from: {env_path_found}")
        critical_vars = [
            'JIRA_API_URL', 'JIRA_API_EMAIL', 'JIRA_API_TOKEN',
            'GREPTILE_API_KEY', 'PERPLEXITY_API_KEY', 'GEMINI_API_KEY',
            'MICROSOFT_APP_ID', 'MICROSOFT_APP_PASSWORD'
        ]
        logger.info(
            "Environment variable status (partial values for security):"
        )
        for var in critical_vars:
            val = os.environ.get(var)
            if val:
                logger.info(f"  {var}: {val[:4]}*** (length: {len(val)})")
            else:
                logger.warning(f"  {var}: NOT FOUND")
    else:
        logger.warning(
            "No .env file found in standard locations. "
            "Using system environment variables as is."
        )

    logger.info("=== ENVIRONMENT LOADED SUCCESSFULLY ===")
    # Matches SECTIONS["ENV"]["end"]
    return env_loaded


# Load environment variables BEFORE ANY other imports that might use them
load_environment()


# --- Now import application-specific modules that depend on
# environment/config ---
try:
    # Config class now used for APP_SETTINGS
    from config import get_config, Config
    from bot_core.adapter_with_error_handler import AdapterWithErrorHandler
    from bot_core.my_bot import MyBot
    from bot_core.redis_storage import RedisStorage
    # For the /healthz endpoint
    from health_checks import run_health_checks
except ImportError as e:
    # Use print for critical startup errors before logger might be fully
    # effective or if it fails
    print(
        f"FATAL: Failed to import core modules: {e}. "
        f"Ensure all dependencies are installed and paths are correct.",
        file=sys.stderr
    )
    logger.critical(
        f"Failed to import core modules: {e}. "
        f"Ensure all dependencies are installed and paths are correct.",
        exc_info=True
    )
    sys.exit(1)


# --- Application and Bot Framework Configuration ---
try:
    APP_SETTINGS: Config = get_config()
    # Now that config is loaded, potentially update root logger level
    # Note: MyBot and other modules might get their own loggers and set
    # levels based on APP_SETTINGS.LOG_LEVEL
    # This ensures startup messages before this point used INFO,
    # and now respects config.
    if hasattr(APP_SETTINGS, 'LOG_LEVEL'):
        root_logger.setLevel(APP_SETTINGS.LOG_LEVEL)
        # Ensure formatter is reapplied if level changes
        console_handler.setFormatter(ColoredFormatter(use_colors=True))
        logger.info(
            f"Root logger level set to {APP_SETTINGS.LOG_LEVEL} "
            f"from configuration."
        )
    # Part of SECTIONS["CONFIG"]["start"]
    logger.info("Configuration loaded successfully (APP_SETTINGS).")

    # Log critical tool configurations status (example)
    # Matches SECTIONS["CONFIG"]["start"]
    logger.info("=== CONFIG VALIDATION RESULTS ===")
    tools_to_check = ['github', 'jira', 'greptile', 'perplexity']
    for tool in tools_to_check:
        # Assumes Config has this method
        configured = APP_SETTINGS.is_tool_configured(tool)
        logger.info(f"Tool '{tool}' properly configured: {configured}")
    # Matches SECTIONS["CONFIG"]["end"]
    logger.info("=== CONFIG VALIDATED ===")


except (ValueError, RuntimeError) as config_e:
    print(f"FATAL: Configuration error: {config_e}", file=sys.stderr)
    logger.critical(f"Configuration error: {config_e}", exc_info=True)
    sys.exit(1)
except Exception as e:
    print(
        "FATAL: An unexpected error occurred during initial config: {e}",
        file=sys.stderr
    )
    logger.critical(
        f"An unexpected error occurred during initial config: {e}",
        exc_info=True
    )
    sys.exit(1)


BOT_FRAMEWORK_SETTINGS = BotFrameworkAdapterSettings(
    app_id=APP_SETTINGS.get_env_value("MICROSOFT_APP_ID") or "",
    app_password=APP_SETTINGS.get_env_value("MICROSOFT_APP_PASSWORD") or ""
)
# Pass config for error handling context
ADAPTER = AdapterWithErrorHandler(BOT_FRAMEWORK_SETTINGS, config=APP_SETTINGS)

# --- Bot Initialization ---
try:
    BOT = MyBot(APP_SETTINGS)
    logger.info("MyBot initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize MyBot: {e}", exc_info=True)
    sys.exit(1)


# --- Cleanup function for bot resources ---
async def on_bot_shutdown(app: web.Application):
    """Cleanup bot resources on application shutdown."""
    logger.info("Bot application shutting down. Cleaning up resources...")
    if hasattr(BOT, 'storage') and BOT.storage:
        if isinstance(BOT.storage, RedisStorage):
            try:
                logger.info("Closing Redis bot storage connection...")
                await BOT.storage.close()
                logger.info("Redis bot storage connection closed.")
            except Exception as e:
                logger.error(f"Error closing Redis bot storage: {e}", exc_info=True)
        elif hasattr(BOT.storage, 'aclose'):
            try:
                logger.info("Closing other type of bot storage connection (aclose)...")
                await BOT.storage.aclose()
                logger.info("Other bot storage connection closed.")
            except Exception as e:
                logger.error(f"Error closing other bot storage (aclose): {e}", exc_info=True)
        else:
            logger.info("Bot storage does not have a recognized close/aclose method.")
    # Add other cleanup here if needed (e.g., tool_executor if it holds resources)


# --- Request Handler for Bot Messages ---
async def messages(req: web.BaseRequest) -> web.Response:
    if "application/json" not in req.headers.get("Content-Type", ""):
        logger.warning("Request received with non-JSON content type.")
        return web.Response(status=415)  # Unsupported Media Type

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    # Log basic activity info, more detailed logging can be in MyBot.on_turn
    logger.debug(
        f"Received activity: Type='{activity.type}', "
        f"From='{activity.from_property.id if activity.from_property else 'N/A'}'"  # noqa: E501
    )

    try:
        response = await ADAPTER.process_activity(
            activity, auth_header, BOT.on_turn
        )
        if response:
            logger.debug(f"Sending response with status: {response.status}")
            return web.json_response(response.body, status=response.status)
        logger.debug(
            "No explicit response body to send (activity processed), "
            "responding with 201 Accepted."
        )
        # Accepted: request processed, no content to return
        return web.Response(status=201)
    except Exception as exception:
        logger.error(
            f"Error processing activity in messages handler: {exception}",
            exc_info=True
        )
        # AdapterWithErrorHandler should handle sending error messages to the
        # user. This ensures a 500 is returned if something goes wrong at this
        # top level.
        raise web.HTTPInternalServerError(
            text=f"Internal Server Error: {str(exception)}"
        )


# --- Health Check Endpoint ---
async def healthz(req: web.BaseRequest) -> web.Response:
    logger.info("Health check endpoint (/healthz) requested.")
    try:
        # BOT.llm_interface and BOT.app_config are initialized in MyBot
        # constructor
        if not hasattr(BOT, 'llm_interface') or \
           not hasattr(BOT, 'app_config'):
            logger.error(
                "BOT object is missing llm_interface or app_config "
                "for health check."
            )
            return web.json_response(
                {"status": "ERROR",
                 "message": "Bot not fully configured for health checks."},
                status=503  # Service Unavailable
            )

        health_results = run_health_checks(BOT.llm_interface, BOT.app_config)

        overall_status = "OK"
        http_status_code = 200
        critical_down = False

        for component, result in health_results.items():
            component_status = result.get("status", "UNKNOWN")
            # Assuming DEGRADED_OPERATIONAL is still a pass
            if component_status not in ["OK", "NOT CONFIGURED",
                                        "DEGRADED_OPERATIONAL"]:
                # Example critical component
                if component_status in ["ERROR", "DOWN"] and \
                   component == "LLM API":
                    critical_down = True
                    overall_status = "ERROR"
                    break
                # If any non-critical is down/error
                overall_status = "DEGRADED"

        if critical_down:
            http_status_code = 503  # Service Unavailable
        elif overall_status == "DEGRADED":
            # Could still be 200 if degraded means partially functional,
            # or 503 if severe.
            # For now, let's keep 200 for DEGRADED unless a critical
            # component is ERROR/DOWN.
            pass

        # BOT.app_config.is_tool_configured can be used to add tool config
        # status to health
        # This part can be expanded in health_checks.py itself.

        logger.info(
            f"Health check completed. Overall status: {overall_status}"
        )
        return web.json_response(
            {"overall_status": overall_status,
             "components": health_results,
             "version": APP_VERSION},
            status=http_status_code
        )

    except Exception as e:
        logger.error(
            f"Error during health check execution: {e}", exc_info=True
        )
        return web.json_response(
            {"overall_status": "ERROR",
             "message": f"Health check failed: {str(e)}"},
            status=500  # Internal Server Error
        )


# --- Server Setup ---
SERVER_APP = web.Application()
SERVER_APP.router.add_post("/api/messages", messages)
SERVER_APP.router.add_get("/healthz", healthz)

# Register the cleanup function
SERVER_APP.on_cleanup.append(on_bot_shutdown)

if __name__ == "__main__":
    port_to_use = 3978  # Default Bot Framework port
    try:
        # Use PORT from APP_SETTINGS if available and valid
        if hasattr(APP_SETTINGS, 'PORT') and \
           APP_SETTINGS.PORT and \
           isinstance(APP_SETTINGS.PORT, int):
            port_to_use = APP_SETTINGS.PORT
        else:
            logger.warning(
                f"APP_SETTINGS.PORT not found or invalid "
                f"('{getattr(APP_SETTINGS, 'PORT', 'N/A')}'). "
                f"Using default port {port_to_use}."
            )

        # Matches SECTIONS["STARTUP"]["start"]
        logger.info(
            f"Bot server starting on http://localhost:{port_to_use}"
        )
        web.run_app(SERVER_APP, host="localhost", port=port_to_use)
        # Note: A "server running" or "ready" message for
        # SECTIONS["STARTUP"]["end"]
        # would typically come from aiohttp's startup signals if desired.
        # For simplicity, we'll assume startup is complete when
        # run_app doesn't crash.
        logger.info("=== Bot server running ===")  # Manual end marker

    except Exception as error:
        logger.critical(
            f"Failed to start bot server: {error}", exc_info=True
        )
        sys.exit(1)  # Ensure exit on critical startup failure


# --- Shim for e2e tests ---
# This function is a shim to allow e2e tests to run.
# It attempts to replicate the previous behavior of process_user_interaction.
async def process_user_interaction(
    user_query: Dict[str, Any],
    app_state: Any,  # Should be AppState, but using Any for broader compatibility # noqa: E501
    llm_interface: LLMInterface,
    tool_executor: ToolExecutor,
    config: Any  # Should be Config
) -> Any:
    """
    Shim function to process user interaction for e2e tests.
    This is intended to bridge the gap from older test structures.
    """
    logger.info(
        "Shim process_user_interaction called with query: %s",
        user_query.get('content')
    )

    if not hasattr(app_state, 'add_message') or \
       not callable(app_state.add_message):
        logger.error("Shim: app_state is missing 'add_message' method.")
        # Potentially raise an error or return a modified state indicating
        # failure
        return app_state

    app_state.add_message(role="user", content=user_query.get("content", ""))

    if hasattr(app_state, 'reset_turn_state') and \
       callable(app_state.reset_turn_state):
        app_state.reset_turn_state()

    try:
        stream = start_streaming_response(
            app_state=app_state,
            llm=llm_interface,
            tool_executor=tool_executor,
            config=config
        )
        async for event in stream:
            # The e2e tests primarily check for tool calls and final state, so
            # we don't need to replicate the full streaming to a client here.
            # We just need to ensure the app_state is updated by the core
            # logic.
            if event.get("type") == "completed":
                if hasattr(app_state, 'last_interaction_status'):
                    app_state.last_interaction_status = event.get(
                        "content", {}).get("status", "COMPLETED_OK")
                break
            elif event.get("type") == "error":
                if hasattr(app_state, 'last_interaction_status'):
                    app_state.last_interaction_status = "ERROR"
                app_state.add_message(
                    role="assistant",
                    content=f"Error: {event.get('content')}"
                )
                break
        # The app_state should have been modified in place by
        # start_streaming_response
        return app_state
    except HistoryResetRequiredError as e:
        logger.warning(f"Shim: HistoryResetRequiredError: {e}")
        if hasattr(app_state, 'last_interaction_status'):
            app_state.last_interaction_status = "HISTORY_RESET"
        app_state.add_message(
            role="assistant", content=f"History reset: {e}"
        )
        return app_state
    except Exception as e:
        logger.error(
            f"Shim: Unhandled error in process_user_interaction: {e}",
            exc_info=True
        )
        if hasattr(app_state, 'last_interaction_status'):
            app_state.last_interaction_status = "FATAL_ERROR"
        # Add a generic error message to app_state for the tests to see
        app_state.add_message(
            role="assistant",
            content="An unexpected error occurred in the shim."
        )
        return app_state
