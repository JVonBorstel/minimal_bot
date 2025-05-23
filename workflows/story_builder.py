"""
Minimal Story Builder workflow implementation.
This is a stub implementation to allow the bot to start up.
The full story builder functionality can be implemented later as needed.
"""

from typing import AsyncIterable, Dict, Any
import logging

# Constants that are imported by agent_loop.py
STORY_BUILDER_WORKFLOW_TYPE = "story_builder"

log = logging.getLogger("workflows.story_builder")


async def handle_story_builder_workflow(
    llm: Any,
    tool_executor: Any,
    app_state: Any,
    config: Any
) -> AsyncIterable[Dict[str, Any]]:
    """
    Minimal stub implementation of the story builder workflow handler.
    
    This is a placeholder that yields a completion event.
    The full implementation would handle the story building workflow stages.
    
    Args:
        llm: LLM interface
        tool_executor: Tool executor instance
        app_state: Application state
        config: Configuration object
        
    Yields:
        Dict[str, Any]: Workflow events
    """
    log.info("Story builder workflow called (stub implementation)")
    
    # For now, just yield a simple completion message
    yield {
        'type': 'text_chunk',
        'content': 'Story builder workflow is not yet fully implemented in this minimal bot. '
                  'This is a placeholder response.'
    }
    
    yield {
        'type': 'completed',
        'content': {'status': 'WORKFLOW_COMPLETED'}
    }
    
    # Update app state to indicate workflow is complete
    if hasattr(app_state, 'last_interaction_status'):
        app_state.last_interaction_status = "WORKFLOW_COMPLETED" 