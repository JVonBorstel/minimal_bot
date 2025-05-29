"""
Onboarding Workflow for New Users
Automatically triggered when a user interacts with the bot for the first time.
Collects personal preferences, credentials, and setup information.
"""

import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from state_models import AppState, WorkflowContext
from user_auth.models import UserProfile
from user_auth.permissions import UserRole
from config import get_config
from pydantic import BaseModel, Field
from botbuilder.schema import CardAction, ActionTypes
from botbuilder.core import TurnContext

# Import LLMInterface for type hinting and potential use
from llm_interface import LLMInterface

log = logging.getLogger(__name__)

# Onboarding question types
class OnboardingQuestionType:
    TEXT = "text"
    CHOICE = "choice" 
    YES_NO = "yes_no"
    EMAIL = "email"
    ROLE_REQUEST = "role_request"
    MULTI_CHOICE = "multi_choice"

class OnboardingQuestion(BaseModel):
    """Represents a single onboarding question."""
    
    key: str
    question: str
    question_type: str
    choices: List[str] = Field(default_factory=list)
    required: bool = True
    help_text: Optional[str] = None
    validation_pattern: Optional[str] = None
    follow_up_questions: Dict[str, List['OnboardingQuestion']] = Field(default_factory=dict)

# Define the onboarding question sequence
ONBOARDING_QUESTIONS = [
    OnboardingQuestion(
        key="welcome_name",
        question="👋 Welcome! I'm Augie, your AI assistant. What would you prefer I call you?",
        question_type=OnboardingQuestionType.TEXT,
        help_text="This will be used for personalized greetings and interactions."
    ),
    
    OnboardingQuestion(
        key="primary_role", 
        question="🎯 What's your primary role on the team?",
        question_type=OnboardingQuestionType.CHOICE,
        choices=[
            "Software Developer/Engineer",
            "Product Manager", 
            "QA/Testing",
            "DevOps/Infrastructure",
            "Designer/UX",
            "Data Analyst/Scientist",
            "Project Manager",
            "Team Lead/Manager",
            "Stakeholder/Business",
            "Other"
        ],
        help_text="This helps me understand what tools and information you'll need most."
    ),
    
    OnboardingQuestion(
        key="main_projects",
        question="📂 What are the main projects or repositories you work with? (comma-separated)",
        question_type=OnboardingQuestionType.TEXT,
        required=False,
        help_text="e.g., 'web-app, mobile-api, data-pipeline' - I'll prioritize these in searches and suggestions."
    ),
    
    OnboardingQuestion(
        key="tool_preferences",
        question="🛠️ Which tools do you use most frequently? (select all that apply)",
        question_type=OnboardingQuestionType.MULTI_CHOICE,
        choices=[
            "GitHub/Git",
            "Jira/Issue Tracking", 
            "Code Search/Documentation",
            "Web Research",
            "Database Queries",
            "API Testing",
            "Deployment/DevOps",
            "Analytics/Reporting"
        ],
        help_text="I'll suggest these tools more often and optimize my responses for your workflow."
    ),
    
    OnboardingQuestion(
        key="communication_style",
        question="💬 How do you prefer me to communicate?",
        question_type=OnboardingQuestionType.CHOICE,
        choices=[
            "Detailed explanations with context",
            "Brief and to-the-point", 
            "Technical focus with code examples",
            "Business-friendly summaries",
            "Step-by-step instructions"
        ],
        help_text="I'll adapt my response style to match your preferences."
    ),
    
    OnboardingQuestion(
        key="notifications",
        question="🔔 Would you like me to proactively notify you about relevant updates?",
        question_type=OnboardingQuestionType.YES_NO,
        help_text="I can alert you about PR reviews, Jira updates, or critical issues in your projects."
    ),
    
    OnboardingQuestion(
        key="personal_credentials",
        question="🔑 Would you like to set up personal API credentials for more personalized access?",
        question_type=OnboardingQuestionType.YES_NO,
        help_text="This allows me to access your personal repos, issues, and data. You can skip this and use shared access.",
        follow_up_questions={
            "yes": [
                OnboardingQuestion(
                    key="github_token",
                    question="🐙 Enter your GitHub Personal Access Token (optional, skip with 'none'):",
                    question_type=OnboardingQuestionType.TEXT,
                    required=False,
                    help_text="Create at: https://github.com/settings/tokens - needs 'repo', 'read:user' scopes"
                ),
                OnboardingQuestion(
                    key="jira_email",
                    question="📧 Enter your Jira email for API access (optional, skip with 'none'):",
                    question_type=OnboardingQuestionType.EMAIL,
                    required=False,
                    help_text="This should be your Jira login email"
                ),
                OnboardingQuestion(
                    key="jira_token",
                    question="🎫 Enter your Jira API token (optional, skip with 'none'):",
                    question_type=OnboardingQuestionType.TEXT,
                    required=False,
                    help_text="Create at: https://id.atlassian.com/manage-profile/security/api-tokens"
                )
            ]
        }
    )
]

