"""
Core logic for the agent's main interaction loop, including orchestrating
LLM calls, tool executions, and workflow management.
"""
import json
# import logging # Replaced by custom logging
import asyncio
import time # Added for timing
from typing import AsyncIterable, Dict, Any, Optional, TypeAlias, Union, List
import uuid

# Core Logic Imports
from .constants import (
    MAX_TOOL_CYCLES_OUTER,
    STATUS_ERROR_LLM,
    STATUS_MAX_CALLS_REACHED,
    STATUS_STORY_BUILDER_PREFIX,
    STATUS_THINKING,
    BREAK_ON_CRITICAL_TOOL_ERROR,
    STATUS_ERROR_TOOL,
    STATUS_ERROR_INTERNAL,
    TOOL_CALL_ID_PREFIX,
)
# Updated to use the new history preparation function
from .history_utils import prepare_messages_for_llm_from_appstate, HistoryResetRequiredError
from .llm_interactions import (
    _perform_llm_interaction, _prepare_tool_definitions
)
from .tool_processing import _execute_tool_calls  # This is async

# Project-level Imports
# Assuming these top-level modules are in PYTHONPATH or accessible
from state_models import AppState, WorkflowContext
# from llm_interface import LLMInterface  # This creates a circular import
from tools.tool_executor import ToolExecutor
from config import Config

from workflows.story_builder import handle_story_builder_workflow, STORY_BUILDER_WORKFLOW_TYPE
# Use a forward reference for LLMInterface to avoid circular imports
LLMInterface: TypeAlias = Any  # Will be resolved at runtime

from utils.logging_config import get_logger, start_llm_call, clear_llm_call_id, start_tool_call, clear_tool_call_id

log = get_logger("core_logic.agent_loop")


