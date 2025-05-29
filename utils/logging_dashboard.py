"""
Intelligent Logging Dashboard and Analytics
==========================================

This module provides real-time logging insights, AI-powered debugging assistance,
and interactive log exploration capabilities for the chatbot system.
"""

import json
import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict, deque
import statistics
import re

from .logging_config import LogCategory, _logging_system, get_logger
from .log_sanitizer import sanitize_for_logging


class LogQueryEngine:
    """Semantic and structured log querying capabilities"""
    
    def __init__(self, logs_directory: str = "logs"):
        self.logs_dir = Path(logs_directory)
        self.logger = get_logger("log_query_engine")
        
    def natural_language_query(self, query: str, time_range: Optional[Tuple[datetime, datetime]] = None) -> List[Dict[str, Any]]:
        """
        Process natural language queries against log data
        
        Examples:
        - "Show me all errors in the last hour"
        - "Find LLM calls that took longer than 5 seconds"
        - "What tools did user john.doe use yesterday?"
        """
        # Parse natural language query into structured filters
        filters = self._parse_nl_query(query)
        
        # Apply time range if specified
        if time_range:
            filters['time_range'] = time_range
        elif 'time_range' not in filters:
            # Default to last 24 hours
            filters['time_range'] = (datetime.now() - timedelta(days=1), datetime.now())
            
        return self._execute_structured_query(filters)
    
    def _parse_nl_query(self, query: str) -> Dict[str, Any]:
        """Parse natural language query into structured filters"""
        filters = {}
        query_lower = query.lower()
        
        # Time patterns
        time_patterns = {
            r'last (\d+) hour': lambda m: timedelta(hours=int(m.group(1))),
            r'last (\d+) day': lambda m: timedelta(days=int(m.group(1))),
            r'yesterday': lambda m: timedelta(days=1),
            r'today': lambda m: timedelta(hours=24),
            r'last week': lambda m: timedelta(weeks=1)
        }
        
        for pattern, delta_func in time_patterns.items():
            match = re.search(pattern, query_lower)
            if match:
                delta = delta_func(match)
                filters['time_range'] = (datetime.now() - delta, datetime.now())
                break
        
        # Level patterns
        if 'error' in query_lower:
            filters['min_level'] = 'ERROR'
        elif 'warning' in query_lower:
            filters['min_level'] = 'WARNING'
        elif 'debug' in query_lower:
            filters['min_level'] = 'DEBUG'
            
        # Performance patterns
        duration_match = re.search(r'(?:longer than|took more than|slower than) (\d+) (?:second|sec)', query_lower)
        if duration_match:
            filters['min_duration_ms'] = int(duration_match.group(1)) * 1000
            
        # User patterns
        user_match = re.search(r'user (\w+(?:\.\w+)*)', query_lower)
        if user_match:
            filters['user_id'] = user_match.group(1)
            
        # Tool patterns
        tool_match = re.search(r'tool (\w+)', query_lower)
        if tool_match:
            filters['tool_name'] = tool_match.group(1)
            
        return filters
    
    def _execute_structured_query(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute structured query against log files"""
        results = []
        
        # Determine which log files to search
        log_files = self._get_relevant_log_files(filters)
        
        for log_file in log_files:
            try:
                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            log_entry = json.loads(line.strip())
                            if self._matches_filters(log_entry, filters):
                                results.append(log_entry)
                        except json.JSONDecodeError:
                            continue
            except FileNotFoundError:
                continue
                
        # Sort by timestamp
        results.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return results[:1000]  # Limit results
    
    def _get_relevant_log_files(self, filters: Dict[str, Any]) -> List[Path]:
        """Determine which log files to search based on filters"""
        files = []
        
        # Always include main structured log
        main_log = self.logs_dir / "bot_structured.jsonl"
        if main_log.exists():
            files.append(main_log)
            
        # Include category-specific logs if relevant
        category_files = {
            'llm_reasoning.jsonl': ['tool_name', 'min_duration_ms'],
            'user_journey.jsonl': ['user_id'],
            'performance.jsonl': ['min_duration_ms'],
            'cost_tracking.jsonl': ['tool_name']
        }
        
        for filename, relevant_filters in category_files.items():
            if any(f in filters for f in relevant_filters):
                file_path = self.logs_dir / filename
                if file_path.exists():
                    files.append(file_path)
                    
        return files
    
    def _matches_filters(self, log_entry: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if log entry matches all filters"""
        # Time range filter
        if 'time_range' in filters:
            start_time, end_time = filters['time_range']
            entry_time = datetime.fromisoformat(log_entry.get('timestamp', ''))
            if not (start_time <= entry_time <= end_time):
                return False
                
        # Level filter
        if 'min_level' in filters:
            level_order = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
            entry_level = level_order.get(log_entry.get('level', 'INFO'), 1)
            min_level = level_order.get(filters['min_level'], 1)
            if entry_level < min_level:
                return False
                
        # Duration filter
        if 'min_duration_ms' in filters:
            duration = log_entry.get('duration_ms', 0)
            if duration < filters['min_duration_ms']:
                return False
                
        # User filter
        if 'user_id' in filters:
            if log_entry.get('user_id') != filters['user_id']:
                return False
                
        # Tool filter
        if 'tool_name' in filters:
            if log_entry.get('tool_name') != filters['tool_name']:
                return False
                
        return True


class AIDebuggingAssistant:
    """AI-powered debugging and error analysis"""
    
    def __init__(self):
        self.logger = get_logger("ai_debugging")
        self.error_patterns = self._load_error_patterns()
        
    def _load_error_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load known error patterns and solutions"""
        return {
            'token_expired': {
                'patterns': ['expired', 'authentication failed', 'unauthorized'],
                'category': 'auth',
                'severity': 'high',
                'solution': 'Regenerate the API token or refresh authentication credentials',
                'investigation_steps': [
                    'Check token expiration date',
                    'Verify token permissions',
                    'Test token with direct API call'
                ]
            },
            'rate_limit': {
                'patterns': ['rate limit', 'too many requests', '429'],
                'category': 'api',
                'severity': 'medium',
                'solution': 'Implement exponential backoff or reduce request frequency',
                'investigation_steps': [
                    'Check current request rate',
                    'Review rate limit headers',
                    'Implement caching if applicable'
                ]
            },
            'timeout': {
                'patterns': ['timeout', 'connection timeout', 'read timeout'],
                'category': 'network',
                'severity': 'medium',
                'solution': 'Increase timeout values or check network connectivity',
                'investigation_steps': [
                    'Check network latency',
                    'Review timeout configuration',
                    'Monitor service health'
                ]
            },
            'llm_context_overflow': {
                'patterns': ['context length', 'token limit', 'maximum context'],
                'category': 'llm',
                'severity': 'high',
                'solution': 'Reduce context size or implement context management',
                'investigation_steps': [
                    'Count tokens in current context',
                    'Review conversation history length',
                    'Implement context summarization'
                ]
            }
        }
    
    def analyze_error(self, error_message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Analyze an error and provide debugging insights
        
        Args:
            error_message: The error message to analyze
            context: Additional context (logs, stack traces, etc.)
            
        Returns:
            Analysis results with suggestions and next steps
        """
        analysis = {
            'error_message': error_message,
            'timestamp': datetime.now().isoformat(),
            'matched_patterns': [],
            'severity': 'unknown',
            'category': 'unknown',
            'suggested_solutions': [],
            'investigation_steps': [],
            'related_logs': []
        }
        
        # Match against known patterns
        error_lower = error_message.lower()
        for pattern_name, pattern_info in self.error_patterns.items():
            if any(pattern in error_lower for pattern in pattern_info['patterns']):
                analysis['matched_patterns'].append(pattern_name)
                analysis['severity'] = pattern_info['severity']
                analysis['category'] = pattern_info['category']
                analysis['suggested_solutions'].append(pattern_info['solution'])
                analysis['investigation_steps'].extend(pattern_info['investigation_steps'])
                
        # Find related logs if context is provided
        if context and 'turn_id' in context:
            query_engine = LogQueryEngine()
            related_logs = query_engine.natural_language_query(
                f"turn_id:{context['turn_id']} in last hour"
            )
            analysis['related_logs'] = related_logs[:10]  # Limit to 10 entries
            
        # Generate AI insights
        analysis['ai_insights'] = self._generate_ai_insights(error_message, analysis)
        
        return analysis
    
    def _generate_ai_insights(self, error_message: str, analysis: Dict[str, Any]) -> List[str]:
        """Generate AI-powered insights about the error"""
        insights = []
        
        # Pattern-based insights
        if 'token_expired' in analysis['matched_patterns']:
            insights.append("🔑 This appears to be an authentication issue. Check if API tokens need renewal.")
            
        if 'rate_limit' in analysis['matched_patterns']:
            insights.append("⏱️ You're hitting rate limits. Consider implementing request throttling.")
            
        if 'timeout' in analysis['matched_patterns']:
            insights.append("🌐 Network timeouts detected. This could indicate connectivity issues or overloaded services.")
            
        # Context-based insights
        if analysis['related_logs']:
            error_count = len([log for log in analysis['related_logs'] if log.get('level') == 'ERROR'])
            if error_count > 1:
                insights.append(f"📊 Found {error_count} related errors in the same session. This might be a systemic issue.")
                
        # Generic insights
        if not insights:
            insights.append("🔍 This is a new error pattern. Consider adding it to the knowledge base for future analysis.")
            
        return insights
    
    def get_debugging_suggestions(self, context: Dict[str, Any]) -> List[str]:
        """Get context-specific debugging suggestions"""
        suggestions = []
        
        # Check for recent performance issues
        if context.get('avg_response_time', 0) > 5000:
            suggestions.append("🐌 Response times are slow. Check performance logs and consider optimization.")
            
        # Check for error spikes
        if context.get('error_rate', 0) > 0.1:
            suggestions.append("🚨 Error rate is elevated. Review recent changes and monitor system health.")
            
        # Check for user experience issues
        if context.get('user_satisfaction', 1.0) < 0.7:
            suggestions.append("😟 User satisfaction is low. Check user journey logs for friction points.")
            
        return suggestions


class RealTimeDashboard:
    """Real-time dashboard for monitoring bot health and performance"""
    
    def __init__(self):
        self.logger = get_logger("dashboard")
        self.metrics = defaultdict(lambda: deque(maxlen=100))
        self.alerts = deque(maxlen=50)
        
    def get_system_health(self) -> Dict[str, Any]:
        """Get current system health metrics"""
        if not _logging_system:
            return {'status': 'logging_system_not_initialized'}
            
        performance_insights = _logging_system.performance_tracker.get_performance_insights()
        
        health = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'metrics': {
                'active_operations': len(_logging_system.performance_tracker.active_operations),
                'completed_operations': len(_logging_system.performance_tracker.completed_operations),
                'avg_response_time': 0,
                'error_rate': 0,
                'cost_per_hour': 0
            },
            'alerts': list(self.alerts),
            'performance_insights': performance_insights
        }
        
        # Calculate aggregate metrics
        if performance_insights:
            all_durations = []
            total_cost = 0
            
            for op_type, metrics in performance_insights.items():
                if 'avg_duration_ms' in metrics:
                    all_durations.append(metrics['avg_duration_ms'])
                if 'total_cost' in metrics and metrics['total_cost']:
                    total_cost += metrics['total_cost']
                    
            if all_durations:
                health['metrics']['avg_response_time'] = statistics.mean(all_durations)
                
            health['metrics']['cost_per_hour'] = total_cost
            
        # Determine overall status
        if health['metrics']['avg_response_time'] > 10000:  # 10 seconds
            health['overall_status'] = 'degraded'
            
        if health['metrics']['error_rate'] > 0.1:  # 10% error rate
            health['overall_status'] = 'unhealthy'
            
        return health
    
    def generate_insights_report(self) -> Dict[str, Any]:
        """Generate comprehensive insights report"""
        if not _logging_system:
            return {'error': 'Logging system not initialized'}
            
        from .logging_config import LogAnalytics
        analytics = LogAnalytics(_logging_system)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'performance_report': analytics.generate_performance_report(),
            'user_experience_report': analytics.generate_user_experience_report(),
            'system_recommendations': self._generate_system_recommendations(),
            'cost_analysis': self._generate_cost_analysis(),
            'trending_issues': self._identify_trending_issues()
        }
    
    def _generate_system_recommendations(self) -> List[str]:
        """Generate system-wide recommendations"""
        recommendations = []
        
        if not _logging_system:
            return ['Initialize logging system for detailed recommendations']
            
        insights = _logging_system.performance_tracker.get_performance_insights()
        
        for op_type, metrics in insights.items():
            avg_duration = metrics.get('avg_duration_ms', 0)
            total_ops = metrics.get('total_operations', 0)
            
            if avg_duration > 5000 and total_ops > 10:
                recommendations.append(f"🚀 Optimize {op_type} operations (avg: {avg_duration:.0f}ms)")
                
            if total_ops > 100:
                recommendations.append(f"📈 Consider caching for {op_type} (high usage: {total_ops} ops)")
                
        return recommendations
    
    def _generate_cost_analysis(self) -> Dict[str, Any]:
        """Generate cost analysis and optimization suggestions"""
        # This would integrate with actual cost tracking data
        return {
            'daily_trend': 'stable',
            'top_cost_drivers': ['LLM calls', 'API requests'],
            'optimization_opportunities': [
                'Implement response caching',
                'Optimize prompt lengths',
                'Use cost-effective model tiers'
            ],
            'projected_monthly_cost': 0.0
        }
    
    def _identify_trending_issues(self) -> List[Dict[str, Any]]:
        """Identify trending issues and patterns"""
        # This would analyze log patterns over time
        return [
            {
                'issue': 'Increased authentication failures',
                'trend': 'increasing',
                'impact': 'medium',
                'first_seen': '2024-01-15T10:00:00Z',
                'frequency': 12
            }
        ]
    
    def add_alert(self, severity: str, message: str, context: Dict[str, Any] = None):
        """Add a system alert"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'severity': severity,
            'message': message,
            'context': context or {},
            'id': f"alert_{int(time.time())}"
        }
        
        self.alerts.appendleft(alert)
        self.logger.warning("System alert", **alert)


class LogExplorer:
    """Interactive log exploration and visualization"""
    
    def __init__(self):
        self.query_engine = LogQueryEngine()
        self.logger = get_logger("log_explorer")
        
    def explore_conversation(self, session_id: str) -> Dict[str, Any]:
        """Explore a complete conversation flow"""
        logs = self.query_engine.natural_language_query(f"session {session_id}")
        
        # Group by turn_id to reconstruct conversation flow
        turns = defaultdict(list)
        for log in logs:
            turn_id = log.get('turn_id', 'unknown')
            turns[turn_id].append(log)
            
        conversation_flow = []
        for turn_id, turn_logs in turns.items():
            # Sort logs within turn by timestamp
            turn_logs.sort(key=lambda x: x.get('timestamp', ''))
            
            # Extract key events
            events = self._extract_turn_events(turn_logs)
            
            conversation_flow.append({
                'turn_id': turn_id,
                'timestamp': turn_logs[0].get('timestamp') if turn_logs else None,
                'events': events,
                'summary': self._summarize_turn(events)
            })
            
        return {
            'session_id': session_id,
            'total_turns': len(conversation_flow),
            'conversation_flow': sorted(conversation_flow, key=lambda x: x.get('timestamp', '')),
            'insights': self._analyze_conversation_patterns(conversation_flow)
        }
    
    def _extract_turn_events(self, turn_logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract key events from a turn's logs"""
        events = []
        
        for log in turn_logs:
            category = log.get('category', 'general')
            
            if category == 'user_interaction':
                events.append({
                    'type': 'user_message',
                    'timestamp': log.get('timestamp'),
                    'content': sanitize_for_logging(log.get('message', ''))
                })
            elif category == 'llm_reasoning':
                events.append({
                    'type': 'llm_reasoning',
                    'timestamp': log.get('timestamp'),
                    'step': log.get('reasoning_step'),
                    'confidence': log.get('confidence_score')
                })
            elif category == 'tool_execution':
                events.append({
                    'type': 'tool_call',
                    'timestamp': log.get('timestamp'),
                    'tool_name': log.get('tool_name'),
                    'duration_ms': log.get('duration_ms'),
                    'success': 'error' not in log.get('level', '').lower()
                })
                
        return events
    
    def _summarize_turn(self, events: List[Dict[str, Any]]) -> str:
        """Generate a summary of what happened in a turn"""
        if not events:
            return "No events recorded"
            
        tool_calls = [e for e in events if e['type'] == 'tool_call']
        reasoning_steps = [e for e in events if e['type'] == 'llm_reasoning']
        
        summary_parts = []
        
        if reasoning_steps:
            summary_parts.append(f"{len(reasoning_steps)} reasoning steps")
            
        if tool_calls:
            successful_tools = [t for t in tool_calls if t.get('success', False)]
            if successful_tools:
                tools_used = list(set(t['tool_name'] for t in successful_tools))
                summary_parts.append(f"Used tools: {', '.join(tools_used)}")
            
            failed_tools = [t for t in tool_calls if not t.get('success', True)]
            if failed_tools:
                summary_parts.append(f"{len(failed_tools)} tool failures")
                
        return "; ".join(summary_parts) if summary_parts else "Basic interaction"
    
    def _analyze_conversation_patterns(self, conversation_flow: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze patterns in the conversation"""
        if not conversation_flow:
            return {}
            
        total_duration = 0
        tool_usage = defaultdict(int)
        error_count = 0
        
        for turn in conversation_flow:
            for event in turn.get('events', []):
                if event['type'] == 'tool_call':
                    tool_usage[event.get('tool_name', 'unknown')] += 1
                    if not event.get('success', True):
                        error_count += 1
                        
        return {
            'total_turns': len(conversation_flow),
            'most_used_tools': dict(sorted(tool_usage.items(), key=lambda x: x[1], reverse=True)[:5]),
            'error_rate': error_count / max(sum(tool_usage.values()), 1),
            'conversation_health': 'healthy' if error_count < 2 else 'problematic'
        }


# Convenience functions for dashboard access
def get_dashboard() -> RealTimeDashboard:
    """Get the real-time dashboard instance"""
    return RealTimeDashboard()

def query_logs(natural_language_query: str) -> List[Dict[str, Any]]:
    """Quick function to query logs using natural language"""
    query_engine = LogQueryEngine()
    return query_engine.natural_language_query(natural_language_query)

def analyze_error(error_message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Quick function to analyze an error"""
    assistant = AIDebuggingAssistant()
    return assistant.analyze_error(error_message, context)

def explore_conversation(session_id: str) -> Dict[str, Any]:
    """Quick function to explore a conversation"""
    explorer = LogExplorer()
    return explorer.explore_conversation(session_id) 