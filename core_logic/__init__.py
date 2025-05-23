"""Core logic package for chat processing."""

import sys
import os

# --- Robust Path Setup for Core Logic ---
# Ensures that the project root is in sys.path for sibling package imports (e.g., 'utils')
_core_logic_file_path = os.path.abspath(__file__)
_core_logic_dir_path = os.path.dirname(_core_logic_file_path)
_project_root_dir_path = os.path.dirname(_core_logic_dir_path) # Assumes core_logic is one level down from project root

if _project_root_dir_path not in sys.path:
    sys.path.insert(0, _project_root_dir_path)
    # print(f"DEBUG: Added project root '{_project_root_dir_path}' to sys.path in core_logic.__init__") # Optional debug
    print(f"DEBUG: sys.path in {__file__} after modification: {sys.path}") # ADDED FOR DEBUGGING
# --- End Robust Path Setup ---

from .constants import MAX_TOOL_CYCLES_OUTER # Example
from .agent_loop import start_streaming_response, run_async_generator
from .history_utils import _prepare_history_for_llm, HistoryResetRequiredError
from .llm_interactions import _perform_llm_interaction, _prepare_tool_definitions
from .tool_processing import _execute_tool_calls
from .tool_selector import ToolSelector # Added based on llm_interface import
import config as config_module

__all__ = [
    'start_streaming_response',
    'run_async_generator',
    '_prepare_history_for_llm',
    'HistoryResetRequiredError',
    '_perform_llm_interaction',
    '_prepare_tool_definitions',
    '_execute_tool_calls',
    'ToolSelector',
    'get_system_prompt',
]

def get_system_prompt(persona_name: str = "Default") -> str:
    """
    Get the system prompt for the specified persona.
    
    Args:
        persona_name: The name of the persona to get the system prompt for.
        
    Returns:
        The system prompt for the specified persona.
    """
    config = config_module.get_config()
    return config.get_system_prompt(persona_name)
