"""
Conversation Context Manager for seamless, anxiety-free bot interactions
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import hashlib

log = logging.getLogger(__name__)

class ConversationState(Enum):
    """Tracks the overall health of the conversation"""
    HEALTHY = "healthy"
    STRUGGLING = "struggling"  # Some errors but recoverable
    DEGRADED = "degraded"     # Multiple errors, need to be careful
    CRITICAL = "critical"     # Major issues, need special handling

class ErrorCategory(Enum):
    """Categories of errors for appropriate response strategies"""
    TOOL_FAILURE = "tool_failure"
    API_TIMEOUT = "api_timeout"
    UNDERSTANDING = "understanding"
    PERMISSION = "permission"
    TECHNICAL = "technical"
    NETWORK = "network"

class ConversationContextManager:
    """
    Manages conversation context to provide seamless, anxiety-free interactions
    even when errors occur. Tracks conversation flow, detects patterns, and
    ensures graceful error handling.
    """
    
    def __init__(self):
        self.conversation_history: deque = deque(maxlen=50)  # Recent interactions
        self.error_history: deque = deque(maxlen=20)        # Recent errors
        self.user_frustration_indicators: List[str] = []     # Detected frustration
        self.conversation_state = ConversationState.HEALTHY
        self.last_responses: deque = deque(maxlen=10)       # Prevent repeats
        self.recovery_strategies_used: Dict[str, int] = {}   # Track what we've tried
        self.conversation_momentum: float = 1.0              # Flow quality metric
        
        # Patterns that indicate user frustration
        self.frustration_patterns = [
            "not working", "broken", "doesn't work", "why isn't", "frustrated",
            "annoying", "stuck", "keeps failing", "again", "still not",
            "come on", "seriously", "ugh", "argh", "ffs", "wtf",
            "same error", "same problem", "not helping"
        ]
        
        # Calming phrases for different situations
        self.calming_responses = {
            ErrorCategory.TOOL_FAILURE: [
                "I'm working on an alternative approach for you.",
                "Let me try a different way to help with that.",
                "I'll find another solution for you right away."
            ],
            ErrorCategory.API_TIMEOUT: [
                "Taking a bit longer than expected - I'm still working on it.",
                "Almost there - just gathering the information.",
                "Thanks for your patience - processing your request."
            ],
            ErrorCategory.UNDERSTANDING: [
                "Let me make sure I understand what you need.",
                "I'd like to help - could you tell me more about what you're looking for?",
                "I want to get this right for you - let me clarify."
            ],
            ErrorCategory.PERMISSION: [
                "I'll help you with what I can access right now.",
                "Let me show you what's available with your current permissions.",
                "I'll work within what's available to help you."
            ],
            ErrorCategory.TECHNICAL: [
                "I'll handle this differently to get you what you need.",
                "Let me take care of that using a different approach.",
                "I've got another way to help with this."
            ],
            ErrorCategory.NETWORK: [
                "Connection seems a bit slow - I'll keep trying.",
                "Working through some network delays - thanks for bearing with me.",
                "I'll get this sorted despite the connection issues."
            ]
        }
    
    def track_user_message(self, message: str) -> Dict[str, Any]:
        """
        Analyzes user message for context and emotional state
        
        Returns context info including detected frustration level
        """
        message_lower = message.lower()
        
        # Check for frustration indicators
        frustration_score = 0
        detected_patterns = []
        
        for pattern in self.frustration_patterns:
            if pattern in message_lower:
                frustration_score += 1
                detected_patterns.append(pattern)
        
        # Check for repeated similar messages (sign of things not working)
        message_hash = hashlib.md5(message_lower.encode()).hexdigest()[:8]
        recent_hashes = [h for h, _ in self.conversation_history if h]
        if message_hash in recent_hashes[-5:]:
            frustration_score += 2  # Repetition is a strong frustration signal
            detected_patterns.append("repeated_message")
        
        # Update conversation history
        self.conversation_history.append((message_hash, {
            "type": "user",
            "content": message,
            "timestamp": datetime.now(),
            "frustration_score": frustration_score,
            "patterns": detected_patterns
        }))
        
        # Update conversation momentum
        self._update_conversation_momentum()
        
        return {
            "frustration_level": self._calculate_frustration_level(),
            "detected_patterns": detected_patterns,
            "conversation_state": self.conversation_state,
            "should_acknowledge_difficulty": frustration_score > 0,
            "momentum": self.conversation_momentum
        }
    
    def track_bot_response(self, response: str, was_error: bool = False) -> bool:
        """
        Tracks bot response to prevent repetition and maintain flow
        
        Returns True if response is OK to send, False if it's a repeat
        """
        # Check for duplicate responses
        response_hash = hashlib.md5(response.lower().encode()).hexdigest()[:8]
        
        if response_hash in self.last_responses:
            log.warning("Attempted to send duplicate response")
            return False
        
        self.last_responses.append(response_hash)
        self.conversation_history.append((None, {
            "type": "bot",
            "content": response,
            "timestamp": datetime.now(),
            "was_error": was_error
        }))
        
        return True
    
    def handle_error(self, error: Exception, category: ErrorCategory, 
                    context: Dict[str, Any]) -> str:
        """
        Generates appropriate user-facing message for an error
        
        Never exposes technical details, always maintains positive flow
        """
        # Record error
        self.error_history.append({
            "error": str(error),
            "category": category,
            "timestamp": datetime.now(),
            "context": context
        })
        
        # Update conversation state based on error frequency
        self._update_conversation_state()
        
        # Get user frustration level
        frustration_level = self._calculate_frustration_level()
        
        # Generate appropriate response
        if frustration_level > 0.7:
            # High frustration - be extra careful
            response = self._generate_high_empathy_response(category)
        elif self.conversation_state == ConversationState.DEGRADED:
            # Multiple errors - acknowledge and reassure
            response = self._generate_acknowledgment_response(category)
        else:
            # Normal error - stay positive and solution-focused
            response = self._generate_standard_error_response(category)
        
        # Ensure we don't repeat the same error message
        if not self.track_bot_response(response, was_error=True):
            # Generate alternative if it's a duplicate
            response = self._generate_alternative_response(category)
            self.track_bot_response(response, was_error=True)
        
        return response
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Provides a summary of the conversation state for logging/debugging
        """
        recent_errors = len([e for e in self.error_history 
                           if datetime.now() - e['timestamp'] < timedelta(minutes=5)])
        
        return {
            "state": self.conversation_state.value,
            "momentum": self.conversation_momentum,
            "frustration_level": self._calculate_frustration_level(),
            "recent_errors": recent_errors,
            "total_interactions": len(self.conversation_history),
            "error_rate": len(self.error_history) / max(len(self.conversation_history), 1)
        }
    
    def suggest_recovery_action(self) -> Optional[str]:
        """
        Suggests proactive recovery actions when conversation is struggling
        """
        if self.conversation_state in [ConversationState.DEGRADED, ConversationState.CRITICAL]:
            frustration = self._calculate_frustration_level()
            
            if frustration > 0.8:
                return "I notice we're having some difficulties. Would you like me to start fresh with a simpler approach?"
            elif frustration > 0.5:
                return "I can see this isn't going smoothly. Let me know if you'd prefer to try something different."
            elif len(self.error_history) > 3:
                return "I'm working through some technical issues, but I'm still here to help. What's most important to you right now?"
        
        return None
    
    def _calculate_frustration_level(self) -> float:
        """
        Calculates user frustration level from 0.0 to 1.0
        """
        if not self.conversation_history:
            return 0.0
        
        # Recent frustration scores
        recent_scores = []
        for _, entry in list(self.conversation_history)[-10:]:
            if entry["type"] == "user" and "frustration_score" in entry:
                recent_scores.append(entry["frustration_score"])
        
        if not recent_scores:
            return 0.0
        
        # Weight recent messages more heavily
        weights = [1.0 + (i * 0.1) for i in range(len(recent_scores))]
        weighted_sum = sum(s * w for s, w in zip(recent_scores, weights))
        
        # Normalize to 0-1 range
        max_possible = sum(weights) * 3  # Assuming max frustration score of 3
        return min(weighted_sum / max_possible, 1.0)
    
    def _update_conversation_state(self):
        """
        Updates conversation state based on error patterns
        """
        recent_errors = [e for e in self.error_history 
                        if datetime.now() - e['timestamp'] < timedelta(minutes=5)]
        
        error_rate = len(recent_errors) / max(len(list(self.conversation_history)[-20:]), 1)
        
        if error_rate > 0.5:
            self.conversation_state = ConversationState.CRITICAL
        elif error_rate > 0.3:
            self.conversation_state = ConversationState.DEGRADED
        elif error_rate > 0.1:
            self.conversation_state = ConversationState.STRUGGLING
        else:
            self.conversation_state = ConversationState.HEALTHY
    
    def _update_conversation_momentum(self):
        """
        Updates conversation momentum (flow quality)
        """
        if len(self.conversation_history) < 2:
            return
        
        # Check time between messages
        recent = list(self.conversation_history)[-5:]
        if len(recent) >= 2:
            time_gaps = []
            for i in range(1, len(recent)):
                prev_time = recent[i-1][1]["timestamp"]
                curr_time = recent[i][1]["timestamp"]
                gap = (curr_time - prev_time).total_seconds()
                time_gaps.append(gap)
            
            # Good momentum = quick exchanges
            avg_gap = sum(time_gaps) / len(time_gaps)
            if avg_gap < 10:
                self.conversation_momentum = min(1.0, self.conversation_momentum + 0.1)
            elif avg_gap > 30:
                self.conversation_momentum = max(0.1, self.conversation_momentum - 0.1)
    
    def _generate_high_empathy_response(self, category: ErrorCategory) -> str:
        """
        Generates response for high frustration situations
        """
        responses = [
            "I completely understand your frustration. Let me take a different approach that should work better.",
            "I apologize for the trouble. I'm switching to a more reliable method right now.",
            "I hear you, and I'm going to make this work. Give me just a moment to try something else.",
            "You're absolutely right to be frustrated. Let me fix this properly for you."
        ]
        
        import random
        base_response = random.choice(responses)
        
        # Add specific context
        if category == ErrorCategory.TOOL_FAILURE:
            base_response += " I'll use a simpler approach that should be more reliable."
        elif category == ErrorCategory.API_TIMEOUT:
            base_response += " I'll break this down into smaller steps that should work better."
        
        return base_response
    
    def _generate_acknowledgment_response(self, category: ErrorCategory) -> str:
        """
        Generates response that acknowledges ongoing issues
        """
        responses = [
            "I see we've hit a few bumps. Let me try a fresh approach.",
            "Thanks for sticking with me. I'm adjusting my approach now.",
            "I'm aware this hasn't been smooth. Here's what I'll do differently."
        ]
        
        import random
        return random.choice(responses)
    
    def _generate_standard_error_response(self, category: ErrorCategory) -> str:
        """
        Generates standard error response
        """
        import random
        if category in self.calming_responses:
            return random.choice(self.calming_responses[category])
        
        # Fallback
        return "Let me try a different approach to help you with that."
    
    def _generate_alternative_response(self, category: ErrorCategory) -> str:
        """
        Generates alternative response when first choice was a duplicate
        """
        alternatives = [
            "I'll approach this from a different angle.",
            "Let me find another way to help with that.",
            "I have another method that should work better.",
            "Here's an alternative solution for you."
        ]
        
        import random
        return random.choice(alternatives) 