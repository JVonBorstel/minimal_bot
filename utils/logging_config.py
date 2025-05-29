"""
World-Class Logging System for AI Chatbot
==========================================

This module implements a comprehensive, intelligent logging system that provides:
- Deep insights into bot behavior and LLM reasoning
- Performance monitoring and cost optimization
- Predictive analytics and anomaly detection
- Interactive debugging with AI assistance
- User journey tracking and experience analytics
- Dynamic adaptation based on context
"""

import asyncio
import contextvars
import json
import logging
import logging.handlers
import time
import uuid
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable, Iterator
import threading
import os
import hashlib
import sys
import re

try:
    import structlog
    from structlog.processors import TimeStamper, add_log_level, JSONRenderer
    from structlog.contextvars import merge_contextvars
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    # Structlog is optional - system works fine without it


# =============================================================================
# CORE CORRELATION AND CONTEXT MANAGEMENT
# =============================================================================

# Context variables for correlation tracking
turn_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('turn_id', default=None)
session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('session_id', default=None)
user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('user_id', default=None)
llm_call_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('llm_call_id', default=None)
tool_call_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('tool_call_id', default=None)
workflow_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('workflow_id', default=None)
reasoning_step: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('reasoning_step', default=None)


class LogLevel(Enum):
    """Enhanced log levels for different insights"""
    TRACE = 5
    DEBUG = 10
    INFO = 20
    INSIGHT = 25  # For AI reasoning insights
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    AUDIT = 60  # For security and compliance


class LogCategory(Enum):
    """Categorization for intelligent filtering"""
    USER_INTERACTION = "user_interaction"
    LLM_REASONING = "llm_reasoning"
    TOOL_EXECUTION = "tool_execution"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COST_TRACKING = "cost_tracking"
    ERROR_ANALYSIS = "error_analysis"
    USER_JOURNEY = "user_journey"
    SYSTEM_HEALTH = "system_health"
    DEBUGGING = "debugging"


@dataclass
class PerformanceMetrics:
    """Comprehensive performance tracking"""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    token_count: Optional[int] = None
    estimated_cost: Optional[float] = None
    api_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class LLMReasoningContext:
    """Context for LLM reasoning transparency"""
    model_name: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt_hash: Optional[str] = None
    tools_available: List[str] = field(default_factory=list)
    reasoning_steps: List[Dict[str, Any]] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    alternative_paths: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class UserJourneyStep:
    """Track user interaction patterns"""
    step_type: str
    timestamp: datetime
    user_intent: Optional[str] = None
    satisfaction_score: Optional[float] = None
    friction_points: List[str] = field(default_factory=list)
    context_switches: int = 0
    tool_usage: List[str] = field(default_factory=list)


# =============================================================================
# INTELLIGENT LOG PROCESSORS
# =============================================================================

class CorrelationProcessor:
    """Adds correlation IDs and context to all log entries"""
    
    def __call__(self, logger, method_name, event_dict):
        # Add correlation IDs
        if turn_id.get():
            event_dict['turn_id'] = turn_id.get()
        if session_id.get():
            event_dict['session_id'] = session_id.get()
        if user_id.get():
            event_dict['user_id'] = user_id.get()
        if llm_call_id.get():
            event_dict['llm_call_id'] = llm_call_id.get()
        if tool_call_id.get():
            event_dict['tool_call_id'] = tool_call_id.get()
        if workflow_id.get():
            event_dict['workflow_id'] = workflow_id.get()
        if reasoning_step.get():
            event_dict['reasoning_step'] = reasoning_step.get()
            
        return event_dict


class SemanticEnrichmentProcessor:
    """Adds semantic meaning and context to log entries"""
    
    def __init__(self):
        self.intent_patterns = {
            'question': ['what', 'how', 'why', 'when', 'where', 'which', '?'],
            'command': ['create', 'delete', 'update', 'get', 'list', 'search'],
            'greeting': ['hello', 'hi', 'hey', 'good morning', 'good afternoon'],
            'farewell': ['bye', 'goodbye', 'see you', 'thanks', 'thank you']
        }
    
    def __call__(self, logger, method_name, event_dict):
        # Detect user intent from message content
        if 'message' in event_dict:
            message = str(event_dict['message']).lower()
            detected_intent = self._detect_intent(message)
            if detected_intent:
                event_dict['user_intent'] = detected_intent
                
        # Add semantic tags based on content
        if 'error' in str(event_dict.get('event', '')).lower():
            event_dict['semantic_tags'] = event_dict.get('semantic_tags', []) + ['error_event']
            
        return event_dict
    
    def _detect_intent(self, message: str) -> Optional[str]:
        for intent, patterns in self.intent_patterns.items():
            if any(pattern in message for pattern in patterns):
                return intent
        return None


