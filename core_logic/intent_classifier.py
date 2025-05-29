"""
Intent Classification System for Aughie Bot

This module provides intelligent intent classification using the LLM rather than 
hardcoded string matching, giving the bot natural language understanding capabilities.
"""

import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
import asyncio
import re

logger = logging.getLogger(__name__)

class UserIntent(Enum):
    """User intent classifications"""
    # Onboarding intents
    ONBOARDING_ACCEPT = "onboarding_accept"
    ONBOARDING_DECLINE = "onboarding_decline" 
    ONBOARDING_POSTPONE = "onboarding_postpone"
    ONBOARDING_QUESTION = "onboarding_question"
    ONBOARDING_ANSWER = "onboarding_answer"
    ONBOARDING_START = "onboarding_start"
    ONBOARDING_STOP = "onboarding_stop"  # Stop/cancel active onboarding
    
    # Command intents
    COMMAND_HELP = "command_help"
    COMMAND_PERMISSIONS = "command_permissions"
    COMMAND_PREFERENCES = "command_preferences"
    COMMAND_RESET_CHAT = "command_reset_chat"
    COMMAND_ADMIN = "command_admin"
    
    # Workflow intents
    WORKFLOW_CONTINUE = "workflow_continue"
    WORKFLOW_CANCEL = "workflow_cancel"
    WORKFLOW_PAUSE = "workflow_pause"
    
    # General intents
    GENERAL_QUESTION = "general_question"
    GENERAL_TASK = "general_task"
    GREETING = "greeting"
    THANKS = "thanks"
    UNCLEAR = "unclear"