class OnboardingWorkflow:
    """Manages the onboarding workflow for new users."""
    
    def __init__(self, user_profile: UserProfile, app_state: AppState, llm_interface: Optional[LLMInterface], workflow_context: WorkflowContext):
        """
        Initializes the OnboardingWorkflow instance.

        Args:
            user_profile: The profile of the user undergoing onboarding.
            app_state: The overall application state (used for context, permissions, etc.).
            llm_interface: The interface to the LLM, for interpreting user responses.
            workflow_context: The specific context for this onboarding workflow instance.
        """
        self.user_profile = user_profile
        self.app_state = app_state # Provides broader context if needed by workflow steps
        self.llm_interface = llm_interface
        self.context = workflow_context # This holds current_stage, data["answers"], etc.
        self.config = get_config() # Existing config loading
        log.info(f"OnboardingWorkflow initialized for user {user_profile.user_id}, workflow ID {self.context.workflow_id}")

    @classmethod
    def from_context(cls, user_profile: UserProfile, app_state: AppState, llm_interface: Optional[LLMInterface], workflow_context: WorkflowContext) -> 'OnboardingWorkflow':
        """Factory method to create/rehydrate an OnboardingWorkflow from its context."""
        return cls(user_profile, app_state, llm_interface, workflow_context)

    @staticmethod
    def should_trigger_onboarding(user_profile: UserProfile, app_state: AppState) -> bool:
        """Determines if onboarding should be triggered for this user."""
        
        # Check if user is new (within last 5 minutes)
        current_time = int(time.time())
        time_since_first_seen = current_time - user_profile.first_seen_timestamp
        is_new_user = time_since_first_seen < 300  # 5 minutes
        
        # Check if onboarding already completed or explicitly postponed/declined
        profile_data = user_profile.profile_data or {}
        onboarding_completed = profile_data.get("onboarding_completed", False)
        onboarding_postponed = profile_data.get("onboarding_interaction_status") == "postponed"
        onboarding_declined = profile_data.get("onboarding_interaction_status") == "declined"
        
        # Check if there's already an active onboarding workflow
        has_active_onboarding = any(
            wf.workflow_type == "onboarding" and wf.status == "active"
            for wf in app_state.active_workflows.values()
        )
        
        should_trigger = (
            is_new_user and 
            not onboarding_completed and 
            not onboarding_postponed and
            not onboarding_declined and
            not has_active_onboarding
        )
        
        if should_trigger:
            log.info(f"Triggering onboarding for new user {user_profile.user_id} (first seen {time_since_first_seen}s ago)")
        elif onboarding_postponed:
            log.info(f"Onboarding for user {user_profile.user_id} was postponed. Not triggering.")
        elif onboarding_declined:
            log.info(f"Onboarding for user {user_profile.user_id} was declined. Not triggering.")
        
        return should_trigger
    
    def start_workflow(self) -> WorkflowContext:
        """DEPRECATED: This logic is now primarily in WorkflowManager.
           This instance method should be replaced by a simpler start() that returns the first question.
        """
        log.warning("OnboardingWorkflow.start_workflow() is deprecated. WorkflowManager now handles context creation.")
        # Fallback or error, as WorkflowManager should create the context.
        # For now, let's assume context is already created and passed in __init__.
        # This method could be repurposed to return the initial activity.
        if not self.context or self.context.workflow_type != "onboarding":
            raise ValueError("OnboardingWorkflow cannot start without a valid onboarding WorkflowContext.")
        
        # If current_stage is already set (e.g. by WorkflowManager), respect it.
        # Otherwise, set to an initial stage.
        if not self.context.current_stage:
            self.context.current_stage = "asking_welcome_name" # Example initial stage for questions
        
        # Ensure necessary data fields are initialized if not already by WorkflowManager
        if "current_question_index" not in self.context.data:
            self.context.data["current_question_index"] = 0
        if "answers" not in self.context.data:
            self.context.data["answers"] = {}
        if "questions_total" not in self.context.data:
            self.context.data["questions_total"] = len(ONBOARDING_QUESTIONS)
        if "started_at" not in self.context.data:
            self.context.data["started_at"] = datetime.utcnow().isoformat()

        self.context.add_history_event(
            "WORKFLOW_INIT",
            f"OnboardingWorkflow instance prepared for user {self.user_profile.display_name}. Stage: {self.context.current_stage}",
            self.context.current_stage
        )
        # The WorkflowContext is already in app_state.active_workflows handled by WorkflowManager
        log.info(f"OnboardingWorkflow prepared for workflow ID {self.context.workflow_id}")
        return self.context # Return the context for WorkflowManager to have it if needed.

    async def start(self, start_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Starts the onboarding process by asking the first question.
        Called by WorkflowManager after the WorkflowContext is created and stored.
        Updates self.context.current_stage and self.context.data as needed.
        Returns:
            A dictionary representing the activity for the first question.
        """
        log.info(f"OnboardingWorkflow.start() called for WF ID: {self.context.workflow_id}")
        self.context.current_stage = "asking_question" # A generic stage for asking any question
        self.context.data["current_question_index"] = 0
        self.context.data["answers"] = {}
        self.context.data["processing_follow_ups"] = False # Ensure reset
        self.context.data.pop("follow_up_questions", None)
        self.context.data.pop("follow_up_index", None)
        self.context.data["questions_total"] = len(ONBOARDING_QUESTIONS)

        first_question_model = ONBOARDING_QUESTIONS[0]
        self.context.data["current_question_key"] = first_question_model.key # Track current question key

        response_dict = self._format_question_response(first_question_model, self.context)
        
        self.context.add_history_event(
            "QUESTION_ASKED", 
            f"Asked: {first_question_model.question}", 
            stage=self.context.current_stage,
            details={"question_key": first_question_model.key}
        )
        self.context.update_timestamp()
        return response_dict

    async def _get_llm_interpreted_answer(self, question: OnboardingQuestion, user_response_text: str) -> Optional[Any]:
        """Uses LLM to interpret user's answer for choice-based or yes/no questions."""
        if not self.llm_interface:
            log.warning(f"LLM interface not available for interpreting answer to: {question.key}")
            return None 

        prompt_text = ""
        if question.question_type == OnboardingQuestionType.CHOICE or question.question_type == OnboardingQuestionType.MULTI_CHOICE:
            choices_str = "\n".join([f"- {c}" for c in question.choices])
            prompt_text = (
                f"You are an intelligent assistant helping a user answer an onboarding question. "
                f"The question is: '{question.question}'\n"
                f"The available choices are:\n{choices_str}\n\n"
                f"The user responded: '{user_response_text}'\n\n"
                f"Carefully analyze the user's response. "
                f"If the user's response clearly matches one or more of the provided choices, respond with the exact text of the matching choice(s). "
                f"For multi-choice questions, if multiple choices match, list them separated by a semicolon and a space (e.g., 'Choice A; Choice B'). "
                f"If the user's response does not clearly match any of the choices, or if it\'s ambiguous, respond with the exact word 'UNCLEAR'. "
                f"Do not add any extra explanation or conversational filler. Respond ONLY with the choice text(s) or 'UNCLEAR'."
            )
        elif question.question_type == OnboardingQuestionType.YES_NO:
            prompt_text = (
                f"You are an intelligent assistant helping a user answer an onboarding question. "
                f"The question is: '{question.question}'\n"
                f"The user responded: '{user_response_text}'\n\n"
                f"Does the user's response definitively mean 'yes' or definitively mean 'no'? "
                f"If it clearly means 'yes', respond with the exact word 'yes'. "
                f"If it clearly means 'no', respond with the exact word 'no'. "
                f"If the meaning is ambiguous or neither clearly yes nor no, respond with the exact word 'UNCLEAR'. "
                f"Do not add any extra explanation or conversational filler. Respond ONLY with 'yes', 'no', or 'UNCLEAR'."
            )
        else:
            log.debug(f"Question type {question.question_type} for key {question.key} is not LLM-interpretable by this method.")
            return None # Not an LLM-interpretable question type for this method

        try:
            # Corrected message format for Gemini
            messages = [{ "role": "user", "parts": [{"text": prompt_text}]}]
            llm_response_str = ""
            
            # Use the llm_interface to get a response. Ensure it handles streaming/non-streaming appropriately.
            # This part assumes llm_interface has a method like generate_text_response or similar for single, non-streamed call.
            # If generate_content_stream is the only option, it needs to be aggregated.
            stream = self.llm_interface.generate_content_stream(messages=messages, app_state=self.app_state)
            async for chunk in stream:
                if hasattr(chunk, 'text') and chunk.text:
                    llm_response_str += chunk.text
                elif isinstance(chunk, dict) and chunk.get('text'): 
                    llm_response_str += chunk['text']
            
            interpreted_value_raw = llm_response_str.strip()
            log.info(f"LLM interpreted answer for Q: '{question.key}'. User: '{user_response_text}'. LLM raw output: '{interpreted_value_raw}'")

            if interpreted_value_raw.upper() == "UNCLEAR":
                return "UNCLEAR_BY_LLM"

            if question.question_type == OnboardingQuestionType.CHOICE:
                for choice in question.choices:
                    if choice.lower() == interpreted_value_raw.lower():
                        return choice
                log.warning(f"LLM returned '{interpreted_value_raw}' for CHOICE which is not an exact match for {question.key}. Will be treated as UNCLEAR by fallback.")
                return "UNCLEAR_BY_LLM" 

            elif question.question_type == OnboardingQuestionType.MULTI_CHOICE:
                selected_choices = []
                raw_selected = [s.strip() for s in interpreted_value_raw.split(';')]
                for sel_text in raw_selected:
                    found_match = False
                    for choice in question.choices:
                        if choice.lower() == sel_text.lower():
                            if choice not in selected_choices: # Avoid duplicates
                                selected_choices.append(choice)
                            found_match = True
                            break
                    if not found_match:
                        log.warning(f"LLM multi-choice selection '{sel_text}' not in choices for {question.key}.")
                
                if selected_choices:
                    return selected_choices
                log.warning(f"LLM interpreted '{interpreted_value_raw}' for MULTI_CHOICE, but no valid selections extracted for {question.key}.")
                return "UNCLEAR_BY_LLM"

            elif question.question_type == OnboardingQuestionType.YES_NO:
                if interpreted_value_raw.lower() == "yes": return "yes"
                if interpreted_value_raw.lower() == "no": return "no"
                log.warning(f"LLM returned '{interpreted_value_raw}' for YES_NO, not 'yes' or 'no' for {question.key}.")
                return "UNCLEAR_BY_LLM"
            
            # Should not be reached if question types are handled above
            log.warning(f"LLM interpretation for {question.key} (type {question.question_type}) fell through: {interpreted_value_raw}")
            return None 
        except Exception as e:
            log.error(f"Error during LLM answer interpretation for {question.key}: {e}", exc_info=True)
            return None # Fallback on error, will trigger standard validation

    def _get_current_question_model(self) -> Optional[OnboardingQuestion]:
        """Gets the current OnboardingQuestion model based on workflow context."""
        if self.context.data.get("processing_follow_ups"):
            follow_up_questions = self.context.data.get("follow_up_questions", [])
            follow_up_index = self.context.data.get("follow_up_index", 0)
            if follow_up_index < len(follow_up_questions):
                return follow_up_questions[follow_up_index]
        else:
            current_index = self.context.data.get("current_question_index", 0)
            if current_index < len(ONBOARDING_QUESTIONS):
                return ONBOARDING_QUESTIONS[current_index]
        log.warning(f"_get_current_question_model: Could not determine current question. Data: {self.context.data}")
        return None

    def _incrementally_update_user_profile(self, question: OnboardingQuestion, processed_value: Any):
        """Helper to incrementally update UserProfile based on an answer."""
        if self.user_profile.profile_data is None: self.user_profile.profile_data = {}
        if "preferences" not in self.user_profile.profile_data: self.user_profile.profile_data["preferences"] = {}

        prefs = self.user_profile.profile_data["preferences"]
        profile_creds = self.user_profile.profile_data.get("personal_credentials", {})
        if not isinstance(profile_creds, dict): profile_creds = {} # Ensure it is a dict

        key = question.key

        if key == "welcome_name": prefs["preferred_name"] = processed_value
        elif key == "primary_role": prefs["primary_role"] = processed_value
        elif key == "main_projects": 
            if isinstance(processed_value, str):
                prefs["main_projects"] = [p.strip() for p in processed_value.split(",") if p.strip()]
            elif isinstance(processed_value, list): # If LLM returns a list
                prefs["main_projects"] = [str(p).strip() for p in processed_value if str(p).strip()]
            else:
                prefs["main_projects"] = []
        elif key == "tool_preferences": 
            prefs["tool_preferences"] = processed_value if isinstance(processed_value, list) else []
        elif key == "communication_style": prefs["communication_style"] = processed_value
        elif key == "notifications": prefs["notifications_enabled"] = (processed_value == "yes")
        elif key == "personal_credentials":
            if processed_value == "no":
                profile_creds = {"setup_declined": True} # Reset credentials if declined
            else: # User said yes, clear any previous decline
                profile_creds.pop("setup_declined", None)
        elif key == "github_token" and processed_value: profile_creds["github_token"] = processed_value 
        elif key == "jira_email" and processed_value: profile_creds["jira_email"] = processed_value
        elif key == "jira_token" and processed_value: profile_creds["jira_token"] = processed_value
        
        self.user_profile.profile_data["personal_credentials"] = profile_creds
        log.debug(f"Incrementally updated user_profile with {key}: {processed_value}. Prefs: {prefs}, Creds: {profile_creds}")
        # Actual DB save of user_profile will be handled by a higher layer or at end of workflow.

    async def handle_response(self, user_input: str, turn_context: TurnContext) -> Dict[str, Any]:
        """Processes a user's answer to an onboarding question."""
        
        if self.context.status != "active":
            log.warning(f"handle_response called on non-active workflow: {self.context.workflow_id}, status: {self.context.status}")
            return {"type":"message", "text": "This onboarding session is no longer active."} # Return a message dict
        
        user_input_lower = user_input.lower().strip()
        self.context.add_history_event("USER_RESPONSE_RECEIVED", f"Received: {user_input}", self.context.current_stage)

        # --- START: Detect if user is asking a question instead of answering (copied from old process_answer) ---
        question_indicators = [
            "what is", "what's", "whats", "who is", "who's", "how do", "how can", 
            "where is", "where's", "when is", "when's", "why is", "why's", "why",
            "can you", "could you", "will you", "would you", "do you", "are you",
            "tell me", "explain", "help me", "show me"
        ]
        
        if (user_input.endswith("?") or 
            any(indicator in user_input_lower for indicator in question_indicators)):
            
            current_question = self._get_current_question_model()
            if current_question:
                return {
                    "type": "message", 
                    "text": f"I noticed you asked a question, but I'm currently waiting for your answer to the setup question. Let me ask again:\n\n{current_question.question}\n\n(If you'd like to skip setup entirely, type 'skip onboarding')",
                    "retry_question": True # This flag is for internal logic that might re-prompt
                }
            else:
                return {"type": "message", "text": "Error: Unable to determine current onboarding question to re-ask."}
        # --- END: Question detection ---

        # --- START: Handle restart onboarding command (copied from old process_answer) ---
        restart_onboarding_commands = ["restart onboarding", "start over onboarding", "reset my onboarding", "restart setup"]
        if user_input_lower in restart_onboarding_commands:
            log.info(f"User {self.user_profile.user_id} requested to restart onboarding. Workflow ID: {self.context.workflow_id}")
            self.context.data["current_question_index"] = 0
            self.context.data["answers"] = {}
            self.context.data["processing_follow_ups"] = False
            self.context.data.pop("follow_up_questions", None)
            self.context.data.pop("follow_up_index", None)
            self.context.current_stage = "welcome_restarted"
            self.context.add_history_event("WORKFLOW_RESTARTED", "User restarted onboarding process.", "welcome_restarted")
            
            first_question = ONBOARDING_QUESTIONS[0]
            response = self._format_question_response(first_question, self.context)
            response["text"] = "Okay, let's start the onboarding over. " + response["text"]
            return response
        # --- END: Handle restart onboarding command ---

        current_question_model = self._get_current_question_model()
        if not current_question_model:
            log.error(f"Could not determine current question for workflow {self.context.workflow_id}. Stage: {self.context.current_stage}, Data: {self.context.data}")
            return await self._complete_onboarding(error_message="Internal error: Could not determine current question.")

        # --- Process user_input against current_question_model --- 
        processed_value: Any = None
        validation_error_message: Optional[str] = None
        skipped_non_required = False

        # Attempt LLM interpretation first for applicable types
        if current_question_model.question_type in [OnboardingQuestionType.CHOICE, OnboardingQuestionType.MULTI_CHOICE, OnboardingQuestionType.YES_NO]:
            llm_interpreted_value = await self._get_llm_interpreted_answer(current_question_model, user_input)
            if llm_interpreted_value == "UNCLEAR_BY_LLM":
                log.info(f"LLM found answer unclear for Q: {current_question_model.key}. Falling back to validation.")
                # Fallback to standard validation if LLM is unclear
                validation_result = self._validate_answer(current_question_model, user_input)
                if validation_result["valid"]:
                    processed_value = validation_result["processed_value"]
                    skipped_non_required = validation_result.get("skipped_non_required", False)
                else:
                    validation_error_message = validation_result["error"]
            elif llm_interpreted_value is not None: # LLM provided a valid interpretation
                processed_value = llm_interpreted_value
                # If LLM returns a value, it implies it's valid according to LLM's understanding of choices/yes_no
            else: # LLM interpretation failed or returned None (not unclear, but actual None)
                log.warning(f"LLM interpretation returned None or failed for {current_question_model.key}. Falling back to standard validation.")
                validation_result = self._validate_answer(current_question_model, user_input)
                if validation_result["valid"]:
                    processed_value = validation_result["processed_value"]
                    skipped_non_required = validation_result.get("skipped_non_required", False)
                else:
                    validation_error_message = validation_result["error"]
        else: # For TEXT, EMAIL, etc. use original validation directly
            validation_result = self._validate_answer(current_question_model, user_input)
            if validation_result["valid"]:
                processed_value = validation_result["processed_value"]
                skipped_non_required = validation_result.get("skipped_non_required", False)
            else:
                validation_error_message = validation_result["error"]

        if validation_error_message:
            return {"type": "message", "text": validation_error_message, "retry_question": True}

        # Store answer and update profile incrementally
        self.context.data["answers"][current_question_model.key] = processed_value
        self._incrementally_update_user_profile(current_question_model, processed_value)
        
        self.context.add_history_event("ANSWER_PROCESSED", f"Processed answer for {current_question_model.key}: {str(processed_value)[:100]}", self.context.current_stage)
        
        confirmation_info = {
            "answer_saved_key": current_question_model.key,
            "answer_saved_value": processed_value,
            "question_skipped": skipped_non_required
        }
        
        next_question_activity_dict = await self._get_next_question_activity(current_question_model, processed_value)
        
        if isinstance(next_question_activity_dict, dict):
            next_question_activity_dict.update(confirmation_info) # Add answer info for potential confirmation message by orchestrator
        
        self.context.update_timestamp()
        return next_question_activity_dict

    def _validate_answer(self, question: OnboardingQuestion, user_input: str) -> Dict[str, Any]:
        """Validates a user's answer to a question."""
        
        user_input = user_input.strip()
        
        # Handle empty/skip answers
        if not user_input or user_input.lower() in ["skip", "none", "n/a"]:
            if question.required:
                return {
                    "valid": False,
                    "error": "This one's important for setup! Could you please provide an answer? Or, if you'd prefer, you can type 'skip onboarding' to bypass the rest of this setup."
                }
            else:
                return {
                    "valid": True,
                    "processed_value": None,
                    "skipped_non_required": True # Flag that a non-required question was skipped
                }
        
        # Validate based on question type
        if question.question_type == OnboardingQuestionType.YES_NO:
            if user_input.lower() in ["yes", "y", "true", "1", "sure", "ok"]:
                return {"valid": True, "processed_value": "yes"}
            elif user_input.lower() in ["no", "n", "false", "0", "nope"]:
                return {"valid": True, "processed_value": "no"}
            else:
                return {
                    "valid": False,
                    "error": "Hmm, I was expecting a 'yes' or 'no' there. Could you try that? (Or type 'skip onboarding' to skip.)"
                }
        
        elif question.question_type == OnboardingQuestionType.CHOICE:
            # Try to match choice by index or text
            try:
                choice_index = int(user_input) - 1
                if 0 <= choice_index < len(question.choices):
                    return {"valid": True, "processed_value": question.choices[choice_index]}
            except ValueError:
                pass
            
            # Try partial text matching
            user_lower = user_input.lower()
            for choice in question.choices:
                if user_lower in choice.lower() or choice.lower() in user_lower:
                    return {"valid": True, "processed_value": choice}
            
            formatted_choices = "\n".join(f"{i+1}. {choice}" for i, choice in enumerate(question.choices))
            return {
                "valid": False,
                "error": f"Hmm, that wasn't one of the options. Could you pick from the list, or enter the number? You can also type 'skip onboarding' to bypass this.\n\nAvailable choices:\n{formatted_choices}"
            }
        
        elif question.question_type == OnboardingQuestionType.MULTI_CHOICE:
            # Handle comma-separated or numbered selections
            selections = []
            parts = [p.strip() for p in user_input.replace(",", " ").split()]
            
            for part in parts:
                try:
                    choice_index = int(part) - 1
                    if 0 <= choice_index < len(question.choices):
                        selections.append(question.choices[choice_index])
                except ValueError:
                    # Try text matching
                    part_lower = part.lower()
                    for choice in question.choices:
                        if part_lower in choice.lower() and choice not in selections:
                            selections.append(choice)
                            break
            
            if not selections:
                formatted_choices = "\n".join(f"{i+1}. {choice}" for i, choice in enumerate(question.choices))
                return {
                    "valid": False,
                    "error": f"Hmm, I didn't quite get that. For this one, please select one or more from the list (you can use numbers or text). Or, feel free to type 'skip onboarding'.\n\nAvailable choices:\n{formatted_choices}"
                }
            
            return {"valid": True, "processed_value": selections}
        
        elif question.question_type == OnboardingQuestionType.EMAIL:
            if "@" in user_input and "." in user_input:
                return {"valid": True, "processed_value": user_input.lower()}
            else:
                return {
                    "valid": False,
                    "error": "That doesn't look quite like an email address. Could you please enter a valid one? (Or type 'skip onboarding' if you'd rather skip this step.)"
                }
        
        else:  # TEXT type
            return {"valid": True, "processed_value": user_input}
    
    async def _get_next_question_activity(self, answered_question: OnboardingQuestion, answer_value: Any) -> Dict[str, Any]:
        """Determines the next question or completes onboarding. Returns an activity dictionary."""
        # ... (Logic from original _get_next_question, adapted to use self.context and async if needed for LLM) ...
        # This will determine if there are follow-ups, or move to the next main question, or complete.
        # For now, placeholder that needs to be filled with adapted logic from _get_next_question

        # Check for follow-up questions first
        if answered_question.follow_up_questions and answer_value == "yes": # Simplified: only for 'yes' to 'personal_credentials'
            if answered_question.key == "personal_credentials" and "yes" in answered_question.follow_up_questions:
                self.context.data["processing_follow_ups"] = True
                self.context.data["follow_up_questions"] = answered_question.follow_up_questions["yes"]
                self.context.data["follow_up_index"] = 0
                next_follow_up_question = self.context.data["follow_up_questions"][0]
                self.context.data["current_question_key"] = next_follow_up_question.key
                self.context.current_stage = f"asking_follow_up_{next_follow_up_question.key}"
                self.context.add_history_event("FOLLOW_UP_TRIGGERED", f"Triggered follow-up for {answered_question.key}", self.context.current_stage)
                return self._format_question_response(next_follow_up_question, self.context)

        # If processing follow-ups, get the next one
        if self.context.data.get("processing_follow_ups"):
            follow_up_index = self.context.data.get("follow_up_index", 0) + 1
            follow_up_questions = self.context.data.get("follow_up_questions", [])
            if follow_up_index < len(follow_up_questions):
                self.context.data["follow_up_index"] = follow_up_index
                next_follow_up_question = follow_up_questions[follow_up_index]
                self.context.data["current_question_key"] = next_follow_up_question.key
                self.context.current_stage = f"asking_follow_up_{next_follow_up_question.key}"
                self.context.add_history_event("NEXT_FOLLOW_UP", f"Asking next follow-up: {next_follow_up_question.key}", self.context.current_stage)
                return self._format_question_response(next_follow_up_question, self.context)
            else:
                # Finished follow-ups, move to next main question
                self.context.data["processing_follow_ups"] = False
                self.context.data.pop("follow_up_questions", None)
                self.context.data.pop("follow_up_index", None)
                # current_question_index for main questions has not been incremented yet for the question that triggered follow-ups.
                # So, we increment it now to move to the *next* main question.
                current_main_index = self.context.data.get("current_question_index", 0) + 1
                self.context.data["current_question_index"] = current_main_index
        else:
            # No active follow-ups, move to next main question
            current_main_index = self.context.data.get("current_question_index", 0) + 1
            self.context.data["current_question_index"] = current_main_index

        # Check if onboarding is complete
        if self.context.data["current_question_index"] >= len(ONBOARDING_QUESTIONS):
            return await self._complete_onboarding()
        else:
            next_main_question = ONBOARDING_QUESTIONS[self.context.data["current_question_index"]]
            self.context.data["current_question_key"] = next_main_question.key
            self.context.current_stage = f"asking_question_{next_main_question.key}"
            self.context.add_history_event("NEXT_QUESTION", f"Asking main question: {next_main_question.key}", self.context.current_stage)
            return self._format_question_response(next_main_question, self.context)

    def _format_question_response(self, question: OnboardingQuestion, workflow: WorkflowContext) -> Dict[str, Any]:
        """Formats a question for presentation to the user."""
        
        response = {
            "success": True,
            "question": question.question,
            "type": question.question_type,
            "progress": f"{workflow.data.get('current_question_index', 0) + 1}/{workflow.data.get('questions_total', len(ONBOARDING_QUESTIONS))}"
        }
        
        if question.choices:
            if question.question_type == OnboardingQuestionType.MULTI_CHOICE:
                response["message"] = f"{question.question}\n\n" + \
                    "\n".join(f"{i+1}. {choice}" for i, choice in enumerate(question.choices)) + \
                    "\n\n*You can select multiple options by number (e.g., '1,3,5') or text*"
            else:
                response["message"] = f"{question.question}\n\n" + \
                    "\n".join(f"{i+1}. {choice}" for i, choice in enumerate(question.choices))
        else:
            response["message"] = question.question
        
        if question.help_text:
            response["message"] += f"\n\n💡 *{question.help_text}*"
        
        if not question.required:
            response["message"] += f"\n\n*Optional - type 'skip' to skip*"

        # Add suggested actions for CHOICE and YES_NO types
        if question.question_type == OnboardingQuestionType.CHOICE and question.choices:
            response["suggested_actions"] = [
                CardAction(type=ActionTypes.im_back, title=choice, value=choice) 
                for choice in question.choices
            ]
        elif question.question_type == OnboardingQuestionType.YES_NO:
            response["suggested_actions"] = [
                CardAction(type=ActionTypes.im_back, title="Yes", value="yes"),
                CardAction(type=ActionTypes.im_back, title="No", value="no")
            ]
        
        workflow.current_stage = question.key
        workflow.update_timestamp()
        
        return response
    
    async def _complete_onboarding(self, error_message: Optional[str] = None) -> Dict[str, Any]:
        """Completes the onboarding workflow and saves user preferences."""
        
        answers = self.context.data.get("answers", {})
        
        # Process and store the answers in user profile
        # Most data is already incrementally added to self.user_profile.profile_data.
        # This function will now mainly handle marking as complete and final cleanup/logging.
        
        if self.user_profile.profile_data is None: # Should be initialized by process_answer
            self.user_profile.profile_data = {}

        profile_data = self.user_profile.profile_data
        
        profile_data["onboarding_completed"] = True
        profile_data["onboarding_completed_at"] = datetime.utcnow().isoformat()
        profile_data["onboarding_status"] = "completed" # Add overall status

        # Ensure all preferences from 'answers' are reflected if any were missed by incremental updates
        # (e.g., if workflow was somehow completed without process_answer running for all)
        final_preferences = profile_data.get("preferences", {})
        final_preferences["preferred_name"] = answers.get("welcome_name", final_preferences.get("preferred_name"))
        final_preferences["primary_role"] = answers.get("primary_role", final_preferences.get("primary_role"))
        raw_main_projects = answers.get("main_projects")
        if raw_main_projects is not None: # Only update if answer was provided
             final_preferences["main_projects"] = [p.strip() for p in (raw_main_projects).split(",") if p.strip()]
        # Ensure tool_preferences is a list
        tool_prefs_ans = answers.get("tool_preferences")
        if tool_prefs_ans is not None:
            final_preferences["tool_preferences"] = tool_prefs_ans if isinstance(tool_prefs_ans, list) else []
        final_preferences["communication_style"] = answers.get("communication_style", final_preferences.get("communication_style"))
        notifications_ans = answers.get("notifications")
        if notifications_ans is not None:
            final_preferences["notifications_enabled"] = (notifications_ans == "yes")
        
        profile_data["preferences"] = final_preferences

        # Handle personal credentials consistency based on final answers
        # This reconciles incremental updates with the final state of "personal_credentials" answer.
        if answers.get("personal_credentials") == "yes":
            final_credentials = profile_data.get("personal_credentials", {})
            if isinstance(final_credentials, dict): # Ensure it's a dict
                # Remove setup_declined if it was "yes", as specific tokens might be present
                final_credentials.pop("setup_declined", None)
                
                # Ensure tokens from answers are present if provided
                if answers.get("github_token"):
                    final_credentials["github_token"] = answers["github_token"]
                if answers.get("jira_email"):
                    final_credentials["jira_email"] = answers["jira_email"]
                if answers.get("jira_token"):
                    final_credentials["jira_token"] = answers["jira_token"]
                
                # Only keep the personal_credentials field if it actually contains credentials
                if final_credentials:
                    profile_data["personal_credentials"] = final_credentials
                elif "personal_credentials" in profile_data: # no actual credentials, remove the key
                    profile_data.pop("personal_credentials")
        elif answers.get("personal_credentials") == "no":
            # If user explicitly said "no" to setting up credentials at the parent question
            profile_data["personal_credentials"] = {"setup_declined": True}
        else: # personal_credentials question might have been skipped
            if "personal_credentials" in profile_data and not profile_data.get("personal_credentials"):
                # If it's an empty dict from incremental adds but main question was skipped, remove
                profile_data.pop("personal_credentials")
        
        # Auto-assign role based on their stated role
        suggested_role = self._suggest_role_from_answers(answers)
        if suggested_role and suggested_role != self.user_profile.assigned_role:
            profile_data["suggested_role"] = suggested_role
        
        # Update user profile
        self.user_profile.profile_data = profile_data
        
        # Mark workflow as completed
        self.context.status = "completed"
        self.context.current_stage = "completed"
        self.context.add_history_event(
            "WORKFLOW_COMPLETED",
            "Onboarding workflow completed successfully",
            "completed",
            {"answers_count": len(answers)}
        )
        
        # Move to completed workflows
        if self.context.workflow_id in self.app_state.active_workflows:
            self.app_state.completed_workflows.append(
                self.app_state.active_workflows.pop(self.context.workflow_id)
            )
        
        # Generate completion message
        preferred_name = answers.get("welcome_name", self.user_profile.display_name)
        completion_card = self._generate_completion_message(preferred_name, answers, suggested_role)
        
        log.info(f"Completed onboarding for user {self.user_profile.user_id} with {len(answers)} answers")
        
        return {
            "success": True,
            "completed": True,
            "message": completion_card,
            "profile_updated": True,
            "suggested_role": suggested_role
        }
    
    def _suggest_role_from_answers(self, answers: Dict[str, Any]) -> Optional[str]:
        """Suggests an appropriate role based on onboarding answers."""
        
        primary_role = answers.get("primary_role", "").lower()
        
        role_mappings = {
            "software developer": "DEVELOPER",
            "engineer": "DEVELOPER", 
            "product manager": "STAKEHOLDER",
            "team lead": "DEVELOPER",
            "manager": "STAKEHOLDER", 
            "devops": "DEVELOPER",
            "qa": "DEVELOPER",
            "testing": "DEVELOPER"
        }
        
        for key, role in role_mappings.items():
            if key in primary_role:
                return role
        
        return None
    
    def _generate_completion_message(self, preferred_name: str, answers: Dict[str, Any], suggested_role: Optional[str]) -> Dict[str, Any]:
        """Generates a personalized completion message as a HeroCard payload."""
        
        summary_items = []
        if answers.get("primary_role"):
            summary_items.append(f"👤 **Role**: {answers['primary_role']}")
        
        main_projects_ans = answers.get("main_projects")
        if main_projects_ans: # Could be None if skipped, or empty string
            projects = []
            if isinstance(main_projects_ans, str):
                projects = [p.strip() for p in main_projects_ans.split(",") if p.strip()]
            elif isinstance(main_projects_ans, list): # Already processed list
                projects = main_projects_ans
            if projects:
                summary_items.append(f"📂 **Main Projects**: {(', '.join(projects))}")
        
        tool_prefs_ans = answers.get("tool_preferences")
        if tool_prefs_ans and isinstance(tool_prefs_ans, list) and tool_prefs_ans:
            summary_items.append(f"🛠️ **Preferred Tools**: {(', '.join(tool_prefs_ans))}")
        
        if answers.get("communication_style"):
            summary_items.append(f"💬 **Communication Style**: {answers['communication_style']}")

        notifications_ans = answers.get("notifications")
        if notifications_ans is not None:
            notifications_text = "Enabled" if notifications_ans == "yes" else "Disabled"
            summary_items.append(f"🔔 **Notifications**: {notifications_text}")

        card_text = "Your onboarding is complete! Here are some of your key preferences:\n\n" + "\n".join(summary_items)
        
        if suggested_role:
            card_text += f"\n\n🎯 Based on your role, I've noted a suggestion to set your access level to **{suggested_role}**. An admin can update this for you."
        
        # Personal credentials summary
        if answers.get("personal_credentials") == "yes":
            cred_keys_present = [key for key in ["github_token", "jira_email", "jira_token"] if answers.get(key)]
            if cred_keys_present:
                card_text += f"\n\n🔑 I've securely stored the personal credential(s) you provided for enhanced access."
            else:
                card_text += f"\n\n🔑 You opted to set up personal credentials, but didn't provide any specific tokens during this setup."
        elif answers.get("personal_credentials") == "no":
            card_text += f"\n\n🔑 You chose not to set up personal API credentials at this time."

        card_text += "\n\n**What's Next?**"

        # Convert CardAction objects to dictionaries for serialization, ensuring ActionTypes is stringified
        buttons = [
            {"type": ActionTypes.im_back.value, "title": "Explore Commands (@augie help)", "value": "@augie help"},
            {"type": ActionTypes.im_back.value, "title": "Manage My Preferences", "value": "@augie preferences"}
        ]
        
        # Using CardFactory structure for a HeroCard
        # Note: botbuilder.schema needs CardFactory, CardImage, ActionTypes, etc.
        # Ensure they are imported where this card is constructed if not already.
        completion_card = {
            "contentType": "application/vnd.microsoft.card.hero",
            "content": {
                "title": f"🎉 Welcome aboard, {preferred_name}!",
                "subtitle": "Setup Complete!",
                "text": card_text,
                "buttons": buttons
            }
        }
        # This method now returns the card payload directly
        return completion_card

    def skip_onboarding(self, workflow_id: str) -> Dict[str, Any]:
        """Skips the onboarding workflow, saving any answers collected so far."""
        if workflow_id not in self.app_state.active_workflows:
            return {"error": "Workflow not found"}

        workflow = self.app_state.active_workflows[workflow_id]
        answers_collected = workflow.data.get("answers", {})
        
        # UserProfile is already being updated incrementally by process_answer.
        # Here, we just mark it as skipped.
        if self.user_profile.profile_data is None:
            self.user_profile.profile_data = {}
        
        self.user_profile.profile_data["onboarding_status"] = "skipped"
        self.user_profile.profile_data["onboarding_skipped_at"] = datetime.utcnow().isoformat()
        # Mark onboarding as completed even when skipped to prevent retriggering
        self.user_profile.profile_data["onboarding_completed"] = True

        # Consolidate any collected answers into preferences, similar to _complete_onboarding
        # This ensures that if skip happens before _complete_onboarding, preferences are still structured.
        final_preferences = self.user_profile.profile_data.get("preferences", {})
        if not final_preferences and answers_collected : # If preferences is empty but we have answers
             final_preferences["preferred_name"] = answers_collected.get("welcome_name")
             final_preferences["primary_role"] = answers_collected.get("primary_role")
             raw_main_projects = answers_collected.get("main_projects")
             if raw_main_projects is not None:
                 final_preferences["main_projects"] = [p.strip() for p in (raw_main_projects).split(",") if p.strip()]
             tool_prefs_ans = answers_collected.get("tool_preferences")
             if tool_prefs_ans is not None:
                final_preferences["tool_preferences"] = tool_prefs_ans if isinstance(tool_prefs_ans, list) else []
             final_preferences["communication_style"] = answers_collected.get("communication_style")
             notifications_ans = answers_collected.get("notifications")
             if notifications_ans is not None:
                final_preferences["notifications_enabled"] = (notifications_ans == "yes")
             self.user_profile.profile_data["preferences"] = final_preferences

        # Similar logic for personal_credentials based on collected answers up to the skip point
        if "personal_credentials" in answers_collected: # Check if the main question was answered
            if answers_collected["personal_credentials"] == "yes":
                final_credentials = self.user_profile.profile_data.get("personal_credentials", {})
                if isinstance(final_credentials, dict): # Should be a dict from incremental updates
                    final_credentials.pop("setup_declined", None) # Remove if it was set
                    # Populate from answers_collected if specific tokens were answered before skip
                    for token_key in ["github_token", "jira_email", "jira_token"]:
                        if token_key in answers_collected and answers_collected[token_key]:
                            final_credentials[token_key] = answers_collected[token_key]
                    if final_credentials:
                         self.user_profile.profile_data["personal_credentials"] = final_credentials
                    elif "personal_credentials" in self.user_profile.profile_data:
                         self.user_profile.profile_data.pop("personal_credentials") # Remove if empty
            elif answers_collected["personal_credentials"] == "no":
                 self.user_profile.profile_data["personal_credentials"] = {"setup_declined": True}
        
        workflow.status = "skipped"
        workflow.current_stage = "skipped"
        workflow.add_history_event(
            "WORKFLOW_SKIPPED",
            "Onboarding workflow skipped by user",
            "skipped",
            {"answers_collected_count": len(answers_collected)}
        )
        
        if workflow.workflow_id in self.app_state.active_workflows:
            self.app_state.completed_workflows.append(
                self.app_state.active_workflows.pop(workflow.workflow_id)
            )
        
        answered_keys = [key for key, value in answers_collected.items() if value is not None]
        confirmation_message = "Okay, I've skipped the rest of the onboarding for now."
        if answered_keys:
            confirmation_message += f" I've saved your answers for: {', '.join(answered_keys)}."
        else:
            confirmation_message += " No preferences were saved."
            
        log.info(f"Onboarding skipped for user {self.user_profile.user_id}. {len(answers_collected)} answers collected.")
        
        return {
            "success": True,
            "skipped": True,
            "message": confirmation_message,
            "profile_updated": True, # Profile is updated with skip status and any collected answers
            "answers_collected_count": len(answers_collected)
        }

    def get_accumulated_answers_summary(self) -> str:
        """Returns a string summarizing the keys of answers collected so far."""
        if self.user_profile.profile_data and "preferences" in self.user_profile.profile_data:
            answered_keys = []
            prefs = self.user_profile.profile_data["preferences"]
            if prefs.get("preferred_name"): answered_keys.append("Preferred Name")
            if prefs.get("primary_role"): answered_keys.append("Primary Role")
            if prefs.get("main_projects"): answered_keys.append("Main Projects")
            if prefs.get("tool_preferences"): answered_keys.append("Tool Preferences")
            if prefs.get("communication_style"): answered_keys.append("Communication Style")
            if prefs.get("notifications_enabled") is not None: answered_keys.append("Notification preference")
            
            # Check personal credentials setup if that question was answered "no" or if tokens exist
            creds = self.user_profile.profile_data.get("personal_credentials")
            if isinstance(creds, dict):
                if creds.get("setup_declined"):
                    answered_keys.append("Personal Credentials choice (declined)")
                elif any(key in creds for key in ["github_token", "jira_email", "jira_token"]):
                     answered_keys.append("Personal Credentials (details provided/attempted)")

            if answered_keys:
                return f"So far, I have your settings for: {', '.join(answered_keys)}."
        return "No preferences have been saved yet."

    def is_completed(self) -> bool:
        """Checks if the onboarding workflow is complete based on its context status."""
        return self.context.status == "completed"

def get_active_onboarding_workflow(app_state: AppState, user_id: str) -> Optional[WorkflowContext]:
    """Gets the active onboarding workflow for a user, if any."""
    
    for workflow in app_state.active_workflows.values():
        if (workflow.workflow_type == "onboarding" and 
            workflow.status == "active" and 
            workflow.data.get("user_id") == user_id):
            return workflow
    
    return None 