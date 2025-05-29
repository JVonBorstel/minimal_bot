# --- FILE: tools/tool_executor.py ---
import inspect
import logging
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
import time # For duration calculation

from config import Config, get_config # Import get_config
from ._tool_decorator import (
    get_registered_tools,
    get_tool_definitions,
)

from user_auth.permissions import Permission
from state_models import AppState

# Import logging utilities
from utils.logging_config import get_logger, start_tool_call, clear_tool_call_id # Use get_logger
from utils.log_sanitizer import sanitize_data

# === CRITICAL: IMPORT ALL TOOL MODULES TO TRIGGER DECORATOR REGISTRATION ===
# This is the missing piece! The @tool_function decorators need to execute
# for tools to be registered. We import all tool modules here.
try:
    import tools.github_tools
    import tools.jira_tools
    import tools.greptile_tools
    import tools.perplexity_tools
    import tools.core_tools  # Import core tools including help
    import tools.user_profile_tools # Added for user preference management
    log_import_success = True
except ImportError as e:
    log_import_success = False
    import_error = e

log = get_logger("tools.executor") # Use get_logger

# Log the import results immediately
if log_import_success:
    log.info("✅ Successfully imported all tool modules - decorators executed")
else:
    log.error(f"❌ Failed to import tool modules: {import_error}")

