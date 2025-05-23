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
            
            "detailed_jira_tickets": [
                WorkflowStep(
                    step_id="get_detailed_jira_tickets",
                    tool_name="jira_get_issues_by_user",
                    parameters={"user_email": "{user_email}", "max_results": 25},
                    description="Get detailed user's Jira tickets"
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
            ],
            
            "search_code": [
                WorkflowStep(
                    step_id="search_codebase",
                    tool_name="greptile_search_code",
                    parameters={"query": "{search_query}"},
                    description="Search codebase for specific code or functions"
                )
            ],
            
            "web_search": [
                WorkflowStep(
                    step_id="web_search",
                    tool_name="perplexity_web_search", 
                    parameters={"query": "{search_query}"},
                    description="Search the web for information"
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
                elif ref == "search_query":
                    # Extract search query from the user's latest message
                    search_query = "general search"  # default
                    if app_state.messages and app_state.messages[-1].get("role") == "user":
                        user_message = app_state.messages[-1].get("content", "")
                        # Remove common command words to extract the actual search terms
                        search_words = ["search", "find", "look for", "locate", "grep", "google", "what is", "who is", "tell me about"]
                        search_query = user_message.lower()
                        for word in search_words:
                            search_query = search_query.replace(word, "").strip()
                        search_query = search_query or user_message  # fallback to full message
                    
                    injected[key] = search_query
                    log.info(f"Injected search_query: {search_query}")
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
        elif workflow_type == "detailed_jira_tickets":
            return self._synthesize_detailed_jira_tickets(results)
        elif workflow_type == "code_ticket_analysis":
            return self._synthesize_code_ticket_analysis(results)
        elif workflow_type == "search_code":
            return self._synthesize_search_code(results)
        elif workflow_type == "web_search":
            return self._synthesize_web_search(results)
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
        synthesis.append(f"📊 **Repository vs Ticket Analysis** ({len(repos)} repos, {len(tickets)} tickets)")
        synthesis.append("")
        
        # Format in two columns as often requested
        synthesis.append("| 📁 **GitHub Repositories** | 🎫 **Jira Tickets** |")
        synthesis.append("|---------------------------|-------------------|")
        
        max_items = max(len(repos), len(tickets))
        for i in range(max_items):
            repo_name = ""
            ticket_name = ""
            
            if i < len(repos) and isinstance(repos[i], dict):
                repo_name = f"{repos[i].get('name', 'Unknown')}"
                
            if i < len(tickets) and isinstance(tickets[i], dict):
                ticket_name = f"{tickets[i].get('key', 'Unknown')} - {tickets[i].get('summary', 'No summary')[:40]}..."
            
            synthesis.append(f"| {repo_name} | {ticket_name} |")
        
        synthesis.append("")
        
        # Look for correlations
        repo_names = [repo.get("name", "") for repo in repos if isinstance(repo, dict)]
        correlations = []
        for repo_name in repo_names:
            for ticket in tickets:
                if isinstance(ticket, dict):
                    ticket_text = f"{ticket.get('summary', '')} {ticket.get('description', '')}"
                    if repo_name.lower() in ticket_text.lower():
                        correlations.append(f"🔗 Repo '{repo_name}' mentioned in ticket {ticket.get('key', 'Unknown')}")
        
        if correlations:
            synthesis.append("**🔗 Found Correlations:**")
            synthesis.extend(correlations)
        else:
            synthesis.append("⚠️ No obvious correlations found between repo names and ticket content.")
        
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
    
    def _synthesize_detailed_jira_tickets(self, results: Dict[str, Any]) -> str:
        """Synthesize detailed Jira tickets information."""
        ticket_result = results.get("get_detailed_jira_tickets", {}).get("result", {})
        
        if not ticket_result:
            return "❌ Could not retrieve detailed Jira ticket data."
        
        # Extract meaningful data
        tickets = ticket_result.get("data", []) if isinstance(ticket_result, dict) else ticket_result
        
        if not tickets:
            return "🎫 No detailed Jira tickets found."
        
        synthesis = []
        synthesis.append("🎫 **Detailed Jira Tickets Information**")
        
        for i, ticket in enumerate(tickets, 1):
            if isinstance(ticket, dict):
                key = ticket.get("key", "Unknown")
                summary = ticket.get("summary", "No summary")
                status = ticket.get("status", "Unknown")
                description = ticket.get("description", "No description")
                synthesis.append(f"{i}. **{key}** - {summary} ({status})")
                synthesis.append(f"  📋 Description: {description}")
        
        return "\n".join(synthesis)
    
    def _synthesize_search_code(self, results: Dict[str, Any]) -> str:
        """Synthesize search code results."""
        code_result = results.get("search_codebase", {}).get("result", {})
        
        synthesis = []
        synthesis.append("💻 **Code Search Results**")
        
        if code_result:
            # Handle the actual search result format from Greptile
            if isinstance(code_result, dict) and "data" in code_result:
                code_data = code_result["data"]
                synthesis.append(f"🔍 Found {len(code_data) if isinstance(code_data, list) else 1} code references")
            else:
                synthesis.append("🔍 Search completed")
        else:
            synthesis.append("❌ No code search results found")
        
        return "\n".join(synthesis)
    
    def _synthesize_web_search(self, results: Dict[str, Any]) -> str:
        """Synthesize web search results."""
        search_result = results.get("web_search", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🌐 **Web Search Results**")
        
        if search_result:
            search_data = search_result.get("data", []) if isinstance(search_result, dict) else search_result
            synthesis.append(f"🔍 Found {len(search_data) if isinstance(search_data, list) else 0} search results")
        
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
        "repos with", "repositories with", "cross reference", "correlation"
    ],
    "code_ticket_analysis": [
        "find code for ticket", "code related to", "ticket implementation",
        "where is ticket", "code for PROJ-", "find implementation",
        "locate code", "ticket code", "code changes"
    ],
    "list_github_repos": [
        "list repos", "show repos", "my repos", "repositories", "github repos",
        "repo names", "repository names", "all repos", "github repositories",
        "what repos", "which repos", "my github", "github projects",
        "projects", "my projects", "code repositories", "my code",
        "repositories I have", "repos I own", "my github repos",
        "show me repos", "show repositories", "display repos"
    ],
    "list_jira_tickets": [
        "list tickets", "show tickets", "my tickets", "jira tickets", 
        "ticket names", "issue names", "my issues", "jira issues",
        "what tickets", "which tickets", "assigned tickets", "my assignments",
        "tasks", "my tasks", "work items", "todo", "to do",
        "show me tickets", "display tickets", "current tickets",
        "open tickets", "active tickets", "pending tickets"
    ],
    "detailed_jira_tickets": [
        "dive deeper", "more details", "detailed view", "ticket details",
        "deeper into tickets", "more info", "expand tickets", "full details",
        "detail view", "complete info", "elaborate", "explain tickets",
        "break down", "specifics", "in depth", "comprehensive",
        "detailed information", "expand on", "tell me more"
    ],
    "search_code": [
        "search code", "find in code", "code search", "look for",
        "search for", "find function", "locate", "where is",
        "grep", "search repository", "code lookup"
    ],
    "web_search": [
        "search web", "google", "look up", "find information",
        "research", "what is", "who is", "when did", "how to",
        "search for", "find out", "tell me about"
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
    
    # CRITICAL: Detect requests for BOTH repos and tickets
    has_github = any(keyword in query_lower for keyword in ["repo", "repositories", "github", "projects", "code"])
    has_jira = any(keyword in query_lower for keyword in ["ticket", "tickets", "jira", "issue", "issues", "task", "tasks"])
    wants_both = any(keyword in query_lower for keyword in ["and", "both", "two", "columns", "together", "along with"])
    
    if has_github and has_jira and (wants_both or ("list" in query_lower and "my" in query_lower)):
        log.info(f"Detected workflow intent: repo_jira_comparison from query: {user_query}")
        return "repo_jira_comparison"
    
    # ULTRA-GENERAL DETECTION - catch ANY data request
    
    # GitHub repository requests
    github_keywords = ["repo", "repositories", "github", "projects", "code"]
    if any(keyword in query_lower for keyword in github_keywords):
        if any(word in query_lower for word in ["list", "show", "my", "what", "which", "display", "get"]):
            log.info(f"Detected workflow intent: list_github_repos from query: {user_query}")
            return "list_github_repos"
    
    # Jira ticket requests  
    jira_keywords = ["ticket", "tickets", "jira", "issue", "issues", "task", "tasks", "todo", "assigned"]
    if any(keyword in query_lower for keyword in jira_keywords):
        # Check for detail/deep dive requests with more variations
        detail_keywords = ["detail", "deeper", "more", "expand", "deep dive", "dive", "explain", "breakdown", "specifics"]
        if any(detail_word in query_lower for detail_word in detail_keywords):
            log.info(f"Detected workflow intent: detailed_jira_tickets from query: {user_query}")
            return "detailed_jira_tickets"
        elif any(word in query_lower for word in ["list", "show", "my", "what", "which", "display", "get"]):
            log.info(f"Detected workflow intent: list_jira_tickets from query: {user_query}")
            return "list_jira_tickets"
    
    # Code search requests
    code_search_keywords = ["search", "find", "locate", "grep", "where", "look"]
    code_targets = ["code", "function", "class", "file", "implementation"]
    if any(search in query_lower for search in code_search_keywords) and any(target in query_lower for target in code_targets):
        log.info(f"Detected workflow intent: search_code from query: {user_query}")
        return "search_code"
    
    # Web search requests
    web_search_keywords = ["what is", "who is", "when", "how", "why", "google", "search", "find information", "look up", "research"]
    if any(keyword in query_lower for keyword in web_search_keywords):
        # Don't trigger for code-related searches
        if not any(target in query_lower for target in code_targets + github_keywords):
            log.info(f"Detected workflow intent: web_search from query: {user_query}")
            return "web_search"
    
    # Fallback: check original specific patterns
    for workflow_type, patterns in WORKFLOW_PATTERNS.items():
        if workflow_type in ["repo_jira_comparison", "list_github_repos", "list_jira_tickets", "detailed_jira_tickets", "search_code", "web_search"]:
            continue  # Already handled above
            
        if any(pattern in query_lower for pattern in patterns):
            log.info(f"Detected workflow intent: {workflow_type} from query: {user_query}")
            return workflow_type
    
    return None 