class CostTrackingProcessor:
    """Tracks and estimates costs for LLM calls and API usage"""
    
    def __init__(self):
        # Cost per 1K tokens (approximate for Gemini)
        self.token_costs = {
            'gemini-1.5-flash': {'input': 0.00015, 'output': 0.0006},
            'gemini-1.5-pro': {'input': 0.0035, 'output': 0.0105}
        }
    
    def __call__(self, logger, method_name, event_dict):
        if 'token_usage' in event_dict and 'model_name' in event_dict:
            model = event_dict['model_name']
            tokens = event_dict['token_usage']
            
            if model in self.token_costs and isinstance(tokens, dict):
                input_cost = (tokens.get('input', 0) / 1000) * self.token_costs[model]['input']
                output_cost = (tokens.get('output', 0) / 1000) * self.token_costs[model]['output']
                total_cost = input_cost + output_cost
                
                event_dict['estimated_cost_usd'] = round(total_cost, 6)
                event_dict['cost_breakdown'] = {
                    'input_cost': round(input_cost, 6),
                    'output_cost': round(output_cost, 6)
                }
                
        return event_dict


class AnomalyDetectionProcessor:
    """Detects unusual patterns and potential issues"""
    
    def __init__(self):
        self.response_times = deque(maxlen=100)
        self.error_patterns = deque(maxlen=50)
        self.token_usage_history = deque(maxlen=100)
        
    def __call__(self, logger, method_name, event_dict):
        # Track response times for anomaly detection
        if 'duration_ms' in event_dict:
            duration = event_dict['duration_ms']
            self.response_times.append(duration)
            
            if len(self.response_times) >= 10:
                avg_time = statistics.mean(self.response_times)
                std_dev = statistics.stdev(self.response_times) if len(self.response_times) > 1 else 0
                
                # Flag unusually slow responses
                if duration > avg_time + (2 * std_dev):
                    event_dict['anomaly_detected'] = 'slow_response'
                    event_dict['anomaly_severity'] = 'medium' if duration < avg_time + (3 * std_dev) else 'high'
                    
        # Track error patterns
        if method_name in ['error', 'critical']:
            error_signature = hashlib.md5(str(event_dict.get('event', '')).encode()).hexdigest()[:8]
            self.error_patterns.append((time.time(), error_signature))
            
            # Detect error spikes
            recent_errors = [t for t, _ in self.error_patterns if time.time() - t < 300]  # Last 5 minutes
            if len(recent_errors) >= 5:
                event_dict['anomaly_detected'] = 'error_spike'
                event_dict['anomaly_severity'] = 'high'
                
        return event_dict


# =============================================================================
# PERFORMANCE MONITORING
# =============================================================================

class PerformanceTracker:
    """Comprehensive performance tracking and analysis"""
    
    def __init__(self):
        self.active_operations = {}
        self.completed_operations = deque(maxlen=1000)
        self.lock = threading.Lock()
        
    def start_operation(self, operation_id: str, operation_type: str, **context) -> str:
        """Start tracking a performance-critical operation"""
        with self.lock:
            metrics = PerformanceMetrics()
            self.active_operations[operation_id] = {
                'metrics': metrics,
                'type': operation_type,
                'context': context
            }
        return operation_id
    
    def end_operation(self, operation_id: str, **results) -> Optional[PerformanceMetrics]:
        """End tracking and calculate metrics"""
        with self.lock:
            if operation_id not in self.active_operations:
                return None
                
            operation = self.active_operations.pop(operation_id)
            metrics = operation['metrics']
            metrics.end_time = time.time()
            metrics.duration_ms = (metrics.end_time - metrics.start_time) * 1000
            
            # Add results to metrics
            for key, value in results.items():
                if hasattr(metrics, key):
                    setattr(metrics, key, value)
                    
            self.completed_operations.append({
                'operation_id': operation_id,
                'type': operation['type'],
                'context': operation['context'],
                'metrics': metrics,
                'timestamp': datetime.now()
            })
            
            return metrics
    
    def get_performance_insights(self) -> Dict[str, Any]:
        """Generate performance insights and recommendations"""
        if not self.completed_operations:
            return {}
            
        operations_by_type = defaultdict(list)
        for op in self.completed_operations:
            operations_by_type[op['type']].append(op['metrics'])
            
        insights = {}
        for op_type, metrics_list in operations_by_type.items():
            durations = [m.duration_ms for m in metrics_list if m.duration_ms]
            token_counts = [m.token_count for m in metrics_list if m.token_count]
            costs = [m.estimated_cost for m in metrics_list if m.estimated_cost]
            
            if durations:
                insights[op_type] = {
                    'avg_duration_ms': statistics.mean(durations),
                    'p95_duration_ms': sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0],
                    'total_operations': len(durations),
                    'avg_tokens': statistics.mean(token_counts) if token_counts else None,
                    'total_cost': sum(costs) if costs else None
                }
                
        return insights


# =============================================================================
# USER JOURNEY ANALYTICS
# =============================================================================

