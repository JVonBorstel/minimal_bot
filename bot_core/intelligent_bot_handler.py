"""
Intelligent Bot Handler

This module demonstrates how to use LLM-based intent classification instead of 
hardcoded string matching for natural, intelligent conversation handling.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from core_logic.intent_classifier import IntentClassifier, UserIntent, classify_and_respond

logger = logging.getLogger(__name__)

class IntelligentBotHandler:
    """
    Intelligent bot interaction handler that uses LLM intent classification
    instead of hardcoded rules for natural conversation handling.
    
    This replaces rigid string matching with intelligent intent understanding.
    """
    
    def __init__(self, llm_interface, app_config):
        self.llm_interface = llm_interface
        self.app_config = app_config
        self.intent_classifier = IntentClassifier(llm_interface)
        
    async def handle_user_message_intelligently(
        self, 
        user_message: str, 
        turn_context, 
        app_state,
        user_profile = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Handle user messages using intelligent intent classification instead of hardcoded rules.
        
        Args:
            user_message: The user's message
            turn_context: Bot Framework turn context
            app_state: Current application state
            user_profile: User profile if available
            
        Returns:
            Tuple of (handled, response_message)
            - handled: True if the message was handled intelligently
            - response_message: Optional response message to send
        """
        
        # Build context for intelligent classification
        context = self._build_conversation_context(app_state, user_profile)
        
        try:
            # Use intelligent classification instead of hardcoded rules
            result = await classify_and_respond(
                self.llm_interface,
                user_message,
                context
            )
            
            intent = result["intent"]
            confidence = result["confidence"]
            suggested_response = result["response"]
            suggestions = result["suggestions"]
            
            logger.info(f"Intelligent classification: '{user_message[:50]}' -> {intent.value} (confidence: {confidence})")
            
            # Handle based on intelligent classification
            if intent == UserIntent.ONBOARDING_ACCEPT:
                return await self._handle_onboarding_accept(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.ONBOARDING_DECLINE:
                return await self._handle_onboarding_decline(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.ONBOARDING_POSTPONE:
                return await self._handle_onboarding_postpone(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.ONBOARDING_QUESTION:
                return await self._handle_onboarding_question(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.ONBOARDING_ANSWER:
                return await self._handle_onboarding_answer(turn_context, app_state, user_profile, user_message)
                
            elif intent == UserIntent.COMMAND_HELP:
                return await self._handle_help_request(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.COMMAND_PERMISSIONS:
                return await self._handle_permissions_request(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.WORKFLOW_CANCEL:
                return await self._handle_workflow_cancellation(turn_context, app_state, user_profile, suggested_response)
                
            elif intent == UserIntent.GREETING:
                return await self._handle_greeting(turn_context, app_state, user_profile, suggested_response)
                
            # For unclear intent, ask for clarification using LLM intelligence
            elif intent == UserIntent.UNCLEAR:
                clarification_response = await self._generate_intelligent_clarification(user_message, context)
                await turn_context.send_activity(clarification_response)
                return True, clarification_response
                
            else:
                # Intent recognized but not specifically handled - let main logic continue
                logger.debug(f"Intent {intent.value} recognized but delegating to main logic")
                return False, None
                
        except Exception as e:
            logger.error(f"Error in intelligent message handling: {e}", exc_info=True)
            # Fallback to main logic on error
            return False, None
    
    def _build_conversation_context(self, app_state, user_profile) -> Dict[str, Any]:
        """Build rich context for intelligent classification"""
        context = {
            "app_state": app_state,
            "session_id": app_state.session_id if app_state else None,
        }
        
        if user_profile:
            context.update({
                "user_role": user_profile.assigned_role,
                "user_id": user_profile.user_id,
                "display_name": user_profile.display_name
            })
            
            # Onboarding context
            if hasattr(user_profile, 'profile_data') and user_profile.profile_data:
                onboarding_status = user_profile.profile_data.get("onboarding_status")
                context["onboarding_status"] = onboarding_status
        
        if app_state:
            # Check for pending onboarding decision
            context["pending_onboarding_decision"] = getattr(app_state, 'meta_flags', {}).get("pending_onboarding_decision", False)
            
            # Active workflows
            if hasattr(app_state, 'active_workflows') and app_state.active_workflows:
                context["active_workflows"] = [wf.workflow_type for wf in app_state.active_workflows]
                
                # Check for active onboarding
                onboarding_workflows = [wf for wf in app_state.active_workflows if wf.workflow_type == "onboarding"]
                context["active_onboarding_workflow"] = len(onboarding_workflows) > 0
            
            # Message history length for context
            if hasattr(app_state, 'messages'):
                context["message_count"] = len(app_state.messages)
        
        return context
    
    async def _handle_onboarding_accept(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle intelligent onboarding acceptance"""
        try:
            from workflows.onboarding import OnboardingWorkflow, ONBOARDING_QUESTIONS
            from botbuilder.core import MessageFactory
            from botbuilder.schema import SuggestedActions
            
            # Start onboarding workflow
            onboarding_handler = OnboardingWorkflow(user_profile, app_state)
            workflow = onboarding_handler.start_workflow()
            
            # Send first question intelligently
            first_question_response = onboarding_handler._format_question_response(ONBOARDING_QUESTIONS[0], workflow)
            response_text = f"**{first_question_response['progress']}** {first_question_response['message']}"
            
            activity = MessageFactory.text(response_text)
            if first_question_response.get("suggested_actions"):
                activity.suggested_actions = SuggestedActions(actions=first_question_response["suggested_actions"])
            
            await turn_context.send_activity(activity)
            
            # Update profile
            if hasattr(user_profile, 'profile_data') and isinstance(user_profile.profile_data, dict):
                user_profile.profile_data["onboarding_status"] = "started"
                from datetime import datetime
                user_profile.profile_data["onboarding_started_at"] = datetime.utcnow().isoformat()
                
                from user_auth import db_manager
                db_manager.save_user_profile(user_profile.model_dump())
            
            logger.info(f"Intelligently started onboarding for user {user_profile.user_id}")
            return True, response_text
            
        except Exception as e:
            logger.error(f"Error handling intelligent onboarding acceptance: {e}", exc_info=True)
            # Fallback to suggested response
            await turn_context.send_activity(suggested_response)
            return True, suggested_response
    
    async def _handle_onboarding_decline(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle intelligent onboarding decline"""
        try:
            from botbuilder.core import MessageFactory
            
            # Use LLM-generated response instead of hardcoded message
            await turn_context.send_activity(MessageFactory.text(suggested_response))
            
            # Update profile
            if hasattr(user_profile, 'profile_data') and isinstance(user_profile.profile_data, dict):
                user_profile.profile_data["onboarding_status"] = "declined"
                from datetime import datetime
                user_profile.profile_data["onboarding_declined_at"] = datetime.utcnow().isoformat()
                
                from user_auth import db_manager
                db_manager.save_user_profile(user_profile.model_dump())
            
            logger.info(f"Intelligently handled onboarding decline for user {user_profile.user_id}")
            return True, suggested_response
            
        except Exception as e:
            logger.error(f"Error handling intelligent onboarding decline: {e}", exc_info=True)
            fallback_response = "No problem! You can always ask me to set up your preferences later."
            await turn_context.send_activity(fallback_response)
            return True, fallback_response
    
    async def _handle_onboarding_postpone(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle intelligent onboarding postponement"""
        try:
            from botbuilder.core import MessageFactory
            
            # Use intelligent response
            await turn_context.send_activity(MessageFactory.text(suggested_response))
            
            # Update profile
            if hasattr(user_profile, 'profile_data') and isinstance(user_profile.profile_data, dict):
                user_profile.profile_data["onboarding_status"] = "postponed"
                from datetime import datetime
                user_profile.profile_data["onboarding_postponed_at"] = datetime.utcnow().isoformat()
                
                from user_auth import db_manager
                db_manager.save_user_profile(user_profile.model_dump())
            
            logger.info(f"Intelligently handled onboarding postponement for user {user_profile.user_id}")
            return True, suggested_response
            
        except Exception as e:
            logger.error(f"Error handling intelligent onboarding postponement: {e}", exc_info=True)
            fallback_response = "Understood! We can do this setup later when you're ready."
            await turn_context.send_activity(fallback_response)
            return True, fallback_response
    
    async def _handle_onboarding_question(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle questions about onboarding process"""
        try:
            from botbuilder.core import MessageFactory
            
            # Use LLM-generated explanation
            await turn_context.send_activity(MessageFactory.text(suggested_response))
            
            logger.info(f"Provided intelligent onboarding explanation to user {user_profile.user_id}")
            return True, suggested_response
            
        except Exception as e:
            logger.error(f"Error handling onboarding question: {e}", exc_info=True)
            fallback_response = "The onboarding helps me understand your preferences and work style to provide better assistance."
            await turn_context.send_activity(fallback_response)
            return True, fallback_response
    
    async def _handle_onboarding_answer(self, turn_context, app_state, user_profile, user_message) -> Tuple[bool, str]:
        """Handle onboarding answers with existing logic but better integration"""
        # This would integrate with existing onboarding workflow processing
        # but with better natural language understanding of the answers
        logger.info(f"Processing onboarding answer intelligently: {user_message[:50]}")
        # Let existing onboarding logic handle this but with better NLU context
        return False, None  # Delegate to existing workflow logic
    
    async def _handle_help_request(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle help requests intelligently"""
        try:
            from botbuilder.core import MessageFactory
            
            # Use contextual help response from LLM
            await turn_context.send_activity(MessageFactory.text(suggested_response))
            
            logger.info(f"Provided intelligent help to user {user_profile.user_id if user_profile else 'unknown'}")
            return True, suggested_response
            
        except Exception as e:
            logger.error(f"Error handling help request: {e}", exc_info=True)
            return False, None  # Let existing help logic handle
    
    async def _handle_permissions_request(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle permissions/role requests intelligently"""
        # Let existing permissions logic handle this but with better NLU
        return False, None
    
    async def _handle_workflow_cancellation(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle workflow cancellation requests intelligently"""
        try:
            from botbuilder.core import MessageFactory
            
            # Cancel active workflows intelligently
            if hasattr(app_state, 'active_workflows') and app_state.active_workflows:
                cancelled_workflows = []
                for workflow in app_state.active_workflows:
                    cancelled_workflows.append(workflow.workflow_type)
                
                app_state.active_workflows.clear()
                
                response = f"I've cancelled the following workflows: {', '.join(cancelled_workflows)}. How can I help you now?"
                await turn_context.send_activity(MessageFactory.text(response))
                return True, response
            else:
                response = "There are no active workflows to cancel. What would you like to do?"
                await turn_context.send_activity(MessageFactory.text(response))
                return True, response
                
        except Exception as e:
            logger.error(f"Error handling workflow cancellation: {e}", exc_info=True)
            return False, None
    
    async def _handle_greeting(self, turn_context, app_state, user_profile, suggested_response) -> Tuple[bool, str]:
        """Handle greetings intelligently"""
        try:
            from botbuilder.core import MessageFactory
            
            # Use LLM-generated contextual greeting
            await turn_context.send_activity(MessageFactory.text(suggested_response))
            
            logger.info(f"Responded to greeting intelligently for user {user_profile.user_id if user_profile else 'unknown'}")
            return True, suggested_response
            
        except Exception as e:
            logger.error(f"Error handling greeting: {e}", exc_info=True)
            fallback_response = "Hello! How can I help you today?"
            await turn_context.send_activity(fallback_response)
            return True, fallback_response
    
    async def _generate_intelligent_clarification(self, user_message: str, context: Dict[str, Any]) -> str:
        """Generate intelligent clarification when intent is unclear"""
        
        clarification_prompt = f"""The user sent a message but their intent is unclear. Generate a helpful clarification question.

User Message: "{user_message}"
Context: {context}

Generate a natural, helpful response that:
1. Acknowledges their message
2. Asks for clarification about what they want to do
3. Offers relevant suggestions based on context
4. Maintains a friendly, helpful tone

Response:"""

        try:
            messages = [{"role": "user", "content": clarification_prompt}]
            
            response_text = ""
            stream = self.llm_interface.generate_content_stream(
                messages=messages,
                app_state=context.get("app_state"),
                tools=None
            )
            
            async for chunk in stream:
                if hasattr(chunk, 'text') and chunk.text:
                    response_text += chunk.text
                elif isinstance(chunk, dict) and chunk.get('text'):
                    response_text += chunk['text']
            
            return response_text.strip() or "I'm not sure what you'd like me to help with. Could you provide more details?"
            
        except Exception as e:
            logger.error(f"Error generating clarification: {e}", exc_info=True)
            return "I'm not sure what you'd like me to help with. Could you provide more details?" 