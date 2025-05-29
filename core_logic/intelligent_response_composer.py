"""
Intelligent Response Composer for enhanced user feedback and context management.
Provides smart message composition with context awareness and progress tracking.
"""

import logging
from typing import Dict, List, Any, Optional, AsyncIterable
from datetime import datetime, timedelta
import json

from state_models import AppState, Message
from config import Config

log = logging.getLogger("core_logic.intelligent_response_composer")

class IntelligentResponseComposer:
    """
    Composes intelligent responses with enhanced context awareness,
    progress tracking, and adaptive communication style.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.response_templates = self._load_response_templates()
        self.context_memory = {}  # Store context across interactions
        
    def _load_response_templates(self) -> Dict[str, str]:
        """Load response templates for different scenarios."""
        return {
            "plan_presentation": """
🎯 **Execution Plan**
I'll complete this in {total_steps} steps (estimated {duration}):

{step_list}

Starting now...
""",
            
            "step_progress": """
⏳ **Step {step_num}/{total_steps}**: {description}
{progress_bar}
""",
            
            "step_completion": """
✅ **Step {step_num}/{total_steps} Complete**: {description}
{result_summary}
""",
            
            "multi_tool_summary": """
📊 **Results Summary**
{summary_content}

{next_steps}
""",
            
            "error_with_recovery": """
⚠️ **Issue Encountered**: {error_description}

🔄 **Recovery Action**: {recovery_plan}
""",
            
            "context_continuation": """
📝 **Continuing from where we left off**
{context_summary}

{current_action}
""",
            
            "intelligent_clarification": """
🤔 I need to clarify something to give you the best results:

{clarification_request}

