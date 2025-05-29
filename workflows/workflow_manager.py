import logging
from typing import Dict, Any, Optional, Type
import uuid # For generating workflow_id
from datetime import datetime # For creating WorkflowContext

# from botbuilder.core import TurnContext # May be needed later
# from state_models import AppState, WorkflowDefinition # Placeholder
from user_auth.models import UserProfile # Placeholder
# from workflows.onboarding import OnboardingWorkflow # Example specific workflow
from state_models import WorkflowContext, AppState # Added AppState for type hint
from llm_interface import LLMInterface # Added LLMInterface for type hint

# Import specific workflow handlers
from workflows.onboarding import OnboardingWorkflow 

logger = logging.getLogger(__name__)

class WorkflowManager:
    """
    Manages the execution and state of various conversational workflows.
    This centralizes workflow logic previously scattered or hardcoded.
    """
    def __init__(self, app_state: AppState, llm_interface: Optional[LLMInterface] = None, config: Optional[Any] = None):
        """
        Initializes the WorkflowManager.
        Args:
            app_state: Application state for managing workflow contexts.
            llm_interface: LLM interface for workflow steps that require LLM interaction.
            config: Application configuration.
        """
        self.app_state = app_state
        self.llm_interface = llm_interface
        self.config = config
        logger.info("WorkflowManager initialized.")

    async def start_workflow(self, turn_context: Any, app_state: AppState, user_profile: UserProfile, workflow_name: str, start_context_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Starts a new workflow (e.g., onboarding, feature configuration).
        Stores the new WorkflowContext in app_state.active_workflows.
        """
        user_id_for_log = user_profile.user_id if user_profile else 'unknown'
        logger.info(f"Attempting to start workflow: {workflow_name} for user {user_id_for_log}")
        
        # Ensure active_workflows dict exists in app_state
        if not hasattr(app_state, 'active_workflows') or app_state.active_workflows is None:
            app_state.active_workflows = {}

        # Check if a workflow of this type is already active for this user/session
        # This simplistic check might need to be more nuanced (e.g. allow multiple of some types?)
        existing_workflow_ctx = app_state.get_active_workflow_by_type(workflow_name) # Assumes app_state has this method
        if existing_workflow_ctx:
            logger.warning(f"Workflow '{workflow_name}' already active (ID: {existing_workflow_ctx.workflow_id}). Cannot start new one of same type.")
            return {"type": "message", "text": f"It looks like you're already in the middle of the '{workflow_name}' process."}

        new_workflow_id = f"wf_{workflow_name}_{uuid.uuid4().hex[:8]}"
        workflow_ctx = WorkflowContext(
            workflow_id=new_workflow_id,
            workflow_type=workflow_name, # Set the type
            status="active",
            current_stage="initial", # Example initial stage
            data=start_context_data if start_context_data else {},
            created_at=datetime.utcnow(), # Ensure datetime is imported if not already
            updated_at=datetime.utcnow()
        )
        workflow_ctx.add_history_event("WORKFLOW_START", f"Workflow '{workflow_name}' started by WorkflowManager.", stage="initial")

        app_state.active_workflows[new_workflow_id] = workflow_ctx
        logger.info(f"Workflow '{workflow_name}' (ID: {new_workflow_id}) context created and added to app_state.active_workflows.")

        if workflow_name == "onboarding":
            onboarding_instance = OnboardingWorkflow(user_profile, app_state, self.llm_interface, workflow_ctx)
            initial_message_dict = await onboarding_instance.start()
            # Update the context in app_state as OnboardingWorkflow.start() might have changed its stage/data
            app_state.active_workflows[new_workflow_id] = onboarding_instance.context 
            logger.info(f"Onboarding workflow (ID: {new_workflow_id}) started via OnboardingWorkflow class. Initial stage: {workflow_ctx.current_stage}")
            return initial_message_dict
        else:
            logger.warning(f"Unknown workflow type for start: {workflow_name}. Removing context.")
            if new_workflow_id in app_state.active_workflows: del app_state.active_workflows[new_workflow_id]
            return {"type": "message", "text": f"WorkflowManager: Don't know how to start workflow '{workflow_name}'."}

    async def process_workflow_step(self, turn_context: Any, app_state: AppState, user_profile: UserProfile, user_response: str) -> Optional[Dict[str, Any]]:
        """
        Processes a user's response within an active workflow.
        """
        # Find the relevant active workflow. For now, assume one primary like onboarding.
        # A more robust system might look for a specific workflow_id if passed in turn_context, or use intent.
        workflow_to_process_type = app_state.get_primary_active_workflow_name() # This gives "onboarding", etc.
        
        if not workflow_to_process_type:
            logger.debug("process_workflow_step: No primary active workflow type found.") # Changed to debug, not necessarily a warning if user is just chatting
            return None

        active_workflow_ctx = app_state.get_active_workflow_by_type(workflow_to_process_type)

        if not active_workflow_ctx:
            logger.error(f"Primary active workflow type '{workflow_to_process_type}' identified, but no active WorkflowContext found for it.")
            return None # No active workflow context to process

        user_id_for_log = user_profile.user_id if user_profile else 'unknown'
        logger.info(f"Processing step for workflow ID: {active_workflow_ctx.workflow_id} (Type: {active_workflow_ctx.workflow_type}), User: {user_id_for_log}, Response: '{user_response[:100]}'") # Log snippet of response
        active_workflow_ctx.add_history_event("USER_RESPONSE", f"User response: {user_response[:100]}", stage=active_workflow_ctx.current_stage)

        next_response_dict: Optional[Dict[str, Any]] = None
        workflow_ended_this_turn = False

        if active_workflow_ctx.workflow_type == "onboarding":
            onboarding_instance = OnboardingWorkflow.from_context(user_profile, app_state, self.llm_interface, active_workflow_ctx)
            # The handle_response method will be the refactored version of process_answer
            next_response_dict = await onboarding_instance.handle_response(user_response, turn_context) 
            # Update the main context in app_state with changes made by the workflow instance
            app_state.active_workflows[active_workflow_ctx.workflow_id] = onboarding_instance.context 
            if onboarding_instance.is_completed(): # is_completed() should check onboarding_instance.context.status
                logger.info(f"Onboarding workflow (ID: {active_workflow_ctx.workflow_id}) reported as completed by instance.")
                await self.end_workflow(app_state, active_workflow_ctx.workflow_id, "completed")
                workflow_ended_this_turn = True
            else:
                active_workflow_ctx.update_timestamp() # Update timestamp if still active
        else:
            logger.warning(f"No handler for processing step of workflow type: {active_workflow_ctx.workflow_type}")
            next_response_dict = {"type": "message", "text": f"WorkflowManager: No step handler for '{active_workflow_ctx.workflow_type}'."}
        
        if workflow_ended_this_turn:
             # If workflow completed, it might have a final message in next_response_dict
             # Or orchestrator might send a generic transition message.
             logger.info(f"Workflow {active_workflow_ctx.workflow_id} ended. Response from workflow: {next_response_dict}")
        
        return next_response_dict

    def is_workflow_active(self, app_state: AppState, workflow_type: str) -> bool:
        """Checks if a specific workflow type is active."""
        if not hasattr(app_state, 'get_active_workflow_by_type'):
            logger.warning("app_state missing get_active_workflow_by_type method in WorkflowManager.is_workflow_active")
            return False # Or raise error
        return app_state.get_active_workflow_by_type(workflow_type) is not None

    async def end_workflow(self, app_state: AppState, workflow_id: str, status: str = "completed") -> bool:
        """Ends a workflow and moves it to completed_workflows in AppState."""
        if hasattr(app_state, 'active_workflows') and workflow_id in app_state.active_workflows:
            wf_context = app_state.active_workflows.pop(workflow_id)
            wf_context.status = status
            wf_context.update_timestamp()
            wf_context.add_history_event("WORKFLOW_END", f"Workflow ended with status: {status}.")
            if not hasattr(app_state, 'completed_workflows') or app_state.completed_workflows is None:
                app_state.completed_workflows = []
            app_state.completed_workflows.append(wf_context)
            logger.info(f"Workflow ID {workflow_id} ended with status '{status}' and moved to completed.")
            return True
        logger.warning(f"Attempted to end workflow ID {workflow_id}, but it was not found in active_workflows.")
        return False

    # More methods will be needed, e.g., for canceling, pausing, resuming workflows.
    # And for specific workflows to register their handlers/definitions. 