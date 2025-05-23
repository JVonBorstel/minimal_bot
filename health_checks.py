"""
Health check system for monitoring service and tool availability.
"""
import logging
import time
import concurrent.futures
from typing import Dict, Any, Optional, Callable, TYPE_CHECKING, List, Tuple

import requests

# --- Project Imports ---
# Import the Config class itself, not the instance
# from config import Config
# Import tool classes for type hinting and instantiation
from tools.github_tools import GitHubTools
from tools.jira_tools import JiraTools
from tools.perplexity_tools import PerplexityTools
from tools.greptile_tools import GreptileTools
# LLMInterface needed for type hinting the check function
from llm_interface import LLMInterface
from config import get_config

# Use TYPE_CHECKING for type hints to avoid circular imports at runtime
if TYPE_CHECKING:
    from config import Config

# Health check interval (in seconds) - moved to Config potentially or keep here?
# Keeping it here for now as it directly relates to health check logic.
HEALTH_CHECK_INTERVAL = 600  # 10 minutes

# Use the 'health' section logger for better organization
log = logging.getLogger("health")

# ANSI color codes for status output
COLORS = {
    "reset": "\033[0m",
    "header": "\033[1;36m",  # Bold Cyan
    "success": "\033[1;32m",  # Bold Green
    "warning": "\033[1;33m",  # Bold Yellow
    "error": "\033[1;31m",    # Bold Red
    "info": "\033[1;34m",     # Bold Blue
}

# Status symbols for visual feedback
STATUS_SYMBOLS = {
    "OK": f"{COLORS['success']}✓{COLORS['reset']}",
    "WARNING": f"{COLORS['warning']}⚠{COLORS['reset']}",
    "ERROR": f"{COLORS['error']}✗{COLORS['reset']}",
    "DOWN": f"{COLORS['error']}⬇{COLORS['reset']}",
    "NOT CONFIGURED": f"{COLORS['info']}•{COLORS['reset']}",
    "UNKNOWN": f"{COLORS['warning']}?{COLORS['reset']}"
}

# --- Health Check Helper Functions (for parallel execution) ---

def _run_single_check(
    check_function: Callable[..., Dict[str, Any]],
    service_name: str,
    *args,
    **kwargs
) -> tuple[str, Dict[str, Any]]:
    """Runs a single health check with enhanced error handling and timing."""
    log.info(f"Starting health check: {service_name}")
    start_time = time.monotonic()
    
    try:
        result = check_function(*args, **kwargs)
        elapsed = time.monotonic() - start_time
        
        if not isinstance(result, dict):
            log.error(f"Invalid check result format from {service_name}")
            return service_name, {
                "status": "ERROR",
                "message": "Invalid check result format",
                "elapsed_time": elapsed
            }
            
        # Check if overall_status exists (for GitHub which has a nested structure)
        if "overall_status" in result:
            status = result.get("overall_status", "UNKNOWN")
            message = result.get("message", "No details provided")
            # Add timing information to result
            result["elapsed_time"] = elapsed
            symbol = STATUS_SYMBOLS.get(status, STATUS_SYMBOLS["UNKNOWN"])
            
            log.info(f"{symbol} {service_name} check completed in {elapsed:.2f}s - Status: {status}")
            if status != "OK":
                log.warning(f"  Details: {message}")
            
            return service_name, {
                "status": status,
                "message": message,
                "elapsed_time": elapsed
            }
        
        # Handle standard format
        if "status" not in result:
            log.error(f"Invalid check result format from {service_name}")
            return service_name, {
                "status": "ERROR",
                "message": "Invalid check result format",
                "elapsed_time": elapsed
            }
            
        # Add timing information to result
        result["elapsed_time"] = elapsed
        status = result.get("status", "UNKNOWN")
        symbol = STATUS_SYMBOLS.get(status, STATUS_SYMBOLS["UNKNOWN"])
        
        log.info(f"{symbol} {service_name} check completed in {elapsed:.2f}s - Status: {status}")
        if status != "OK":
            log.warning(f"  Details: {result.get('message', 'No details provided')}")
            
        return service_name, result
        
    except requests.exceptions.Timeout as e:
        elapsed = time.monotonic() - start_time
        log.error(f"{STATUS_SYMBOLS['DOWN']} {service_name} check timed out after {elapsed:.2f}s")
        return service_name, {
            "status": "DOWN",
            "message": f"Timeout: {str(e)}",
            "elapsed_time": elapsed
        }
        
    except requests.exceptions.ConnectionError as e:
        elapsed = time.monotonic() - start_time
        log.error(f"{STATUS_SYMBOLS['DOWN']} {service_name} connection error after {elapsed:.2f}s")
        return service_name, {
            "status": "DOWN",
            "message": f"Connection failed: {str(e)}",
            "elapsed_time": elapsed
        }
        
    except requests.exceptions.RequestException as e:
        elapsed = time.monotonic() - start_time
        status_code = getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'
        log.error(f"{STATUS_SYMBOLS['ERROR']} {service_name} request failed (Status: {status_code}) after {elapsed:.2f}s")
        return service_name, {
            "status": "ERROR",
            "message": f"Request failed (Status: {status_code}): {str(e)}",
            "elapsed_time": elapsed
        }
        
    except Exception as e:
        elapsed = time.monotonic() - start_time
        log.error(f"{STATUS_SYMBOLS['ERROR']} {service_name} check failed with unexpected error after {elapsed:.2f}s")
        log.error(f"  Error details: {str(e)}", exc_info=True)
        return service_name, {
            "status": "ERROR",
            "message": f"Unexpected error: {str(e)}",
            "elapsed_time": elapsed
        }