class UserJourneyTracker:
    """Track and analyze user interaction patterns"""
    
    def __init__(self):
        self.user_sessions = defaultdict(list)
        self.conversation_flows = defaultdict(list)
        self.friction_detector = FrictionDetector()
        
    def track_interaction(self, user_id: str, session_id: str, interaction_type: str, **context):
        """Track a user interaction step"""
        step = UserJourneyStep(
            step_type=interaction_type,
            timestamp=datetime.now(),
            **context
        )
        
        self.user_sessions[user_id].append(step)
        self.conversation_flows[session_id].append(step)
        
        # Detect friction points
        friction = self.friction_detector.analyze_step(step, self.user_sessions[user_id])
        if friction:
            step.friction_points.extend(friction)
            
    def get_user_insights(self, user_id: str) -> Dict[str, Any]:
        """Generate insights about a specific user"""
        steps = self.user_sessions.get(user_id, [])
        if not steps:
            return {}
            
        return {
            'total_interactions': len(steps),
            'common_intents': self._get_common_intents(steps),
            'avg_session_length': self._calculate_avg_session_length(steps),
            'friction_points': self._aggregate_friction_points(steps),
            'tool_usage_patterns': self._analyze_tool_usage(steps),
            'satisfaction_trend': self._calculate_satisfaction_trend(steps)
        }
    
    def _get_common_intents(self, steps: List[UserJourneyStep]) -> List[str]:
        intent_counts = defaultdict(int)
        for step in steps:
            if step.user_intent:
                intent_counts[step.user_intent] += 1
        return sorted(intent_counts.keys(), key=intent_counts.get, reverse=True)[:5]
    
    def _calculate_avg_session_length(self, steps: List[UserJourneyStep]) -> float:
        sessions = defaultdict(list)
        for step in steps:
            sessions[session_id.get() or 'default'].append(step.timestamp)
            
        session_lengths = []
        for session_steps in sessions.values():
            if len(session_steps) > 1:
                duration = (max(session_steps) - min(session_steps)).total_seconds()
                session_lengths.append(duration)
                
        return statistics.mean(session_lengths) if session_lengths else 0
    
    def _aggregate_friction_points(self, steps: List[UserJourneyStep]) -> Dict[str, int]:
        friction_counts = defaultdict(int)
        for step in steps:
            for friction in step.friction_points:
                friction_counts[friction] += 1
        return dict(friction_counts)
    
    def _analyze_tool_usage(self, steps: List[UserJourneyStep]) -> Dict[str, int]:
        tool_counts = defaultdict(int)
        for step in steps:
            for tool in step.tool_usage:
                tool_counts[tool] += 1
        return dict(tool_counts)
    
    def _calculate_satisfaction_trend(self, steps: List[UserJourneyStep]) -> Optional[str]:
        scores = [step.satisfaction_score for step in steps[-10:] if step.satisfaction_score]
        if len(scores) < 3:
            return None
            
        recent_avg = statistics.mean(scores[-3:])
        earlier_avg = statistics.mean(scores[:-3]) if len(scores) > 3 else scores[0]
        
        if recent_avg > earlier_avg + 0.1:
            return "improving"
        elif recent_avg < earlier_avg - 0.1:
            return "declining"
        else:
            return "stable"


class FrictionDetector:
    """Detect potential user experience friction points"""
    
    def analyze_step(self, step: UserJourneyStep, user_history: List[UserJourneyStep]) -> List[str]:
        """Analyze a step for potential friction"""
        friction_points = []
        
        # Check for repeated failed attempts
        recent_steps = user_history[-5:]
        if len([s for s in recent_steps if 'error' in s.step_type]) >= 2:
            friction_points.append("repeated_errors")
            
        # Check for context switching (switching between different tools/topics rapidly)
        if len(recent_steps) >= 3:
            tools_used = [set(s.tool_usage) for s in recent_steps if s.tool_usage]
            if len(tools_used) >= 2 and len(set.intersection(*tools_used)) == 0:
                friction_points.append("excessive_context_switching")
                
        # Check for long response times (this would be populated by performance tracking)
        # This is a placeholder for integration with performance metrics
        
        return friction_points


# =============================================================================
# INTELLIGENT LOG FORMATTERS
# =============================================================================