class IntentClassifier:
    """
    Intelligent intent classification using LLM instead of hardcoded rules.
    
    This gives the bot natural language understanding capabilities and allows it
    to make intelligent decisions about user intent without rigid string matching.
    """
    
    def __init__(self, llm_interface):
        self.llm_interface = llm_interface
        self.classification_cache = {}  # Simple cache for recent classifications
        
    def get_intent_classification_prompt(self, context: Dict[str, Any]) -> str:
        """Generate a prompt for intent classification based on context"""
        
        base_prompt = """You are an intelligent intent classifier for Aughie, a development assistant bot.

Analyze the user's message and classify their intent. Consider the current context and conversation state.

**Available Intent Categories:**

**Onboarding Context:**
- ONBOARDING_ACCEPT: User wants to start/continue onboarding
- ONBOARDING_DECLINE: User doesn't want onboarding (permanent decline)  
- ONBOARDING_POSTPONE: User wants to skip onboarding for now (temporary)
- ONBOARDING_QUESTION: User has questions about onboarding process
- ONBOARDING_ANSWER: User is providing an answer to an onboarding question

**Command Context:**
- COMMAND_HELP: User wants help/assistance information
- COMMAND_PERMISSIONS: User wants to see their permissions/role
- COMMAND_PREFERENCES: User wants to view/edit their preferences
- COMMAND_RESET_CHAT: User wants to reset the conversation
- COMMAND_ADMIN: User wants to perform administrative actions

**Workflow Context:**
- WORKFLOW_CONTINUE: User wants to continue current workflow
- WORKFLOW_CANCEL: User wants to cancel current workflow
- WORKFLOW_PAUSE: User wants to pause current workflow

**General Context:**
- GENERAL_QUESTION: User has a general question
- GENERAL_TASK: User wants to accomplish a specific task
- GREETING: User is greeting the bot
- THANKS: User is expressing gratitude
- UNCLEAR: Intent is unclear and needs clarification

**Context Information:**"""

        # Add current context
        if context.get("pending_onboarding_decision"):
            base_prompt += "\n- User has a pending onboarding decision"
        
        if context.get("active_onboarding_workflow"):
            base_prompt += "\n- User is currently in onboarding workflow"
            
        if context.get("active_workflows"):
            workflows = context["active_workflows"]
            base_prompt += f"\n- User has {len(workflows)} active workflow(s): {', '.join(workflows)}"
            
        if context.get("user_role"):
            base_prompt += f"\n- User role: {context['user_role']}"

        base_prompt += f"""

**User Message:** "{context.get('user_message', '')}"

**Instructions:**
1. Consider the context and conversation state
2. Look for natural language patterns, not exact phrases
3. Understand intent from meaning, not keywords
4. If unsure between multiple intents, choose the most likely one
5. Respond with ONLY the intent category (e.g., "ONBOARDING_ACCEPT")

**Intent Classification:**"""

        return base_prompt

    async def classify_intent(self, user_message: str, context: Dict[str, Any] = None) -> Tuple[UserIntent, float]:
        """Classify the intent of a user message using the LLM"""
        context = context or {}
        user_role = context.get("user_role", "guest")
        pending_onboarding_decision = context.get("pending_onboarding_decision", False)
        active_onboarding_workflow = context.get("active_onboarding_workflow", False)
        
        if not user_message:
            return UserIntent.UNCLEAR, 0.0
            
        # Fast pass for obvious patterns without LLM
        user_input_lower = user_message.lower().strip()
        
        # Check very specific exact commands first - prioritize precision
        if user_input_lower in ["help", "help me", "what can you do", "what can you do?", "/help"]:
            return UserIntent.COMMAND_HELP, 0.95
            
        if user_input_lower in ["reset chat", "clear history", "clear chat", "start over"]:
            return UserIntent.COMMAND_RESET_CHAT, 0.95
            
        if active_onboarding_workflow:
            # If already in onboarding workflow, categorize most messages as workflow continuations
            if user_input_lower in ["exit", "stop", "quit", "skip onboarding", "cancel", "cancel onboarding", "exit onboarding", "abort"]:
                return UserIntent.ONBOARDING_STOP, 0.9
            
            # Otherwise, treat as workflow continuation
            return UserIntent.WORKFLOW_CONTINUE, 0.8
            
        if pending_onboarding_decision:
            # If user was prompted for onboarding and is responding
            if user_input_lower in ["yes", "start", "begin", "let's go", "let's start", "start onboarding", "I want to onboard", "onboard me"]:
                return UserIntent.ONBOARDING_ACCEPT, 0.95
                
            if user_input_lower in ["no", "skip", "later", "maybe later", "not now", "nah", "nope", "skip onboarding", "no thanks", "not interested"]:
                return UserIntent.ONBOARDING_DECLINE, 0.95
                
            if user_input_lower in ["remind me later", "tomorrow", "next time", "postpone"]:
                return UserIntent.ONBOARDING_POSTPONE, 0.95
                
            # If message doesn't clearly address onboarding prompt, return unclear
            # Let the LLM analyze it more deeply below
            
        try:
            # Regular expression patterns for specific commands
            onboarding_pattern = r"(?i)^(onboard|set(up)? preferences?|config(ure)?( me)?|set(up)?( me)?)$"
            perms_pattern = r"(?i)(my role|my permissions?|what( can)? i (do|access)|access control|admin rights|what is my role|show my role)$"

            # Check patterns without LLM
            if re.match(onboarding_pattern, user_input_lower):
                return UserIntent.ONBOARDING_START, 0.9

            if re.match(perms_pattern, user_input_lower):
                return UserIntent.COMMAND_PERMISSIONS, 0.9

            # For more complex requests, use LLM
            system_prompt = """You are an intent classification system. Your job is to categorize user messages into the following intents:
- COMMAND_HELP: User is asking for help about the bot's capabilities
- COMMAND_RESET_CHAT: User wants to clear chat history or restart conversation
- COMMAND_PERMISSIONS: User is asking about their role, permissions, or admin status
- ONBOARDING_START: User wants to start the onboarding process (setting preferences, etc)
- ONBOARDING_ACCEPT: User is accepting an onboarding invitation
- ONBOARDING_DECLINE: User is declining an onboarding invitation
- ONBOARDING_POSTPONE: User wants to postpone onboarding for later
- WORKFLOW_CONTINUE: User is continuing an active workflow
- GENERAL_QUESTION: User is asking a general question
- GENERAL_TASK: User is requesting a task to be performed (like creating code)
- UNCLEAR: Intent is unclear or doesn't fit other categories

Output ONLY ONE of these intent labels followed by a confidence score from 0-1, like this:
INTENT_LABEL|0.85

Don't explain your reasoning, just output the label and score."""

            # Fix: Format messages properly for the LLM
            # Combine system prompt with user message for Gemini compatibility
            combined_user_content = f"{system_prompt}\n\nUser message: {user_message}\nPending onboarding decision: {pending_onboarding_decision}\nActive workflow: {active_onboarding_workflow}\nUser role: {user_role}"
            
            messages = [
                {"role": "user", "parts": [{"text": combined_user_content}]}
            ]

            response = await self.llm_interface.generate_content(messages=messages)
            
            if not response:
                return UserIntent.UNCLEAR, 0.3
                
            # Extract intent and confidence from response
            result_text = response.text.strip()
            
            # Parse response in format "INTENT|confidence"
            parts = result_text.split('|', 1)
            if len(parts) != 2:
                logging.warning(f"LLM returned unknown intent: {result_text}")
                return UserIntent.UNCLEAR, 0.3
                
            intent_str = parts[0].strip().upper()
            try:
                confidence = float(parts[1].strip())
                # Sanity check on confidence
                if not 0 <= confidence <= 1:
                    confidence = 0.5
            except ValueError:
                confidence = 0.5
                
            # Map string to enum
            try:
                intent = UserIntent[intent_str]
            except KeyError:
                logging.warning(f"LLM returned unknown intent: {intent_str}")
                return UserIntent.UNCLEAR, 0.3
                
            return intent, confidence
            
        except Exception as e:
            logging.error(f"Error in intent classification: {e}")
            return UserIntent.UNCLEAR, 0.1

    def get_intent_handler_suggestions(self, intent: UserIntent, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get suggested actions/responses for a classified intent.
        
        This provides the bot with intelligent next steps rather than hardcoded responses.
        """
        
        suggestions = {
            "intent": intent.value,
            "actions": [],
            "response_tone": "helpful",
            "context_updates": {}
        }
        
        if intent == UserIntent.ONBOARDING_ACCEPT:
            suggestions.update({
                "actions": ["start_onboarding_workflow", "send_first_question"],
                "response_tone": "welcoming",
                "context_updates": {"onboarding_status": "starting"}
            })
            
        elif intent == UserIntent.ONBOARDING_DECLINE:
            suggestions.update({
                "actions": ["mark_onboarding_declined", "offer_alternatives"],
                "response_tone": "understanding",
                "context_updates": {"onboarding_status": "declined"}
            })
            
        elif intent == UserIntent.ONBOARDING_POSTPONE:
            suggestions.update({
                "actions": ["mark_onboarding_postponed", "continue_conversation"],
                "response_tone": "accommodating", 
                "context_updates": {"onboarding_status": "postponed"}
            })
            
        elif intent == UserIntent.COMMAND_HELP:
            suggestions.update({
                "actions": ["show_contextual_help", "list_available_commands"],
                "response_tone": "instructive"
            })
            
        elif intent == UserIntent.GENERAL_TASK:
            suggestions.update({
                "actions": ["analyze_task", "plan_execution", "use_tools"],
                "response_tone": "professional"
            })
            
        # Add more intent handling as needed
        
        return suggestions

    async def get_intelligent_response(
        self, 
        user_message: str, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get an intelligent response using intent classification + LLM reasoning.
        
        This is the main entry point for intelligent conversation handling.
        """
        
        # Classify intent
        intent, confidence = await self.classify_intent(user_message, context)
        
        # Get handler suggestions
        suggestions = self.get_intent_handler_suggestions(intent, context)
        
        # Use LLM to generate contextual response
        response_prompt = f"""Based on the classified user intent and context, generate an appropriate response.

**User Message:** "{user_message}"
**Classified Intent:** {intent.value}
**Confidence:** {confidence}
**Context:** {json.dumps(context, indent=2)}
**Suggested Actions:** {suggestions['actions']}
**Response Tone:** {suggestions['response_tone']}

Generate a natural, helpful response that:
1. Acknowledges the user's intent
2. Takes appropriate action based on the intent
3. Maintains the suggested tone
4. Considers the current context

**Response:**"""

        # Generate response using LLM
        messages = [{"role": "user", "content": response_prompt}]
        
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
        
        return {
            "intent": intent,
            "confidence": confidence,
            "response": response_text.strip(),
            "suggestions": suggestions,
            "context_updates": suggestions.get("context_updates", {})
        }

# Convenience function for easy integration
async def classify_and_respond(
    llm_interface, 
    user_message: str, 
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convenience function to classify intent and get intelligent response.
    
    Usage:
        result = await classify_and_respond(llm, "I don't want to do this", context)
        intent = result["intent"]
        response = result["response"]
    """
    classifier = IntentClassifier(llm_interface)
    return await classifier.get_intelligent_response(user_message, context) 