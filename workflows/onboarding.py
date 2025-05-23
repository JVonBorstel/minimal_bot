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

log = logging.getLogger(__name__)

# Onboarding question types
class OnboardingQuestionType:
    TEXT = "text"
    CHOICE = "choice" 
    YES_NO = "yes_no"
    EMAIL = "email"
    ROLE_REQUEST = "role_request"
    MULTI_CHOICE = "multi_choice"

class OnboardingQuestion:
    """Represents a single onboarding question."""
    
    def __init__(
        self,
        key: str,
        question: str,
        question_type: str,
        choices: Optional[List[str]] = None,
        required: bool = True,
        help_text: Optional[str] = None,
        validation_pattern: Optional[str] = None,
        follow_up_questions: Optional[Dict[str, List['OnboardingQuestion']]] = None
    ):
        self.key = key
        self.question = question
        self.question_type = question_type
        self.choices = choices or []
        self.required = required
        self.help_text = help_text
        self.validation_pattern = validation_pattern
        self.follow_up_questions = follow_up_questions or {}

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
        
        if current_index >= len(ONBOARDING_QUESTIONS):
            return self._complete_onboarding(workflow)
        
        current_question = ONBOARDING_QUESTIONS[current_index]
        
        # Validate and store the answer
        validation_result = self._validate_answer(current_question, user_input)
        if not validation_result["valid"]:
            return {
                "success": False,
                "message": validation_result["error"],
                "retry_question": True
            }
        
        # Store the answer
        workflow.data["answers"][current_question.key] = validation_result["processed_value"]
        
        workflow.add_history_event(
            "ANSWER_RECORDED",
            f"Answer recorded for {current_question.key}: {validation_result['processed_value']}",
            current_question.key
        )
        
        # Move to next question or handle follow-ups
        next_question_result = self._get_next_question(workflow, current_question, validation_result["processed_value"])
        
        return next_question_result
    
    def _validate_answer(self, question: OnboardingQuestion, user_input: str) -> Dict[str, Any]:
        """Validates a user's answer to a question."""
        
        user_input = user_input.strip()
        
        # Handle empty/skip answers
        if not user_input or user_input.lower() in ["skip", "none", "n/a"]:
            if question.required:
                return {
                    "valid": False,
                    "error": "This question is required. Please provide an answer."
                }
            else:
                return {
                    "valid": True,
                    "processed_value": None
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
                    "error": "Please answer with 'yes' or 'no'"
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
            
            return {
                "valid": False,
                "error": f"Please choose from: {', '.join(f'{i+1}. {choice}' for i, choice in enumerate(question.choices))}"
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
                return {
                    "valid": False,
                    "error": f"Please select from: {', '.join(f'{i+1}. {choice}' for i, choice in enumerate(question.choices))}"
                }
            
            return {"valid": True, "processed_value": selections}
        
        elif question.question_type == OnboardingQuestionType.EMAIL:
            if "@" in user_input and "." in user_input:
                return {"valid": True, "processed_value": user_input.lower()}
            else:
                return {
                    "valid": False,
                    "error": "Please enter a valid email address"
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
        
        workflow.current_stage = question.key
        workflow.update_timestamp()
        
        return response
    
    def _complete_onboarding(self, workflow: WorkflowContext) -> Dict[str, Any]:
        """Completes the onboarding workflow and saves user preferences."""
        
        answers = workflow.data.get("answers", {})
        
        # Process and store the answers in user profile
        profile_data = self.user_profile.profile_data or {}
        
        # Store onboarding responses
        profile_data["onboarding_completed"] = True
        profile_data["onboarding_completed_at"] = datetime.utcnow().isoformat()
        profile_data["preferences"] = {
            "preferred_name": answers.get("welcome_name"),
            "primary_role": answers.get("primary_role"),
            "main_projects": [p.strip() for p in (answers.get("main_projects") or "").split(",") if p.strip()],
            "tool_preferences": answers.get("tool_preferences", []),
            "communication_style": answers.get("communication_style"),
            "notifications_enabled": answers.get("notifications") == "yes"
        }
        
        # Store personal credentials if provided
        if answers.get("personal_credentials") == "yes":
            credentials = {}
            if answers.get("github_token"):
                credentials["github_token"] = answers["github_token"]
            if answers.get("jira_email"):
                credentials["jira_email"] = answers["jira_email"]
            if answers.get("jira_token"):
                credentials["jira_token"] = answers["jira_token"]
            
            if credentials:
                profile_data["personal_credentials"] = credentials
        
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
        completion_message = self._generate_completion_message(preferred_name, answers, suggested_role)
        
        log.info(f"Completed onboarding for user {self.user_profile.user_id} with {len(answers)} answers")
        
        return {
            "success": True,
            "completed": True,
            "message": completion_message,
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
    
    def _generate_completion_message(self, preferred_name: str, answers: Dict[str, Any], suggested_role: Optional[str]) -> str:
        """Generates a personalized completion message."""
        
        message = f"🎉 **Welcome aboard, {preferred_name}!** Your onboarding is complete.\n\n"
        
        # Summarize their preferences
        if answers.get("primary_role"):
            message += f"👤 **Role**: {answers['primary_role']}\n"
        
        if answers.get("main_projects"):
            projects = [p.strip() for p in answers["main_projects"].split(",") if p.strip()]
            if projects:
                message += f"📂 **Main Projects**: {', '.join(projects)}\n"
        
        if answers.get("tool_preferences"):
            tools = answers["tool_preferences"]
            if isinstance(tools, list) and tools:
                message += f"🛠️ **Preferred Tools**: {', '.join(tools)}\n"
        
        if answers.get("communication_style"):
            message += f"💬 **Communication Style**: {answers['communication_style']}\n"
        
        message += "\n"
        
        # Role suggestion
        if suggested_role:
            message += f"🎯 Based on your role, I suggest setting your access level to **{suggested_role}**. "
            message += "An admin can update this for you.\n\n"
        
        # Personal credentials
        if answers.get("personal_credentials") == "yes":
            cred_count = sum(1 for key in ["github_token", "jira_email", "jira_token"] if answers.get(key))
            if cred_count > 0:
                message += f"🔑 I've securely stored your {cred_count} personal credential(s) for enhanced access.\n\n"
        
        # Next steps
        message += "**What's Next?**\n"
        message += "• Try asking me `help` to see available commands\n"
        message += "• Ask about your projects or repositories\n"
        message += "• Request Jira tickets or GitHub information\n"
        message += "• Use `@augie preferences` anytime to update your settings\n\n"
        
        message += "I'm here to help make your workflow smoother! 🚀"
        
        return message

def get_active_onboarding_workflow(app_state: AppState, user_id: str) -> Optional[WorkflowContext]:
    """Gets the active onboarding workflow for a user, if any."""
    
    for workflow in app_state.active_workflows.values():
        if (workflow.workflow_type == "onboarding" and 
            workflow.status == "active" and 
            workflow.data.get("user_id") == user_id):
            return workflow
    
    return None 