from botbuilder.core import TurnContext, MessageFactory, ConversationState, UserState, BotState, CardFactory
from botbuilder.schema import Activity, ActivityTypes, SuggestedActions, CardAction, HeroCard, CardImage, ActionTypes, Attachment
import logging
from typing import Optional, Dict, Any, List, AsyncIterable, Union
import asyncio
import time
from datetime import datetime
from enum import Enum

# Placeholder for LLMInterface and other future dependencies
# from llm_interface import LLMInterface
from config import Config
from core_logic.intent_classifier import IntentClassifier, UserIntent
from workflows.workflow_manager import WorkflowManager
from llm_interface import LLMInterface
from tools.tool_executor import ToolExecutor
from core_logic.history_utils import prepare_messages_for_llm_from_appstate
from user_auth import db_manager
from user_auth.models import UserProfile
from user_auth.utils import get_current_user_profile, invalidate_user_profile_cache
from state_models import AppState, _migrate_state_if_needed, Message, TextPart
from core_logic.constants import MAX_TOOL_CYCLES_OUTER, TOOL_CALL_ID_PREFIX
import uuid
from utils.utils import validate_and_repair_state
from workflows.onboarding import OnboardingWorkflow, get_active_onboarding_workflow, ONBOARDING_QUESTIONS