class ToolExecutor:
    """
    Manages discovery, validation, instantiation, and execution of tools.
    Assumes tool modules (like github_tools.py) are imported eagerly elsewhere.
    """
    def __init__(self, config: Config):
        """
        Initializes ToolExecutor: finds all registered tools, instantiates needed *Tools classes,
        and validates tool configurations.
        
        Args:
            config: The application configuration object
        """
        self.config = config
        self.configured_tools: Dict[str, Callable] = {}
        self.configured_tool_definitions: List[Dict[str, Any]] = []
        self.tool_instances: Dict[str, Any] = {}
        self.tool_name_to_instance_key: Dict[str, str] = {}
        
        # Track tool discovery and configuration stats
        self.discovery_stats = {
            "tools_registered": 0,
            "classes_found": 0,
            "classes_instantiated": 0,
            "tools_configured": 0,
            "tools_skipped": 0,
            "errors": 0
        }

        log.info("=== TOOL INITIALIZATION ===")
        # Simplified workflow: find and instantiate needed tool classes, then validate
        self._find_and_instantiate_tool_classes()
        self._validate_and_filter_tools()
        log.info("=== TOOLS INITIALIZED ===")

    def _find_and_instantiate_tool_classes(self) -> None:
        """
        Finds all *Tools classes needed by registered tools and instantiates them.
        Assumes that tool modules have already been imported, so tools are already
        registered via the @tool_function decorator.
        """
        log.info("Finding and instantiating tool classes...")
        
        # Track all unique class names that tools belong to
        all_registered_tools = get_registered_tools()
        self.discovery_stats["tools_registered"] = len(all_registered_tools)
        
        # Step 1: Identify all unique class names from registered tools
        needed_class_names = set()
        for tool_name, wrapper_func in all_registered_tools.items():
            class_name = getattr(wrapper_func, '_tool_class_name', None)
            if class_name:
                needed_class_names.add(class_name)
        
        # Track the number of classes we need to instantiate
        self.discovery_stats["classes_found"] = len(needed_class_names)
        if not needed_class_names:
            log.info("No tool classes found to instantiate.")
            return
            
        log.info(f"Found {len(needed_class_names)} tool classes to instantiate: {', '.join(needed_class_names)}")
        
        # Step 2: Find and instantiate the classes from loaded modules
        # Inspect all modules in the 'tools' package
        tools_dir = Path(__file__).parent
        
        # Find all potential tool classes across all loaded modules
        for module_name, module in list(sys.modules.items()):
            # Skip modules that don't have a proper __name__ attribute or aren't in our tools dir
            if not hasattr(module, '__name__') or 'tools.' not in module_name or module_name.startswith('tools._'):
                continue
                
            # Look for classes in the module matching our needed class names
            for class_name in needed_class_names.copy():  # Use copy to avoid modifying while iterating
                if class_name in self.tool_instances:
                    continue  # Skip if already instantiated
                    
                # Try to get the class from the module
                cls = getattr(module, class_name, None)
                if cls and inspect.isclass(cls):
                    log.info(f"Found class {class_name} in module {module_name}")
                    try:
                        # Instantiate the class with our config
                        instance = cls(self.config)
                        self.tool_instances[class_name] = instance
                        log.info(f"Instantiated {class_name} successfully")
                        self.discovery_stats["classes_instantiated"] += 1
                        needed_class_names.remove(class_name)
                    except Exception as e:
                        log.error(f"Failed to instantiate {class_name}: {e}", exc_info=True)
                        self.discovery_stats["errors"] += 1
        
        # Check if we found all needed classes
        if needed_class_names:
            log.warning(f"Could not find or instantiate these tool classes: {', '.join(needed_class_names)}")
            
        log.info(f"Tool class instantiation summary: {self.discovery_stats['classes_instantiated']}/{self.discovery_stats['classes_found']} classes instantiated")

    def _validate_and_filter_tools(self) -> None:
        """
        Validates discovered tools against config and populates configured tool lists.
        Only tools that pass configuration validation will be available for execution.
        """
        log.info("Validating tools and checking configurations...")
        
        # Get all registered tools and their definitions
        all_registered_tools = get_registered_tools()
        all_tool_defs = {defn['name']: defn for defn in get_tool_definitions()}
        
        # Temporary dictionaries to store validated tools
        configured_tools_temp: Dict[str, Callable] = {}
        configured_defs_temp: List[Dict[str, Any]] = []
        name_to_instance_map: Dict[str, str] = {}
        
        # Statistics for reporting
        validation_stats = {"configured": 0, "skipped": 0, "errors": 0, "missing_definitions": 0}
        tool_groups: Dict[str, List[str]] = {}  # Group tools by service for reporting
        
        log.info(f"Validating {len(all_registered_tools)} registered tools...")
        
        # Validate each registered tool
        for tool_name, wrapper_func in all_registered_tools.items():
            # Get the tool definition (schema)
            definition = all_tool_defs.get(tool_name)
            if not definition:
                log.warning(f"Tool '{tool_name}' is registered but missing its definition. Skipping.")
                validation_stats["missing_definitions"] += 1
                continue
                
            # --- Add required permission to tool definition metadata ---
            tool_callable = all_registered_tools.get(tool_name)
            required_permission_enum: Optional[Permission] = None
            if tool_callable:
                required_permission_enum = getattr(tool_callable, '_permission_required', None)
            
            if required_permission_enum and isinstance(required_permission_enum, Permission):
                if 'metadata' not in definition:
                    definition['metadata'] = {}
                definition['metadata']['required_permission'] = required_permission_enum.value
                definition['metadata']['required_permission_name'] = required_permission_enum.name
                log.debug(f"Added permission '{required_permission_enum.name}' to metadata for tool '{tool_name}'.")
            # --- End permission addition ---

            # Get the class name stored on the wrapper by the decorator
            class_name = getattr(wrapper_func, '_tool_class_name', None)
            
            # Handle standalone functions vs. class methods
            if not class_name:
                # Standalone function (not part of a *Tools class)
                log.info(f"Tool '{tool_name}' is a standalone function. Assuming configured.")
                config_key = "standalone"
                instance_key = None  # No instance needed
            else:
                # Get the tool class instance that should have been created
                instance = self.tool_instances.get(class_name)
                if not instance:
                    log.error(f"Tool '{tool_name}' belongs to class '{class_name}', but no instance was found.")
                    validation_stats["errors"] += 1
                    continue  # Skip this tool as we can't execute it
                
                # Extract service name from the class name (e.g., "GitHubTools" -> "github")
                config_key = class_name.replace("Tools", "").lower()
                instance_key = class_name
            
            # Group tools by service for reporting
            if config_key not in tool_groups:
                tool_groups[config_key] = []
            tool_groups[config_key].append(tool_name)
            
            # Check if the tool's service is properly configured
            is_configured = True
            if instance_key:  # Only check config for class methods, not standalone functions
                is_configured = self.config.is_tool_configured(config_key)
            
            # Only add the tool to our available tools if it's properly configured
            if is_configured:
                configured_tools_temp[tool_name] = wrapper_func
                configured_defs_temp.append(definition)
                validation_stats["configured"] += 1
                
                # Map the tool name to its instance key (if it's a class method)
                if instance_key:
                    name_to_instance_map[tool_name] = instance_key
            else:
                validation_stats["skipped"] += 1
                log.warning(f"Skipped '{tool_name}' (service: {config_key}): Configuration missing or incomplete.")
        
        # Store the validated tools and mappings
        self.configured_tools = configured_tools_temp
        self.configured_tool_definitions = configured_defs_temp
        self.tool_name_to_instance_key = name_to_instance_map
        
        # Update discovery stats
        self.discovery_stats["tools_configured"] = validation_stats["configured"]
        self.discovery_stats["tools_skipped"] = validation_stats["skipped"]
        self.discovery_stats["errors"] += validation_stats["errors"]
        
        # Log validation summary
        log.info("\n=== Tool Validation Summary ===")
        for service, tools in sorted(tool_groups.items()):
            configured_count = sum(1 for t in tools if t in self.configured_tools)
            total_count = len(tools)
            status = "[OK]" if configured_count == total_count and total_count > 0 else ("[WARN]" if configured_count > 0 else "[FAIL]")
            log.info(f"{status} {service.capitalize()}: {configured_count}/{total_count} tools configured")
        
        log.info(f"\nTotal Results:")
        log.info(f"• Configured: {validation_stats['configured']}")
        log.info(f"• Skipped: {validation_stats['skipped']}")
        
        # Log warnings for missing definitions
        if validation_stats['missing_definitions'] > 0:
            warning_color = "\033[93m" # Yellow
            reset_color = "\033[0m"
            missing_def_msg = f"• Missing Definitions: {validation_stats['missing_definitions']}"
            log.warning(f"{warning_color}{missing_def_msg}{reset_color}")
            log.warning(f"{warning_color}  >> Some tools have missing definitions. This may be due to registration issues or incomplete implementations.{reset_color}")
        
        # Highlight errors more prominently
        error_color = "\033[91m" # Red
        reset_color = "\033[0m"
        error_msg = f"• Errors: {validation_stats['errors']}"
        if validation_stats['errors'] > 0:
            log.error(f"{error_color}{error_msg}{reset_color}")
            log.warning(f"{error_color}  >> Some tools could not be validated due to missing instances. Check logs above.{reset_color}")
        else:
            log.info(error_msg)
        
        log.info("============================\n")

    def get_available_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns schema definitions for configured tools."""
        return self.configured_tool_definitions

    def get_available_tool_names(self) -> List[str]:
        """Returns names of configured tools."""
        return list(self.configured_tools.keys())

    async def execute_tool(self, tool_name: str, tool_input: Any, app_state: Any = None) -> Any:
        """
        Executes a configured tool by name with the provided input.
        
        Args:
            tool_name: Name of the tool to execute
            tool_input: JSON string or dict containing the tool's input parameters
            app_state: The current application state (Optional)
            
        Returns:
            The result of the tool execution
        """
        current_config = get_config() # Get current config instance
        tool_call_id = start_tool_call() # Start tool call context
        start_time = time.monotonic()
        
        log_extra_base = {"tool_name": tool_name}

        try:
            # Check if the tool exists and is configured
            if tool_name not in self.configured_tools:
                log.error(f"Cannot execute unconfigured tool '{tool_name}'", extra=log_extra_base)
                
                # Provide more helpful error messages based on the tool type
                if tool_name in get_registered_tools():
                    # Tool exists but isn't configured
                    service_name = self._get_service_name_from_tool(tool_name)
                    friendly_message = self._get_configuration_help_message(service_name, tool_name)
                    error_payload = {
                        "status": "ERROR",
                        "error_type": "ToolNotConfigured",
                        "message": friendly_message,
                        "service": service_name,
                        "actionable_advice": self._get_actionable_advice(service_name),
                        "fallback_suggestions": self._get_fallback_suggestions(service_name, tool_name)
                    }
                else:
                    # Tool doesn't exist at all
                    error_payload = {
                        "status": "ERROR", 
                        "error_type": "ToolNotFound",
                        "message": f"I don't have a tool called '{tool_name}'. Use the 'help' command to see available tools.",
                        "actionable_advice": "Try asking for help to see what tools are available.",
                        "fallback_suggestions": ["Use '@bot help' to see available commands", "Try rephrasing your request"]
                    }
                
                log.info(
                    f"Tool Execution Summary: {tool_name} - FAILED (Not Configured/Found)",
                    extra={
                        **log_extra_base,
                        "event_type": "tool_execution_summary",
                        "status": "FAILED",
                        "duration_ms": (time.monotonic() - start_time) * 1000,
                        "error": error_payload
                    }
                )
                return error_payload

            # Get the tool function and its instance (if it's a class method)
            tool_function = self.configured_tools[tool_name]
            instance_key = self.tool_name_to_instance_key.get(tool_name)
            
            instance = None
            if instance_key:
                instance = self.tool_instances.get(instance_key)
                if not instance:
                    log.error(f"No instance found for tool '{tool_name}' (class: {instance_key})", extra=log_extra_base)
                    error_payload = {
                        "status": "ERROR",
                        "error_type": "InstanceNotFound",
                        "message": f"Internal error: Could not find instance for tool '{tool_name}'."
                    }
                    log.info(
                        f"Tool Execution Summary: {tool_name} - FAILED (Instance Not Found)",
                        extra={
                            **log_extra_base,
                            "event_type": "tool_execution_summary",
                            "status": "FAILED",
                            "duration_ms": (time.monotonic() - start_time) * 1000,
                            "error": error_payload
                        }
                    )
                    return error_payload
                
            kwargs = {}
            try:
                if isinstance(tool_input, dict):
                    kwargs = tool_input
                elif isinstance(tool_input, str) and tool_input.strip():
                    kwargs = json.loads(tool_input)
                    if not isinstance(kwargs, dict):
                        raise TypeError("Tool input must be a JSON object")
                elif tool_input is None or (isinstance(tool_input, str) and not tool_input.strip()):
                    pass # Empty input is fine
                else:
                    raise TypeError(f"Invalid input type: {type(tool_input).__name__}")
            except (json.JSONDecodeError, TypeError) as e:
                log.error(f"Invalid input for '{tool_name}': {e}", extra=log_extra_base)
                error_payload = {
                    "status": "ERROR",
                    "error_type": "InvalidInput",
                    "message": f"Invalid input format: {str(e)}"
                }
                log.info(
                    f"Tool Execution Summary: {tool_name} - FAILED (Invalid Input)",
                    extra={
                        **log_extra_base,
                        "event_type": "tool_execution_summary",
                        "status": "FAILED",
                        "duration_ms": (time.monotonic() - start_time) * 1000,
                        "error": error_payload
                    }
                )
                return error_payload

            # Log Tool Call Parameters if log_tool_io is True
            if current_config.settings.log_tool_io:
                sanitized_params = sanitize_data(kwargs.copy()) # Sanitize a copy
                log.info(
                    "Tool Call Parameters",
                    extra={
                        **log_extra_base,
                        "event_type": "tool_parameters", 
                        "data": {"parameters": sanitized_params}
                    }
                )
            else:
                 log.debug(f"Executing {tool_name} with args: {kwargs}", extra=log_extra_base) # Keep original debug log if not verbose

            # Execute the tool
            # CRITICAL: Always pass tool_config=self.config and app_state to the tool_function wrapper
            result = await tool_function(instance, tool_config=self.config, app_state=app_state, **kwargs)
            
            duration_ms = (time.monotonic() - start_time) * 1000

            # Log Tool Call Raw Result if log_tool_io is True
            if current_config.settings.log_tool_io:
                sanitized_result = sanitize_data(result) # Sanitize result (might be complex type)
                log.info(
                    "Tool Call Raw Result",
                    extra={
                        **log_extra_base,
                        "event_type": "tool_raw_result",
                        "data": {"result": sanitized_result}
                    }
                )
            
            # Log Tool Execution Summary (always)
            log.info(
                f"Tool Execution Summary: {tool_name} - SUCCESS",
                extra={
                    **log_extra_base,
                    "event_type": "tool_execution_summary",
                    "status": "SUCCESS",
                    "duration_ms": duration_ms
                }
            )
            return result
            
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            log.error(f"Error executing {tool_name}: {e}", exc_info=True, extra=log_extra_base)
            error_payload = {
                "status": "ERROR",
                "error_type": "ExecutionError",
                "message": f"Tool execution failed: {str(e)}"
            }
            # Log Tool Execution Summary for failure
            log.info(
                f"Tool Execution Summary: {tool_name} - FAILED (Execution Error)",
                extra={
                    **log_extra_base,
                    "event_type": "tool_execution_summary",
                    "status": "FAILED",
                    "duration_ms": duration_ms,
                    "error": sanitize_data(error_payload) # Sanitize error payload too
                }
            )
            return error_payload
        finally:
            clear_tool_call_id() # Clear tool call ID in all cases

    def _get_service_name_from_tool(self, tool_name: str) -> str:
        """Extract service name from tool name."""
        if tool_name.startswith("github_"):
            return "github"
        elif tool_name.startswith("jira_"):
            return "jira"
        elif tool_name.startswith("greptile_"):
            return "greptile"
        elif tool_name.startswith("perplexity_"):
            return "perplexity"
        else:
            return "unknown"
    
    def _get_configuration_help_message(self, service_name: str, tool_name: str) -> str:
        """Generate helpful configuration error messages."""
        service_messages = {
            "github": "🔧 GitHub tools aren't set up yet. I need a GitHub Personal Access Token to access repositories, issues, and pull requests.",
            "jira": "🔧 Jira tools aren't fully configured. I need Jira API credentials (email and token) to access your tickets and projects.",
            "greptile": "🔧 Greptile code search isn't configured. I need a Greptile API key to search through codebases.",
            "perplexity": "🔧 Perplexity web search isn't configured. I need a Perplexity API key to search the web for information."
        }
        
        return service_messages.get(service_name, f"🔧 The {service_name} service isn't configured properly.")
    
    def _get_actionable_advice(self, service_name: str) -> str:
        """Generate actionable advice for configuration issues."""
        advice = {
            "github": "Ask your administrator to add GITHUB_TOKEN to the environment variables, or provide your own GitHub Personal Access Token through the onboarding process.",
            "jira": "Ask your administrator to verify JIRA_API_EMAIL and JIRA_API_TOKEN are set correctly, or provide your own Jira credentials through onboarding.",
            "greptile": "Ask your administrator to add GREPTILE_API_KEY to the environment variables.",
            "perplexity": "Ask your administrator to add PERPLEXITY_API_KEY to the environment variables."
        }
        
        return advice.get(service_name, "Contact your administrator to configure this service.")
    
    def _get_fallback_suggestions(self, service_name: str, tool_name: str) -> List[str]:
        """Generate fallback suggestions when tools aren't available."""
        fallbacks = {
            "github": [
                "I can help you with Jira tickets instead",
                "Try asking me to search the web for GitHub-related information",
                "You can manually check GitHub.com for your repositories"
            ],
            "jira": [
                "I can help you search the web for Jira-related information",
                "Try asking me about GitHub repositories instead",
                "You can manually check your Jira instance for tickets"
            ],
            "greptile": [
                "I can help you search the web for code examples",
                "Try asking me about your GitHub repositories or Jira tickets",
                "You can search your codebase manually using your IDE or GitHub"
            ],
            "perplexity": [
                "I can help you with GitHub repositories or Jira tickets",
                "Try asking me about your configured tools instead",
                "You can search the web manually using your browser"
            ]
        }
        
        return fallbacks.get(service_name, ["Try asking about available tools with '@bot help'"])