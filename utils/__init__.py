"""
Utils Package - World-Class Logging System
==========================================

This package provides comprehensive logging, analytics, and debugging capabilities
for the AI chatbot system.
"""

# Core logging functionality
from .logging_config import (
    initialize_logging,
    get_logger,
    get_category_logger,
    start_turn,
    start_llm_call,
    end_llm_call,
    clear_llm_call_id,
    start_tool_call,
    end_tool_call,
    clear_tool_call_id,
    log_reasoning_step,
    log_user_interaction,
    log_cost_event,
    performance_monitor,
    aperformance_monitor,
    LogCategory,
    LogLevel,
    PerformanceMetrics,
    LLMReasoningContext,
    UserJourneyStep,
    # Backward compatibility
    setup_logging,
    start_new_turn,
    clear_turn_ids
)

# Data sanitization
from .log_sanitizer import (
    sanitize_data,
    sanitize_for_logging,
    sanitize_for_external,
    DataSanitizer,
    ContextAwareSanitizer,
    SensitivityLevel
)

# Dashboard and analytics
from .logging_dashboard import (
    get_dashboard,
    query_logs,
    analyze_error,
    explore_conversation,
    LogQueryEngine,
    AIDebuggingAssistant,
    RealTimeDashboard,
    LogExplorer
)

__all__ = [
    # Core logging
    'initialize_logging',
    'get_logger',
    'get_category_logger',
    'start_turn',
    'start_llm_call',
    'end_llm_call',
    'clear_llm_call_id',
    'start_tool_call',
    'end_tool_call',
    'clear_tool_call_id',
    'log_reasoning_step',
    'log_user_interaction',
    'log_cost_event',
    'performance_monitor',
    'aperformance_monitor',
    'LogCategory',
    'LogLevel',
    'PerformanceMetrics',
    'LLMReasoningContext',
    'UserJourneyStep',
    
    # Backward compatibility
    'setup_logging',
    'start_new_turn',
    'clear_turn_ids',
    
    # Data sanitization
    'sanitize_data',
    'sanitize_for_logging',
    'sanitize_for_external',
    'DataSanitizer',
    'ContextAwareSanitizer',
    'SensitivityLevel',
    
    # Dashboard and analytics
    'get_dashboard',
    'query_logs',
    'analyze_error',
    'explore_conversation',
    'LogQueryEngine',
    'AIDebuggingAssistant',
    'RealTimeDashboard',
    'LogExplorer'
]

# Version info
__version__ = "1.0.0"
__author__ = "AI Chatbot Team"
__description__ = "World-class logging and observability system" 