# --- Specific Service Check Functions ---

def _check_llm(llm_instance: LLMInterface) -> Dict[str, Any]:
    """Performs health check for LLM service."""
    if not llm_instance:
        return {"status": "ERROR", "message": "LLM interface not initialized"}
    return llm_instance.health_check()

def _check_tool(config: 'Config', tool_key: str, tool_class: type) -> Dict[str, Any]:
    """Performs health check for a specific tool."""
    if not config.is_tool_configured(tool_key):
        return {
            "status": "NOT CONFIGURED",
            "message": f"Tool '{tool_key}' is not configured"
        }
        
    try:
        tool_instance = tool_class(config)
        if not hasattr(tool_instance, 'health_check'):
            log.warning(f"Tool '{tool_key}' lacks health check implementation")
            return {
                "status": "WARNING",
                "message": "Health check not implemented"
            }
            
        return tool_instance.health_check()
        
    except Exception as e:
        log.error(f"Failed to initialize {tool_key}: {e}", exc_info=True)
        return {
            "status": "ERROR",
            "message": f"Initialization failed: {str(e)}"
        }

# --- Main Health Check Runner (Parallelized) ---

def run_health_checks(llm_instance: LLMInterface, config: 'Config') -> Dict[str, Dict[str, Any]]:
    """Runs all health checks in parallel with improved logging."""
    log.info(f"\n{COLORS['header']}=== Starting Health Checks ==={COLORS['reset']}\n")
    results: Dict[str, Dict[str, Any]] = {}
    start_time = time.monotonic()

    # Define tool configurations
    tool_configs = {
        "github": (GitHubTools, "GitHub API"),
        "jira": (JiraTools, "Jira API"),
        "greptile": (GreptileTools, "Greptile API"),
        "perplexity": (PerplexityTools, "Perplexity API")
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_configs) + 1) as executor:
        # Submit all checks
        future_to_service = {
            executor.submit(_run_single_check, _check_llm, "LLM API", llm_instance): "LLM API"
        }
        
        # Submit tool checks
        for tool_key, (tool_class, service_name) in tool_configs.items():
            future = executor.submit(
                _run_single_check, _check_tool, service_name,
                config, tool_key, tool_class
            )
            future_to_service[future] = service_name

        # Track completion
        completed = 0
        total = len(future_to_service)
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_service):
            service_name = future_to_service[future]
            completed += 1
            
            try:
                service_name, result = future.result()
                results[service_name] = result
                
                # Progress indicator
                progress = (completed / total) * 100
                log.info(f"Progress: {progress:.0f}% ({completed}/{total} checks complete)")
                
                # Update tool health status in config
                # Map service name back to tool key
                tool_key = next((k for k, (_, s) in tool_configs.items() if s == service_name), "")
                if tool_key and hasattr(config, 'update_tool_health_status'):
                    config.update_tool_health_status(tool_key, result.get('status', 'UNKNOWN'))
                
            except Exception as e:
                log.error(f"Check task failed for {service_name}: {e}", exc_info=True)
                results[service_name] = {
                    "status": "ERROR",
                    "message": f"Check failed: {str(e)}"
                }

    # Ensure all services have results
    all_services = ["LLM API"] + [v[1] for v in tool_configs.values()]
    for service in all_services:
        if service not in results:
            results[service] = {
                "status": "ERROR",
                "message": "Check did not complete"
            }

    # Calculate total time
    total_time = time.monotonic() - start_time
    log.info(f"\n{COLORS['header']}Health checks completed in {total_time:.2f}s{COLORS['reset']}\n")
    
    return results