class IntelligentConversationOrchestrator:
    def __init__(self, 
                 app_state: AppState,
                 config: Config,
                 llm_interface: Optional[LLMInterface] = None, 
                 tool_executor: Optional[ToolExecutor] = None,
                 workflow_manager: Optional[WorkflowManager] = None,
                 intent_classifier: Optional[IntentClassifier] = None,
                 conversation_state: Optional[ConversationState] = None,
                 user_state: Optional[UserState] = None):
        """
        Initialize the IntelligentConversationOrchestrator.
        
        Args:
            app_state: The application state
            config: The application configuration
            llm_interface: Interface to the language model
            tool_executor: Tool execution handler
            workflow_manager: Workflow management system
            intent_classifier: Intent classification system
            conversation_state: Bot framework conversation state
            user_state: Bot framework user state
        """
        self.app_state = app_state
        self.config = config
        self.llm_interface = llm_interface
        self.tool_executor = tool_executor
        self.workflow_manager = workflow_manager
        self.intent_classifier = intent_classifier
        self.conversation_state = conversation_state
        self.user_state = user_state
        self.logger = logging.getLogger(__name__)
        
        # Initialize workflow manager if not provided
        if not self.workflow_manager:
            self.workflow_manager = WorkflowManager(self.app_state, self.llm_interface, self.config)
            
        # Initialize intent classifier if not provided
        if not self.intent_classifier:
            self.intent_classifier = IntentClassifier(self.llm_interface)

        if self.conversation_state:
            self.convo_state_accessor = self.conversation_state.create_property("AppStateForOrchestrator")
        else:
            self.convo_state_accessor = None
            self.logger.warning("ConversationState not provided to Orchestrator. State management will be limited.")

        # Basic logging setup
        self.logger.info("IntelligentConversationOrchestrator initialized.")

    async def _get_app_state_and_user(self, turn_context: TurnContext) -> tuple[Optional[AppState], Optional[UserProfile]]:
        """
        Placeholder for loading AppState and UserProfile.
        In the final architecture, this logic will be more robust, likely involving
        direct use of state accessors passed during __init__ or a dedicated state utility.
        This mimics what MyBot._get_conversation_data and get_current_user_profile do.
        """
        app_state: Optional[AppState] = None
        user_profile: Optional[UserProfile] = None

        if not self.convo_state_accessor:
            self.logger.error("Orchestrator: convo_state_accessor not initialized. Cannot load AppState.")
            return None, None

        try:
            # Load AppState similar to MyBot._get_conversation_data
            app_state_raw = await self.convo_state_accessor.get(turn_context, lambda: {})
            self.logger.debug(f"Orchestrator: Raw state from accessor: {type(app_state_raw)}")

            if not app_state_raw:
                app_state = AppState(session_id=turn_context.activity.conversation.id)
                self.logger.info(f"Orchestrator: Initialized fresh AppState for conv {app_state.session_id}")
            elif isinstance(app_state_raw, AppState):
                app_state = app_state_raw
                self.logger.info(f"Orchestrator: Accessor returned AppState instance directly for conv {app_state.session_id}")
            elif isinstance(app_state_raw, dict):
                self.logger.info(f"Orchestrator: Existing dict state found for conv {turn_context.activity.conversation.id}. Migrating/Validating.")
                migrated_data = _migrate_state_if_needed(app_state_raw)
                if isinstance(migrated_data, AppState):
                    app_state = migrated_data
                else: # Should be dict after migration
                    app_state = AppState(**migrated_data)
            else:
                self.logger.error(f"Orchestrator: Loaded state is unexpected type {type(app_state_raw)}. Re-initializing.")
                app_state = AppState(session_id=turn_context.activity.conversation.id)

            # Ensure session_id is set
            if not app_state.session_id and turn_context.activity and turn_context.activity.conversation:
                app_state.session_id = turn_context.activity.conversation.id
            
            # Load UserProfile
            # For now, using get_current_user_profile which uses db_manager or a direct DB interaction.
            # In future, could use self.user_state if that becomes primary for UserProfile storage.
            if self.config:
                user_profile = get_current_user_profile(turn_context, db_path=self.config.STATE_DB_PATH)
                if user_profile:
                    app_state.current_user = user_profile # Ensure app_state has the latest user profile
                    self.logger.info(f"Orchestrator: User profile loaded/set for {user_profile.user_id}")
                else:
                    app_state.current_user = None # Ensure it's None if not found
                    self.logger.info("Orchestrator: No user profile found for current turn.")
            else:
                self.logger.warning("Orchestrator: Config not available, cannot determine DB path for UserProfile.")
                app_state.current_user = None

            # TODO: Add other AppState initializations/validations from MyBot._get_conversation_data if needed here
            # (e.g., selected_model, available_personas, etc., if not handled by Pydantic defaults adequately)

            return app_state, app_state.current_user # Return user_profile from app_state
        
        except Exception as e:
            self.logger.error(f"Orchestrator: Error in _get_app_state_and_user: {e}", exc_info=True)
            return None, None

    async def _save_app_state(self, turn_context: TurnContext, app_state: Optional[AppState]):
        if not self.convo_state_accessor:
            self.logger.error("Orchestrator: convo_state_accessor not initialized. Cannot save AppState.")
            return
        if app_state is None:
            self.logger.warning("Orchestrator: Attempted to save None AppState. Skipping.")
            return
        try:
            await self.convo_state_accessor.set(turn_context, app_state)
            if self.conversation_state:
                 await self.conversation_state.save_changes(turn_context, force=False)
                 self.logger.info(f"Orchestrator: AppState saved for conv {app_state.session_id}")
            if self.user_state: 
                 await self.user_state.save_changes(turn_context, force=False)
        except Exception as e:
            self.logger.error(f"Orchestrator: Error saving AppState: {e}", exc_info=True)

    async def _send_activity_from_dict(self, turn_context: TurnContext, response_dict: Optional[Dict[str, Any]]):
        """Helper to send an activity described by a dictionary (e.g., from workflow manager)."""
        if not response_dict:
            self.logger.info("No response dict provided to _send_activity_from_dict.")
            return

        activity_text = response_dict.get("text") or response_dict.get("message")
        activity_type = response_dict.get("type", ActivityTypes.message.value) # Default to message type
        suggested_actions = response_dict.get("suggested_actions")

        # Check if the message is actually a card structure
        if isinstance(activity_text, dict) and activity_text.get("contentType") and activity_text.get("content"):
            # The 'message' field contains a card structure
            attachment = Attachment(
                content_type=activity_text["contentType"],
                content=activity_text["content"]
            )
            activity = MessageFactory.attachment(attachment)
            await turn_context.send_activity(activity)
            self.logger.info(f"Sent card attachment from nested message dict with content type: {activity_text['contentType']}")
            return

        if activity_text and isinstance(activity_text, str):
            # If there's text, we will always try to send it as a message.
            # The original 'type' from response_dict (like 'choice', 'yes_no') primarily informs the OnboardingWorkflow,
            # here we care about constructing a sendable Bot Framework activity.
            activity = MessageFactory.text(activity_text)
            if suggested_actions and isinstance(suggested_actions, list):
                processed_actions = []
                for action_data in suggested_actions:
                    if isinstance(action_data, dict):
                        action_type_val = action_data.get("type", ActionTypes.im_back)
                        if isinstance(action_type_val, Enum): action_type_val = action_type_val.value
                        processed_actions.append(CardAction(
                            type=action_type_val,
                            title=action_data.get("title", "Action"),
                            value=action_data.get("value", action_data.get("title"))
                        ))
                    elif isinstance(action_data, CardAction):
                        processed_actions.append(action_data)
                    else:
                        self.logger.warning(f"Unsupported suggested action type: {type(action_data)}")
                if processed_actions:
                    activity.suggested_actions = SuggestedActions(actions=processed_actions)
            
            await turn_context.send_activity(activity)
            log_text_preview = activity_text[:100] if isinstance(activity_text, str) else "[activity_text is not a string]"
            self.logger.info(f"Sent message activity (derived from text/message field) from dict: '{log_text_preview}...' with {len(suggested_actions or [])} suggested actions.")

        elif response_dict.get("contentType") and response_dict.get("content"): # No primary text, but looks like a card/attachment
             # This handles HeroCards or other attachments if the dict is structured like an Attachment
             attachment = Attachment(
                content_type=response_dict["contentType"],
                content=response_dict["content"]
             )
             activity = MessageFactory.attachment(attachment)
             # Suggested actions might not be directly compatible with all card types in this simple helper
             # but can be added if the card schema supports it.
             await turn_context.send_activity(activity)
             self.logger.info(f"Sent attachment from dict with content type: {response_dict['contentType']}")   
        else:
            self.logger.warning(f"Received response_dict of unsupported format or missing text/message and suggested_actions: {response_dict}")

    async def _send_help_message(self, turn_context: TurnContext, user_message: str = None):
        """Sends a help message by calling the actual help tool with extracted topic."""
        topic = None
        
        # Extract topic from user message if provided
        if user_message:
            user_message_lower = user_message.lower()
            
            # Check for specific service mentions
            if any(keyword in user_message_lower for keyword in ['github', 'git', 'repository', 'repo', 'pull request', 'pr', 'issue']):
                topic = "github"
            elif any(keyword in user_message_lower for keyword in ['jira', 'ticket', 'sprint', 'story', 'epic']):
                topic = "jira"
            elif any(keyword in user_message_lower for keyword in ['greptile', 'code search', 'search code']):
                topic = "greptile"
            elif any(keyword in user_message_lower for keyword in ['perplexity', 'web search', 'search web']):
                topic = "perplexity"
        
        # Try to call the actual help tool
        if self.tool_executor:
            try:
                # Get app state for tool execution
                app_state, user_profile = await self._get_app_state_and_user(turn_context)
                if not app_state:
                    self.logger.warning("Could not get app_state for help tool execution, falling back to simple help.")
                    await self._send_fallback_help_message(turn_context)
                    return
                
                # Prepare parameters for help tool
                help_params = {}
                if topic:
                    help_params["topic"] = topic
                    self.logger.info(f"Calling help tool with topic: {topic}")
                else:
                    self.logger.info("Calling help tool without specific topic")
                
                # Execute the help tool
                help_result = await self.tool_executor.execute_tool("help", help_params, app_state)
                
                if help_result and help_result.get("status") == "SUCCESS":
                    help_data = help_result.get("data", {})
                    
                    # Format the help response nicely
                    formatted_help = self._format_help_response(help_data)
                    await turn_context.send_activity(MessageFactory.text(formatted_help))
                    self.logger.info(f"Sent dynamic help message with topic: {topic}")
                else:
                    self.logger.warning(f"Help tool execution failed: {help_result}")
                    await self._send_fallback_help_message(turn_context)
                    
            except Exception as e:
                self.logger.error(f"Error executing help tool: {e}", exc_info=True)
                await self._send_fallback_help_message(turn_context)
        else:
            # No tool executor available, use fallback
            await self._send_fallback_help_message(turn_context)

    def _format_help_response(self, help_data: dict) -> str:
        """Format the help tool response into a readable message."""
        lines = []
        
        # Add title and description
        if help_data.get("title"):
            lines.append(f"**{help_data['title']}**")
        if help_data.get("description"):
            lines.append(help_data["description"])
            lines.append("")
        
        # Add sections
        sections = help_data.get("sections", [])
        for section in sections:
            section_name = section.get("name", "")
            section_content = section.get("content", [])
            
            if section_name:
                lines.append(f"## {section_name}")
                lines.append("")
            
            if isinstance(section_content, list):
                for item in section_content:
                    lines.append(item)
            elif isinstance(section_content, str):
                lines.append(section_content)
            
            lines.append("")
        
        return "\n".join(lines).strip()

    async def _send_fallback_help_message(self, turn_context: TurnContext):
        """Sends a simple fallback help message when the help tool isn't available."""
        help_text_lines = [
            "I'm your ChatOps assistant. Here's a general overview of what I can do:",
            "",
            "• Ask me questions or give me tasks in natural language.",
            "• I can use various tools to help you (e.g., GitHub, Jira).",
            "• Type `tools?` to see what tools I have available.",
            "• Type `@bot my role` or `@bot my permissions` to see your current role and permissions.",
            "• Type `@bot reset chat` to clear our conversation history and start fresh.",
            "",
            "If you're new, I might ask to set up your preferences to assist you better!",
            "You can also type `onboard me` or `setup preferences` anytime."
        ]
        await turn_context.send_activity(MessageFactory.text("\n".join(help_text_lines)))
        self.logger.info(f"Sent fallback help message.")

    async def _handle_general_task_with_tools(self, turn_context: TurnContext, app_state: AppState, user_profile: Optional[UserProfile], initial_user_message: str) -> None:
        """
        Handles general tasks that may involve LLM interaction and tool use.
        This adapts the core loop from agent_loop.py.
        """
        self.logger.info(f"Orchestrator: Starting general task handling for: '{initial_user_message[:100]}'")
        max_cycles = self.config.MAX_CONSECUTIVE_TOOL_CALLS if self.config else MAX_TOOL_CYCLES_OUTER
        
        # Ensure user message is in history if not already (e.g. if this is first pass after intent classification)
        # agent_loop.py does this via app_state.add_message in its entry point.
        # Here, we assume the user_message that led to this handler is the last one.

        for cycle_num in range(max_cycles):
            self.logger.info(f"Orchestrator: Tool/LLM Cycle {cycle_num + 1}/{max_cycles}")

            # 1. Prepare messages for LLM
            # Ensure system prompt is handled correctly (prepare_messages_for_llm_from_appstate should manage this)
            llm_messages, history_preparation_notes = prepare_messages_for_llm_from_appstate(app_state, self.config.LLM_MAX_HISTORY_ITEMS)
            if not llm_messages:
                self.logger.error("Orchestrator: No messages prepared for LLM. Aborting cycle.")
                await turn_context.send_activity(MessageFactory.text("I couldn't prepare our conversation history for my AI. Please try again."))
                return
            
            if history_preparation_notes:
                self.logger.debug(f"History preparation notes: {', '.join(history_preparation_notes[:3])}" + 
                                 (f" and {len(history_preparation_notes) - 3} more..." if len(history_preparation_notes) > 3 else ""))

            # 2. Prepare tools for LLM
            available_tools = self.tool_executor.get_available_tool_definitions()
            query_for_tool_selection = app_state.get_last_user_message() or initial_user_message

            # 3. Call LLM
            # The llm_interface.generate_content_stream now handles its own tool preparation via ToolSelector
            llm_stream = self.llm_interface.generate_content_stream(
                messages=llm_messages,
                app_state=app_state,
                tools=available_tools, # Pass all available, selector in LLMInterface will pick
                query=query_for_tool_selection
            )

            accumulated_text_response = []
            tool_calls_received: List[Dict[str, Any]] = []
            llm_turn_completed_without_tools = False
            final_bot_message_sent_this_llm_turn = False
            last_activity_id_to_update = None

            # Send initial typing indicator / placeholder message
            # if cycle_num == 0: # Only for the very first LLM call in this task handler
            typing_activity = Activity(type=ActivityTypes.typing)
            sent_typing_activity_resource_response = await turn_context.send_activity(typing_activity)
            last_activity_id_to_update = sent_typing_activity_resource_response.id if sent_typing_activity_resource_response else None
            self.logger.debug(f"Orchestrator: Initial last_activity_id_to_update for LLM response: {last_activity_id_to_update}")

            async for event in llm_stream:
                event_type = event.get("type")
                event_content = event.get("content")

                if event_type == "text_chunk":
                    if event_content:
                        accumulated_text_response.append(str(event_content))
                        # Update activity if possible
                        if last_activity_id_to_update:
                            updated_text = "".join(accumulated_text_response).strip()
                            if updated_text:
                                # Check if accumulated text is getting too long for reliable updates
                                text_is_long = len(updated_text) > 1000  # Threshold for streaming updates
                                
                                if not text_is_long:
                                    # Try to update for shorter messages
                                    try:
                                        await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=updated_text))
                                        final_bot_message_sent_this_llm_turn = True
                                    except Exception as e_update:
                                        self.logger.warning(f"Orchestrator: Failed to update activity {last_activity_id_to_update}, sending new. Error: {e_update}")
                                        res = await turn_context.send_activity(MessageFactory.text(updated_text))
                                        last_activity_id_to_update = res.id if res else None
                                        final_bot_message_sent_this_llm_turn = True
                                        accumulated_text_response = []  # Clear after sending new message
                                else:
                                    # Text is too long for reliable updates, send as new message
                                    self.logger.info(f"Orchestrator: Streaming text too long ({len(updated_text)} chars), sending as new message.")
                                    res = await turn_context.send_activity(MessageFactory.text(updated_text))
                                    last_activity_id_to_update = res.id if res else None
                                    final_bot_message_sent_this_llm_turn = True
                                    accumulated_text_response = []  # Clear after sending new message
                        elif accumulated_text_response: # No activity to update, send new if there's content
                            updated_text = "".join(accumulated_text_response).strip()
                            if updated_text:  # Only send if there's actual content
                                res = await turn_context.send_activity(MessageFactory.text(updated_text))
                                last_activity_id_to_update = res.id if res else None
                                final_bot_message_sent_this_llm_turn = True
                                accumulated_text_response = [] # Clear after sending
                elif event_type == "tool_calls":
                    if isinstance(event_content, list):
                        tool_calls_received.extend(event_content)
                        self.logger.info(f"Orchestrator: LLM requested {len(event_content)} tool_calls: {[tc.get('function',{}).get('name') for tc in event_content]}")
                    # If there was text before tool_calls, send it as a separate message
                    if accumulated_text_response:
                        updated_text = "".join(accumulated_text_response).strip()
                        if updated_text:  # Only send if there's actual content
                            await turn_context.send_activity(MessageFactory.text(updated_text))
                            accumulated_text_response = []  # Clear after sending
                            final_bot_message_sent_this_llm_turn = True 
                            last_activity_id_to_update = None # New message was sent
                elif event_type == "error":
                    self.logger.error(f"Orchestrator: Error event from LLM stream: {event_content}")
                    err_text_for_user = "I encountered an issue with my AI core."
                    err_code = event_content.get("code", "UNKNOWN_LLM_ERROR") if isinstance(event_content, dict) else "UNKNOWN_LLM_ERROR"
                    raw_err_detail = event_content.get("content", str(event_content)) if isinstance(event_content, dict) else str(event_content)
                    
                    internal_situation = f"LLM interaction failed. Code: {err_code}. Detail: {raw_err_detail[:150]}"
                    desired_tone = "apologetic and helpful"
                    
                    if err_code == "API_TIMEOUT":
                        internal_situation = "My attempt to reach my AI core timed out."
                        desired_tone = "apologetic, suggesting to try again shortly"
                    elif err_code == "API_SERVICE_UNAVAILABLE":
                        internal_situation = "My AI core seems to be temporarily unavailable."
                        desired_tone = "apologetic, suggesting to try again later"
                    elif err_code == "API_RATE_LIMIT":
                        internal_situation = "I'm a bit overwhelmed with requests right now."
                        desired_tone = "apologetic, suggesting a brief pause before trying again"
                    elif err_code == "API_CLIENT_ERROR" or err_code == "NO_VALID_MESSAGES":
                        internal_situation = "There was a problem with the information I tried to process."
                        desired_tone = "apologetic, perhaps suggesting user rephrase if it was a complex request"
                    
                    phrased_error_message = await self._get_llm_phrased_response(app_state, initial_user_message, internal_situation, desired_tone)
                    await turn_context.send_activity(MessageFactory.text(phrased_error_message))
                    app_state.last_interaction_status = f"ERROR_LLM_{err_code}"
                    return # End task handling on error
                elif event_type == "completed":
                    self.logger.info("Orchestrator: LLM stream completed for this turn.")
                    if not tool_calls_received: # LLM finished and didn't call tools
                        llm_turn_completed_without_tools = True
                    break # Break from LLM event loop

            # Add LLM's final response (if any) to history before tool execution
            final_text_str = "".join(accumulated_text_response).strip()
            
            if tool_calls_received: # LLM wants to use tools
                self.logger.info(f"Orchestrator: LLM requested tools. Final text before tools: '{final_text_str}'")
                if final_text_str: # There was introductory text from LLM before tool calls
                    # Ensure this text was sent if not already part of a stream update
                    if not final_bot_message_sent_this_llm_turn:
                        if last_activity_id_to_update:
                            try:
                                await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=final_text_str))
                                self.logger.debug(f"Updated activity {last_activity_id_to_update} with pre-tool text.")
                            except Exception as e_update_pre_tool:
                                self.logger.warning(f"Failed to update activity {last_activity_id_to_update} with pre-tool text, sending new. Error: {e_update_pre_tool}")
                                await turn_context.send_activity(MessageFactory.text(final_text_str))
                        else:
                            await turn_context.send_activity(MessageFactory.text(final_text_str))
                    app_state.add_message(role="assistant", content=final_text_str)
                    last_activity_id_to_update = None # Pre-tool text sent, next tool messages will be new

                # Add tool calls to history
                processed_tool_calls_for_history = []
                for tc_event_content in tool_calls_received:
                    processed_tool_calls_for_history.append({
                        "id": tc_event_content.get("id", f"{TOOL_CALL_ID_PREFIX}{uuid.uuid4().hex[:8]}"),
                        "type": "function", 
                        "functionCall": { 
                            "name": tc_event_content.get("function", {}).get("name"),
                            "args": tc_event_content.get("function", {}).get("arguments", {})
                        }
                    })
                if processed_tool_calls_for_history:
                    app_state.add_message(role="assistant", tool_calls=processed_tool_calls_for_history) 

                # Execute tools and gather results
                all_tool_executions_successful = True
                if tool_calls_received: # Ensure we only try if there are calls
                    try:
                        for tool_call_event_item in tool_calls_received:
                            tool_result_msg_dict = await self.tool_executor.execute_tool_call_from_event(
                                app_state=app_state,
                                tool_call_event_content=tool_call_event_item, 
                                config=self.config,
                                turn_context=turn_context
                            )
                            if tool_result_msg_dict:
                                app_state.add_message(**tool_result_msg_dict)
                                self.logger.debug(f"Orchestrator: Added tool result for {tool_result_msg_dict.get('name', 'unknown_tool')} to app_state.")
                                # Check if this specific tool call failed based on its content
                                if isinstance(tool_result_msg_dict.get('parts'), list) and tool_result_msg_dict['parts']: 
                                    part_content = tool_result_msg_dict['parts'][0]
                                    if isinstance(part_content, dict) and isinstance(part_content.get('function_response'), dict): 
                                        response_content = part_content['function_response'].get('response',{}).get('content',{}) 
                                        if isinstance(response_content, dict) and response_content.get('status') == 'ERROR': 
                                            all_tool_executions_successful = False 
                                            self.logger.warning(f"Tool execution reported an error: {response_content.get('message')}")
                            else:
                                self.logger.warning(f"Orchestrator: Tool execution for {tool_call_event_item.get('function',{}).get('name')} returned no message dict. Assuming failure for this call.")
                                all_tool_executions_successful = False
                        
                        if not all_tool_executions_successful:
                            self.logger.warning("One or more tool executions failed in the batch.")

                    except Exception as e_tool_exec: 
                        self.logger.error(f"Orchestrator: Error during tool execution phase: {e_tool_exec}", exc_info=True)
                        situation = f"I encountered an issue while trying to use one of my tools to help with: '{initial_user_message[:50]}...' (Details: {str(e_tool_exec)[:100]})"
                        phrased_err_msg = await self._get_llm_phrased_response(app_state, initial_user_message, situation, "apologetic")
                        # Try to update typing indicator with error, or send new
                        if last_activity_id_to_update:
                            try:
                                await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=phrased_err_msg))
                            except Exception: await turn_context.send_activity(MessageFactory.text(phrased_err_msg))
                        else: await turn_context.send_activity(MessageFactory.text(phrased_err_msg))
                        app_state.last_interaction_status = "ERROR_TOOL_EXECUTION"
                        return 

            elif llm_turn_completed_without_tools: # LLM completed and didn't call tools
                self.logger.info(f"Orchestrator: LLM completed its turn without requesting tools. Final text: '{final_text_str}'")
                app_state.last_interaction_status = "COMPLETED_OK"
                
                message_to_send = final_text_str
                if not message_to_send: # LLM provided no text
                    situation = "I've processed your request."
                    message_to_send = await self._get_llm_phrased_response(app_state, initial_user_message, situation, "neutral and acknowledging")
                    self.logger.info(f"LLM provided no text, using phrased acknowledgement: '{message_to_send}'")

                if message_to_send: # We have something to say (either original LLM text or fallback)
                    if final_text_str: # Original LLM text was not empty
                         app_state.add_message(role="assistant", content=message_to_send)

                    # Check if message is long - if so, always send as new message to avoid emulator issues
                    message_is_long = len(message_to_send) > 500  # Threshold for long messages
                    
                    if last_activity_id_to_update and not final_bot_message_sent_this_llm_turn and not message_is_long:
                        # Only try to update for shorter messages
                        try:
                            await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=message_to_send))
                            self.logger.debug(f"Updated activity {last_activity_id_to_update} with final LLM response/acknowledgement.")
                        except Exception as e_update_final:
                            self.logger.warning(f"Failed to update activity {last_activity_id_to_update} with final response, sending new. Error: {e_update_final}")
                            await turn_context.send_activity(MessageFactory.text(message_to_send))
                    else:
                        # Send as new message for long content or when update isn't appropriate
                        if message_is_long:
                            self.logger.info(f"Sending long message ({len(message_to_send)} chars) as new activity to avoid emulator issues.")
                        await turn_context.send_activity(MessageFactory.text(message_to_send))
                else: # Still no message to send (e.g. _get_llm_phrased_response also returned empty) - highly unlikely with fallback
                    self.logger.warning("No final message or acknowledgement to send to user.")
                break # End of general task loop

            else: # LLM stream ended without tool calls and without explicit completion.
                self.logger.warning("Orchestrator: LLM stream ended without tool calls and without explicit completion. Ending task.")
                app_state.last_interaction_status = "COMPLETED_UNKNOWN"
                if not final_bot_message_sent_this_llm_turn and not tool_calls_received: 
                    situation = "I finished my current step, but I'm not sure how to proceed further with that."
                    phrased_msg = await self._get_llm_phrased_response(app_state, initial_user_message, situation, "slightly puzzled but helpful")
                    if last_activity_id_to_update:
                        try: await turn_context.update_activity(Activity(id=last_activity_id_to_update, type=ActivityTypes.message, text=phrased_msg))
                        except Exception: await turn_context.send_activity(MessageFactory.text(phrased_msg))
                    else: await turn_context.send_activity(MessageFactory.text(phrased_msg))
                break
        else: # Loop finished (max_cycles reached)
            self.logger.warning(f"Orchestrator: Max tool/LLM cycles ({max_cycles}) reached.")
            situation = f"I've been working on your request for '{initial_user_message[:50]}...' for a few steps, but it's becoming quite complex."
            phrased_msg = await self._get_llm_phrased_response(app_state, initial_user_message, situation, "apologetic, suggesting to simplify or rephrase")
            await turn_context.send_activity(MessageFactory.text(phrased_msg))
            app_state.last_interaction_status = "MAX_CYCLES_REACHED"
        
        self.logger.info(f"Orchestrator: General task handling finished. Final status: {app_state.last_interaction_status}")
        # Final state save is handled by the caller (process_activity)

    async def _get_llm_phrased_response(self, app_state: AppState, user_message: str, internal_situation: str, desired_tone: str = "helpful and understanding") -> str:
        """Generates a user-facing message based on an internal situation using the LLM."""
        if not self.llm_interface:
            self.logger.warning("LLM interface not available for phrasing response. Returning generic message.")
            return f"I encountered a situation: {internal_situation}. I'm still learning how to best respond to that!"
        
        prompt = (
            f"You are the Aughie chatbot. You need to communicate something to the user based on an internal situation. "
            f"The user just said: '{user_message}'\n"
            f"The internal situation is: {internal_situation}\n"
            f"Please phrase a response to the user that is {desired_tone}. "
            f"If the situation implies confusion, ask for clarification gently. "
            f"If it implies an error, apologize and perhaps suggest trying again or rephrasing. "
            f"Keep it concise and natural. "
            f"IMPORTANT: Do NOT mention technical details like intent classifications, confidence scores, or internal system states."
        )
        try:
            messages_for_llm = [{
                "role": "user", 
                "parts": [{"text": f"You are a helpful assistant that rephrases internal bot statuses into natural user-facing messages.\n\n{prompt}"}]
            }]
            
            phrased_response_text = ""
            stream = self.llm_interface.generate_content_stream(messages=messages_for_llm, app_state=app_state)
            async for event in stream:
                if event.get("type") == "text_chunk" and event.get("content"):
                    phrased_response_text += event.get("content")
                elif event.get("type") == "error":
                    self.logger.error(f"Error from LLM while trying to phrase response: {event.get('content')}")
                    return f"I had a thought, but struggled to phrase it: {internal_situation}"
            
            return phrased_response_text.strip() if phrased_response_text.strip() else f"I noted: {internal_situation}"
        except Exception as e:
            self.logger.error(f"Exception in _get_llm_phrased_response: {e}", exc_info=True)
            return f"I encountered an issue trying to respond to: {internal_situation}"

    async def _get_contextual_llm_response(self, app_state: AppState, user_message: str, situation: str, context_info: str, desired_tone: str = "helpful") -> str:
        """Generates a contextual response using the LLM with additional context and guidance."""
        if not self.llm_interface:
            self.logger.warning("LLM interface not available for contextual response.")
            return "I understand what you're asking, but I'm having trouble formulating a response right now."
        
        # Get user context for personalization
        user_context = ""
        if app_state.current_user and app_state.current_user.profile_data:
            prefs = app_state.current_user.profile_data.get("preferences", {})
            if prefs.get("preferred_name"):
                user_context += f"User's preferred name: {prefs['preferred_name']}\n"
            if prefs.get("primary_role"):
                user_context += f"User's role: {prefs['primary_role']}\n"
            if prefs.get("communication_style"):
                user_context += f"User prefers: {prefs['communication_style']}\n"
        
        # Get available tools for accurate information
        tools_info = ""
        if self.tool_executor:
            available_tools = self.tool_executor.get_available_tool_definitions()
            if available_tools:
                tool_names = [tool.get("name", "unknown") for tool in available_tools[:10]]  # Limit to avoid token bloat
                tools_info = f"Available tools I can use: {', '.join(tool_names)}"
        
        prompt = f"""You are Aughie, an intelligent development assistant bot. Generate a natural response based on the following context.

User said: "{user_message}"

Situation: {situation}

Context: {context_info}

{user_context}
{tools_info}

Generate a response that is {desired_tone}. Be specific and helpful. Use markdown formatting where appropriate.
If discussing tools or capabilities, mention actual tools available to you.
Keep the response concise but informative.
"""
        
        try:
            messages_for_llm = [{
                "role": "user", 
                "parts": [{"text": f"You are Aughie, a helpful development assistant that provides contextual, intelligent responses.\n\n{prompt}"}]
            }]
            
            response_text = ""
            stream = self.llm_interface.generate_content_stream(messages=messages_for_llm, app_state=app_state)
            async for event in stream:
                if event.get("type") == "text_chunk" and event.get("content"):
                    response_text += event.get("content")
                elif event.get("type") == "error":
                    self.logger.error(f"Error from LLM in contextual response: {event.get('content')}")
                    return "I understand what you're asking, but I encountered an issue generating a response. Could you try rephrasing?"
            
            return response_text.strip() if response_text.strip() else "I'm here to help! What would you like to know?"
        except Exception as e:
            self.logger.error(f"Exception in _get_contextual_llm_response: {e}", exc_info=True)
            return "I understand your question, but I'm having trouble formulating a complete response right now."

    async def process_activity(self, turn_context: TurnContext):
        """
        Processes an incoming activity from the user.
        This is the main entry point for the orchestrator.
        """
        if turn_context.activity.type == ActivityTypes.message:
            user_message = turn_context.activity.text
            self.logger.info(f"Orchestrator received user message: {user_message}")

            app_state, user_profile = await self._get_app_state_and_user(turn_context)

            if not app_state:
                self.logger.error("Orchestrator: Failed to load AppState. Aborting turn processing.")
                await turn_context.send_activity(MessageFactory.text("Sorry, I encountered an issue with my memory. Please try again."))
                return
            
            user_id_for_log = user_profile.user_id if user_profile else "anonymous"
            self.logger.info(f"Orchestrator: Processing for user: {user_id_for_log}, AppState version: {app_state.version}")

            # Add user message to app_state history (unless it's an event or something)
            # Ensure it's only added if it's a new message to avoid duplicates on retries/internal loops.
            if not app_state.messages or app_state.messages[-1].text != user_message or app_state.messages[-1].role != "user":
                app_state.add_message(role="user", content=user_message)
                self.logger.debug(f"Orchestrator: Added current user message to app_state: '{user_message[:100]}'")
            
            handled_by_active_workflow = False
            # 1. Check if an active workflow should handle this message first
            if self.workflow_manager and user_profile: # Workflows typically need user context
                active_workflow_type = app_state.get_primary_active_workflow_name()
                if active_workflow_type:
                    self.logger.info(f"Orchestrator: Active workflow '{active_workflow_type}' detected. Routing to WorkflowManager.")
                    workflow_response_dict = await self.workflow_manager.process_workflow_step(turn_context, app_state, user_profile, user_message)
                    if workflow_response_dict: # If workflow provided a response, it handled it.
                        await self._send_activity_from_dict(turn_context, workflow_response_dict)
                        handled_by_active_workflow = True # Mark as handled
                        
                        # If workflow updated the user profile, save it and invalidate cache
                        if workflow_response_dict.get("profile_updated") and user_profile:
                            self.logger.info(f"Workflow '{active_workflow_type}' updated user profile. Saving and invalidating cache.")
                            try:
                                if db_manager.save_user_profile(user_profile.model_dump()):
                                    self.logger.info(f"User profile saved successfully after workflow update.")
                                    # Invalidate cache to ensure fresh data next time
                                    invalidate_user_profile_cache(user_profile.user_id)
                                    self.logger.info(f"Cache invalidated for user {user_profile.user_id} after workflow update.")
                                else:
                                    self.logger.error(f"Failed to save user profile after workflow '{active_workflow_type}' update.")
                            except Exception as e:
                                self.logger.error(f"Error saving profile after workflow: {e}", exc_info=True)
                    else:
                        self.logger.info(f"Orchestrator: Workflow '{active_workflow_type}' processed input but yielded no immediate response. Continuing.")
                        if not app_state.get_active_workflow_by_type(active_workflow_type): 
                            self.logger.info(f"Orchestrator: Workflow '{active_workflow_type}' seems to have ended after processing.")
            
            if handled_by_active_workflow:
                await self._save_app_state(turn_context, app_state)
                self.logger.info("Orchestrator: Turn handled by active workflow.")
                return

            # --- START: Proactive Onboarding Trigger for New Users (before intent classification) ---
            if user_profile and self.workflow_manager: # Ensure user_profile and workflow_manager are available
                # Check if an onboarding workflow is already active OR if a decision is pending
                is_onboarding_active_or_pending = get_active_onboarding_workflow(app_state, user_profile.user_id) is not None or \
                                                  (hasattr(app_state, 'meta_flags') and app_state.meta_flags and app_state.meta_flags.get("pending_onboarding_decision"))

                if not is_onboarding_active_or_pending and OnboardingWorkflow.should_trigger_onboarding(user_profile, app_state):
                    self.logger.info(f"Orchestrator: User {user_profile.user_id} is eligible for onboarding. Prompting user.", extra={"event_type": "onboarding_prompt_initiated_orchestrator"})
                    
                    prompt_hero_card = HeroCard(
                        title="🤖 Welcome to Aughie!",
                        subtitle="Your AI Development Assistant",
                        text=f"Hi {user_profile.display_name}! 👋\n\nI'm here to help with your development tasks. To provide the best assistance, I'd love to learn a bit about you and your preferences.\n\n**Quick Setup** (~2 minutes)\n• Personalize my responses\n• Configure your tools\n• Set communication style",
                        images=[CardImage(url=getattr(self.config.settings, "AUGIE_LOGO_URL", "https://raw.githubusercontent.com/Aughie/augie_images/main/logos_various_formats/logo_circle_transparent_256.png"))],
                        buttons=[
                            CardAction(type=ActionTypes.im_back, title="🚀 Let's Get Started!", value="start onboarding"),
                            CardAction(type=ActionTypes.im_back, title="⏭️ Maybe Later", value="skip onboarding for now")
                        ]
                    )
                    prompt_activity = MessageFactory.attachment(CardFactory.hero_card(prompt_hero_card))
                    await turn_context.send_activity(prompt_activity)
                    
                    if not hasattr(app_state, 'meta_flags') or app_state.meta_flags is None:
                        app_state.meta_flags = {}
                    app_state.meta_flags["pending_onboarding_decision"] = True
                    
                    await self._save_app_state(turn_context, app_state)
                    self.logger.info(f"Orchestrator: Sent onboarding prompt to user {user_profile.user_id}. Awaiting decision.", extra={"event_type": "onboarding_prompt_sent_orchestrator"})
                    return # Important: End turn here, wait for user's response to the prompt
            # --- END: Proactive Onboarding Trigger ---

            # 2. If not handled by an active workflow or proactive onboarding prompt, proceed with intent classification
            intent = UserIntent.UNCLEAR
            confidence = 0.0
            if self.intent_classifier and self.llm_interface:
                classification_context = {
                    "user_message": user_message,
                    "user_role": user_profile.assigned_role if user_profile and hasattr(user_profile, 'assigned_role') else "guest",
                    "pending_onboarding_decision": app_state.meta_flags.get("pending_onboarding_decision", False) if hasattr(app_state, 'meta_flags') and app_state.meta_flags else False,
                    # active_onboarding_workflow is false here as we are past the active workflow check
                    "active_onboarding_workflow": False, 
                    "app_state_version": app_state.version
                }
                try:
                    # Fix: Use strings instead of dict objects for message content, as the LLM expects string messages
                    intent, confidence = await self.intent_classifier.classify_intent(
                        user_message, 
                        classification_context
                    )
                    self.logger.info(f"Orchestrator: Classified intent: {intent.value} with confidence: {confidence:.2f}")
                except Exception as e_intent:
                    self.logger.error(f"Orchestrator: Intent classification failed: {e_intent}", exc_info=True)
                    situation = "I had a little trouble understanding your main request."
                    phrased_msg = await self._get_llm_phrased_response(app_state, user_message, situation, "apologetic, asking to rephrase")
                    await turn_context.send_activity(MessageFactory.text(phrased_msg))
                    await self._save_app_state(turn_context, app_state)
                    return
            else:
                self.logger.warning("Orchestrator: Intent classifier or LLM interface not available. Defaulting to UNCLEAR intent.")

            # 3. Route based on classified intent (if not handled by workflow)
            handled_by_specific_intent = False
            if intent == UserIntent.COMMAND_HELP and confidence > 0.5:
                await self._send_help_message(turn_context, user_message)
                handled_by_specific_intent = True
            elif intent == UserIntent.COMMAND_PERMISSIONS and confidence > 0.5:
                self.logger.info(f"Orchestrator: Routing to permissions command based on classified intent: {intent.value}")
                
                # Check if user is asking about bot rules/guidelines rather than permissions
                if any(word in user_message.lower() for word in ["rules", "guidelines", "constraints", "limitations"]):
                    # Use LLM to generate a contextual response about bot capabilities
                    situation = "The user is asking about my rules, guidelines, or capabilities as a bot assistant."
                    context_info = "I should explain my capabilities (code assistance, GitHub/Jira integration, search, etc.) and my guidelines (respecting permissions, being helpful, asking for clarification when needed)."
                    response_text = await self._get_contextual_llm_response(app_state, user_message, situation, context_info, "informative and friendly")
                    await turn_context.send_activity(MessageFactory.text(response_text))
                else:
                    await turn_context.send_activity(MessageFactory.text("I understand you're asking about your permissions or role. This feature is being integrated! Soon I'll be able to tell you more."))
                handled_by_specific_intent = True
            elif intent == UserIntent.ONBOARDING_ACCEPT and confidence > 0.5:
                self.logger.info(f"Orchestrator: Routing to ONBOARDING_ACCEPT based on classified intent: {intent.value}")
                if self.workflow_manager and user_profile and app_state:
                    if hasattr(app_state, 'meta_flags') and app_state.meta_flags:
                        app_state.meta_flags["pending_onboarding_decision"] = False
                    workflow_response = await self.workflow_manager.start_workflow(turn_context, app_state, user_profile, "onboarding")
                    await self._send_activity_from_dict(turn_context, workflow_response)
                else:
                    await turn_context.send_activity(MessageFactory.text("Onboarding cannot be started (missing components)."))
                handled_by_specific_intent = True
            elif intent == UserIntent.ONBOARDING_DECLINE and confidence > 0.5:
                self.logger.info(f"Orchestrator: Routing to ONBOARDING_DECLINE based on classified intent: {intent.value}")
                if hasattr(app_state, 'meta_flags') and app_state.meta_flags:
                    app_state.meta_flags["pending_onboarding_decision"] = False
                
                if user_profile:
                    if user_profile.profile_data is None:
                        user_profile.profile_data = {}
                    user_profile.profile_data["onboarding_interaction_status"] = "declined"
                    user_profile.profile_data["onboarding_declined_at"] = datetime.utcnow().isoformat()
                    user_profile.profile_data["onboarding_completed"] = True  # Align with skip_onboarding behavior

                    self.logger.info(f"Attempting to save profile for user {user_profile.user_id} after decline.")
                    try:
                        if db_manager.save_user_profile(user_profile.model_dump()):
                            self.logger.info(f"User {user_profile.user_id} declined onboarding. Flag set and profile SAVED successfully.")
                            # Invalidate the cache to ensure fresh data is loaded next time
                            invalidate_user_profile_cache(user_profile.user_id)
                            self.logger.info(f"Cache invalidated for user {user_profile.user_id} after decline.")
                        else:
                            self.logger.error(f"User {user_profile.user_id} declined onboarding. Flag set BUT FAILED TO SAVE PROFILE (db_manager.save_user_profile returned False).")
                    except NameError as ne:
                        self.logger.error(f"User {user_profile.user_id} declined onboarding. Flag set BUT NameError on save (db_manager likely not imported): {ne}", exc_info=True)
                    except Exception as e_save_profile:
                        self.logger.error(f"User {user_profile.user_id} declined onboarding. Flag set BUT EXCEPTION ON SAVE: {e_save_profile}", exc_info=True)
                else:
                    self.logger.warning("Orchestrator: User profile not found, cannot set onboarding decline flag.")

                await turn_context.send_activity(MessageFactory.text("Okay, I understand you don't want to proceed with the detailed setup. We can skip it."))
                handled_by_specific_intent = True
            elif intent == UserIntent.ONBOARDING_POSTPONE and confidence > 0.5:
                self.logger.info(f"Orchestrator: Routing to ONBOARDING_POSTPONE based on classified intent: {intent.value}")
                if hasattr(app_state, 'meta_flags') and app_state.meta_flags:
                    app_state.meta_flags["pending_onboarding_decision"] = False
                
                if user_profile:
                    if user_profile.profile_data is None:
                        user_profile.profile_data = {}
                    user_profile.profile_data["onboarding_interaction_status"] = "postponed"
                    user_profile.profile_data["onboarding_postponed_at"] = datetime.utcnow().isoformat()
                    user_profile.profile_data["onboarding_completed"] = True  # Prevent unwanted re-prompts
                    
                    self.logger.info(f"Attempting to save profile for user {user_profile.user_id} after postpone.")
                    try:
                        if db_manager.save_user_profile(user_profile.model_dump()): # Use model_dump() for Pydantic v2+
                            self.logger.info(f"User {user_profile.user_id} postponed onboarding. Flag set and profile SAVED successfully.")
                            # Invalidate the cache to ensure fresh data is loaded next time
                            invalidate_user_profile_cache(user_profile.user_id)
                            self.logger.info(f"Cache invalidated for user {user_profile.user_id} after postpone.")
                        else:
                            self.logger.error(f"User {user_profile.user_id} postponed onboarding. Flag set BUT FAILED TO SAVE PROFILE (db_manager.save_user_profile returned False).")
                    except NameError as ne:
                        self.logger.error(f"User {user_profile.user_id} postponed onboarding. Flag set BUT NameError on save (db_manager likely not imported): {ne}", exc_info=True)
                    except Exception as e_save_profile:
                        self.logger.error(f"User {user_profile.user_id} postponed onboarding. Flag set BUT EXCEPTION ON SAVE: {e_save_profile}", exc_info=True)
                        
                else:
                    self.logger.warning("Orchestrator: User profile not found, cannot set onboarding postponement flag.")

                await turn_context.send_activity(MessageFactory.text("Alright, we can skip the setup for now."))
                handled_by_specific_intent = True
            elif intent == UserIntent.COMMAND_RESET_CHAT and confidence > 0.5:
                self.logger.info(f"Orchestrator: Routing to COMMAND_RESET_CHAT. Clearing chat.")
                if app_state: app_state.clear_chat()
                # Use LLM to phrase the reset confirmation
                situation = "The chat history has just been reset at the user's request."
                response_text = await self._get_llm_phrased_response(app_state, user_message, situation, "reassuring and ready for next steps")
                await turn_context.send_activity(MessageFactory.text(response_text))
                handled_by_specific_intent = True
            elif intent == UserIntent.ONBOARDING_START and confidence > 0.7:
                self.logger.info(f"Orchestrator: Routing to ONBOARDING_START based on classified intent: {intent.value}")
                if self.workflow_manager and user_profile and app_state:
                    # Check if user previously declined/skipped/postponed
                    interaction_status = user_profile.profile_data.get("onboarding_interaction_status") if user_profile.profile_data else None
                    previously_declined = interaction_status in ["declined", "skipped", "postponed"]
                    onboarding_completed = user_profile.profile_data.get("onboarding_completed", False) if user_profile.profile_data else False
                    
                    if previously_declined and onboarding_completed:
                        # User previously opted out but now wants to start
                        self.logger.info(f"User {user_profile.user_id} previously {interaction_status} onboarding, now requesting to start.")
                        
                        # Ask for confirmation
                        hero_card = HeroCard(
                            title="🤔 Start Onboarding Setup?",
                            text=f"I see you previously chose not to complete the setup. Would you like to start it now?\n\nThis will help me personalize my responses and configure your preferences.",
                            buttons=[
                                CardAction(type=ActionTypes.im_back, title="✅ Yes, start setup", value="confirm start onboarding"),
                                CardAction(type=ActionTypes.im_back, title="❌ No, not now", value="cancel start onboarding")
                            ]
                        )
                        confirm_activity = MessageFactory.attachment(CardFactory.hero_card(hero_card))
                        await turn_context.send_activity(confirm_activity)
                        
                        # Set a flag to track pending confirmation
                        if not hasattr(app_state, 'meta_flags') or app_state.meta_flags is None:
                            app_state.meta_flags = {}
                        app_state.meta_flags["pending_onboarding_restart_confirmation"] = True
                    else:
                        # User hasn't completed onboarding yet, start directly
                        self.logger.info(f"Starting onboarding workflow for user {user_profile.user_id}")
                        if user_profile.profile_data is None:
                            user_profile.profile_data = {}
                        user_profile.profile_data["onboarding_completed"] = False
                        
                        workflow_response = await self.workflow_manager.start_workflow(turn_context, app_state, user_profile, "onboarding")
                        await self._send_activity_from_dict(turn_context, workflow_response)
                else:
                    await turn_context.send_activity(MessageFactory.text("I'd like to help you get set up, but some components aren't available right now. Please try again later."))
                handled_by_specific_intent = True
            elif user_message.lower() in ["confirm start onboarding", "yes, start setup"] and \
                 hasattr(app_state, 'meta_flags') and app_state.meta_flags and \
                 app_state.meta_flags.get("pending_onboarding_restart_confirmation"):
                # Handle confirmation of onboarding restart
                self.logger.info("User confirmed onboarding restart")
                app_state.meta_flags["pending_onboarding_restart_confirmation"] = False
                
                if self.workflow_manager and user_profile:
                    if user_profile.profile_data is None:
                        user_profile.profile_data = {}
                    
                    # Clear previous decline/skip/postpone flags
                    user_profile.profile_data["onboarding_interaction_status"] = "re-initiated"
                    user_profile.profile_data["onboarding_completed"] = False
                    for key in ["onboarding_declined_at", "onboarding_skipped_at", "onboarding_postponed_at"]:
                        user_profile.profile_data.pop(key, None)
                    
                    # Save updated profile and invalidate cache
                    try:
                        if db_manager.save_user_profile(user_profile.model_dump()):
                            self.logger.info(f"User profile updated for onboarding restart. Invalidating cache.")
                            invalidate_user_profile_cache(user_profile.user_id)
                    except Exception as e:
                        self.logger.error(f"Error saving profile for onboarding restart: {e}", exc_info=True)
                    
                    # Start the workflow
                    workflow_response = await self.workflow_manager.start_workflow(turn_context, app_state, user_profile, "onboarding")
                    await self._send_activity_from_dict(turn_context, workflow_response)
                handled_by_specific_intent = True
            elif user_message.lower() in ["cancel start onboarding", "no, not now"] and \
                 hasattr(app_state, 'meta_flags') and app_state.meta_flags and \
                 app_state.meta_flags.get("pending_onboarding_restart_confirmation"):
                # Handle cancellation of onboarding restart
                self.logger.info("User cancelled onboarding restart")
                app_state.meta_flags["pending_onboarding_restart_confirmation"] = False
                await turn_context.send_activity(MessageFactory.text("No problem! I'm here whenever you're ready. Just let me know if you'd like to set up your preferences later."))
                handled_by_specific_intent = True
            elif intent == UserIntent.WORKFLOW_CONTINUE and confidence > 0.5:
                # User seems to want to continue something, but there's no active workflow
                self.logger.info(f"Orchestrator: WORKFLOW_CONTINUE intent but no active workflow")
                
                # Check if they just completed onboarding
                recently_completed_onboarding = False
                if user_profile and user_profile.profile_data:
                    onboarding_status = user_profile.profile_data.get("onboarding_status")
                    if onboarding_status == "completed" and app_state.messages:
                        # Check if onboarding was recently completed (within last few messages)
                        recently_completed_onboarding = any(
                            "onboarding" in msg.text.lower() or "setup complete" in msg.text.lower()
                            for msg in app_state.messages[-5:] if msg.role == "assistant" and msg.text
                        )
                
                if recently_completed_onboarding:
                    situation = "The user just completed onboarding and is asking what to do next."
                    context_info = "They've just finished setting up their preferences. Suggest concrete next steps they can take with the bot, focusing on their stated role and tool preferences if available."
                else:
                    situation = "The user wants to continue or know what's next, but there's no active workflow or clear context."
                    context_info = "Provide helpful suggestions for what they can do with the bot, focusing on common tasks and available capabilities."
                
                response_text = await self._get_contextual_llm_response(app_state, user_message, situation, context_info, "encouraging and helpful")
                await turn_context.send_activity(MessageFactory.text(response_text))
                handled_by_specific_intent = True

            # Ensure all explicit intent handlers that `return` also set handled_by_specific_intent = True before returning,
            # or adjust this flow.
            if handled_by_specific_intent:
                await self._save_app_state(turn_context, app_state)
                return

            # 4. Fallback to General Task Handling or Phrased Default Response
            if intent in [UserIntent.GENERAL_TASK, UserIntent.GENERAL_QUESTION] or (intent == UserIntent.UNCLEAR and confidence < 0.7) or confidence <= 0.5:
                self.logger.info(f"Orchestrator: Intent '{intent.value}' (conf: {confidence:.2f}) or low confidence. Proceeding to general task/tool handler.")
                
                # Check if user is asking about tools specifically
                if user_message.lower().strip() in ["tools", "tools?", "what tools", "what tools?", "available tools", "list tools"]:
                    situation = "The user is asking about what tools are available."
                    context_info = "List the specific tools you have access to with brief descriptions of what each can do. Be specific about actual capabilities."
                    response_text = await self._get_contextual_llm_response(app_state, user_message, situation, context_info, "informative and organized")
                    await turn_context.send_activity(MessageFactory.text(response_text))
                    handled_by_specific_intent = True
                elif self.tool_executor: 
                    await self._handle_general_task_with_tools(turn_context, app_state, user_profile, user_message)
                else:
                    self.logger.warning("Orchestrator: Tool executor not available for general task.")
                    situation = f"User message was '{user_message}'. My tool handling is not set up right now, but I understood the request."
                    response_text = await self._get_llm_phrased_response(app_state, user_message, situation)
                    await turn_context.send_activity(MessageFactory.text(response_text))
            else: # Intent recognized with some confidence but not handled by specific flows or general task handler
                self.logger.warning(f"Orchestrator: Intent '{intent.value}' (conf: {confidence:.2f}) was recognized but not explicitly handled. Using LLM to phrase acknowledgement.")
                
                # Create a more user-friendly response based on the intent type
                if intent == UserIntent.GREETING:
                    situation = "The user is greeting me."
                    context_info = "Respond warmly and ask how you can help. If you know their name from preferences, use it."
                    response_text = await self._get_contextual_llm_response(app_state, user_message, situation, context_info, "warm and welcoming")
                    await turn_context.send_activity(MessageFactory.text(response_text))
                elif intent == UserIntent.THANKS:
                    situation = "The user is thanking me."
                    context_info = "Acknowledge their thanks graciously and offer continued assistance."
                    response_text = await self._get_contextual_llm_response(app_state, user_message, situation, context_info, "gracious and helpful")
                    await turn_context.send_activity(MessageFactory.text(response_text))
                else:
                    # For other unhandled intents, provide a helpful response without technical details
                    situation = f"The user said something I recognized but don't have a specific handler for."
                    context_info = "Acknowledge their message and offer to help with common tasks. Don't mention intent classification or technical details."
                    response_text = await self._get_contextual_llm_response(app_state, user_message, situation, context_info, "helpful and proactive")
                    await turn_context.send_activity(MessageFactory.text(response_text))
                handled_by_specific_intent = True
            
            await self._save_app_state(turn_context, app_state)

        elif turn_context.activity.type == ActivityTypes.conversation_update:
            self.logger.info("Received conversation update activity.")
            if turn_context.activity.members_added:
                app_state_for_welcome_check = None # Initialize before loop
                for member in turn_context.activity.members_added:
                    # Prevent bot from welcoming itself.
                    # The recipient.id should be the bot's ID.
                    # We also add an explicit check against a common bot ID pattern if known.
                    # Your log shows bot ID as "bot-1"
                    is_bot_itself = (member.id == turn_context.activity.recipient.id) or (member.id == "bot-1")

                    if not is_bot_itself:
                        self.logger.info(f"Member added: {member.name} (ID: {member.id}) - this is not the bot itself.")
                        
                        # Load app_state only once if needed within the loop, or use one loaded before.
                        if app_state_for_welcome_check is None:
                             app_state_for_welcome_check, _ = await self._get_app_state_and_user(turn_context)
                        
                        welcome_already_sent = False
                        if app_state_for_welcome_check:
                            welcome_key = f"welcomed_user_{member.id}"
                            if hasattr(app_state_for_welcome_check, 'meta_flags') and app_state_for_welcome_check.meta_flags and app_state_for_welcome_check.meta_flags.get(welcome_key):
                                welcome_already_sent = True
                                self.logger.info(f"Welcome message already sent to {member.name} ({member.id}) in this conversation. Skipping.")
                        
                        if not welcome_already_sent:
                            self.logger.info(f"Sending welcome message to {member.name} ({member.id}).")
                            if self.config and hasattr(self.config.settings, 'AUGIE_LOGO_URL'):
                                logo_url = self.config.settings.AUGIE_LOGO_URL
                            else:
                                logo_url = "https://raw.githubusercontent.com/Aughie/augie_images/main/logos_various_formats/logo_circle_transparent_256.png"

                            hero_card = HeroCard(
                                title="👋 Welcome to Aughie!",
                                subtitle="Your AI Development Assistant (Orchestrated)",
                                text=f"Hi {member.name}! I'm here to help. You can ask me questions or tell me to do things.",
                                images=[CardImage(url=logo_url)]
                            )
                            welcome_activity = MessageFactory.attachment(CardFactory.hero_card(hero_card))
                            await turn_context.send_activity(welcome_activity)
                            
                            if app_state_for_welcome_check:
                                if not hasattr(app_state_for_welcome_check, 'meta_flags') or not app_state_for_welcome_check.meta_flags:
                                    app_state_for_welcome_check.meta_flags = {}
                                app_state_for_welcome_check.meta_flags[f"welcomed_user_{member.id}"] = True
                                # Save state after updating welcome flag FOR THIS USER
                                await self._save_app_state(turn_context, app_state_for_welcome_check) 
                        else: # Welcome already sent to this specific member
                            pass # Do nothing further for this member
                    else:
                        self.logger.info(f"Member added: {member.name} (ID: {member.id}) - this IS the bot itself or recipient. Skipping welcome.")

            # General state save outside the loop if app_state was loaded and potentially modified
            # The _save_app_state inside the loop handles saving after a welcome is sent.
            # If no welcome was sent (e.g. all members were bot or already welcomed), 
            # ensure any initial state load/creation is saved if it happened before the loop.
            # However, _get_app_state_and_user in the loop and subsequent _save_app_state for *that specific user* should be sufficient.
            # A final save might be redundant if state hasn't changed outside the welcome logic for a *new* user.
            # Re-evaluate if a final unconditional save is needed here.
            # The original code had:
            # if not app_state: app_state, _ = await self._get_app_state_and_user(turn_context)
            # if app_state: await self._save_app_state(turn_context, app_state)
            # This can be kept if there are other state modifications in conversation_update outside members_added.
            # For now, assuming the targeted save inside the loop is primary for welcome.
            # If app_state_for_welcome_check was loaded and potentially modified (e.g. initialized), ensure it's saved.
            if app_state_for_welcome_check and not turn_context.responded: # Check if any response was sent this turn
                 # This might be too broad if no new user was actually welcomed.
                 # Consider if this save is truly necessary or if the save *after a welcome* is enough.
                 # self.logger.info("Orchestrator: Performing a general AppState save at the end of conversation_update if state was loaded.")
                 # await self._save_app_state(turn_context, app_state_for_welcome_check) # Potentially redundant
                 pass

        else:
            self.logger.info(f"Orchestrator received unhandled activity type: {turn_context.activity.type}.")

        # Optionally, send a generic "I can only process messages" or handle other types 