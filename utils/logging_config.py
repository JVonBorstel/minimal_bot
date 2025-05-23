import logging
import json
import datetime
import traceback
import contextvars
import uuid
import os # Added import for os
import sys # ADDED FOR DEBUGGING

print(f"DEBUG: sys.path in {__file__}: {sys.path}") # ADDED FOR DEBUGGING

# Contextvars for correlation IDs
turn_id_var = contextvars.ContextVar("turn_id", default=None)
llm_call_id_var = contextvars.ContextVar("llm_call_id", default=None)
tool_call_id_var = contextvars.ContextVar("tool_call_id", default=None)

class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for logging.
    Ensures logs are output in a structured JSON format.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensitive_keys = set()
        log_sensitive_fields_env = os.environ.get("LOG_SENSITIVE_FIELDS")
        if log_sensitive_fields_env:
            self.sensitive_keys = {key.strip() for key in log_sensitive_fields_env.split(',') if key.strip()}

    def _sanitize_log_entry(self, data: dict):
        """Recursively sanitizes dictionary data by masking sensitive keys."""
        for key, value in list(data.items()): # Iterate over a copy of items for safe modification
            if key in self.sensitive_keys:
                data[key] = "***MASKED***"
            elif isinstance(value, dict):
                self._sanitize_log_entry(value) # Recurse for nested dictionaries
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        # Create a new dictionary for the sanitized item to avoid modifying original list item if it's shared
                        # However, standard logging practice usually means these are new dicts anyway.
                        # For simplicity, we'll recurse directly. If issues arise, consider deepcopying item before recursion.
                        self._sanitize_log_entry(item)
                    # Non-dict list items are not sanitized further by this key-based method

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger_name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line_no": record.lineno,
        }

        # Add correlation IDs from contextvars
        current_turn_id = turn_id_var.get()
        if current_turn_id:
            log_entry["turn_id"] = current_turn_id
        
        current_llm_call_id = llm_call_id_var.get()
        if current_llm_call_id:
            log_entry["llm_call_id"] = current_llm_call_id

        current_tool_call_id = tool_call_id_var.get()
        if current_tool_call_id:
            log_entry["tool_call_id"] = current_tool_call_id

        # Add event_type and details if provided in 'extra'
        if hasattr(record, 'event_type'):
            log_entry['event_type'] = record.event_type
        else:
            log_entry['event_type'] = "general"

        # Add all other 'extra' fields, prioritizing 'details' if it exists
        # These are fields passed via logger.info("...", extra={...})
        standard_record_attrs = set(logging.LogRecord('', '', '', '', '', '', '', '').__dict__.keys())
        custom_attrs = {}
        for key, value in record.__dict__.items():
            if key not in standard_record_attrs and key not in log_entry:
                custom_attrs[key] = value
        
        if 'details' in custom_attrs and isinstance(custom_attrs['details'], dict):
            log_entry.update(custom_attrs.pop('details')) # Merge details directly

        if custom_attrs: # Add remaining custom attributes under a 'data' key or merge if simple
             # For simplicity, let's merge them if they don't conflict with top-level keys
            for k, v in custom_attrs.items():
                if k not in log_entry:
                    log_entry[k] = v
                else: # Handle potential conflicts, e.g., by prefixing
                    log_entry[f"extra_{k}"] = v


        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info).splitlines()
            }
        elif record.exc_text:
             log_entry["exception_text"] = record.exc_text

        # Sanitize the log entry before dumping to JSON
        if self.sensitive_keys: # Only sanitize if there are keys to sanitize
            self._sanitize_log_entry(log_entry)

        return json.dumps(log_entry, ensure_ascii=False, default=str) # default=str for non-serializable

def setup_logging(level_str: str = "INFO") -> logging.Logger:
    """
    Configures logging for the project.
    Sets up a JSON formatter and a stream handler.
    """
    level = logging.getLevelName(level_str.upper())
    if not isinstance(level, int):
        level = logging.INFO # Default to INFO if level_str is invalid

    # Get the root logger for the project_light namespace
    # All loggers created via logging.getLogger("project_light.module") will inherit this
    logger = logging.getLogger("project_light")
    logger.setLevel(level)
    logger.propagate = False # Prevent passing messages to the root logger if it has handlers

    # Prevent duplicate handlers if setup_logging is called multiple times
    if not any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter) for h in logger.handlers):
        handler = logging.StreamHandler() # Log to stdout/stderr by default
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    # Optionally configure other specific loggers (e.g., for libraries)
    # logging.getLogger("some_external_library").setLevel(logging.WARNING)

    return logger

# --- Helper functions for managing correlation ID context ---
def get_logger(name: str) -> logging.Logger:
    """Gets a logger instance, ensuring it's part of the project_light namespace."""
    if not name.startswith("project_light."):
        name = f"project_light.{name}"
    return logging.getLogger(name)

def start_new_turn() -> str:
    """Generates and sets a new turn_id in context."""
    new_id = f"urn:uuid:{uuid.uuid4()}"
    turn_id_var.set(new_id)
    return new_id

def start_llm_call() -> str:
    """Generates and sets a new llm_call_id in context."""
    new_id = f"urn:uuid:{uuid.uuid4()}"
    llm_call_id_var.set(new_id)
    return new_id

def start_tool_call() -> str:
    """Generates and sets a new tool_call_id in context."""
    new_id = f"urn:uuid:{uuid.uuid4()}"
    tool_call_id_var.set(new_id)
    return new_id

def clear_llm_call_id():
    """Clears the llm_call_id from context."""
    llm_call_id_var.set(None)

def clear_tool_call_id():
    """Clears the tool_call_id from context."""
    tool_call_id_var.set(None)

def clear_turn_ids():
    """Clears all correlation IDs from context (at the end of a turn)."""
    turn_id_var.set(None)
    llm_call_id_var.set(None)
    tool_call_id_var.set(None)

# Example usage (for testing this module directly):
if __name__ == "__main__":
    # Initialize logging
    logger = setup_logging(level_str="DEBUG")
    
    # Simulate starting a turn
    current_turn_id = start_new_turn()
    logger.info("Turn started.", extra={"event_type": "turn_start", "details": {"session_id": "session123"}})

    # Simulate an LLM call within the turn
    current_llm_id = start_llm_call()
    logger.debug("Preparing LLM request.", extra={"event_type": "llm_request_prepared", "details": {"model": "gemini-pro"}})
    
    # Simulate a tool call within the LLM call
    current_tool_id = start_tool_call()
    logger.info("Executing tool.", extra={"event_type": "tool_execution_start", "details": {"tool_name": "example_tool"}})
    
    try:
        raise ValueError("Something went wrong in the tool")
    except ValueError:
        logger.error("Tool execution failed.", exc_info=True, extra={"event_type": "tool_execution_error", "details": {"tool_name": "example_tool"}})
    
    clear_tool_call_id()
    clear_llm_call_id()
    
    logger.info("LLM processing complete.", extra={"event_type": "llm_response_processed"})
    
    clear_turn_ids()
    logger.info("Turn ended.", extra={"event_type": "turn_end"})

    # Test without context IDs
    logger.warning("A log message outside any specific turn context.")