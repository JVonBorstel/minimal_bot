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
    
    def __init__(self, user_profile: UserProfile, app_state: AppState):
        self.user_profile = user_profile
        self.app_state = app_state
        self.config = get_config()
        
    @staticmethod
    def should_trigger_onboarding(user_profile: UserProfile, app_state: AppState) -> bool:
        """Determines if onboarding should be triggered for this user."""
        
        # Check if user is new (within last 5 minutes)
        current_time = int(time.time())
        time_since_first_seen = current_time - user_profile.first_seen_timestamp
        is_new_user = time_since_first_seen < 300  # 5 minutes
        
        # Check if onboarding already completed
        profile_data = user_profile.profile_data or {}
        onboarding_completed = profile_data.get("onboarding_completed", False)
        
        # Check if there's already an active onboarding workflow
        has_active_onboarding = any(
            wf.workflow_type == "onboarding" and wf.status == "active"
            for wf in app_state.active_workflows.values()
        )
        
        should_trigger = (
            is_new_user and 
            not onboarding_completed and 
            not has_active_onboarding
        )
        
        if should_trigger:
            log.info(f"Triggering onboarding for new user {user_profile.user_id} (first seen {time_since_first_seen}s ago)")
        
        return should_trigger
    
    def start_workflow(self) -> WorkflowContext:
        """Starts the onboarding workflow."""
        
        workflow = WorkflowContext(
            workflow_type="onboarding",
            status="active",
            current_stage="welcome",
            data={
                "user_id": self.user_profile.user_id,
                "current_question_index": 0,
                "answers": {},
                "started_at": datetime.utcnow().isoformat(),
                "questions_total": len(ONBOARDING_QUESTIONS)
            }
        )
        
        workflow.add_history_event(
            "WORKFLOW_STARTED",
            f"Onboarding workflow started for user {self.user_profile.display_name}",
            "welcome"
        )
        
        # Add to active workflows
        self.app_state.active_workflows[workflow.workflow_id] = workflow
        
        log.info(f"Started onboarding workflow {workflow.workflow_id} for user {self.user_profile.user_id}")
        return workflow
    
    def process_answer(self, workflow_id: str, user_input: str) -> Dict[str, Any]:
        """Processes a user's answer to an onboarding question."""
        
        if workflow_id not in self.app_state.active_workflows:
            return {"error": "Workflow not found"}
            
        workflow = self.app_state.active_workflows[workflow_id]
        
        if workflow.workflow_type != "onboarding" or workflow.status != "active":
            return {"error": "Invalid workflow state"}
        
        current_index = workflow.data.get("current_question_index", 0)
        
        # Handle case where current_index might be out of bounds due to follow-ups being processed
        # This situation should ideally be handled by _get_next_question advancing states correctly
        # but as a safeguard:
        if workflow.data.get("processing_follow_ups"):
            follow_up_questions = workflow.data.get("follow_up_questions", [])
            follow_up_index = workflow.data.get("follow_up_index", 0)
            if follow_up_index >= len(follow_up_questions):
                 # Attempt to transition from follow-ups to next main question if stuck
                log.warning(f"process_answer: Follow-up index {follow_up_index} out of bounds for {len(follow_up_questions)} follow-ups. Attempting to advance state.")
                # This mimics part of _get_next_question logic to ensure progression
                workflow.data["processing_follow_ups"] = False
                workflow.data.pop("follow_up_questions", None)
                workflow.data.pop("follow_up_index", None)
                current_index = workflow.data.get("current_question_index", 0) + 1 # Advance main index
                workflow.data["current_question_index"] = current_index
                # Now check if onboarding is complete after this forced advancement
        if current_index >= len(ONBOARDING_QUESTIONS):
                    log.info(f"process_answer: Forced advancement led to onboarding completion for workflow {workflow_id}.")
                    return self._complete_onboarding(workflow) # Complete onboarding
                # Otherwise, proceed to fetch the new current_question
                log.info(f"process_answer: Forced advancement to main question index {current_index} for workflow {workflow_id}.")


        if current_index >= len(ONBOARDING_QUESTIONS) and not workflow.data.get("processing_follow_ups"):
            return self._complete_onboarding(workflow)
        
        # Determine if we are processing a main question or a follow-up question
        if workflow.data.get("processing_follow_ups"):
            follow_up_questions = workflow.data.get("follow_up_questions", [])
            follow_up_index = workflow.data.get("follow_up_index", 0)
            if follow_up_index < len(follow_up_questions):
                current_question = follow_up_questions[follow_up_index]
            else:
                # Should have been handled by _get_next_question or the safeguard above
                log.error(f"Inconsistent state: processing_follow_ups is true but follow_up_index is out of bounds. WF: {workflow_id}")
                return {"error": "Internal error: Inconsistent follow-up state."}
        else:
        current_question = ONBOARDING_QUESTIONS[current_index]
        
        # Validate and store the answer
        validation_result = self._validate_answer(current_question, user_input)
        if not validation_result["valid"]:
            return {
                "success": False,
                "message": validation_result["error"],
                "retry_question": True
            }
        
        processed_value = validation_result["processed_value"]
        
        # Store the raw answer in workflow.data for full record
        workflow.data["answers"][current_question.key] = processed_value
        
        # Incrementally update UserProfile's profile_data with the answer
        # Initialize profile_data and preferences if they don't exist
        if self.user_profile.profile_data is None:
            self.user_profile.profile_data = {}
        if "preferences" not in self.user_profile.profile_data:
            self.user_profile.profile_data["preferences"] = {}

        # Map onboarding keys to UserProfile.preferences keys
        # This logic is similar to _complete_onboarding but applied incrementally
        if current_question.key == "welcome_name":
            self.user_profile.profile_data["preferences"]["preferred_name"] = processed_value
        elif current_question.key == "primary_role":
            self.user_profile.profile_data["preferences"]["primary_role"] = processed_value
        elif current_question.key == "main_projects":
            projects = [p.strip() for p in (processed_value or "").split(",") if p.strip()]
            self.user_profile.profile_data["preferences"]["main_projects"] = projects
        elif current_question.key == "tool_preferences":
            self.user_profile.profile_data["preferences"]["tool_preferences"] = processed_value if isinstance(processed_value, list) else []
        elif current_question.key == "communication_style":
            self.user_profile.profile_data["preferences"]["communication_style"] = processed_value
        elif current_question.key == "notifications":
            self.user_profile.profile_data["preferences"]["notifications_enabled"] = (processed_value == "yes")
        elif current_question.key == "personal_credentials":
             # This doesn't directly go into preferences, but its answer ("yes"/"no") is recorded.
             # Follow-up questions will handle specific credential details.
             # If "no", then personal_credentials might be cleared or marked as declined.
            if processed_value == "no":
                if "personal_credentials" in self.user_profile.profile_data:
                    self.user_profile.profile_data["personal_credentials"] = {"setup_declined": True}
        # For credential follow-up questions
        elif current_question.key in ["github_token", "jira_email", "jira_token"]:
            if processed_value: # Only save if a value was provided (not skipped/none)
                if "personal_credentials" not in self.user_profile.profile_data or \
                   not isinstance(self.user_profile.profile_data.get("personal_credentials"), dict) or \
                   self.user_profile.profile_data["personal_credentials"].get("setup_declined"): # type: ignore
                    self.user_profile.profile_data["personal_credentials"] = {}
                self.user_profile.profile_data["personal_credentials"][current_question.key] = processed_value # type: ignore
        
        workflow.add_history_event(
            "ANSWER_RECORDED",
            f"Answer recorded for {current_question.key}: {processed_value}",
            current_question.key
        )
        
        # Prepare information for confirmation message
        confirmation_info = {
            "answer_saved_key": current_question.key,
            "answer_saved_value": processed_value,
            "question_skipped": validation_result.get("skipped_non_required", False)
        }
        
        # Move to next question or handle follow-ups
        next_question_result = self._get_next_question(workflow, current_question, processed_value)
        
        # Merge confirmation info with next question result
        if isinstance(next_question_result, dict):
            next_question_result.update(confirmation_info)
        
        return next_question_result
    
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
    
    def _get_next_question(self, workflow: WorkflowContext, current_question: OnboardingQuestion, answer: Any) -> Dict[str, Any]:
        """Gets the next question in the sequence."""
        
        # Check for follow-up questions
        if (current_question.follow_up_questions and 
            str(answer).lower() in current_question.follow_up_questions):
            
            follow_ups = current_question.follow_up_questions[str(answer).lower()]
            workflow.data["follow_up_questions"] = follow_ups
            workflow.data["follow_up_index"] = 0
            workflow.data["processing_follow_ups"] = True
            
            # Return first follow-up question
            return self._format_question_response(follow_ups[0], workflow)
        
        # Handle follow-up question progression
        if workflow.data.get("processing_follow_ups"):
            follow_up_index = workflow.data.get("follow_up_index", 0) + 1
            follow_ups = workflow.data.get("follow_up_questions", [])
            
            if follow_up_index < len(follow_ups):
                workflow.data["follow_up_index"] = follow_up_index
                return self._format_question_response(follow_ups[follow_up_index], workflow)
            else:
                # Done with follow-ups, move to next main question
                workflow.data["processing_follow_ups"] = False
                workflow.data.pop("follow_up_questions", None)
                workflow.data.pop("follow_up_index", None)
        
        # Move to next main question
        current_index = workflow.data.get("current_question_index", 0) + 1
        workflow.data["current_question_index"] = current_index
        
        if current_index >= len(ONBOARDING_QUESTIONS):
            return self._complete_onboarding(workflow)
        
        next_question = ONBOARDING_QUESTIONS[current_index]
        return self._format_question_response(next_question, workflow)
    
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
    
    def _complete_onboarding(self, workflow: WorkflowContext) -> Dict[str, Any]:
        """Completes the onboarding workflow and saves user preferences."""
        
        answers = workflow.data.get("answers", {})
        
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
        workflow.status = "completed"
        workflow.current_stage = "completed"
        workflow.add_history_event(
            "WORKFLOW_COMPLETED",
            "Onboarding workflow completed successfully",
            "completed",
            {"answers_count": len(answers)}
        )
        
        # Move to completed workflows
        if workflow.workflow_id in self.app_state.active_workflows:
            self.app_state.completed_workflows.append(
                self.app_state.active_workflows.pop(workflow.workflow_id)
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

        buttons = [
            CardAction(type=ActionTypes.im_back, title="Explore Commands (@augie help)", value="@augie help"),
            CardAction(type=ActionTypes.im_back, title="Manage My Preferences", value="@augie preferences")
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
        # Ensure onboarding_completed is explicitly false if skipped
        self.user_profile.profile_data["onboarding_completed"] = False 

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

def get_active_onboarding_workflow(app_state: AppState, user_id: str) -> Optional[WorkflowContext]:
    """Gets the active onboarding workflow for a user, if any."""
    
    for workflow in app_state.active_workflows.values():
        if (workflow.workflow_type == "onboarding" and 
            workflow.status == "active" and 
            workflow.data.get("user_id") == user_id):
            return workflow
    
    return None 