# Helper function to run an async generator and return all its items
def run_async_generator(async_gen: AsyncIterable[Any]) -> List[Any]:
    """
    Run an async generator synchronously and return all its items.
    
    Args:
        async_gen: The async generator to run
        
    Returns:
        A list containing all items yielded by the generator
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(_collect_async_gen(async_gen))
    finally:
        loop.close()

async def _collect_async_gen(async_gen: AsyncIterable[Any]) -> List[Any]:
    """Helper to collect all items from an async generator."""
    results = []
    async for item in async_gen:
        results.append(item)
    return results

# Copied from migration/chat_logic.py.new (lines 2169-2214)
def _determine_status_message(
    cycle_num: int,
    is_initial_decision_call: bool,
    stage_name: Optional[str]
) -> str:
    """
    Determines the appropriate status message based on interaction context.

    Args:
        cycle_num: Current interaction cycle number (0-indexed)
        is_initial_decision_call: Whether this is the first LLM call for user
            request
        stage_name: Current workflow stage name if in a workflow

    Returns:
        str: Formatted status message for display to the user
    """
    if is_initial_decision_call:
        if stage_name:
            # This was "dY c Planning..." in original, assuming it's a custom
            # status string
            return f"⚙️ Planning {stage_name.replace('_', ' ').title()} approach..."
        else:
            # This was "dY  Analyzing..." in original, maps to STATUS_THINKING
            # prefix
            return f"{STATUS_THINKING} Analyzing request and planning response..."
    elif stage_name:
        formatted_stage = stage_name.replace('_', ' ').title()
        # Use cycle_num+1 for 1-based display
        # cycle_num is 0-indexed stage_cycle
        step_info = f" (Step {cycle_num + 1})" if cycle_num > 0 else ""
        if stage_name == "collecting_info":
            return f"{STATUS_STORY_BUILDER_PREFIX}Gathering information{step_info}"
        elif stage_name == "detailing":
            return (
                f"{STATUS_STORY_BUILDER_PREFIX}Generating detailed "
                f"requirements{step_info}"
            )
        elif stage_name == "drafting_1":
            return f"{STATUS_STORY_BUILDER_PREFIX}Creating initial draft{step_info}"
        elif stage_name == "drafting_2":
            # Note: Original line was too long.
            return f"{STATUS_STORY_BUILDER_PREFIX}Refining draft{step_info}"
        elif stage_name in ("draft1_review", "draft2_review", "awaiting_confirmation"):
            # These stages typically wait for user, not LLM calls
            return (
                f"{STATUS_STORY_BUILDER_PREFIX}{formatted_stage} - Awaiting user "
                f"input"
            )
        elif stage_name == "creating_ticket":
            return f"{STATUS_STORY_BUILDER_PREFIX}Creating Jira ticket..."
        else:
            return f"{STATUS_STORY_BUILDER_PREFIX}{formatted_stage}{step_info}"
    else:
        # General non-workflow cycles
        if cycle_num == 0:  # cycle_num is 0-indexed general cycle
            return f"{STATUS_THINKING} Analyzing your request..."
        else:
            return (
                f"{STATUS_THINKING} Processing information "
                f"(Cycle {cycle_num + 1})"
            )

# Copied from migration/chat_logic.py.new (lines 2558-2940)
# and imports updated
async def start_streaming_response(
    app_state: AppState,
    llm: LLMInterface,
    tool_executor: ToolExecutor,
    config: Config
) -> AsyncIterable[Dict[str, Any]]:  # Async generator yields events
    """
    Starts a new response streaming process from the LLM + tools.
    Returns a generator of streaming events.

    Events have format: {'type': event_type, 'content': event_content}
    where event_type can be:
    - 'text_chunk': A chunk of text from the LLM
    - 'tool_calls': A list of tool calls requested by the LLM
    - 'tool_results': Results from tool execution
    - 'status': A status update for UI
    - 'error': Error information
    - 'completed': Indicates the streaming is complete
    """
    # Initialize streaming state
    start_time = time.perf_counter() # Record start time
    app_state.is_streaming = True
    app_state.streaming_placeholder_content = ""  # Reset placeholder for LLM text
    general_agent_cycle_num = 0  # For the outer tool use loop if not in a workflow
    # Max cycles for the general agent loop
    max_general_cycles = MAX_TOOL_CYCLES_OUTER

    # Get current workflow information for logging, if available
    active_workflow_type = None
    active_workflow_stage = None
    if app_state.active_workflows:
        # Assuming the first active workflow is the relevant one for this log
        # You might need a more sophisticated way to pick the 'current' one if multiple can be active
        # and relevant to the agent loop's context simultaneously.
        first_workflow_id = next(iter(app_state.active_workflows))
        active_workflow_instance = app_state.active_workflows[first_workflow_id]
        active_workflow_type = active_workflow_instance.workflow_type
        active_workflow_stage = active_workflow_instance.current_stage

    log.info(
        "Entering agent_loop.start_streaming_response",
        extra={
            "event_type": "agent_loop_start",
            "details": {
                "active_workflow_type": active_workflow_type,
                "active_workflow_stage": active_workflow_stage,
                "last_interaction_status": app_state.last_interaction_status,
                "message_count": len(app_state.messages),
                "session_id": app_state.session_id,
            }
        }
    )
    try:
        # Reset flags for new interaction
        app_state.current_step_error = None
        app_state.current_tool_execution_feedback = []  # Reset feedback for this turn
        app_state.last_interaction_status = "PROCESSING"
        log.debug("Initialized flags for new interaction.", extra={"event_type": "agent_loop_flags_reset"})

        # Ensure system prompt is in messages if defined and not already first
        system_prompt = config.get_system_prompt("Default")  # Use the config method to get system prompt
        if system_prompt:
            if not app_state.messages or \
               not (app_state.messages[0].role == "system" and \
                    app_state.messages[0].text == system_prompt):
                app_state.messages.insert(0, {"role": "system", "content": system_prompt})
                log.info("Prepended system prompt to messages.", extra={"event_type": "system_prompt_prepended"})
            elif app_state.messages[0].role == "system" and \
                 app_state.messages[0].text != system_prompt:
                app_state.messages[0].parts = [SafeTextPart(content=system_prompt)] # Assuming SafeTextPart is the correct type
                log.info("Updated existing system prompt in messages.", extra={"event_type": "system_prompt_updated"})

        # Check if this is a help command
        is_help_command = False
        latest_user_message = ""
        if app_state.messages and app_state.messages[-1].role == "user":
            latest_user_message = app_state.messages[-1].text.lower() if app_state.messages[-1].text else ""
            help_keywords = ["help", "what can you do", "show commands", "available tools"]
            is_help_command = any(keyword in latest_user_message for keyword in help_keywords)

        # Check for multi-tool workflow patterns
        from .workflow_orchestrator import detect_workflow_intent, WorkflowOrchestrator
        workflow_intent = detect_workflow_intent(latest_user_message) if latest_user_message else None
        
        if workflow_intent:
            log.info(f"Detected multi-tool workflow: {workflow_intent}", extra={"event_type": "workflow_intent_detected"})
            yield {'type': 'status', 'content': f"🔄 Orchestrating {workflow_intent} workflow..."}
            
            try:
                orchestrator = WorkflowOrchestrator(tool_executor, config)
                workflow_result = await orchestrator.execute_workflow(
                    workflow_intent, 
                    app_state
                )
                
                if workflow_result.success:
                    # Add the synthesized result as an assistant message
                    app_state.add_message("assistant", content=workflow_result.final_synthesis)
                    app_state.last_interaction_status = "COMPLETED_OK"
                    
                    yield {'type': 'text_chunk', 'content': workflow_result.final_synthesis}
                    yield {'type': 'completed', 'content': 'Workflow completed successfully'}
                    
                    log.info(f"Workflow {workflow_intent} completed successfully in {workflow_result.execution_time_ms}ms")
                    return
                else:
                    log.warning(f"Workflow {workflow_intent} failed: {workflow_result.final_synthesis}")
                    yield {'type': 'error', 'content': f"Workflow failed: {workflow_result.final_synthesis}"}
                    
            except Exception as e:
                log.error(f"Workflow orchestration failed: {e}", exc_info=True)
                yield {'type': 'error', 'content': f"Failed to execute workflow: {str(e)}"}
                app_state.last_interaction_status = "ERROR"
                return

        # Continue with existing workflow logic...

        # FIXED: Always provide ALL available tools to the LLM
        # For help commands, the LLM needs to see all tools to describe them to the user
        app_state.current_tool_definitions = tool_executor.get_available_tool_definitions()
        
        if is_help_command:
            log.info(f"Help command detected. Providing {len(app_state.current_tool_definitions)} tools to LLM for description.")
        
        # --- Check for and execute unresolved tool calls from previous model turn ---
        log.debug("Checking for unresolved tool calls from previous model turn.", extra={"event_type": "unresolved_tool_check_start"})
        unresolved_tool_calls_details = []
        if app_state.messages:
            last_assistant_msg_index = -1
            for i in range(len(app_state.messages) - 1, -1, -1):
                if app_state.messages[i].role == "assistant":
                    last_assistant_msg_index = i
                    break
            
            if last_assistant_msg_index != -1:
                last_assistant_msg = app_state.messages[last_assistant_msg_index]
                if last_assistant_msg.tool_calls:
                    log.debug(
                        "Last assistant message has tool_calls. Verifying responses.",
                        extra={
                            "event_type": "unresolved_tool_check_assistant_message",
                            "details": {"last_assistant_msg_index": last_assistant_msg_index, "tool_call_count": len(last_assistant_msg.tool_calls)}
                        }
                    )
                    original_model_tool_calls = last_assistant_msg.tool_calls
                    model_tool_call_ids = {tc.id for tc in original_model_tool_calls}
                    responded_tool_call_ids = set()
                    for i in range(last_assistant_msg_index + 1, len(app_state.messages)):
                        msg = app_state.messages[i]
                        if msg.role == "tool" and msg.tool_call_id in model_tool_call_ids:
                            responded_tool_call_ids.add(msg.tool_call_id)
                    pending_tool_call_ids = model_tool_call_ids - responded_tool_call_ids
                    if pending_tool_call_ids:
                        unresolved_tool_calls_details = [tc for tc in original_model_tool_calls if tc.id in pending_tool_call_ids]
                        log.info(
                            f"Found {len(unresolved_tool_calls_details)} unresolved tool calls.",
                            extra={
                                "event_type": "unresolved_tool_calls_found",
                                "details": {"count": len(unresolved_tool_calls_details), "ids": [tc.id for tc in unresolved_tool_calls_details]}
                            }
                        )
        if unresolved_tool_calls_details:
            status_update_msg = "Executing pending tool calls from previous turn..."
            log.info(status_update_msg, extra={"event_type": "pending_tool_execution_start"})
            yield {'type': 'status', 'content': status_update_msg}
            app_state.current_status_message = status_update_msg
            
            exec_tool_defs = tool_executor.get_available_tool_definitions()
            log.debug(
                f"Using {len(exec_tool_defs)} available tool definitions for pending execution.",
                extra={"event_type": "pending_tool_definitions_loaded", "details": {"count": len(exec_tool_defs)}}
            )
            
            pending_tool_call_batch_id = start_tool_call()
            try:
                pending_tool_results, pending_internal_msgs, pending_critical_err, pending_updated_calls = \
                    await _execute_tool_calls(
                        unresolved_tool_calls_details,
                        tool_executor,
                        app_state.previous_tool_calls,
                        app_state,
                        config,
                        exec_tool_defs
                    )
            finally:
                clear_tool_call_id()

            app_state.previous_tool_calls = pending_updated_calls
            log.debug(
                "Updated previous_tool_calls after pending execution.",
                extra={"event_type": "previous_tool_calls_updated", "details": {"count": len(app_state.previous_tool_calls)}}
            )

            for msg_dict in pending_tool_results:
                log.debug(
                    "Adding pending tool result to app_state.messages.",
                    extra={
                        "event_type": "pending_tool_result_added_to_history",
                        "details": {"role": msg_dict.get('role'), "name": msg_dict.get('name'), "tool_call_id": msg_dict.get('tool_call_id'), "is_error": msg_dict.get('is_error', False)}
                    }
                )
                app_state.add_message(**msg_dict)
            for msg_dict in pending_internal_msgs:
                log.debug(
                    "Adding pending internal message to app_state.messages.",
                     extra={
                         "event_type": "pending_internal_message_added_to_history",
                         "details": {"role": msg_dict.get('role'), "message_type": msg_dict.get('message_type'), "content_preview": str(msg_dict.get('content'))[:100]}
                     }
                )
                app_state.add_message(**msg_dict)
            
            yield {'type': 'tool_results', 'content': pending_tool_results}
            app_state.streaming_placeholder_content = ""

            if pending_critical_err:
                error_detail = "Critical tool failure during pending execution."
                for res_msg in pending_tool_results:
                    if res_msg.get("is_error"):
                        try:
                            error_content_str = res_msg.get("content", "{}")
                            error_payload = json.loads(error_content_str) if isinstance(error_content_str, str) else error_content_str
                            if isinstance(error_payload, dict):
                                error_detail = error_payload.get("message", error_detail)
                        except (json.JSONDecodeError, TypeError): pass
                        break
                log.error(
                    "Critical error during execution of pending tool calls. Ending turn.",
                    extra={"event_type": "pending_tool_critical_error", "details": {"error_detail": error_detail}}
                )
                app_state.current_step_error = error_detail
                app_state.last_interaction_status = STATUS_ERROR_TOOL
                app_state.current_status_message = f"{STATUS_ERROR_TOOL}: {error_detail}"
                yield {'type': 'status', 'content': app_state.current_status_message}
                yield {'type': 'error', 'content': error_detail}
                yield {'type': 'completed', 'content': {'status': app_state.last_interaction_status}}
                return
        else:
            log.debug("No unresolved tool calls found from previous model turn.", extra={"event_type": "unresolved_tool_check_none_found"})
        # --- End of unresolved tool call handling ---

        primary_workflow_id_to_run: Optional[str] = None
        primary_workflow_instance_to_run: Optional[WorkflowContext] = None

        active_sb_workflow_id: Optional[str] = None
        active_sb_instance: Optional[WorkflowContext] = None

        if app_state.active_workflows:
            for wf_id, wf_ctx in app_state.active_workflows.items():
                if wf_ctx.workflow_type == STORY_BUILDER_WORKFLOW_TYPE and wf_ctx.status == "active":
                    active_sb_workflow_id = wf_id
                    active_sb_instance = wf_ctx
                    log.info(
                        f"Found active Story Builder workflow (ID: {active_sb_workflow_id}, Stage: {active_sb_instance.current_stage}). Attempting to handle.",
                        extra={
                            "event_type": "active_story_builder_workflow_found",
                            "details": {
                                "workflow_id": active_sb_workflow_id,
                                "current_stage": active_sb_instance.current_stage
                            }
                        }
                    )
                    break # Handle the first active Story Builder workflow found

        if active_sb_instance and active_sb_instance.current_stage: # If a Story Builder workflow is active
            log.info(
                f"Entering Story Builder workflow handler for workflow ID: {active_sb_workflow_id}, Stage: {active_sb_instance.current_stage}.",
                extra={
                    "event_type": "story_builder_workflow_handler_enter",
                    "details": {
                        "workflow_id": active_sb_workflow_id,
                        "workflow_type": active_sb_instance.workflow_type, # Should be STORY_BUILDER_WORKFLOW_TYPE
                        "current_stage": active_sb_instance.current_stage
                    }
                }
            )
            # handle_story_builder_workflow is imported at the top of the file
            async for event_dict_wf in handle_story_builder_workflow(
                llm=llm,
                tool_executor=tool_executor,
                app_state=app_state,
                config=config
                # scratchpad_memory and previous_tool_calls are accessed from app_state by the handler
            ):
                yield event_dict_wf
            # The rest of the logic (checking app_state.last_interaction_status, etc.)
            # starting from original line 364 will continue after this block
            if app_state.last_interaction_status == "WAITING_USER_INPUT" or \
               app_state.last_interaction_status.startswith("WORKFLOW_COMPLETED") or \
               app_state.last_interaction_status.startswith("WORKFLOW_ERROR") or \
               app_state.last_interaction_status == "HISTORY_RESET_REQUIRED" or \
               app_state.last_interaction_status == "WORKFLOW_MAX_CYCLES" or \
               app_state.last_interaction_status == "WORKFLOW_UNEXPECTED_ERROR":
                log.info(
                    "Workflow ended turn. Concluding streaming response.",
                    extra={"event_type": "workflow_turn_concluded", "details": {"status": app_state.last_interaction_status}}
                )
                yield {'type': 'completed', 'content': {'status': app_state.last_interaction_status}}
                return
            if primary_workflow_instance_to_run and primary_workflow_instance_to_run.current_stage:
                 log.warning(
                    "Workflow stage completed its generator run for this turn. Workflow still active, proceeding to general agent loop if necessary.",
                    extra={
                        "event_type": "workflow_stage_yielded_control",
                        "details": {
                            "workflow_type": primary_workflow_instance_to_run.workflow_type,
                            "current_stage": primary_workflow_instance_to_run.current_stage,
                            "status": app_state.last_interaction_status
                        }
                    }
                )
            else:
                 log.info(
                    "Workflow processing concluded or no primary workflow was run this turn. Proceeding to general agent logic if applicable.",
                    extra={"event_type": "workflow_processing_concluded_no_primary", "details": {"last_status": app_state.last_interaction_status}}
                )
        else:
            log.info(
                "No active workflow, or workflow concluded. Entering general agent loop.",
                extra={"event_type": "general_agent_loop_enter_no_workflow", "details": {"last_status": app_state.last_interaction_status}}
            )
 
        accumulated_llm_text_this_turn = ""
        tool_executed_successfully_in_previous_cycle = False # Tracks if tools ran successfully in the prior cycle
 
        # General Agent Loop
        while general_agent_cycle_num < max_general_cycles:
            log.info(
                "General Agent Cycle starting.",
                extra={
                    "event_type": "general_agent_cycle_start",
                    "details": {"cycle_num": general_agent_cycle_num + 1, "max_cycles": max_general_cycles}
                }
            )
            is_initial_llm_call_this_cycle = (general_agent_cycle_num == 0)
            provide_tools_for_this_llm_call = not tool_executed_successfully_in_previous_cycle
            
            if tool_executed_successfully_in_previous_cycle:
                log.info(
                    "Tools were successfully executed in the previous cycle. Forcing text-only response from LLM.",
                    extra={"event_type": "general_agent_force_text_response"}
                )
            
            current_tool_definitions = _prepare_tool_definitions(
                tool_executor.get_available_tool_definitions(),
                is_initial_decision_call=is_initial_llm_call_this_cycle,
                provide_tools=provide_tools_for_this_llm_call,
                user_query=app_state.messages[-1].text if app_state.messages and app_state.messages[-1].role == "user" else None,
                config=config,
                app_state=app_state
            )
            log.debug(
                "Tool definitions prepared for LLM.",
                extra={"event_type": "general_agent_tool_definitions_prepared", "details": {"count": len(current_tool_definitions) if current_tool_definitions else 0}}
            )

            log.debug(
                "Preparing history for LLM.",
                extra={"event_type": "general_agent_history_preparation_start", "details": {"message_count": len(app_state.messages)}}
            )
            current_llm_history, history_errors = prepare_messages_for_llm_from_appstate(
                app_state, max_history_items=config.MAX_HISTORY_MESSAGES
            )
            log.debug(
                "History prepared for LLM.",
                extra={
                    "event_type": "general_agent_history_preparation_end",
                    "details": {"glm_history_items": len(current_llm_history), "preparation_errors": len(history_errors)}
                }
            )

            if history_errors:
                log.warning(
                    "History preparation issues found.",
                    extra={"event_type": "history_preparation_warning", "details": {"error_count": len(history_errors), "errors": history_errors[:3]}}
                )
                is_critical_history_error = any("History ends prematurely" in e or "History sequence error" in e or "must be followed by" in e for e in history_errors)
                if is_critical_history_error:
                    err_content = f"A critical error occurred with the conversation history: {history_errors[0]}. This may require a reset or a new conversation. Please try again."
                    log.error(
                        "Critical history preparation error.",
                        extra={"event_type": "critical_history_error", "details": {"error_message": history_errors[0]}}
                    )
                    yield {'type': 'error', 'content': err_content}
                    log.debug("Adding critical history error message to app_state.messages.", extra={"event_type": "add_message_history_error"})
                    app_state.add_message("assistant", f"[System Error: {err_content}]", is_error=True)
                    app_state.last_interaction_status = "CRITICAL_HISTORY_ERROR"
                    app_state.current_status_message = "Critical History Error"
                    yield {'type': 'status', 'content': app_state.current_status_message}
                    break

            status_msg = _determine_status_message(general_agent_cycle_num, is_initial_llm_call_this_cycle, stage_name=None)
            app_state.current_status_message = status_msg
            yield {'type': 'status', 'content': status_msg}
            
            llm_text_parts_general = []
            tool_calls_requested_general = []
            llm_debug_info_general = None
            llm_stream_error_general = False

            log.debug(
                "Performing LLM interaction.",
                extra={
                    "event_type": "llm_interaction_start",
                    "details": {"history_items": len(current_llm_history), "tool_definitions_count": len(current_tool_definitions) if current_tool_definitions else 0}
                }
            )
            
            current_llm_call_id = start_llm_call()
            try:
                llm_stream_iter_general = _perform_llm_interaction(
                    current_llm_history=current_llm_history,
                    available_tool_definitions=current_tool_definitions,
                    llm=llm,
                    cycle_num=general_agent_cycle_num,
                    app_state=app_state,
                    is_initial_decision_call=is_initial_llm_call_this_cycle,
                    stage_name=None,
                    config=config
                )
                for event_type_llm, event_data_llm in llm_stream_iter_general:
                    if event_type_llm == "text":
                        llm_text_parts_general.append(event_data_llm)
                        yield {'type': 'text_chunk', 'content': event_data_llm}
                    elif event_type_llm == "tool_calls":
                        tool_calls_requested_general = event_data_llm
                        log.info(
                            f"LLM requested {len(tool_calls_requested_general)} tool calls.",
                            extra={
                                "event_type": "llm_tool_calls_requested",
                                "details": {"count": len(tool_calls_requested_general), "tool_names": [tc.get('function', {}).get('name') for tc in tool_calls_requested_general]}
                            }
                        )
                    elif event_type_llm == "debug_info":
                        llm_debug_info_general = event_data_llm
                        log.debug(
                            "LLM debug info received.",
                            extra={"event_type": "llm_debug_info", "details": llm_debug_info_general}
                        )
                        if llm_debug_info_general and llm_debug_info_general.get("error"):
                            llm_stream_error_general = True
            finally:
                clear_llm_call_id()
            
            current_llm_text_output = "".join(llm_text_parts_general)
            accumulated_llm_text_this_turn += current_llm_text_output
            log.debug(
                "LLM interaction yielded results.",
                extra={
                    "event_type": "llm_interaction_results",
                    "details": {"text_length": len(current_llm_text_output), "tool_call_count": len(tool_calls_requested_general)}
                }
            )

            if llm_stream_error_general:
                error_detail_from_llm = "LLM interaction failed."
                if llm_debug_info_general and llm_debug_info_general.get("error"):
                    error_detail_from_llm = f"LLM Error: {llm_debug_info_general.get('error_type', 'Unknown')}: {llm_debug_info_general.get('error', 'No details')}"
                log.error(
                    "LLM stream failed.",
                    extra={"event_type": "llm_stream_failure", "details": {"error_detail": error_detail_from_llm, "last_text_preview": current_llm_text_output[:100]}}
                )
                user_facing_llm_error = "I encountered an issue trying to generate a response. Please try again."
                if "API key not valid" in error_detail_from_llm:
                    user_facing_llm_error = "There's an issue with the AI service configuration. Please contact support."
                app_state.current_status_message = f"{STATUS_ERROR_LLM}: Generation failed."
                app_state.current_step_error = error_detail_from_llm
                yield {'type': 'status', 'content': app_state.current_status_message}
                yield {'type': 'error', 'content': user_facing_llm_error}
                log.debug("Adding LLM stream error message to app_state.messages.", extra={"event_type": "add_message_llm_error"})
                app_state.add_message("assistant", f"[System Error: {user_facing_llm_error}]", is_error=True)
                app_state.last_interaction_status = "LLM_FAILURE"
                break

            if not current_llm_text_output and not tool_calls_requested_general:
                log.warning("LLM produced no content or tool calls. Ending turn.", extra={"event_type": "llm_empty_response"})
                app_state.last_interaction_status = "COMPLETED_EMPTY"
                if general_agent_cycle_num == 0 and (not app_state.messages or app_state.messages[-1].role != "assistant"):
                    log.debug("Adding 'LLM returned no response' message to app_state.messages.", extra={"event_type": "add_message_llm_no_response"})
                    app_state.add_message("assistant", "[LLM returned no response]", is_internal=True)
                break

            if tool_calls_requested_general:
                assistant_message_content = current_llm_text_output if current_llm_text_output else "Okay, I need to use some tools."
                log.debug(
                    "Adding assistant message with tool_calls to app_state.messages.",
                    extra={
                        "event_type": "add_message_assistant_tool_call",
                        "details": {"tool_names": [tc.get('function', {}).get('name') for tc in tool_calls_requested_general], "text_preview": assistant_message_content[:100]}
                    }
                )
                app_state.add_message("assistant", assistant_message_content, tool_calls=tool_calls_requested_general)
                accumulated_llm_text_this_turn = ""
                
                yield {'type': 'tool_calls', 'content': tool_calls_requested_general}
                log.debug("Yielded tool_calls event.", extra={"event_type": "yield_tool_calls_event", "details": {"tool_call_count": len(tool_calls_requested_general)}})

                workflow_trigger_call_details = None
                if is_initial_llm_call_this_cycle:
                    for tc in tool_calls_requested_general:
                        if tc.get("function", {}).get("name") == "start_story_builder_workflow":
                            workflow_trigger_call_details = tc
                            break
                
                if workflow_trigger_call_details:
                    log.info(
                        "Detected Story Builder trigger. Initializing workflow.",
                        extra={"event_type": "workflow_trigger_detected", "details": {"tool_name": workflow_trigger_call_details['function']['name']}}
                    )
                    yield {'type': 'status', 'content': f"{STATUS_STORY_BUILDER_PREFIX}Initializing..."}
                    
                    trigger_tool_call_batch_id = start_tool_call()
                    try:
                        trigger_results, trigger_internal_msgs, trigger_tool_err, updated_prev_calls_after_trigger = \
                            await _execute_tool_calls(
                                [workflow_trigger_call_details], tool_executor, app_state.previous_tool_calls,
                                app_state, config, current_tool_definitions
                            )
                    finally:
                        clear_tool_call_id()
                    log.debug(
                        "Workflow trigger tool execution completed.",
                        extra={
                            "event_type": "workflow_trigger_tool_execution_end",
                            "details": {"critical_error": trigger_tool_err, "results_count": len(trigger_results), "internal_msgs_count": len(trigger_internal_msgs)}
                        }
                    )
                    app_state.previous_tool_calls = updated_prev_calls_after_trigger
                    log.debug(
                        "Updated previous_tool_calls after workflow trigger.",
                        extra={"event_type": "previous_tool_calls_updated_workflow_trigger", "details": {"count": len(app_state.previous_tool_calls)}}
                    )

                    for msg_dict in trigger_results:
                        log.debug("Adding workflow trigger tool result to app_state.messages.", extra={"event_type": "add_message_workflow_trigger_result", "details": msg_dict})
                        app_state.add_message(**msg_dict)
                    for msg_dict in trigger_internal_msgs:
                        log.debug("Adding workflow trigger internal message to app_state.messages.", extra={"event_type": "add_message_workflow_trigger_internal", "details": msg_dict})
                        app_state.add_message(**msg_dict)
                    yield {'type': 'tool_results', 'content': trigger_results}
                    log.debug("Yielded tool_results event for workflow trigger.", extra={"event_type": "yield_tool_results_workflow_trigger", "details": {"results_count": len(trigger_results)}})

                    try:
                        workflow_started_successfully = False
                        newly_started_workflow_id: Optional[str] = None
                        user_facing_workflow_error: Optional[str] = None

                        # Check if the trigger tool (start_story_builder_workflow) executed without framework error
                        if not trigger_tool_err and trigger_results and isinstance(trigger_results, list) and len(trigger_results) > 0:
                            first_result = trigger_results[0]
                            if isinstance(first_result, dict) and not first_result.get("is_error"):
                                tool_output_str: Optional[str] = None
                                # Extract the actual output string from the tool
                                if "content" in first_result: # Standard format
                                    tool_output_str = first_result.get("content")
                                elif "parts" in first_result and isinstance(first_result["parts"], list) and first_result["parts"]:
                                    part = first_result["parts"][0]
                                    if isinstance(part, dict):
                                        if "output" in part: # Greptile-like structure
                                            tool_output_str = part.get("output")
                                        elif "function_response" in part and isinstance(part["function_response"], dict): # Gemini structure
                                            response_val = part["function_response"].get("response")
                                            if isinstance(response_val, str): tool_output_str = response_val
                                            elif isinstance(response_val, dict) and "result" in response_val: tool_output_str = response_val.get("result")

                                if tool_output_str and isinstance(tool_output_str, str):
                                    try:
                                        parsed_tool_result = json.loads(tool_output_str)
                                        if isinstance(parsed_tool_result, dict):
                                            if parsed_tool_result.get("status") == "success":
                                                newly_started_workflow_id = parsed_tool_result.get("workflow_id")
                                                if newly_started_workflow_id and newly_started_workflow_id in app_state.active_workflows and \
                                                   app_state.active_workflows[newly_started_workflow_id].workflow_type == STORY_BUILDER_WORKFLOW_TYPE:
                                                    workflow_started_successfully = True
                                                    log.info(
                                                        f"Story Builder workflow successfully started by tool. ID: {newly_started_workflow_id}",
                                                        extra={"event_type": "workflow_tool_start_success", "details": {"workflow_id": newly_started_workflow_id}}
                                                    )
                                                else:
                                                    user_facing_workflow_error = f"Workflow tool reported success but workflow ID '{newly_started_workflow_id}' is invalid, not found, or wrong type."
                                                    log.error(
                                                        user_facing_workflow_error,
                                                        extra={"event_type": "workflow_tool_start_id_error", "details": {"returned_id": newly_started_workflow_id, "active_ids": list(app_state.active_workflows.keys())}}
                                                    )
                                            else: # Tool returned status other than "success"
                                                user_facing_workflow_error = parsed_tool_result.get("message", "Story Builder workflow failed to start.")
                                                log.warning(
                                                    f"Tool '{workflow_trigger_call_details.get('function',{}).get('name')}' failed or returned unexpected status: {user_facing_workflow_error}",
                                                    extra={"event_type": "workflow_tool_start_failed_status", "details": {"tool_result": parsed_tool_result}}
                                                )
                                        else: # Parsed JSON is not a dict
                                            user_facing_workflow_error = "Workflow tool returned malformed success data."
                                            log.error(f"{user_facing_workflow_error} Parsed: {parsed_tool_result}", extra={"event_type": "workflow_tool_malformed_data"})
                                    except json.JSONDecodeError:
                                        user_facing_workflow_error = "Failed to parse response from workflow start tool."
                                        log.error(f"{user_facing_workflow_error} Raw: '{tool_output_str}'", exc_info=True, extra={"event_type": "workflow_tool_json_error"})
                                else: # tool_output_str is None or not a string
                                    user_facing_workflow_error = "Workflow start tool returned no valid output string."
                                    log.warning(f"{user_facing_workflow_error} Result structure: {first_result}", extra={"event_type": "workflow_tool_no_output_string"})
                            else: # first_result.get("is_error") is True or result malformed
                                user_facing_workflow_error = "Error reported by the workflow start tool's execution framework."
                                log.warning(f"{user_facing_workflow_error} Result: {first_result}", extra={"event_type": "workflow_tool_framework_error"})
                                if isinstance(first_result, dict) and first_result.get("content"):
                                    user_facing_workflow_error += f" Details: {str(first_result.get('content'))[:100]}"
                        elif trigger_tool_err: # Critical error from _execute_tool_calls itself
                            user_facing_workflow_error = "A critical error occurred while trying to execute the workflow start tool."
                            log.error(user_facing_workflow_error, extra={"event_type": "workflow_tool_critical_exec_error"})
                        else: # No results or malformed results from _execute_tool_calls
                            user_facing_workflow_error = "No valid result from workflow start tool execution."
                            log.warning(user_facing_workflow_error, extra={"event_type": "workflow_tool_no_valid_result_from_exec", "details": {"trigger_results": trigger_results}})

                        # If workflow did not start successfully, inform user and app_state
                        if not workflow_started_successfully and user_facing_workflow_error:
                            yield {'type': 'error', 'content': user_facing_workflow_error}
                            app_state.add_message("assistant", f"[Workflow Error: {user_facing_workflow_error}]", is_error=True)
                            app_state.current_status_message = f"Workflow Error: {user_facing_workflow_error[:50]}..."
                            yield {'type': 'status', 'content': app_state.current_status_message}
                        
                        # If workflow started successfully, proceed to handle it for this turn
                        if workflow_started_successfully and newly_started_workflow_id:
                            log.info(
                                f"Newly started Story Builder workflow (ID: {newly_started_workflow_id}) will now be handled.",
                                extra={"event_type": "handle_newly_started_workflow", "details": {"workflow_id": newly_started_workflow_id}}
                            )
                            # handle_story_builder_workflow is imported at the top of the file.
                            async for event_dict_wf in handle_story_builder_workflow(
                                llm=llm,
                                tool_executor=tool_executor,
                                app_state=app_state,
                                config=config
                            ):
                                yield event_dict_wf
                            
                            ran_workflow_instance = app_state.active_workflows.get(newly_started_workflow_id)
                            
                            if not ran_workflow_instance or ran_workflow_instance.status != "active" or \
                               app_state.last_interaction_status == "WAITING_USER_INPUT" or \
                               app_state.last_interaction_status.startswith("WORKFLOW_COMPLETED") or \
                               app_state.last_interaction_status.startswith("WORKFLOW_ERROR") or \
                               app_state.last_interaction_status == "HISTORY_RESET_REQUIRED" or \
                               app_state.last_interaction_status == "WORKFLOW_MAX_CYCLES" or \
                               app_state.last_interaction_status == "WORKFLOW_UNEXPECTED_ERROR":
                                log.info(
                                    f"Story Builder workflow (ID: {newly_started_workflow_id}, started by trigger) ended turn. Concluding streaming response.",
                                    extra={"event_type": "workflow_trigger_turn_concluded", "details": {"workflow_id": newly_started_workflow_id, "status": app_state.last_interaction_status}}
                                )
                                if ran_workflow_instance and ran_workflow_instance.status != "active":
                                    if newly_started_workflow_id in app_state.active_workflows:
                                        app_state.completed_workflows.append(app_state.active_workflows.pop(newly_started_workflow_id))
                                        log.info(f"Moved workflow {newly_started_workflow_id} to completed_workflows after triggered run.", extra={"event_type": "workflow_moved_to_completed_trigger", "details": {"workflow_id": newly_started_workflow_id}})
                                yield {'type': 'completed', 'content': {'status': app_state.last_interaction_status}}
                                return
                        # If workflow_started_successfully was false, errors were already yielded by the preceding block.
                        # The agent loop will then continue to the next cycle or break.
                    except Exception as wf_init_e:
                        log.error(f"Error during Story Builder workflow trigger processing or execution: {wf_init_e}", exc_info=True, extra={"event_type": "workflow_init_error_story_builder", "details": {"error": str(wf_init_e)}})
                        yield {'type': 'error', 'content': f"Failed to start or handle Story Builder workflow: {wf_init_e}"}
                        app_state.add_message("assistant", f"[Error processing workflow trigger: {wf_init_e}]", is_error=True)
                        app_state.last_interaction_status = "ERROR" # General error status
                        break # Break from the while general_agent_cycle_num < max_general_cycles loop
                    else:
                        log.warning("Story Builder trigger tool execution failed or errored. Workflow not started.", extra={"event_type": "workflow_trigger_tool_failed"})
                    general_agent_cycle_num += 1
                    continue
                
                general_tool_call_batch_id = start_tool_call()
                try:
                    tool_results_general, internal_msgs_general, has_critical_err_general, updated_calls_general = \
                        await _execute_tool_calls(
                            tool_calls_requested_general, tool_executor, app_state.previous_tool_calls,
                            app_state, config, current_tool_definitions
                        )
                finally:
                    clear_tool_call_id()
                log.info(
                    "General tool execution completed.",
                    extra={
                        "event_type": "general_tool_execution_end",
                        "details": {"critical_error": has_critical_err_general, "results_count": len(tool_results_general), "internal_msgs_count": len(internal_msgs_general)}
                    }
                )
                log.debug("Tool results details.", extra={"event_type": "general_tool_results_details", "details": tool_results_general})
                app_state.previous_tool_calls = updated_calls_general
                log.debug(
                    "Updated previous_tool_calls after general execution.",
                    extra={"event_type": "previous_tool_calls_updated_general", "details": {"count": len(app_state.previous_tool_calls)}}
                )
                for msg_dict in tool_results_general:
                    log.debug("Adding general tool result to app_state.messages.", extra={"event_type": "add_message_general_tool_result", "details": msg_dict})
                    app_state.add_message(**msg_dict)
                for msg_dict in internal_msgs_general:
                    log.debug("Adding general internal message to app_state.messages.", extra={"event_type": "add_message_general_internal", "details": msg_dict})
                    app_state.add_message(**msg_dict)
                yield {'type': 'tool_results', 'content': tool_results_general}
                log.debug("Yielded tool_results event for general tools.", extra={"event_type": "yield_tool_results_general", "details": {"results_count": len(tool_results_general)}})
                app_state.streaming_placeholder_content = ""
                if has_critical_err_general:
                    log.warning("Critical tool error encountered. Breaking agent cycle.", extra={"event_type": "general_tool_critical_error"})
                    app_state.last_interaction_status = STATUS_ERROR_TOOL
                    specific_error_detail = "Critical tool failure occurred."
                    if tool_results_general:
                        for tool_msg_dict in tool_results_general:
                            if tool_msg_dict.get("is_error"):
                                try:
                                    error_content_str = tool_msg_dict.get("content", "{}")
                                    error_payload = json.loads(error_content_str) if isinstance(error_content_str, str) else error_content_str
                                    if isinstance(error_payload, dict):
                                        specific_error_detail = error_payload.get("message") or error_payload.get("error") or specific_error_detail
                                except (json.JSONDecodeError, TypeError): pass
                                break
                    app_state.current_step_error = specific_error_detail
                    app_state.current_status_message = f"{STATUS_ERROR_TOOL}: {app_state.current_step_error}"
                    yield {'type': 'status', 'content': app_state.current_status_message}
                    yield {'type': 'error', 'content': specific_error_detail}
                    tool_executed_successfully_in_previous_cycle = False
                    break
                
                all_tools_succeeded_without_any_errors = True
                if not tool_results_general and tool_calls_requested_general:
                    all_tools_succeeded_without_any_errors = False
                    log.warning("Tools were requested by LLM, but no tool results were generated by executor.", extra={"event_type": "tool_request_no_results"})
                elif tool_calls_requested_general:
                    for res_msg in tool_results_general:
                        if res_msg.get("is_error"):
                            all_tools_succeeded_without_any_errors = False
                            log.warning(f"Tool {res_msg.get('name', 'Unknown')} reported an error.", extra={"event_type": "tool_execution_error_reported", "details": {"tool_name": res_msg.get('name', 'Unknown')}})
                            break
                else:
                    all_tools_succeeded_without_any_errors = False

                if all_tools_succeeded_without_any_errors:
                    tool_executed_successfully_in_previous_cycle = True
                    log.info("All tools in this cycle executed successfully without errors.", extra={"event_type": "all_tools_succeeded"})
                else:
                    tool_executed_successfully_in_previous_cycle = False
                    if tool_calls_requested_general:
                         log.info("Not all tools executed successfully or no tools were run. Will allow tools in next LLM call if loop continues.", extra={"event_type": "some_tools_failed_or_not_run"})
                general_agent_cycle_num += 1
                continue
            else: # LLM provided text and no tool calls
                tool_executed_successfully_in_previous_cycle = False
                if current_llm_text_output:
                    if not app_state.messages or app_state.messages[-1].role != "assistant" or app_state.messages[-1].text != current_llm_text_output:
                        log.debug(
                            "Adding assistant message with final text to app_state.messages.",
                            extra={"event_type": "add_message_assistant_final_text", "details": {"text_preview": current_llm_text_output[:100]}}
                        )
                        app_state.add_message("assistant", content=current_llm_text_output)
                    if app_state.last_interaction_status == STATUS_ERROR_TOOL and not current_llm_text_output:
                        log.info(f"LLM provided no text after non-critical tool errors. Maintaining {STATUS_ERROR_TOOL} status.", extra={"event_type": "llm_no_text_after_tool_error"})
                    else:
                        app_state.last_interaction_status = "COMPLETED_OK"
                        log.info("LLM provided text output. Setting status to COMPLETED_OK.", extra={"event_type": "llm_text_output_completed_ok"})
                elif app_state.last_interaction_status == STATUS_ERROR_TOOL:
                    log.info(f"LLM provided no text or tools after non-critical tool errors. Maintaining {STATUS_ERROR_TOOL} status.", extra={"event_type": "llm_no_text_or_tools_after_tool_error"})
                else:
                    app_state.last_interaction_status = "COMPLETED_EMPTY"
                    log.info("LLM provided no text and no tools. Setting status to COMPLETED_EMPTY.", extra={"event_type": "llm_no_text_no_tools_completed_empty"})
                
                final_status_msg = "Response generated."
                if app_state.last_interaction_status == "COMPLETED_OK": final_status_msg = "Response generated."
                elif app_state.last_interaction_status == STATUS_ERROR_TOOL: final_status_msg = f"{STATUS_ERROR_TOOL}: {app_state.current_step_error or 'Tool execution failed.'}"
                elif app_state.last_interaction_status == "COMPLETED_EMPTY": final_status_msg = "No further response generated."
                else: final_status_msg = f"Processing complete: {app_state.last_interaction_status}"

                app_state.current_status_message = final_status_msg
                log.debug("Yielding final status for UI.", extra={"event_type": "yield_final_status_ui", "details": {"status_message": final_status_msg}})
                yield {'type': 'status', 'content': final_status_msg}
                break

        if general_agent_cycle_num >= max_general_cycles:
            tool_executed_successfully_in_previous_cycle = False
            log.warning(
                f"Reached maximum general agent cycles ({max_general_cycles}). Ending turn.",
                extra={"event_type": "max_agent_cycles_reached", "details": {"max_cycles": max_general_cycles}}
            )
            app_state.last_interaction_status = STATUS_MAX_CALLS_REACHED
            status_msg_max_cycles = STATUS_MAX_CALLS_REACHED
            user_message_max_cycles = "I've reached the maximum processing steps for this request. If you need further assistance, please try rephrasing or starting a new topic."
            final_assistant_text_max_cycles = accumulated_llm_text_this_turn
            if final_assistant_text_max_cycles: final_assistant_text_max_cycles += f"\n\n[{user_message_max_cycles}]"
            else: final_assistant_text_max_cycles = f"[{user_message_max_cycles}]"

            if not app_state.messages or app_state.messages[-1].text != final_assistant_text_max_cycles:
                 log.debug(
                     "Adding max_cycles message to app_state.messages.",
                     extra={"event_type": "add_message_max_cycles", "details": {"text_preview": final_assistant_text_max_cycles[:100]}}
                 )
                 app_state.add_message("assistant", content=final_assistant_text_max_cycles)
            yield {'type': 'error', 'content': user_message_max_cycles}
            app_state.current_status_message = status_msg_max_cycles
            log.debug("Yielding status for max_cycles.", extra={"event_type": "yield_status_max_cycles", "details": {"status_message": status_msg_max_cycles}})
            yield {'type': 'status', 'content': status_msg_max_cycles}

        log.info(
            "General agent processing finished.",
            extra={"event_type": "general_agent_processing_end", "details": {"final_status": app_state.last_interaction_status}}
        )
        yield {'type': 'completed', 'content': {'status': app_state.last_interaction_status}}

    except HistoryResetRequiredError as reset_e:
        reset_msg_for_user = f"A problem occurred with the conversation history ({str(reset_e)[:100]}...). The history has been reset. Please try your request again."
        log.warning("HistoryResetRequiredError caught in agent_loop.", exc_info=True, extra={"event_type": "history_reset_error_agent_loop", "details": {"error": str(reset_e)}})
        app_state.last_interaction_status = "HISTORY_RESET_REQUIRED"
        app_state.current_status_message = "Conversation History Reset"
        app_state.current_step_error = str(reset_e)
        try:
            last_msg_content = app_state.messages[-1].text if app_state.messages else ""
            if "history has been reset" not in last_msg_content.lower():
                 log.debug("Adding history reset error message to app_state.messages.", extra={"event_type": "add_message_history_reset_error_agent_loop"})
                 app_state.add_message("assistant", f"[System: {reset_msg_for_user}]", is_error=True)
        except Exception as add_msg_e:
            log.error("Could not add history reset message to app_state.", exc_info=True, extra={"event_type": "add_message_history_reset_failed", "details": {"error": str(add_msg_e)}})
        yield {'type': 'error', 'content': reset_msg_for_user}
        yield {'type': 'status', 'content': app_state.current_status_message}
        yield {'type': 'completed', 'content': {'status': app_state.last_interaction_status}}

    except Exception as e:
        error_msg_for_log = f"Unexpected error in agent_loop (start_streaming_response): {e}"
        log.error(error_msg_for_log, exc_info=True, extra={"event_type": "unexpected_agent_loop_error"})
        user_facing_error = "An unexpected internal error occurred. I'm unable to continue with this request. Please try again, or if the problem persists, contact support."
        app_state.current_step_error = str(e)
        app_state.last_interaction_status = "UNEXPECTED_AGENT_ERROR"
        app_state.current_status_message = STATUS_ERROR_INTERNAL
        try:
            log.debug("Adding unexpected error message to app_state.messages.", extra={"event_type": "add_message_unexpected_agent_error"})
            app_state.add_message("assistant", f"[System Error: {user_facing_error}]", is_error=True)
        except Exception as add_msg_e:
            log.error("Could not add unexpected error message to app_state.", exc_info=True, extra={"event_type": "add_message_unexpected_error_failed", "details": {"error": str(add_msg_e)}})
        yield {'type': 'error', 'content': user_facing_error}
        yield {'type': 'status', 'content': app_state.current_status_message}
        yield {'type': 'completed', 'content': {'status': app_state.last_interaction_status}}
        
    finally:
        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)
        if hasattr(app_state, 'session_stats') and hasattr(app_state.session_stats, 'total_agent_turn_ms'):
            app_state.session_stats.total_agent_turn_ms = duration_ms
        app_state.is_streaming = False
        log.info(
            "Streaming response finished.",
            extra={
                "event_type": "agent_loop_end",
                "details": {
                    "final_status": app_state.last_interaction_status,
                    "duration_ms": duration_ms,
                    "message_count": len(app_state.messages),
                    "session_id": app_state.session_id,
                }
            }
        )
