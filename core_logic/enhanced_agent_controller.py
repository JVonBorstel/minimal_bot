"""
Enhanced Agent Controller for improved agentic behavior and user feedback.
Provides intelligent multi-step processing with detailed progress updates.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, AsyncIterable
from dataclasses import dataclass
from datetime import datetime
import time

from config import Config
from state_models import AppState
from tools.tool_executor import ToolExecutor
from core_logic.workflow_orchestrator import WorkflowOrchestrator

log = logging.getLogger("core_logic.enhanced_agent_controller")

@dataclass
class AgentStep:
    """Represents a single step in an agent's execution plan."""
    step_id: str
    description: str
    tool_name: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    depends_on: List[str] = None
    estimated_duration_ms: int = 5000
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

@dataclass
class AgentPlan:
    """Represents a complete execution plan for a user request."""
    plan_id: str
    user_query: str
    total_steps: int
    steps: List[AgentStep]
    estimated_total_duration_ms: int
    created_at: datetime
    status: str = "created"  # created, executing, completed, failed, cancelled

class EnhancedAgentController:
    """
    Provides enhanced agentic behavior with intelligent planning, 
    detailed progress feedback, and robust error handling.
    """
    
    def __init__(self, tool_executor: ToolExecutor, config: Config):
        self.tool_executor = tool_executor
        self.config = config
        self.workflow_orchestrator = WorkflowOrchestrator(tool_executor, config)
        
    async def process_request_with_feedback(
        self, 
        user_query: str, 
        app_state: AppState
    ) -> AsyncIterable[Dict[str, Any]]:
        """
        Process a user request with detailed progress feedback and intelligent planning.
        
        Args:
            user_query: The user's request
            app_state: Current application state
            
        Yields:
            Dict with progress updates, results, and status information
        """
        # Step 1: Analyze intent and create execution plan
        yield {'type': 'planning', 'content': 'Analyzing your request and creating execution plan...'}
        
        plan = await self._create_execution_plan(user_query, app_state)
        
        # Step 2: Present plan to user
        yield {
            'type': 'plan_created', 
            'content': {
                'plan_id': plan.plan_id,
                'total_steps': plan.total_steps,
                'estimated_duration': f"{plan.estimated_total_duration_ms / 1000:.1f}s",
                'steps': [
                    {
                        'step_number': i + 1,
                        'description': step.description,
                        'estimated_duration': f"{step.estimated_duration_ms / 1000:.1f}s"
                    }
                    for i, step in enumerate(plan.steps)
                ]
            }
        }
        
        # Step 3: Execute plan with detailed feedback
        plan.status = "executing"
        start_time = time.time()
        
        try:
            completed_steps = 0
            
            for i, step in enumerate(plan.steps):
                # Check dependencies
                if not await self._check_step_dependencies(step, plan):
                    step.status = "failed"
                    step.error = "Dependencies not met"
                    yield self._create_step_error_event(step, i + 1, plan.total_steps)
                    continue
                
                # Start step execution
                step.status = "running"
                step.started_at = datetime.utcnow()
                
                yield self._create_step_start_event(step, i + 1, plan.total_steps)
                
                # Execute step
                try:
                    if step.tool_name:
                        # Execute tool with progress tracking
                        async for progress_event in self._execute_tool_with_progress(step, app_state):
                            yield progress_event
                        
                        step.status = "completed"
                        step.completed_at = datetime.utcnow()
                        completed_steps += 1
                        
                        yield self._create_step_completion_event(step, i + 1, plan.total_steps)
                    else:
                        # Handle non-tool steps (analysis, synthesis, etc.)
                        await self._execute_analysis_step(step, plan, app_state)
                        step.status = "completed"
                        completed_steps += 1
                
                except Exception as e:
                    step.status = "failed"
                    step.error = str(e)
                    step.completed_at = datetime.utcnow()
                    
                    log.error(f"Step {step.step_id} failed: {e}", exc_info=True)
                    yield self._create_step_error_event(step, i + 1, plan.total_steps)
                    
                    # Attempt recovery or continue based on step criticality
                    if await self._should_continue_after_error(step, plan):
                        yield {
                            'type': 'recovery', 
                            'content': f'Step failed but continuing with remaining steps. Error: {str(e)}'
                        }
                        continue
                    else:
                        break
                
                # Update overall progress
                progress_percentage = (completed_steps / plan.total_steps) * 100
                yield {
                    'type': 'overall_progress',
                    'content': {
                        'percentage': progress_percentage,
                        'completed_steps': completed_steps,
                        'total_steps': plan.total_steps,
                        'elapsed_time_ms': int((time.time() - start_time) * 1000)
                    }
                }
            
            # Step 4: Synthesize final results
            yield {'type': 'synthesis', 'content': 'Analyzing results and preparing final response...'}
            
            final_result = await self._synthesize_plan_results(plan, app_state)
            
            plan.status = "completed"
            total_duration = int((time.time() - start_time) * 1000)
            
            yield {
                'type': 'completed',
                'content': {
                    'plan_id': plan.plan_id,
                    'success': completed_steps > 0,
                    'completed_steps': completed_steps,
                    'total_steps': plan.total_steps,
                    'total_duration_ms': total_duration,
                    'final_result': final_result
                }
            }
            
        except Exception as e:
            plan.status = "failed"
            log.error(f"Plan execution failed: {e}", exc_info=True)
            yield {
                'type': 'plan_failed',
                'content': {
                    'plan_id': plan.plan_id,
                    'error': str(e),
                    'completed_steps': completed_steps,
                    'total_steps': plan.total_steps
                }
            }
    
    async def _create_execution_plan(self, user_query: str, app_state: AppState) -> AgentPlan:
        """Create an intelligent execution plan based on user intent."""
        plan_id = f"plan_{int(time.time())}"
        
        # Analyze user intent and determine required steps
        intent_analysis = await self._analyze_user_intent(user_query)
        
        steps = []
        if intent_analysis['type'] == 'jira_query':
            steps = [
                AgentStep(
                    step_id="authenticate_jira",
                    description="Authenticating with Jira API",
                    estimated_duration_ms=2000
                ),
                AgentStep(
                    step_id="fetch_tickets",
                    description="Retrieving your Jira tickets",
                    tool_name="jira_get_issues_by_user",
                    parameters={"user_email": app_state.current_user.email if app_state.current_user else None},
                    depends_on=["authenticate_jira"],
                    estimated_duration_ms=5000
                ),
                AgentStep(
                    step_id="analyze_tickets",
                    description="Analyzing ticket status and priorities",
                    depends_on=["fetch_tickets"],
                    estimated_duration_ms=3000
                )
            ]
        elif intent_analysis['type'] == 'web_search':
            steps = [
                AgentStep(
                    step_id="web_search",
                    description=f"Searching the web for: {intent_analysis['query']}",
                    tool_name="perplexity_web_search",
                    parameters={"query": intent_analysis['query']},
                    estimated_duration_ms=4000
                ),
                AgentStep(
                    step_id="summarize_results",
                    description="Summarizing and organizing search results",
                    depends_on=["web_search"],
                    estimated_duration_ms=2000
                )
            ]
        else:
            # Default single-step plan
            steps = [
                AgentStep(
                    step_id="process_query",
                    description="Processing your request",
                    estimated_duration_ms=3000
                )
            ]
        
        total_duration = sum(step.estimated_duration_ms for step in steps)
        
        return AgentPlan(
            plan_id=plan_id,
            user_query=user_query,
            total_steps=len(steps),
            steps=steps,
            estimated_total_duration_ms=total_duration,
            created_at=datetime.utcnow()
        )
    
    async def _analyze_user_intent(self, user_query: str) -> Dict[str, Any]:
        """Analyze user intent to determine the best execution strategy."""
        query_lower = user_query.lower()
        
        # Jira-related queries
        jira_keywords = ['jira', 'ticket', 'issue', 'sprint', 'story', 'bug']
        if any(keyword in query_lower for keyword in jira_keywords):
            return {'type': 'jira_query', 'keywords': jira_keywords}
        
        # Web search queries
        web_keywords = ['weather', 'news', 'search', 'find', 'what is', 'how to']
        if any(keyword in query_lower for keyword in web_keywords):
            return {'type': 'web_search', 'query': user_query}
        
        # GitHub-related queries
        github_keywords = ['github', 'repository', 'repo', 'commit', 'pull request', 'pr']
        if any(keyword in query_lower for keyword in github_keywords):
            return {'type': 'github_query', 'keywords': github_keywords}
        
        return {'type': 'general', 'query': user_query}
    
    async def _check_step_dependencies(self, step: AgentStep, plan: AgentPlan) -> bool:
        """Check if all dependencies for a step are satisfied."""
        if not step.depends_on:
            return True
        
        for dep_id in step.depends_on:
            dep_step = next((s for s in plan.steps if s.step_id == dep_id), None)
            if not dep_step or dep_step.status != "completed":
                return False
        
        return True
    
    async def _execute_tool_with_progress(
        self, 
        step: AgentStep, 
        app_state: AppState
    ) -> AsyncIterable[Dict[str, Any]]:
        """Execute a tool with detailed progress tracking."""
        yield {
            'type': 'tool_start',
            'content': {
                'tool_name': step.tool_name,
                'step_description': step.description
            }
        }
        
        try:
            # Execute the tool
            result = await self.tool_executor.execute_tool(
                step.tool_name,
                step.parameters or {},
                app_state=app_state
            )
            
            step.result = result
            
            yield {
                'type': 'tool_completed',
                'content': {
                    'tool_name': step.tool_name,
                    'success': True,
                    'result_summary': self._summarize_tool_result(result)
                }
            }
            
        except Exception as e:
            step.error = str(e)
            yield {
                'type': 'tool_error',
                'content': {
                    'tool_name': step.tool_name,
                    'error': str(e)
                }
            }
            raise
    
    async def _execute_analysis_step(
        self, 
        step: AgentStep, 
        plan: AgentPlan, 
        app_state: AppState
    ) -> None:
        """Execute a non-tool step like analysis or synthesis."""
        # Simulate processing time for analysis steps
        await asyncio.sleep(step.estimated_duration_ms / 1000.0)
        
        # Add analysis logic here based on step type
        if step.step_id == "analyze_tickets":
            # Analyze Jira ticket results from previous step
            fetch_step = next((s for s in plan.steps if s.step_id == "fetch_tickets"), None)
            if fetch_step and fetch_step.result:
                step.result = self._analyze_jira_tickets(fetch_step.result)
        
        step.result = {"analysis": "completed", "step_id": step.step_id}
    
    def _analyze_jira_tickets(self, jira_result: Any) -> Dict[str, Any]:
        """Analyze Jira ticket data and extract insights."""
        # Implementation would analyze the actual Jira data
        return {
            "total_tickets": 0,
            "by_status": {},
            "by_priority": {},
            "insights": []
        }
    
    async def _should_continue_after_error(self, failed_step: AgentStep, plan: AgentPlan) -> bool:
        """Determine if execution should continue after a step failure."""
        # For now, continue unless it's a critical authentication step
        return failed_step.step_id not in ["authenticate_jira", "authenticate_github"]
    
    async def _synthesize_plan_results(self, plan: AgentPlan, app_state: AppState) -> str:
        """Synthesize the results from all completed steps into a final response."""
        completed_steps = [s for s in plan.steps if s.status == "completed"]
        
        if not completed_steps:
            return "I wasn't able to complete any steps successfully. Please try your request again."
        
        # Build a comprehensive response based on completed steps
        synthesis_parts = []
        
        for step in completed_steps:
            if step.result:
                step_summary = self._summarize_step_result(step)
                if step_summary:
                    synthesis_parts.append(step_summary)
        
        if synthesis_parts:
            return "\n\n".join(synthesis_parts)
        else:
            return f"I completed {len(completed_steps)} steps successfully."
    
    def _summarize_tool_result(self, result: Any) -> str:
        """Create a brief summary of a tool result for progress updates."""
        if isinstance(result, dict):
            if 'data' in result and isinstance(result['data'], list):
                return f"Retrieved {len(result['data'])} items"
            elif 'status' in result:
                return f"Status: {result['status']}"
        
        return "Completed successfully"
    
    def _summarize_step_result(self, step: AgentStep) -> Optional[str]:
        """Create a detailed summary of a step's result for the final response."""
        if not step.result:
            return None
        
        if step.tool_name == "jira_get_issues_by_user":
            if isinstance(step.result, dict) and 'data' in step.result:
                tickets = step.result['data']
                return f"Found {len(tickets)} Jira tickets assigned to you."
        
        return f"Completed: {step.description}"
    
    def _create_step_start_event(self, step: AgentStep, step_num: int, total_steps: int) -> Dict[str, Any]:
        """Create a step start event for the UI."""
        return {
            'type': 'step_start',
            'content': {
                'step_number': step_num,
                'total_steps': total_steps,
                'description': step.description,
                'estimated_duration_ms': step.estimated_duration_ms
            }
        }
    
    def _create_step_completion_event(self, step: AgentStep, step_num: int, total_steps: int) -> Dict[str, Any]:
        """Create a step completion event for the UI."""
        duration_ms = 0
        if step.started_at and step.completed_at:
            duration_ms = int((step.completed_at - step.started_at).total_seconds() * 1000)
        
        return {
            'type': 'step_completed',
            'content': {
                'step_number': step_num,
                'total_steps': total_steps,
                'description': step.description,
                'duration_ms': duration_ms,
                'result_summary': self._summarize_tool_result(step.result) if step.result else None
            }
        }
    
    def _create_step_error_event(self, step: AgentStep, step_num: int, total_steps: int) -> Dict[str, Any]:
        """Create a step error event for the UI."""
        return {
            'type': 'step_error',
            'content': {
                'step_number': step_num,
                'total_steps': total_steps,
                'description': step.description,
                'error': step.error or "Unknown error occurred"
            }
        } 