# --- Logging Health Status ---

def log_health_changes(
    new: Dict[str, Dict[str, Any]],
    old: Dict[str, Dict[str, Any]]
) -> None:
    """Logs health status changes with visual indicators."""
    log.info(f"\n{COLORS['header']}=== Health Status Changes ==={COLORS['reset']}\n")
    
    for service_name, new_result in new.items():
        old_result = old.get(service_name, {})
        old_status = old_result.get("status", "UNKNOWN")
        new_status = new_result.get("status", "UNKNOWN")
        
        if new_status != old_status:
            old_symbol = STATUS_SYMBOLS.get(old_status, STATUS_SYMBOLS["UNKNOWN"])
            new_symbol = STATUS_SYMBOLS.get(new_status, STATUS_SYMBOLS["UNKNOWN"])
            
            log.warning(
                f"Status Change: {service_name}\n"
                f"  {old_symbol} {old_status} → {new_symbol} {new_status}\n"
                f"  Details: {new_result.get('message', 'No details')}"
            )

def log_full_health_summary(
    results: Dict[str, Dict[str, Any]],
    config: Optional['Config'] = None
) -> None:
    """Logs a detailed health status summary with visual formatting."""
    if not results:
        log.info("No health check results available")
        return

    log.info(f"\n{COLORS['header']}=== Health Status Summary ==={COLORS['reset']}\n")
    
    # Calculate column widths
    service_width = max(len(name) for name in results.keys())
    status_width = max(len(result.get("status", "")) for result in results.values())
    
    # Print header
    header = (
        f"{'Service':<{service_width}} | "
        f"{'Status':<{status_width}} | "
        f"{'Time':>6} | "
        f"Details"
    )
    log.info(header)
    log.info("-" * len(header))
    
    # Group results by status
    status_groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {
        "OK": [],
        "WARNING": [],
        "ERROR": [],
        "DOWN": [],
        "NOT CONFIGURED": [],
        "UNKNOWN": []
    }
    
    for service, result in sorted(results.items()):
        status = result.get("status", "UNKNOWN")
        status_groups.setdefault(status, []).append((service, result))
    
    # Print results by status group
    for status in ["OK", "WARNING", "ERROR", "DOWN", "NOT CONFIGURED", "UNKNOWN"]:
        for service, result in status_groups[status]:
            symbol = STATUS_SYMBOLS.get(status, STATUS_SYMBOLS["UNKNOWN"])
            elapsed = result.get("elapsed_time", 0)
            message = result.get("message", "No details")
            
            log.info(
                f"{service:<{service_width}} | "
                f"{symbol} {status:<{status_width-2}} | "
                f"{elapsed:>5.1f}s | "
                f"{message}"
            )
    
    # Print summary statistics
    log.info("\nSummary:")
    for status in status_groups:
        count = len(status_groups[status])
        if count > 0:
            symbol = STATUS_SYMBOLS.get(status, STATUS_SYMBOLS["UNKNOWN"])
            log.info(f"{symbol} {status}: {count}")
    
    log.info(f"\n{'=' * len(header)}\n")

# Re-export for app.py
# from .config import HEALTH_CHECK_INTERVAL # Already imported at the top