{suggested_options}
"""
        }
    
    async def compose_multi_step_response(
        self, 
        operation_type: str,
        steps: List[Dict[str, Any]],
        app_state: AppState
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Compose a multi-step response with intelligent progress tracking.
        
        Args:
            operation_type: Type of operation being performed
            steps: List of steps to execute
            app_state: Current application state
        """
        # Store operation context
        operation_id = f"op_{int(datetime.now().timestamp())}"
        self.context_memory[operation_id] = {
            "type": operation_type,
            "steps": steps,
            "started_at": datetime.now(),
            "user_id": app_state.current_user.user_id if app_state.current_user else "unknown"
        }
        
        # Present the plan to the user
        yield self._create_plan_presentation(steps, operation_id)
        
        # Execute steps with progress feedback
        completed_steps = 0
        total_steps = len(steps)
        
        for i, step in enumerate(steps):
            step_num = i + 1
            
            # Send step start notification
            yield self._create_step_start(step, step_num, total_steps)
            
            # Simulate step execution (in real implementation, this would integrate with actual execution)
            step_result = await self._execute_step_with_context(step, app_state, operation_id)
            
            if step_result.get("success"):
                completed_steps += 1
                yield self._create_step_completion(step, step_result, step_num, total_steps)
            else:
                yield self._create_step_error(step, step_result, step_num, total_steps)
                
                # Check if we should continue or halt
                if step_result.get("critical", False):
                    yield self._create_operation_halt(step_result, completed_steps, total_steps)
                    break
                else:
                    yield self._create_error_recovery(step_result, step_num, total_steps)
            
            # Update progress
            progress_percentage = (completed_steps / total_steps) * 100
            yield {
                'type': 'progress_update',
                'content': {
                    'percentage': progress_percentage,
                    'completed': completed_steps,
                    'total': total_steps,
                    'current_step': step.get('description', 'Processing...')
                }
            }
        
        # Provide final summary
        yield self._create_final_summary(operation_id, completed_steps, total_steps, app_state)
    
    def compose_contextual_continuation(
        self, 
        user_query: str, 
        app_state: AppState
    ) -> Dict[str, Any]:
        """
        Compose a response that acknowledges previous context and continues intelligently.
        """
        # Analyze recent conversation for context
        context_analysis = self._analyze_conversation_context(app_state)
        
        if context_analysis.get("has_unfinished_operation"):
            return {
                'type': 'context_continuation',
                'content': self.response_templates["context_continuation"].format(
                    context_summary=context_analysis["summary"],
                    current_action=f"Now addressing: {user_query}"
                )
            }
        
        # Check for related previous operations
        if context_analysis.get("related_operations"):
            return {
                'type': 'context_aware_response',
                'content': f"I notice you previously {context_analysis['related_operations'][0]}. {user_query}"
            }
        
        return {
            'type': 'fresh_response',
            'content': f"I'll help you with: {user_query}"
        }
    
    def compose_intelligent_clarification(
        self, 
        ambiguous_request: str, 
        clarification_options: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compose an intelligent clarification request when user intent is ambiguous.
        """
        options_text = "\n".join([
            f"**{i+1}.** {option['description']}"
            for i, option in enumerate(clarification_options[:5])  # Limit to 5 options
        ])
        
        return {
            'type': 'clarification_request',
            'content': self.response_templates["intelligent_clarification"].format(
                clarification_request=f"I can help with '{ambiguous_request}' in several ways:",
                suggested_options=options_text
            ),
            'options': clarification_options
        }
    
    def _create_plan_presentation(self, steps: List[Dict[str, Any]], operation_id: str) -> Dict[str, Any]:
        """Create a plan presentation for the user."""
        total_duration = sum(step.get('estimated_duration_ms', 3000) for step in steps)
        duration_text = f"{total_duration / 1000:.1f} seconds"
        
        step_list = "\n".join([
            f"**{i+1}.** {step.get('description', 'Processing step')}"
            for i, step in enumerate(steps)
        ])
        
        return {
            'type': 'plan_presentation',
            'content': self.response_templates["plan_presentation"].format(
                total_steps=len(steps),
                duration=duration_text,
                step_list=step_list
            ),
            'operation_id': operation_id
        }
    
    def _create_step_start(self, step: Dict[str, Any], step_num: int, total_steps: int) -> Dict[str, Any]:
        """Create a step start notification."""
        progress_bar = self._generate_progress_bar(step_num - 1, total_steps)
        
        return {
            'type': 'step_start',
            'content': self.response_templates["step_progress"].format(
                step_num=step_num,
                total_steps=total_steps,
                description=step.get('description', 'Processing...'),
                progress_bar=progress_bar
            )
        }
    
    def _create_step_completion(
        self, 
        step: Dict[str, Any], 
        result: Dict[str, Any], 
        step_num: int, 
        total_steps: int
    ) -> Dict[str, Any]:
        """Create a step completion notification."""
        result_summary = self._format_step_result(result)
        
        return {
            'type': 'step_completion',
            'content': self.response_templates["step_completion"].format(
                step_num=step_num,
                total_steps=total_steps,
                description=step.get('description', 'Completed'),
                result_summary=result_summary
            )
        }
    
    def _create_step_error(
        self, 
        step: Dict[str, Any], 
        result: Dict[str, Any], 
        step_num: int, 
        total_steps: int
    ) -> Dict[str, Any]:
        """Create a step error notification."""
        return {
            'type': 'step_error',
            'content': f"❌ **Step {step_num}/{total_steps} Failed**: {step.get('description', 'Unknown step')}\n"
                      f"Error: {result.get('error', 'Unknown error occurred')}"
        }
    
    def _create_error_recovery(
        self, 
        step_result: Dict[str, Any], 
        step_num: int, 
        total_steps: int
    ) -> Dict[str, Any]:
        """Create an error recovery notification."""
        recovery_plan = self._determine_recovery_plan(step_result)
        
        return {
            'type': 'error_recovery',
            'content': self.response_templates["error_with_recovery"].format(
                error_description=step_result.get('error', 'Unknown error'),
                recovery_plan=recovery_plan
            )
        }
    
    def _create_operation_halt(
        self, 
        step_result: Dict[str, Any], 
        completed_steps: int, 
        total_steps: int
    ) -> Dict[str, Any]:
        """Create an operation halt notification."""
        return {
            'type': 'operation_halt',
            'content': f"🛑 **Operation Halted**\n"
                      f"Critical error prevented completion.\n"
                      f"Completed {completed_steps}/{total_steps} steps.\n"
                      f"Error: {step_result.get('error', 'Unknown critical error')}"
        }
    
    def _create_final_summary(
        self, 
        operation_id: str, 
        completed_steps: int, 
        total_steps: int, 
        app_state: AppState
    ) -> Dict[str, Any]:
        """Create a final operation summary."""
        operation_context = self.context_memory.get(operation_id, {})
        duration = datetime.now() - operation_context.get("started_at", datetime.now())
        
        success_rate = (completed_steps / total_steps) * 100
        
        summary_content = f"**Operation Complete**: {completed_steps}/{total_steps} steps successful ({success_rate:.0f}%)\n"
        summary_content += f"**Duration**: {duration.total_seconds():.1f} seconds\n"
        
        if completed_steps == total_steps:
            summary_content += "✅ All steps completed successfully!"
            next_steps = "Is there anything else you'd like me to help you with?"
        elif completed_steps > 0:
            summary_content += f"⚠️ {total_steps - completed_steps} steps had issues, but I was able to complete the main operation."
            next_steps = "Would you like me to retry the failed steps or help with something else?"
        else:
            summary_content += "❌ Unable to complete the operation due to errors."
            next_steps = "Would you like to try a different approach or get help with the issues?"
        
        return {
            'type': 'final_summary',
            'content': self.response_templates["multi_tool_summary"].format(
                summary_content=summary_content,
                next_steps=next_steps
            ),
            'operation_id': operation_id
        }
    
    async def _execute_step_with_context(
        self, 
        step: Dict[str, Any], 
        app_state: AppState, 
        operation_id: str
    ) -> Dict[str, Any]:
        """Execute a step with context awareness (mock implementation)."""
        # This would integrate with the actual tool execution system
        # For now, simulate success/failure based on step type
        
        import asyncio
        import random
        
        # Simulate processing time
        await asyncio.sleep(random.uniform(0.5, 2.0))
        
        # Simulate different success rates based on step type
        if step.get('tool_name') == 'jira_get_issues_by_user':
            success = random.random() > 0.1  # 90% success rate
        elif step.get('tool_name') == 'web_search':
            success = random.random() > 0.05  # 95% success rate
        else:
            success = random.random() > 0.2  # 80% success rate
        
        if success:
            return {
                "success": True,
                "data": {"mock_result": f"Step {step.get('description')} completed"},
                "duration_ms": random.randint(500, 3000)
            }
        else:
            return {
                "success": False,
                "error": f"Mock error for {step.get('description')}",
                "critical": step.get('critical', False)
            }
    
    def _analyze_conversation_context(self, app_state: AppState) -> Dict[str, Any]:
        """Analyze the conversation for relevant context."""
        if not app_state.messages:
            return {"has_context": False}
        
        recent_messages = app_state.messages[-5:]  # Look at last 5 messages
        
        # Check for unfinished operations
        has_unfinished = any(
            "executing" in msg.text.lower() or "processing" in msg.text.lower()
            for msg in recent_messages
            if msg.role == "assistant"
        )
        
        # Look for operation patterns
        operation_keywords = ["jira", "github", "search", "analyze", "create"]
        related_operations = []
        
        for msg in recent_messages:
            if msg.role == "user":
                for keyword in operation_keywords:
                    if keyword in msg.text.lower():
                        related_operations.append(f"worked with {keyword}")
                        break
        
        return {
            "has_context": True,
            "has_unfinished_operation": has_unfinished,
            "related_operations": list(set(related_operations)),
            "summary": "Previous operations detected" if related_operations else "No previous operations"
        }
    
    def _generate_progress_bar(self, current: int, total: int, width: int = 20) -> str:
        """Generate a text-based progress bar."""
        if total == 0:
            return "▓" * width
        
        filled = int((current / total) * width)
        bar = "▓" * filled + "░" * (width - filled)
        percentage = (current / total) * 100
        
        return f"[{bar}] {percentage:.0f}%"
    
    def _format_step_result(self, result: Dict[str, Any]) -> str:
        """Format a step result for display."""
        if not result.get("success"):
            return f"❌ {result.get('error', 'Failed')}"
        
        data = result.get("data", {})
        if isinstance(data, dict):
            if "count" in data:
                return f"Retrieved {data['count']} items"
            elif len(data) > 0:
                return f"Retrieved {len(data)} results"
        
        duration = result.get("duration_ms", 0)
        return f"✅ Completed in {duration}ms"
    
    def _determine_recovery_plan(self, step_result: Dict[str, Any]) -> str:
        """Determine an appropriate recovery plan for a failed step."""
        error = step_result.get("error", "").lower()
        
        if "network" in error or "timeout" in error:
            return "Retrying with increased timeout"
        elif "permission" in error or "auth" in error:
            return "Checking authentication and retrying"
        elif "not found" in error:
            return "Searching with alternative parameters"
        else:
            return "Continuing with remaining steps" 