class SimpleHumanFormatter(logging.Formatter):
    """Ultra-clean formatter for human consumption"""
    
    def __init__(self):
        super().__init__()
        self.colors = {
            'DEBUG': '\033[36m',     # Cyan
            'INFO': '\033[32m',      # Green  
            'WARNING': '\033[33m',   # Yellow
            'ERROR': '\033[31m',     # Red
            'CRITICAL': '\033[41m',  # Red background
            'RESET': '\033[0m',
            'DIM_GREEN': '\033[2;32m', # Dim Green for common info loggers
            'DIM_CYAN': '\033[2;36m',  # Dim Cyan for debug loggers
            'DIM_DEFAULT': '\033[2m',   # Dim default color
            'HEADER_COLOR': '\033[1;36m', # Bold Cyan for section headers
            'BORDER_COLOR': '\033[0;36m'  # Regular Cyan for borders
        }
        self.common_info_loggers = [
            '__main__', 'config', 'bot_core.my_bot', 'tools.executor',
            'aiohttp.access', 'msrest.serialization', 'msrest.universal_http',
            'bot_core.redis_storage'
        ]
        # Define SECTIONS triggers and titles here
        # Section keys should match what appears in the output
        self.sections = {
            "ENV": {
                "start": "=== LOADING ENVIRONMENT VARIABLES ===", 
                "title": f"{self.colors['HEADER_COLOR']}[KEY] Environment Setup{self.colors['RESET']}", 
                "end": "=== ENVIRONMENT LOADED SUCCESSFULLY ==="
            },
            "CONFIG_VALIDATE": {
                "start": "=== CONFIG VALIDATION RESULTS ===", 
                "title": f"{self.colors['HEADER_COLOR']}[GEAR] Configuration Validation{self.colors['RESET']}", 
                "end": "=== CONFIG VALIDATED ==="
            },
            "TOOL_INIT": {
                "start": "=== TOOL INITIALIZATION ===",
                "title": f"{self.colors['HEADER_COLOR']}[WRENCH] Tool Initialization{self.colors['RESET']}",
                "end": "=== TOOLS INITIALIZED ==="
            },
            "STARTUP": {
                "start": "Bot server starting on", 
                "title": f"{self.colors['HEADER_COLOR']}[ROCKET] Bot Server Startup{self.colors['RESET']}", 
                "end": "=== BOT SERVER RUNNING ==="  # This should match what we'll add to app.py
            }
        }
    
    def format(self, record):
        level = record.levelname
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        original_message = record.getMessage()
        message_to_format = original_message
        logger_name = record.name
        output_parts = []

        terminal_width = 80  # Default width
        try:
            terminal_width = os.get_terminal_size().columns
        except OSError:
            pass  # Keep default if it fails
        terminal_width = max(60, min(terminal_width, 120))  # Clamp to reasonable range

        # Check for section triggers first
        if isinstance(original_message, str):
            for section_key, section_details in self.sections.items():
                is_start_trigger = (
                    section_details["start"] in original_message or
                    (section_details["start"].endswith("on") and original_message.startswith(section_details["start"]))
                )
                is_end_trigger = section_details["end"] in original_message

                if is_start_trigger:
                    title_str = section_details['title']
                    clean_title = re.sub(r'\x1b\[[0-9;]*m', '', title_str)  # Strip ANSI for length calc
                    padding = max(0, (terminal_width - 2 - len(clean_title)) // 2)
                    padding_str = ' ' * padding
                    remainder = (terminal_width - 2 - len(clean_title)) % 2
                    title_line = f"║{padding_str}{title_str}{padding_str}{' ' if remainder else ''}║"
                    
                    # Build section header
                    border_color = self.colors['BORDER_COLOR']
                    reset = self.colors['RESET']
                    output_parts.append(f"\n{border_color}╔{'═' * (terminal_width - 2)}╗{reset}")
                    output_parts.append(f"{border_color}{title_line}{reset}")
                    output_parts.append(f"{border_color}╠{'═' * (terminal_width - 2)}╣{reset}")
                    
                    # Format the trigger line as normal but make it less prominent
                    # Extract clean message text first
                    clean_message = original_message
                    if hasattr(record, '_record') and record._record:
                        clean_message = record._record.get('event', original_message)
                    elif hasattr(record, 'msg') and isinstance(record.msg, dict):
                        clean_message = record.msg.get('event', str(original_message))
                    
                    emoji = '🚀'
                    color = self.colors['DIM_GREEN']
                    trigger_line = f"{color}{emoji} [{timestamp}] [{logger_name}] {clean_message}{self.colors['RESET']}"
                    output_parts.append(trigger_line)
                    
                    return "\n".join(output_parts)
                
                elif is_end_trigger:
                    # Format the trigger message normally first
                    base_log_line = self._format_standard_line(record, timestamp, original_message, logger_name, level)
                    output_parts.append(base_log_line)
                    
                    # Add footer
                    end_title = f"Section {section_key} completed"
                    padding = max(0, (terminal_width - 2 - len(end_title)) // 2)
                    padding_str = ' ' * padding
                    remainder = (terminal_width - 2 - len(end_title)) % 2
                    end_title_line = f"║{padding_str}{end_title}{padding_str}{' ' if remainder else ''}║"
                    
                    border_color = self.colors['BORDER_COLOR']
                    reset = self.colors['RESET']
                    output_parts.append(f"{border_color}{end_title_line}{reset}")
                    output_parts.append(f"{border_color}╚{'═' * (terminal_width - 2)}╝{reset}\n")
                    
                    return "\n".join(output_parts)

        # Standard line formatting for non-section triggers
        standard_line = self._format_standard_line(record, timestamp, message_to_format, logger_name, level)
        return standard_line
    
    def _format_standard_line(self, record, timestamp, message, logger_name, level):
        """Format a standard log line with emoji, colors, and context"""
        
        # Handle structured data from the record
        if hasattr(record, '_record') and record._record:
            # If the record has structured data, use the 'event' field as the message
            message = record._record.get('event', message)
            logger_name = record._record.get('logger_name', logger_name)
        elif hasattr(record, 'msg') and isinstance(record.msg, dict):
            # Handle direct dict messages
            message = record.msg.get('event', str(message))
            logger_name = record.msg.get('logger_name', logger_name)
        
        # Clean up any remaining dict formatting
        if isinstance(message, dict):
            message = message.get('event', str(message))
        
        color = self.colors.get(level, '')
        reset = self.colors['RESET']
        emoji = self._get_emoji(record, level, message)
        
        # Handle level display - only show for non-INFO levels
        level_display = f" {level}" if level not in ['INFO'] else ""
        
        # Logger name coloring
        logger_color = color
        if logger_name:
            if level == 'INFO' and logger_name in self.common_info_loggers:
                logger_color = self.colors.get('DIM_GREEN', color)
            elif level == 'DEBUG':
                logger_color = self.colors.get('DIM_CYAN', color)
            logger_display = f" [{logger_color}{logger_name}{reset}]"
        else:
            logger_display = ""

        # Build the base line
        base_line = f"{color}{emoji} [{timestamp}]{level_display}{logger_display} {message}{reset}"
        
        # Add context if available
        context_str = self._get_important_context(record)
        if context_str:
            base_line += f" {color}({context_str}){reset}"
        
        return base_line
    
    def _get_emoji(self, record, level, message):
        """Get emoji based on log content"""
        message_lower = message.lower()
        
        # Level-based first
        if level == 'ERROR':
            return '❌'
        elif level == 'WARNING':
            return '⚠️'
        elif level == 'DEBUG':
            return '🔍'
            
        # Content-based with more specific matching
        if any(word in message_lower for word in ['success', 'completed', 'initialized successfully', 'loaded successfully']):
            return '✅'
        elif any(word in message_lower for word in ['starting', 'loading', 'initializing']):
            return '🚀'
        elif 'github' in message_lower:
            return '🐙'
        elif 'jira' in message_lower:
            return '📋'
        elif any(word in message_lower for word in ['tool', 'greptile', 'perplexity']):
            return '🔧'
        elif any(word in message_lower for word in ['llm', 'model', 'gemini', 'google']):
            return '🧠'
        elif 'user' in message_lower:
            return '👤'
        elif 'cost' in message_lower:
            return '💰'
        elif any(word in message_lower for word in ['config', 'environment', 'setting']):
            return '⚙️'
        elif any(word in message_lower for word in ['redis', 'storage', 'database']):
            return '💾'
        elif any(word in message_lower for word in ['server', 'port', 'running', 'endpoint']):
            return '🌐'
            
        return '📝'
    
    def _get_important_context(self, record):
        """Extract only the most important context info, more structured"""
        parts = []
        
        if hasattr(record, '_record') and record._record:
            data = record._record
            
            # Core IDs if they are set and not default/generic
            if turn_id_val := data.get('turn_id'):
                parts.append(f"turn:{turn_id_val[:8]}") # Shortened Turn ID
            if session_id_val := data.get('session_id'):
                if session_id_val not in ['unknown', 'anonymous']: # Avoid noisy defaults
                     parts.append(f"session:{session_id_val[:8]}") # Shortened Session ID

            if user_id_val := data.get('user_id'):
                if user_id_val not in [None, 'unknown', 'anonymous']:
                    parts.append(f"user:{user_id_val}")
            
            if tool_name_val := data.get('tool_name'):
                parts.append(f"tool:{tool_name_val}")

            if llm_call_id_val := data.get('llm_call_id'):
                parts.append(f"llm:{llm_call_id_val[:8]}") # Shortened LLM Call ID

            if tool_call_id_val := data.get('tool_call_id'):
                 parts.append(f"tool_id:{tool_call_id_val[:8]}") # Shortened Tool Call ID
            
            if duration_ms_val := data.get('duration_ms'):
                if duration_ms_val > 500: # Only show if somewhat significant
                    parts.append(f"⏱️{duration_ms_val:.0f}ms")
                
            if cost_usd_val := data.get('estimated_cost_usd'):
                if cost_usd_val > 0: # Only show if there's a cost
                    parts.append(f"💰${cost_usd_val:.4f}")
            
            # Display error type if it's an error log
            if record.levelno >= logging.ERROR and (error_type := data.get('error_type')):
                parts.append(f"type:{error_type}")

        return ' | '.join(parts) if parts else None


class StructlogConsoleRenderer:
    """Custom console renderer for structlog that outputs human-readable format"""
    
    def __init__(self):
        self.processor = SimpleHumanFormatter()
    
    def __call__(self, logger, method_name, event_dict):
        return self.processor(logger, method_name, event_dict)


# =============================================================================
# MAIN LOGGING CONFIGURATION
# =============================================================================

class IntelligentLoggingSystem:
    """Main logging system that orchestrates all components"""
    
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        self.config = config_dict or {}
        self.performance_tracker = PerformanceTracker()
        self.user_journey_tracker = UserJourneyTracker()
        self.log_analyzers = []
        
        if STRUCTLOG_AVAILABLE:
            self.setup_structlog()
        self.setup_handlers()
        
    def setup_structlog(self):
        """Configure structlog for clean human output"""
        # Processors that bridge structlog to Python logging
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            CorrelationProcessor(),  # Still track correlations
            CostTrackingProcessor(),  # Still calculate costs
            merge_contextvars,  # Include context variables
            # This processor formats for the underlying Python logger
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
    def setup_handlers(self):
        """Setup different handlers for different purposes"""
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Configure root logger to work with structlog
        root_logger = logging.getLogger()
        
        # Clear existing StreamHandlers from the root logger to ensure our formatter takes precedence
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                root_logger.removeHandler(handler)
        
        root_logger.setLevel(logging.DEBUG) # Ensure root is at DEBUG to allow handlers to filter
        
        # Console handler with beautiful, clean formatting
        # console_handler = logging.StreamHandler() # Defaults to sys.stderr
        console_handler = logging.StreamHandler(sys.stdout) # Use sys.stdout for app logs
        console_handler.setFormatter(SimpleHumanFormatter())
        console_handler.setLevel(logging.INFO)
        
        # File handler for structured JSON logs (detailed for analytics)
        file_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "bot_structured.jsonl",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10
        )
        file_handler.setFormatter(JSONFileFormatter())
        file_handler.setLevel(logging.DEBUG)
        
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        
        # Separate handlers for different categories
        self._setup_category_handlers(logs_dir)

    def _setup_category_handlers(self, logs_dir: Path):
        """Setup category-specific log files"""
        categories = {
            'llm_reasoning': logging.handlers.RotatingFileHandler(
                logs_dir / "llm_reasoning.jsonl", maxBytes=25*1024*1024, backupCount=5
            ),
            'user_journey': logging.handlers.RotatingFileHandler(
                logs_dir / "user_journey.jsonl", maxBytes=25*1024*1024, backupCount=5
            ),
            'performance': logging.handlers.RotatingFileHandler(
                logs_dir / "performance.jsonl", maxBytes=25*1024*1024, backupCount=5
            ),
            'cost_tracking': logging.handlers.RotatingFileHandler(
                logs_dir / "cost_tracking.jsonl", maxBytes=10*1024*1024, backupCount=3
            ),
        }
        
        for category, handler in categories.items():
            handler.setFormatter(JSONFileFormatter())
            handler.setLevel(logging.DEBUG)
            # These handlers are accessed via get_category_logger()


class JSONFileFormatter(logging.Formatter):
    """Enhanced JSON formatter for file output that preserves all structured data"""
    
    def format(self, record):
        # Basic log entry
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Extract structured data from structlog record
        if hasattr(record, '_record') and record._record:
            data = record._record
            
            # Add all structured data
            for key, value in data.items():
                if key not in ['event', 'level', 'logger', 'timestamp']:
                    log_entry[key] = value
                    
            # Use the 'event' field as the primary message if available
            if 'event' in data:
                log_entry['message'] = data['event']
        
        # Add any other custom attributes from the log record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                          'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'getMessage', '_record']:
                if not key.startswith('_'):  # Skip private attributes
                    log_entry[key] = value
                
        return json.dumps(log_entry, default=str, separators=(',', ':'))


# =============================================================================
# CONVENIENCE FUNCTIONS AND DECORATORS
# =============================================================================

# Global instance
_logging_system = None

def initialize_logging(config_dict: Optional[Dict[str, Any]] = None) -> IntelligentLoggingSystem:
    """Initialize the global logging system"""
    global _logging_system
    _logging_system = IntelligentLoggingSystem(config_dict)
    return _logging_system

def get_logger(name: str = None):
    """Get a logger instance (structlog if available, otherwise standard logging)"""
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        return logging.getLogger(name)

def get_category_logger(category: LogCategory):
    """Get a logger for a specific category"""
    logger = get_logger(f"category.{category.value}")
    if STRUCTLOG_AVAILABLE:
        return logger.bind(category=category.value)
    else:
        # For standard logging, add category as extra
        import logging
        return logging.LoggerAdapter(logger, {'category': category.value})

def start_turn(user_id_param: str, session_id_val: str = None) -> str:
    """Start a new conversation turn"""
    turn_id_val = str(uuid.uuid4())
    session_id_val = session_id_val or str(uuid.uuid4())
    
    turn_id.set(turn_id_val)
    session_id.set(session_id_val)
    user_id.set(user_id_param)
    
    logger = get_category_logger(LogCategory.USER_INTERACTION)
    logger.info("Turn started", 
               turn_id=turn_id_val,
               session_id=session_id_val,
               user_id=user_id_param)
    
    return turn_id_val

def start_llm_call(model_name: str, **context) -> str:
    """Start tracking an LLM call"""
    call_id = str(uuid.uuid4())
    llm_call_id.set(call_id)
    
    if _logging_system:
        _logging_system.performance_tracker.start_operation(
            call_id, "llm_call", model_name=model_name, **context
        )
    
    logger = get_category_logger(LogCategory.LLM_REASONING)
    logger.info("LLM call started",
               llm_call_id=call_id,
               model_name=model_name,
               **context)
    
    return call_id

def end_llm_call(call_id: str, **results):
    """End tracking an LLM call"""
    if _logging_system:
        metrics = _logging_system.performance_tracker.end_operation(call_id, **results)
        
        logger = get_category_logger(LogCategory.LLM_REASONING)
        
        # Prepare log data without conflicts
        log_data = results.copy()
        log_data['llm_call_id'] = call_id
        if metrics:
            # Only add duration if it's not already in results
            if 'duration_ms' not in log_data:
                log_data['duration_ms'] = metrics.duration_ms
        
        logger.info("LLM call completed", **log_data)
    
    llm_call_id.set(None)

def clear_llm_call_id():
    """Clear the current LLM call ID"""
    llm_call_id.set(None)

def start_tool_call(tool_name: str, **context) -> str:
    """Start tracking a tool call"""
    call_id = str(uuid.uuid4())
    tool_call_id.set(call_id)
    
    if _logging_system:
        _logging_system.performance_tracker.start_operation(
            call_id, "tool_call", tool_name=tool_name, **context
        )
    
    logger = get_category_logger(LogCategory.TOOL_EXECUTION)
    logger.info("Tool call started",
               tool_call_id=call_id,
               tool_name=tool_name,
               **context)
    
    return call_id

def end_tool_call(call_id: str, **results):
    """End tracking a tool call"""
    if _logging_system:
        metrics = _logging_system.performance_tracker.end_operation(call_id, **results)
        
        logger = get_category_logger(LogCategory.TOOL_EXECUTION)
        
        # Prepare log data without conflicts
        log_data = results.copy()
        log_data['tool_call_id'] = call_id
        if metrics:
            # Only add duration if it's not already in results
            if 'duration_ms' not in log_data:
                log_data['duration_ms'] = metrics.duration_ms
        
        logger.info("Tool call completed", **log_data)
    
    tool_call_id.set(None)

def clear_tool_call_id():
    """Clear the current tool call ID"""
    tool_call_id.set(None)

def log_reasoning_step(step_name: str, confidence: float = None, **context):
    """Log an LLM reasoning step"""
    reasoning_step.set(step_name)
    
    logger = get_category_logger(LogCategory.LLM_REASONING)
    logger.info("Reasoning step",
               reasoning_step=step_name,
               confidence_score=confidence,
               **context)

def log_user_interaction(interaction_type: str, **context):
    """Log a user interaction event"""
    if _logging_system:
        _logging_system.user_journey_tracker.track_interaction(
            user_id.get() or 'anonymous',
            session_id.get() or 'unknown',
            interaction_type,
            **context
        )
    
    logger = get_category_logger(LogCategory.USER_JOURNEY)
    logger.info("User interaction",
               interaction_type=interaction_type,
               **context)

def log_cost_event(operation_type: str, cost_usd: float, **context):
    """Log a cost-related event"""
    logger = get_category_logger(LogCategory.COST_TRACKING)
    logger.info("Cost event",
               operation_type=operation_type,
               cost_usd=cost_usd,
               **context)

def performance_monitor(operation_type: str = None):
    """Decorator for automatic performance monitoring"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            op_type = operation_type or f"{func.__module__}.{func.__name__}"
            op_id = str(uuid.uuid4())
            
            if _logging_system:
                _logging_system.performance_tracker.start_operation(op_id, op_type)
            
            try:
                result = func(*args, **kwargs)
                if _logging_system:
                    _logging_system.performance_tracker.end_operation(op_id, success=True)
                return result
            except Exception as e:
                if _logging_system:
                    _logging_system.performance_tracker.end_operation(op_id, success=False, error=str(e))
                raise
        return wrapper
    return decorator

async def aperformance_monitor(operation_type: str = None):
    """Async decorator for automatic performance monitoring"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            op_type = operation_type or f"{func.__module__}.{func.__name__}"
            op_id = str(uuid.uuid4())
            
            if _logging_system:
                _logging_system.performance_tracker.start_operation(op_id, op_type)
            
            try:
                result = await func(*args, **kwargs)
                if _logging_system:
                    _logging_system.performance_tracker.end_operation(op_id, success=True)
                return result
            except Exception as e:
                if _logging_system:
                    _logging_system.performance_tracker.end_operation(op_id, success=False, error=str(e))
                raise
        return wrapper
    return decorator


# =============================================================================
# ANALYTICS AND INSIGHTS
# =============================================================================

class LogAnalytics:
    """Generate insights and analytics from log data"""
    
    def __init__(self, logging_system: IntelligentLoggingSystem):
        self.logging_system = logging_system
        
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        insights = self.logging_system.performance_tracker.get_performance_insights()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'performance_insights': insights,
            'recommendations': self._generate_performance_recommendations(insights),
            'cost_analysis': self._analyze_costs(),
            'anomalies_detected': self._detect_performance_anomalies(insights)
        }
    
    def generate_user_experience_report(self, user_id: str = None) -> Dict[str, Any]:
        """Generate user experience insights"""
        if user_id:
            user_insights = self.logging_system.user_journey_tracker.get_user_insights(user_id)
            return {
                'user_id': user_id,
                'insights': user_insights,
                'recommendations': self._generate_ux_recommendations(user_insights)
            }
        else:
            # Aggregate insights across all users
            return self._generate_aggregate_ux_report()
    
    def _generate_performance_recommendations(self, insights: Dict[str, Any]) -> List[str]:
        """Generate performance optimization recommendations"""
        recommendations = []
        
        for op_type, metrics in insights.items():
            avg_duration = metrics.get('avg_duration_ms', 0)
            p95_duration = metrics.get('p95_duration_ms', 0)
            
            if avg_duration > 5000:  # 5 seconds
                recommendations.append(
                    f"Consider optimizing {op_type} operations - average duration is {avg_duration:.0f}ms"
                )
            
            if p95_duration > avg_duration * 3:
                recommendations.append(
                    f"High variability detected in {op_type} - investigate outlier cases"
                )
                
        return recommendations
    
    def _analyze_costs(self) -> Dict[str, Any]:
        """Analyze cost patterns and trends"""
        # This would integrate with the cost tracking data
        # Placeholder implementation
        return {
            'daily_cost_trend': [],
            'cost_by_operation': {},
            'optimization_opportunities': []
        }
    
    def _detect_performance_anomalies(self, insights: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect performance anomalies"""
        anomalies = []
        
        for op_type, metrics in insights.items():
            avg_duration = metrics.get('avg_duration_ms', 0)
            p95_duration = metrics.get('p95_duration_ms', 0)
            
            if p95_duration > avg_duration * 5:
                anomalies.append({
                    'type': 'high_variance',
                    'operation': op_type,
                    'severity': 'medium',
                    'description': f"High variance in {op_type} response times"
                })
                
        return anomalies
    
    def _generate_ux_recommendations(self, user_insights: Dict[str, Any]) -> List[str]:
        """Generate UX improvement recommendations"""
        recommendations = []
        
        friction_points = user_insights.get('friction_points', {})
        satisfaction_trend = user_insights.get('satisfaction_trend')
        
        if 'repeated_errors' in friction_points:
            recommendations.append("Improve error handling and user guidance")
            
        if 'excessive_context_switching' in friction_points:
            recommendations.append("Consider improving tool integration and workflow continuity")
            
        if satisfaction_trend == 'declining':
            recommendations.append("User satisfaction is declining - investigate recent interactions")
            
        return recommendations
    
    def _generate_aggregate_ux_report(self) -> Dict[str, Any]:
        """Generate aggregate UX report across all users"""
        # Placeholder implementation
        return {
            'total_users': 0,
            'common_friction_points': {},
            'satisfaction_distribution': {},
            'recommendations': []
        }


# =============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# =============================================================================

def setup_logging(config_dict: Optional[Dict[str, Any]] = None, level_str: str = None) -> IntelligentLoggingSystem:
    """Backward compatibility: alias for initialize_logging"""
    if config_dict is None:
        config_dict = {}
    
    # Handle level_str parameter for backward compatibility
    if level_str is not None:
        config_dict['log_level'] = level_str.upper()
    
    return initialize_logging(config_dict)

def start_new_turn(user_id_param: str, session_id_val: str = None) -> str:
    """Backward compatibility: alias for start_turn"""
    return start_turn(user_id_param, session_id_val)

def clear_turn_ids():
    """Backward compatibility: clear all turn-related context"""
    turn_id.set(None)
    session_id.set(None)
    user_id.set(None)
    llm_call_id.set(None)
    tool_call_id.set(None)
    reasoning_step.set(None)

# =============================================================================
# ANALYTICS AND INSIGHTS
# =============================================================================

# Initialize logging on module import
def init():
    """Initialize the logging system if not already done"""
    global _logging_system
    if _logging_system is None:
        _logging_system = initialize_logging()

# Auto-initialize
init()