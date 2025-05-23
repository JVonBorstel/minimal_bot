# core_logic/workflow_orchestrator.py

"""
Advanced multi-tool workflow orchestrator that handles complex natural language requests
requiring sequential tool calls and intelligent information synthesis.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from config import Config
from state_models import AppState
from tools.tool_executor import ToolExecutor

log = logging.getLogger("core_logic.workflow_orchestrator")

@dataclass
class WorkflowStep:
    """Represents a single step in a multi-tool workflow."""
    tool_name: str
    parameters: Dict[str, Any]
    depends_on: List[str] = None  # IDs of previous steps this depends on
    step_id: str = None
    description: str = ""

@dataclass
class WorkflowResult:
    """Contains the results of an executed workflow."""
    success: bool
    steps_executed: List[str]
    results: Dict[str, Any]  # step_id -> result
    final_synthesis: str
    execution_time_ms: int

class WorkflowOrchestrator:
    """
    Orchestrates complex multi-tool workflows based on natural language intent.
    
    Examples:
    - "Compare my GitHub repo against my Jira tickets"
    - "Find all code related to ticket PROJ-123" 
    - "Check if my PRs match my assigned tickets"
    """
    
    def __init__(self, tool_executor: ToolExecutor, config: Config):
        self.tool_executor = tool_executor
        self.config = config
        self.workflow_patterns = self._initialize_workflow_patterns()
    
    def _initialize_workflow_patterns(self) -> Dict[str, List[WorkflowStep]]:
        """Define common multi-tool workflow patterns."""
        return {
            "repo_jira_comparison": [
                WorkflowStep(
                    step_id="get_repos",
                    tool_name="github_list_repositories", 
                    parameters={},
                    description="Get user's GitHub repositories"
                ),
                WorkflowStep(
                    step_id="get_jira_tickets",
                    tool_name="jira_get_issues_by_user",
                    parameters={"user_email": "{user_email}"},  # Will be injected
                    description="Get user's Jira tickets"
                )
            ],
            
            "list_github_repos": [
                WorkflowStep(
                    step_id="get_repos",
                    tool_name="github_list_repositories", 
                    parameters={},
                    description="Get user's GitHub repositories"
                )
            ],
            
            "list_jira_tickets": [
                WorkflowStep(
                    step_id="get_jira_tickets",
                    tool_name="jira_get_issues_by_user",
                    parameters={"user_email": "{user_email}"},
                    description="Get user's Jira tickets"
                )
            ],
            
            "code_ticket_analysis": [
                WorkflowStep(
                    step_id="get_ticket_details",
                    tool_name="jira_get_issue_details",
                    parameters={"issue_key": "{ticket_id}"},
                    description="Get detailed ticket information"
                ),
                WorkflowStep(
                    step_id="search_related_code",
                    tool_name="greptile_search_code", 
                    parameters={"query": "{ticket_title} {ticket_description}"},
                    depends_on=["get_ticket_details"],
                    description="Search codebase for ticket-related code"
                ),
                WorkflowStep(
                    step_id="find_recent_commits",
                    tool_name="github_search_commits",
                    parameters={"query": "{ticket_id}"},
                    description="Find commits referencing the ticket"
                )
            ]
        }
    
    async def execute_workflow(
        self, 
        workflow_type: str, 
        app_state: AppState,
        context: Dict[str, Any] = None
    ) -> WorkflowResult:
        """
        Execute a multi-tool workflow with intelligent parameter injection and result synthesis.
        
        Args:
            workflow_type: The type of workflow to execute
            app_state: Current application state
            context: Additional context for parameter injection
            
        Returns:
            WorkflowResult containing execution results and synthesis
        """
        start_time = asyncio.get_event_loop().time()
        
        if workflow_type not in self.workflow_patterns:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        
        workflow_steps = self.workflow_patterns[workflow_type]
        results = {}
        executed_steps = []
        
        log.info(f"Starting workflow '{workflow_type}' with {len(workflow_steps)} steps")
        
        try:
            # Execute steps in dependency order
            for step in workflow_steps:
                if step.depends_on:
                    # Wait for dependencies to complete
                    missing_deps = [dep for dep in step.depends_on if dep not in results]
                    if missing_deps:
                        log.warning(f"Step {step.step_id} has unmet dependencies: {missing_deps}")
                        continue
                
                # Inject parameters from previous results and context
                injected_params = self._inject_parameters(
                    step.parameters, 
                    results, 
                    app_state, 
                    context or {}
                )
                
                log.info(f"Executing step '{step.step_id}': {step.description}")
                
                # Execute the tool
                step_result = await self.tool_executor.execute_tool(
                    step.tool_name,
                    injected_params,
                    app_state=app_state
                )
                
                results[step.step_id] = {
                    "tool_name": step.tool_name,
                    "parameters": injected_params,
                    "result": step_result,
                    "success": self._determine_success(step_result)
                }
                
                executed_steps.append(step.step_id)
                
                if not results[step.step_id]["success"]:
                    log.warning(f"Step '{step.step_id}' failed, continuing workflow")
            
            # Synthesize final result
            final_synthesis = await self._synthesize_workflow_results(
                workflow_type, 
                results, 
                app_state
            )
            
            execution_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
            
            return WorkflowResult(
                success=len(executed_steps) > 0,
                steps_executed=executed_steps,
                results=results,
                final_synthesis=final_synthesis,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            log.error(f"Workflow '{workflow_type}' failed: {e}", exc_info=True)
            execution_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
            
            return WorkflowResult(
                success=False,
                steps_executed=executed_steps,
                results=results,
                final_synthesis=f"Workflow failed: {str(e)}",
                execution_time_ms=execution_time
            )
    
    def _inject_parameters(
        self, 
        template_params: Dict[str, Any],
        previous_results: Dict[str, Any],
        app_state: AppState,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inject dynamic values into parameter templates.
        
        Supports:
        - {user_email} -> from app_state.current_user.email (with fallback to config)
        - {step_id.field} -> from previous_results[step_id][field]
        - {context_key} -> from context dict
        """
        injected = {}
        
        for key, value in template_params.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                # Extract the reference
                ref = value[1:-1]
                
                if ref == "user_email":
                    # Try user email first, then fallback to config Jira email
                    user_email = None
                    if app_state.current_user and app_state.current_user.email:
                        user_email = app_state.current_user.email
                    elif hasattr(self.config, 'get_env_value'):
                        user_email = self.config.get_env_value('JIRA_API_EMAIL')
                    
                    if user_email:
                        injected[key] = user_email
                        log.info(f"Injected user_email: {user_email}")
                    else:
                        log.warning(f"Could not resolve user_email - no user email or JIRA_API_EMAIL configured")
                        injected[key] = value  # Keep original template
                elif "." in ref:
                    # Reference to previous step result
                    step_id, field = ref.split(".", 1)
                    if step_id in previous_results:
                        step_data = previous_results[step_id]
                        if field == "results":
                            injected[key] = step_data["result"]
                        elif field in step_data:
                            injected[key] = step_data[field]
                elif ref in context:
                    injected[key] = context[ref]
                else:
                    log.warning(f"Could not resolve parameter reference: {ref}")
                    injected[key] = value  # Keep original template
            else:
                injected[key] = value
        
        return injected
    
    def _determine_success(self, result: Any) -> bool:
        """Determine if a tool execution was successful."""
        if isinstance(result, dict):
            return result.get("status", "").upper() in ["SUCCESS", "OK"]
        return result is not None
    
    async def _synthesize_workflow_results(
        self, 
        workflow_type: str, 
        results: Dict[str, Any],
        app_state: AppState
    ) -> str:
        """
        Synthesize results from multiple tools into a coherent summary.
        
        This is where the magic happens - combining data from multiple sources
        into useful insights for the user.
        """
        if workflow_type == "repo_jira_comparison":
            return self._synthesize_repo_jira_comparison(results)
        elif workflow_type == "list_github_repos":
            return self._synthesize_github_repos(results)
        elif workflow_type == "list_jira_tickets":
            return self._synthesize_jira_tickets(results)
        elif workflow_type == "code_ticket_analysis":
            return self._synthesize_code_ticket_analysis(results)
        else:
            # Generic synthesis
            return self._generic_synthesis(results)
    
    def _synthesize_repo_jira_comparison(self, results: Dict[str, Any]) -> str:
        """Synthesize GitHub repo and Jira ticket comparison."""
        repos_result = results.get("get_repos", {}).get("result", {})
        jira_result = results.get("get_jira_tickets", {}).get("result", {})
        
        if not repos_result or not jira_result:
            return "❌ Could not retrieve both repository and ticket data for comparison."
        
        # Extract meaningful data
        repos = repos_result.get("data", []) if isinstance(repos_result, dict) else repos_result
        tickets = jira_result.get("data", []) if isinstance(jira_result, dict) else jira_result
        
        synthesis = []
        synthesis.append(f"📊 **Repository vs Ticket Analysis**")
        synthesis.append(f"🗂️ Found {len(repos)} repositories and {len(tickets)} Jira tickets")
        
        # Look for correlations
        repo_names = [repo.get("name", "") for repo in repos if isinstance(repo, dict)]
        ticket_summaries = [ticket.get("summary", "") for ticket in tickets if isinstance(ticket, dict)]
        
        correlations = []
        for repo_name in repo_names:
            for ticket in tickets:
                if isinstance(ticket, dict):
                    ticket_text = f"{ticket.get('summary', '')} {ticket.get('description', '')}"
                    if repo_name.lower() in ticket_text.lower():
                        correlations.append(f"🔗 Repo '{repo_name}' mentioned in ticket {ticket.get('key', 'Unknown')}")
        
        if correlations:
            synthesis.append("\n**Found Correlations:**")
            synthesis.extend(correlations)
        else:
            synthesis.append("\n⚠️ No obvious correlations found between repo names and ticket content.")
        
        return "\n".join(synthesis)
    
    def _synthesize_code_ticket_analysis(self, results: Dict[str, Any]) -> str:
        """Synthesize code and ticket analysis."""
        ticket_result = results.get("get_ticket_details", {}).get("result", {})
        code_result = results.get("search_related_code", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🎫 **Code-Ticket Analysis**")
        
        if ticket_result:
            ticket_data = ticket_result.get("data", {}) if isinstance(ticket_result, dict) else {}
            synthesis.append(f"📋 Ticket: {ticket_data.get('key', 'Unknown')} - {ticket_data.get('summary', 'No summary')}")
        
        if code_result:
            code_data = code_result.get("data", []) if isinstance(code_result, dict) else code_result
            synthesis.append(f"💻 Found {len(code_data) if isinstance(code_data, list) else 0} related code references")
        
        return "\n".join(synthesis)
    
    def _synthesize_github_repos(self, results: Dict[str, Any]) -> str:
        """Synthesize GitHub repositories list."""
        repos_result = results.get("get_repos", {}).get("result", {})
        
        if not repos_result:
            return "❌ Could not retrieve repository data."
        
        # Extract meaningful data
        repos = repos_result.get("data", []) if isinstance(repos_result, dict) else repos_result
        
        if not repos:
            return "📁 No repositories found."
        
        synthesis = []
        synthesis.append(f"📁 **Your GitHub Repositories** ({len(repos)} found)")
        
        for i, repo in enumerate(repos, 1):
            if isinstance(repo, dict):
                name = repo.get("name", "Unknown")
                description = repo.get("description", "No description")
                updated = repo.get("updated_at", "Unknown")
                synthesis.append(f"{i}. **{name}** - {description}")
        
        return "\n".join(synthesis)
    
    def _synthesize_jira_tickets(self, results: Dict[str, Any]) -> str:
        """Synthesize Jira tickets list."""
        jira_result = results.get("get_jira_tickets", {}).get("result", {})
        
        if not jira_result:
            return "❌ Could not retrieve Jira ticket data."
        
        # Extract meaningful data  
        tickets = jira_result.get("data", []) if isinstance(jira_result, dict) else jira_result
        
        if not tickets:
            return "🎫 No Jira tickets found."
        
        synthesis = []
        synthesis.append(f"🎫 **Your Jira Tickets** ({len(tickets)} found)")
        
        for i, ticket in enumerate(tickets, 1):
            if isinstance(ticket, dict):
                key = ticket.get("key", "Unknown")
                summary = ticket.get("summary", "No summary")
                status = ticket.get("status", "Unknown")
                synthesis.append(f"{i}. **{key}** - {summary} ({status})")
        
        return "\n".join(synthesis)
    
    def _generic_synthesis(self, results: Dict[str, Any]) -> str:
        """Generic synthesis for unknown workflow types."""
        successful_steps = [
            step_id for step_id, result in results.items() 
            if result.get("success", False)
        ]
        
        synthesis = []
        synthesis.append(f"🔄 **Workflow Complete**")
        synthesis.append(f"✅ Successfully executed {len(successful_steps)} steps: {', '.join(successful_steps)}")
        
        for step_id, step_result in results.items():
            if step_result.get("success"):
                tool_name = step_result.get("tool_name", "Unknown")
                synthesis.append(f"  📌 {step_id} ({tool_name}): Success")
        
        return "\n".join(synthesis)


# Workflow pattern detection
WORKFLOW_PATTERNS = {
    "repo_jira_comparison": [
        "compare", "repos", "repositories", "github", "jira", "tickets",
        "repo against jira", "github vs jira", "github with jira",
        "match repositories to tickets", "repo ticket correlation",
        "repos with", "repositories with"
    ],
    "code_ticket_analysis": [
        "find code for ticket", "code related to", "ticket implementation",
        "where is ticket", "code for PROJ-"
    ],
    "list_github_repos": [
        "list repos", "show repos", "my repos", "repositories", "github repos",
        "repo names", "repository names", "all repos"
    ],
    "list_jira_tickets": [
        "list tickets", "show tickets", "my tickets", "jira tickets", 
        "ticket names", "issue names", "my issues"
    ]
}

def detect_workflow_intent(user_query: str) -> Optional[str]:
    """
    Detect if a user query matches a known workflow pattern.
    
    Args:
        user_query: The user's natural language request
        
    Returns:
        The workflow type if detected, None otherwise
    """
    query_lower = user_query.lower()
    
    # Special logic for repo_jira_comparison
    if "compare" in query_lower and ("repo" in query_lower or "github" in query_lower) and ("jira" in query_lower or "ticket" in query_lower):
        log.info(f"Detected workflow intent: repo_jira_comparison from query: {user_query}")
        return "repo_jira_comparison"
    
    # Simple single-tool requests
    if any(pattern in query_lower for pattern in WORKFLOW_PATTERNS["list_github_repos"]):
        log.info(f"Detected workflow intent: list_github_repos from query: {user_query}")
        return "list_github_repos"
        
    if any(pattern in query_lower for pattern in WORKFLOW_PATTERNS["list_jira_tickets"]):
        log.info(f"Detected workflow intent: list_jira_tickets from query: {user_query}")
        return "list_jira_tickets"
    
    # Check other patterns
    for workflow_type, patterns in WORKFLOW_PATTERNS.items():
        if workflow_type in ["repo_jira_comparison", "list_github_repos", "list_jira_tickets"]:
            continue  # Already handled above
            
        if any(pattern in query_lower for pattern in patterns):
            log.info(f"Detected workflow intent: {workflow_type} from query: {user_query}")
            return workflow_type
    
    return None 