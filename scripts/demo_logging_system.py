#!/usr/bin/env python3
"""
World-Class Logging System Demonstration
=========================================

This script demonstrates the comprehensive logging capabilities including:
- Correlation tracking across operations
- Performance monitoring and analytics
- AI-powered debugging and error analysis
- Real-time dashboard and insights
- Natural language log querying
- User journey analytics
- Cost tracking and optimization
"""

import asyncio
import time
import random
from typing import Dict, Any
import json

# Import the new logging system
from utils import (
    initialize_logging,
    get_logger,
    get_category_logger,
    start_turn,
    start_llm_call,
    end_llm_call,
    start_tool_call,
    end_tool_call,
    log_reasoning_step,
    log_user_interaction,
    log_cost_event,
    performance_monitor,
    LogCategory,
    get_dashboard,
    query_logs,
    analyze_error,
    explore_conversation,
    sanitize_for_logging
)


class LoggingSystemDemo:
    """Comprehensive demonstration of the logging system capabilities"""
    
    def __init__(self):
        # Initialize the logging system
        self.logging_system = initialize_logging({
            'demo_mode': True,
            'verbose_logging': True
        })
        
        self.logger = get_logger("demo")
        self.dashboard = get_dashboard()
        
        print("🚀 World-Class Logging System Demo")
        print("=" * 50)
        
    def demo_basic_logging(self):
        """Demonstrate basic logging with categories and formatting"""
        print("\n📝 1. Basic Logging with Categories")
        print("-" * 30)
        
        # Different category loggers
        user_logger = get_category_logger(LogCategory.USER_INTERACTION)
        llm_logger = get_category_logger(LogCategory.LLM_REASONING)
        tool_logger = get_category_logger(LogCategory.TOOL_EXECUTION)
        perf_logger = get_category_logger(LogCategory.PERFORMANCE)
        
        user_logger.info("User sent message", message="Hello, can you help me with GitHub?")
        llm_logger.info("Processing user intent", confidence_score=0.95, intent="help_request")
        tool_logger.info("Preparing GitHub tool", tool_name="github_search")
        perf_logger.info("System metrics", response_time_ms=150, memory_usage_mb=45.2)
        
        print("✅ Basic logging demonstrated with intelligent console formatting")
        
    def demo_correlation_tracking(self):
        """Demonstrate correlation tracking across operations"""
        print("\n🔗 2. Correlation Tracking")
        print("-" * 30)
        
        # Start a user turn - this sets context for all subsequent logs
        turn_id = start_turn("demo_user_123", "session_abc")
        
        logger = get_logger("correlation_demo")
        logger.info("Turn started with correlation context")
        
        # Start an LLM call - this gets correlated to the turn
        llm_call_id = start_llm_call("gemini-1.5-flash", 
                                   temperature=0.7, 
                                   user_query="Help me search GitHub")
        
        log_reasoning_step("intent_analysis", confidence=0.92, 
                          detected_intent="github_search_request")
        
        log_reasoning_step("tool_selection", confidence=0.88,
                          selected_tools=["github_search", "github_list_repos"])
        
        # Start a tool call - this gets correlated to both turn and LLM call
        tool_call_id = start_tool_call("github_search", 
                                     query="machine learning repositories",
                                     user_id="demo_user_123")
        
        # Simulate tool execution
        time.sleep(0.1)  # Simulate work
        
        end_tool_call(tool_call_id, 
                     success=True,
                     results_count=25,
                     api_response_time_ms=342)
        
        end_llm_call(llm_call_id,
                    token_usage={'input': 150, 'output': 200},
                    total_tokens=350,
                    response_quality="high")
        
        print(f"✅ Correlation tracking demonstrated with turn_id: {turn_id[:8]}...")
        print("   All logs are now correlated and can be traced together")
        
    def demo_performance_monitoring(self):
        """Demonstrate performance monitoring and analytics"""
        print("\n⚡ 3. Performance Monitoring")
        print("-" * 30)
        
        @performance_monitor("demo_operation")
        def slow_operation():
            """Simulate a slow operation"""
            time.sleep(random.uniform(0.1, 0.3))
            return {"processed_items": random.randint(10, 100)}
        
        @performance_monitor("demo_fast_operation")
        def fast_operation():
            """Simulate a fast operation"""
            time.sleep(random.uniform(0.01, 0.05))
            return {"cached_result": True}
        
        # Run several operations to generate performance data
        print("Running monitored operations...")
        for i in range(5):
            result1 = slow_operation()
            result2 = fast_operation()
            
        # Get performance insights
        health = self.dashboard.get_system_health()
        print(f"✅ Performance monitoring active")
        print(f"   Active operations: {health['metrics']['active_operations']}")
        print(f"   Completed operations: {health['metrics']['completed_operations']}")
        print(f"   System status: {health['overall_status']}")
        
    def demo_cost_tracking(self):
        """Demonstrate cost tracking and optimization insights"""
        print("\n💰 4. Cost Tracking & Optimization")
        print("-" * 30)
        
        # Simulate various LLM calls with cost tracking
        models_and_costs = [
            ("gemini-1.5-flash", {"input": 100, "output": 150}),
            ("gemini-1.5-pro", {"input": 200, "output": 300}),
            ("gemini-1.5-flash", {"input": 80, "output": 120}),
        ]
        
        total_estimated_cost = 0
        for model, tokens in models_and_costs:
            call_id = start_llm_call(model, purpose="user_assistance")
            
            # Cost calculation happens automatically in the logging processor
            end_llm_call(call_id, 
                        token_usage=tokens,
                        model_name=model)
            
            # Manual cost logging for demonstration
            if model == "gemini-1.5-flash":
                cost = (tokens["input"] / 1000 * 0.00015) + (tokens["output"] / 1000 * 0.0006)
            else:  # gemini-1.5-pro
                cost = (tokens["input"] / 1000 * 0.0035) + (tokens["output"] / 1000 * 0.0105)
            
            total_estimated_cost += cost
            log_cost_event("llm_call", cost, model=model, tokens=sum(tokens.values()))
        
        print(f"✅ Cost tracking demonstrated")
        print(f"   Total estimated cost: ${total_estimated_cost:.6f}")
        print("   Cost optimization recommendations available in dashboard")
        
    def demo_error_analysis(self):
        """Demonstrate AI-powered error analysis"""
        print("\n🔍 5. AI-Powered Error Analysis")
        print("-" * 30)
        
        # Simulate different types of errors
        error_scenarios = [
            "Authentication failed: API token expired for GitHub service",
            "Rate limit exceeded: 429 Too Many Requests from Jira API",
            "Connection timeout: Failed to connect to external service after 30 seconds",
            "Context length exceeded: Maximum token limit of 32768 reached for model",
        ]
        
        for error_msg in error_scenarios:
            print(f"\nAnalyzing error: {error_msg[:50]}...")
            
            # Analyze the error
            analysis = analyze_error(error_msg, {
                'turn_id': 'demo_turn_123',
                'user_id': 'demo_user',
                'operation': 'tool_execution'
            })
            
            print(f"   Severity: {analysis['severity']}")
            print(f"   Category: {analysis['category']}")
            print(f"   Matched patterns: {analysis['matched_patterns']}")
            
            if analysis['suggested_solutions']:
                print(f"   Solution: {analysis['suggested_solutions'][0]}")
                
            if analysis['ai_insights']:
                print(f"   AI Insight: {analysis['ai_insights'][0]}")
        
        print("\n✅ AI-powered error analysis demonstrated")
        
    def demo_natural_language_querying(self):
        """Demonstrate natural language log querying"""
        print("\n🗣️  6. Natural Language Log Querying")
        print("-" * 30)
        
        # First, generate some log data to query
        self._generate_sample_log_data()
        
        # Example natural language queries
        queries = [
            "Show me all errors in the last hour",
            "Find LLM calls that took longer than 5 seconds",
            "What tools did user demo_user use today?",
            "Show me performance issues from yesterday",
        ]
        
        for query in queries:
            print(f"\nQuery: '{query}'")
            try:
                results = query_logs(query)
                print(f"   Found {len(results)} matching log entries")
                
                if results:
                    # Show a sample result
                    sample = results[0]
                    timestamp = sample.get('timestamp', 'N/A')[:19]  # Just date/time part
                    level = sample.get('level', 'N/A')
                    message = sample.get('message', 'N/A')[:50]
                    print(f"   Sample: [{timestamp}] {level}: {message}...")
                    
            except Exception as e:
                print(f"   Query processing: {str(e)}")
        
        print("\n✅ Natural language querying demonstrated")
        
    def demo_user_journey_analytics(self):
        """Demonstrate user journey tracking and analytics"""
        print("\n👤 7. User Journey Analytics")
        print("-" * 30)
        
        # Simulate a user journey
        session_id = "demo_session_456"
        user_id = "demo_user_456"
        
        # Start user session
        turn_1 = start_turn(user_id, session_id)
        log_user_interaction("session_start", 
                           user_agent="Demo Browser",
                           entry_point="direct_message")
        
        log_user_interaction("message_sent",
                           message="Hello, I need help with Jira tickets",
                           user_intent="help_request")
        
        # Simulate tool usage
        tool_call_1 = start_tool_call("jira_search", user_query="assigned tickets")
        end_tool_call(tool_call_1, success=True, results_count=5)
        
        log_user_interaction("tool_result_viewed",
                           tool_name="jira_search",
                           satisfaction_score=0.8)
        
        # Second turn
        turn_2 = start_turn(user_id, session_id)
        log_user_interaction("message_sent",
                           message="Can you create a new ticket?",
                           user_intent="create_request")
        
        tool_call_2 = start_tool_call("jira_create_ticket", 
                                    title="New bug report",
                                    project="DEMO")
        end_tool_call(tool_call_2, success=False, error="Permission denied")
        
        log_user_interaction("error_encountered",
                           tool_name="jira_create_ticket",
                           satisfaction_score=0.3,
                           friction_detected=True)
        
        print(f"✅ User journey tracking demonstrated")
        print(f"   Session: {session_id}")
        print(f"   User: {user_id}")
        print("   Journey includes successful and failed interactions")
        
    def demo_real_time_dashboard(self):
        """Demonstrate real-time dashboard capabilities"""
        print("\n📊 8. Real-Time Dashboard & Insights")
        print("-" * 30)
        
        # Get current system health
        health = self.dashboard.get_system_health()
        print("Current System Health:")
        print(f"   Overall Status: {health['overall_status']}")
        print(f"   Active Operations: {health['metrics']['active_operations']}")
        print(f"   Completed Operations: {health['metrics']['completed_operations']}")
        print(f"   Average Response Time: {health['metrics']['avg_response_time']:.2f}ms")
        
        # Generate comprehensive insights report
        try:
            insights_report = self.dashboard.generate_insights_report()
            print("\nSystem Insights Generated:")
            
            perf_report = insights_report.get('performance_report', {})
            if 'recommendations' in perf_report:
                print("   Performance Recommendations:")
                for rec in perf_report['recommendations'][:3]:  # Show top 3
                    print(f"     • {rec}")
            
            print("   Cost Analysis: Available")
            print("   Trending Issues: Monitored")
            
        except Exception as e:
            print(f"   Insights generation: {str(e)}")
        
        print("\n✅ Real-time dashboard demonstrated")
        
    def demo_data_sanitization(self):
        """Demonstrate intelligent data sanitization"""
        print("\n🔒 9. Data Sanitization & Privacy")
        print("-" * 30)
        
        # Sensitive data examples
        sensitive_data = {
            "user_email": "john.doe@company.com",
            "api_key": "sk-1234567890abcdef1234567890abcdef",
            "phone": "555-123-4567",
            "message": "My email is user@test.com and my phone is 555-987-6543",
            "config": {
                "database_url": "postgresql://user:pass@localhost:5432/db",
                "github_token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            }
        }
        
        print("Original sensitive data (truncated for demo):")
        print("   User email, API keys, phone numbers, etc.")
        
        # Sanitize for logging
        sanitized = sanitize_for_logging(sensitive_data)
        
        print("\nSanitized for logging:")
        print(json.dumps(sanitized, indent=2)[:300] + "...")
        
        print("\n✅ Data sanitization demonstrated")
        print("   Sensitive information protected while preserving structure")
        
    def _generate_sample_log_data(self):
        """Generate sample log data for querying demonstration"""
        # This would normally be done by actual application usage
        # For demo purposes, we'll simulate some log entries
        
        # Create some demo log entries with various scenarios
        scenarios = [
            ("github_search", True, 150),
            ("jira_search", True, 200),
            ("github_create_issue", False, 5000),  # Slow operation
            ("perplexity_query", True, 300),
        ]
        
        for tool_name, success, duration_ms in scenarios:
            call_id = start_tool_call(tool_name, demo_mode=True)
            time.sleep(0.01)  # Small delay for realistic timing
            
            if success:
                end_tool_call(call_id, success=True, duration_ms=duration_ms)
            else:
                # Log an error for this tool call
                logger = get_logger("demo_error")
                logger.error(f"Tool {tool_name} failed", 
                           tool_name=tool_name,
                           error_type="timeout" if duration_ms > 3000 else "auth_failed")
                end_tool_call(call_id, success=False, error="Operation failed")
    
    async def run_complete_demo(self):
        """Run the complete demonstration"""
        print("Starting comprehensive logging system demonstration...\n")
        
        try:
            # Run all demonstrations
            self.demo_basic_logging()
            self.demo_correlation_tracking()
            self.demo_performance_monitoring()
            self.demo_cost_tracking()
            self.demo_error_analysis()
            self.demo_natural_language_querying()
            self.demo_user_journey_analytics()
            self.demo_real_time_dashboard()
            self.demo_data_sanitization()
            
            print("\n" + "=" * 50)
            print("🎉 Demonstration Complete!")
            print("=" * 50)
            print("\nKey Features Demonstrated:")
            print("✅ Intelligent console formatting with emojis and colors")
            print("✅ Correlation tracking across operations")
            print("✅ Performance monitoring and analytics")
            print("✅ Cost tracking and optimization insights")
            print("✅ AI-powered error analysis and debugging")
            print("✅ Natural language log querying")
            print("✅ User journey analytics and friction detection")
            print("✅ Real-time dashboard and insights")
            print("✅ Privacy-preserving data sanitization")
            
            print("\nNext Steps:")
            print("1. Check the 'logs/' directory for structured log files")
            print("2. Review the JSON log files for machine-parseable data")
            print("3. Integrate the logging system into your bot components")
            print("4. Set up monitoring and alerting based on log insights")
            
            # Final system health check
            print("\nFinal System Health:")
            final_health = self.dashboard.get_system_health()
            print(f"Status: {final_health['overall_status']}")
            print(f"Operations Completed: {final_health['metrics']['completed_operations']}")
            
        except Exception as e:
            print(f"\n❌ Demo error: {str(e)}")
            import traceback
            traceback.print_exc()


async def main():
    """Main demonstration runner"""
    demo = LoggingSystemDemo()
    await demo.run_complete_demo()


if __name__ == "__main__":
    asyncio.run(main()) 