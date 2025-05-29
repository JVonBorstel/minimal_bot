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
            ],
            
            "create_jira_story": [
                WorkflowStep(
                    step_id="create_story",
                    tool_name="jira_create_story",
                    parameters={
                        "summary": "{story_summary}",
                        "description": "{story_description}",
                        "template": "{story_template}",
                        "issue_type": "{issue_type}",
                        "priority": "{priority}",
                        "assignee_email": "{assignee_email}",
                        "labels": "{labels}",
                        "story_points": "{story_points}"
                    },
                    description="Create a new Jira story with template support"
                )
            ],
            
            "create_user_story": [
                WorkflowStep(
                    step_id="create_user_story",
                    tool_name="jira_create_story",
                    parameters={
                        "summary": "{story_summary}",
                        "description": "{story_description}",
                        "template": "user_story",
                        "issue_type": "Story",
                        "priority": "{priority}",
                        "assignee_email": "{assignee_email}",
                        "story_points": "{story_points}"
                    },
                    description="Create a user story with structured template"
                )
            ],
            
            "create_bug_ticket": [
                WorkflowStep(
                    step_id="create_bug",
                    tool_name="jira_create_story",
                    parameters={
                        "summary": "{story_summary}",
                        "description": "{story_description}",
                        "template": "bug_fix",
                        "issue_type": "Bug",
                        "priority": "{priority}",
                        "assignee_email": "{assignee_email}"
                    },
                    description="Create a bug ticket with structured template"
                )
            ],
            
            "create_tech_debt_ticket": [
                WorkflowStep(
                    step_id="create_tech_debt",
                    tool_name="jira_create_story",
                    parameters={
                        "summary": "{story_summary}",
                        "description": "{story_description}",
                        "template": "tech_debt",
                        "issue_type": "Task",
                        "priority": "{priority}",
                        "assignee_email": "{assignee_email}"
                    },
                    description="Create a technical debt ticket"
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
                
                # Update session statistics for workflow tool execution
                if app_state and hasattr(app_state, 'session_stats') and app_state.session_stats:
                    # Determine success for stats
                    is_success = self._determine_success(step_result)
                    
                    # Extract execution time if available
                    execution_time_ms = 0
                    if isinstance(step_result, dict):
                        execution_time_ms = step_result.get("execution_time_ms", 0)
                    
                    # Update session stats
                    app_state.session_stats.tool_calls = getattr(app_state.session_stats, 'tool_calls', 0) + 1
                    app_state.session_stats.tool_execution_ms = getattr(app_state.session_stats, 'tool_execution_ms', 0) + execution_time_ms
                    
                    if not is_success:
                        app_state.session_stats.failed_tool_calls = getattr(app_state.session_stats, 'failed_tool_calls', 0) + 1
                    
                    # Update tool usage tracking if available
                    if hasattr(app_state, 'update_tool_usage') and callable(app_state.update_tool_usage):
                        app_state.update_tool_usage(step.tool_name, execution_time_ms, is_success)
                
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
                    if app_state.messages and len(app_state.messages) > 0:
                        last_message = app_state.messages[-1]
                        if hasattr(last_message, 'role') and last_message.role == "user":
                            # Use the text property which handles our Message model correctly
                            user_message = getattr(last_message, 'text', '') or getattr(last_message, 'raw_text', '')
                            if user_message:
                                # Remove common command words to extract the actual search terms
                                search_words = ["search", "find", "look for", "locate", "grep", "google", "what is", "who is", "tell me about", "use", "perplexity", "web"]
                                search_query = user_message.lower()
                                for word in search_words:
                                    search_query = search_query.replace(word, "").strip()
                                search_query = search_query or user_message  # fallback to full message
                                # Clean up extra whitespace
                                search_query = " ".join(search_query.split())
                    
                    injected[key] = search_query
                    log.info(f"Injected search_query: {search_query}")
                elif ref in ["story_summary", "story_description", "story_template", "issue_type", "priority", "assignee_email", "labels", "story_points"]:
                    # Extract story creation parameters from user message
                    injected_value = self._extract_story_parameter(ref, app_state, context)
                    injected[key] = injected_value
                    log.info(f"Injected {ref}: {injected_value}")
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
    
    def _extract_story_parameter(self, parameter: str, app_state: AppState, context: Dict[str, Any]) -> Any:
        """
        Extract story creation parameters from user message using intelligent parsing.
        
        Args:
            parameter: The parameter to extract (story_summary, story_description, etc.)
            app_state: Application state containing messages
            context: Additional context
            
        Returns:
            Extracted parameter value or intelligent default
        """
        user_message = ""
        if app_state.messages and len(app_state.messages) > 0:
            last_message = app_state.messages[-1]
            if hasattr(last_message, 'role') and last_message.role == "user":
                user_message = getattr(last_message, 'text', '') or getattr(last_message, 'raw_text', '')
        
        # Check context first for explicit values
        if parameter in context and context[parameter]:
            return context[parameter]
        
        if parameter == "story_summary":
            # Extract summary from user message
            # Look for patterns like "create story: title" or "add task: title"
            summary_patterns = [
                r"create\s+(?:story|task|ticket|issue):\s*(.+)",
                r"add\s+(?:story|task|ticket|issue):\s*(.+)",
                r"new\s+(?:story|task|ticket|issue):\s*(.+)",
                r"(?:story|task|ticket|issue)\s+for\s+(.+)",
                r"(?:story|task|ticket|issue)\s+to\s+(.+)"
            ]
            
            import re
            for pattern in summary_patterns:
                match = re.search(pattern, user_message.lower())
                if match:
                    # Take only the part immediately after the colon, before additional details
                    full_match = match.group(1).strip()
                    # Split by common separators for additional details
                    summary_parts = re.split(r'\s+(?:with|and|#|assign|priority|points|estimate)', full_match, 1)
                    return summary_parts[0].strip().title()
            
            # Fallback: extract meaningful part after common command words
            command_words = ["create", "add", "new", "make", "build", "story", "task", "ticket", "issue", "jira"]
            clean_message = user_message.lower()
            for word in command_words:
                clean_message = clean_message.replace(word, "").strip()
            
            if clean_message:
                # Take first part before additional details and limit to 80 characters
                clean_parts = re.split(r'\s+(?:with|and|#|assign|priority|points|estimate)', clean_message, 1)
                return clean_parts[0][:80].strip().title()
            
            return "New Story"
        
        elif parameter == "story_description":
            # Look for description patterns or use full message as description
            desc_patterns = [
                r"description:\s*(.+)",
                r"details:\s*(.+)",
                r"requirement:\s*(.+)"
            ]
            
            import re
            for pattern in desc_patterns:
                match = re.search(pattern, user_message.lower())
                if match:
                    return match.group(1).strip()
            
            # Use full message as description if no specific pattern found
            return user_message if user_message else "Story description"
        
        elif parameter == "story_template":
            # Detect template from keywords in message
            template_keywords = {
                "user_story": ["user story", "as a user", "user wants", "user needs"],
                "bug_fix": ["bug", "issue", "problem", "fix", "broken", "error"],
                "tech_debt": ["tech debt", "technical debt", "refactor", "cleanup", "improve"],
                "research": ["research", "investigate", "explore", "spike", "poc", "proof of concept"]
            }
            
            message_lower = user_message.lower()
            for template, keywords in template_keywords.items():
                if any(keyword in message_lower for keyword in keywords):
                    return template
            
            return "custom"
        
        elif parameter == "issue_type":
            # Detect issue type from keywords
            type_keywords = {
                "Bug": ["bug", "issue", "problem", "fix", "broken", "error"],
                "Epic": ["epic", "large", "major", "big"],
                "Task": ["task", "todo", "work", "do", "tech debt", "technical debt", "refactor", "cleanup"],
                "Story": ["story", "feature", "requirement", "user"]
            }
            
            message_lower = user_message.lower()
            
            # Check for tech debt specifically first since it should be a Task
            if any(tech_word in message_lower for tech_word in ["tech debt", "technical debt"]):
                return "Task"
            
            for issue_type, keywords in type_keywords.items():
                if any(keyword in message_lower for keyword in keywords):
                    return issue_type
            
            return "Story"  # Default
        
        elif parameter == "priority":
            # Detect priority from keywords
            priority_keywords = {
                "Highest": ["critical", "urgent", "asap", "emergency", "highest"],
                "High": ["high", "important", "soon"],
                "Medium": ["medium", "normal", "regular"],
                "Low": ["low", "minor", "whenever"],
                "Lowest": ["lowest", "someday", "nice to have"]
            }
            
            message_lower = user_message.lower()
            for priority, keywords in priority_keywords.items():
                if any(keyword in message_lower for keyword in keywords):
                    return priority
            
            return "Medium"  # Default
        
        elif parameter == "assignee_email":
            # Look for email patterns or assignee mentions
            import re
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            email_match = re.search(email_pattern, user_message)
            if email_match:
                return email_match.group()
            
            # Look for "assign to" patterns
            assign_patterns = [
                r"assign\s+to\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})",
                r"assignee:\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})"
            ]
            
            for pattern in assign_patterns:
                match = re.search(pattern, user_message.lower())
                if match:
                    return match.group(1)
            
            return None  # No assignee
        
        elif parameter == "labels":
            # Extract labels from hashtags or label patterns
            import re
            hashtag_pattern = r'#(\w+)'
            hashtags = re.findall(hashtag_pattern, user_message)
            
            if hashtags:
                return hashtags
            
            # Look for "labels:" pattern
            label_pattern = r'labels?:\s*([^,\n]+)'
            label_match = re.search(label_pattern, user_message.lower())
            if label_match:
                labels_text = label_match.group(1)
                return [label.strip() for label in labels_text.split(',')]
            
            return []  # No labels
        
        elif parameter == "story_points":
            # Look for story points patterns
            import re
            points_patterns = [
                r'(\d+)\s*(?:points?|pts?)',
                r'points?:\s*(\d+)',
                r'estimate:\s*(\d+)',
                r'effort:\s*(\d+)'
            ]
            
            for pattern in points_patterns:
                match = re.search(pattern, user_message.lower())
                if match:
                    return int(match.group(1))
            
            return None  # No story points
        
        # Default fallback
        return None
    
    def _determine_success(self, result: Any) -> bool:
        """Determine if a tool execution was successful."""
        if isinstance(result, dict):
            # Handle explicit error status
            if result.get("status", "").upper() in ["ERROR", "FAILED", "FAILURE"]:
                return False
            # Handle successful status
            if result.get("status", "").upper() in ["SUCCESS", "OK", "COMPLETED"]:
                return True
            # Handle configuration errors (these are failures but we want to track them specially)
            if result.get("error_type") == "ToolNotConfigured":
                return False
        # If result is None or empty, consider it a failure
        return result is not None and result != ""
    
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
        elif workflow_type == "create_jira_story":
            return self._synthesize_create_jira_story(results)
        elif workflow_type == "create_user_story":
            return self._synthesize_create_user_story(results)
        elif workflow_type == "create_bug_ticket":
            return self._synthesize_create_bug_ticket(results)
        elif workflow_type == "create_tech_debt_ticket":
            return self._synthesize_create_tech_debt_ticket(results)
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
        
        # Check if the tool execution failed
        step_success = results.get("get_repos", {}).get("success", False)
        if not step_success or not repos_result:
            # Check if this is a configuration error
            if isinstance(repos_result, dict) and repos_result.get("error_type") == "ToolNotConfigured":
                error_message = repos_result.get("message", "GitHub tools aren't configured")
                actionable_advice = repos_result.get("actionable_advice", "")
                fallback_suggestions = repos_result.get("fallback_suggestions", [])
                
                synthesis = []
                synthesis.append("⚠️ **GitHub Repository Access Issue**")
                synthesis.append(f"{error_message}")
                
                if actionable_advice:
                    synthesis.append(f"\n💡 **How to fix this:** {actionable_advice}")
                
                if fallback_suggestions:
                    synthesis.append(f"\n🔄 **What you can do instead:**")
                    for i, suggestion in enumerate(fallback_suggestions, 1):
                        synthesis.append(f"  {i}. {suggestion}")
                
                return "\n".join(synthesis)
            else:
                return "❌ Could not retrieve repository data. There may be a connection issue or the service is temporarily unavailable."
        
        # Extract meaningful data
        repos = repos_result.get("data", []) if isinstance(repos_result, dict) else repos_result
        
        if not repos:
            return "📁 No repositories found in your GitHub account."
        
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
        
        # Check if the tool execution failed
        step_success = results.get("get_jira_tickets", {}).get("success", False)
        if not step_success or not jira_result:
            # Check if this is a configuration error
            if isinstance(jira_result, dict) and jira_result.get("error_type") == "ToolNotConfigured":
                error_message = jira_result.get("message", "Jira tools aren't configured")
                actionable_advice = jira_result.get("actionable_advice", "")
                fallback_suggestions = jira_result.get("fallback_suggestions", [])
                
                synthesis = []
                synthesis.append("⚠️ **Jira Ticket Access Issue**")
                synthesis.append(f"{error_message}")
                
                if actionable_advice:
                    synthesis.append(f"\n💡 **How to fix this:** {actionable_advice}")
                
                if fallback_suggestions:
                    synthesis.append(f"\n🔄 **What you can do instead:**")
                    for i, suggestion in enumerate(fallback_suggestions, 1):
                        synthesis.append(f"  {i}. {suggestion}")
                
                return "\n".join(synthesis)
            else:
                return "❌ Could not retrieve Jira ticket data. There may be a connection issue or the service is temporarily unavailable."
        
        # Extract meaningful data  
        tickets = jira_result.get("data", []) if isinstance(jira_result, dict) else jira_result
        
        if not tickets:
            return "🎫 No Jira tickets found for your account."
        
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
        
        # Check if the tool execution failed
        step_success = results.get("search_codebase", {}).get("success", False)
        if not step_success or not code_result:
            # Check if this is a configuration error
            if isinstance(code_result, dict) and code_result.get("error_type") == "ToolNotConfigured":
                error_message = code_result.get("message", "Code search tools aren't configured")
                actionable_advice = code_result.get("actionable_advice", "")
                fallback_suggestions = code_result.get("fallback_suggestions", [])
                
                synthesis.append(f"⚠️ {error_message}")
                
                if actionable_advice:
                    synthesis.append(f"\n💡 **How to fix this:** {actionable_advice}")
                
                if fallback_suggestions:
                    synthesis.append(f"\n🔄 **What you can do instead:**")
                    for i, suggestion in enumerate(fallback_suggestions, 1):
                        synthesis.append(f"  {i}. {suggestion}")
                
                return "\n".join(synthesis)
            else:
                synthesis.append("❌ Code search failed. There may be a connection issue or the service is temporarily unavailable.")
                return "\n".join(synthesis)
        
        if code_result:
            # Handle the actual search result format from Greptile
            if isinstance(code_result, dict) and "data" in code_result:
                code_data = code_result["data"]
                synthesis.append(f"🔍 Found {len(code_data) if isinstance(code_data, list) else 1} code references")
            else:
                synthesis.append("🔍 Search completed")
        else:
            synthesis.append("🔍 No code search results found")
        
        return "\n".join(synthesis)
    
    def _synthesize_web_search(self, results: Dict[str, Any]) -> str:
        """Synthesize web search results."""
        search_result = results.get("web_search", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🌐 **Web Search Results**")
        
        # Check if the tool execution failed
        step_success = results.get("web_search", {}).get("success", False)
        if not step_success or not search_result:
            # Check if this is a configuration error
            if isinstance(search_result, dict) and search_result.get("error_type") == "ToolNotConfigured":
                error_message = search_result.get("message", "Web search tools aren't configured")
                actionable_advice = search_result.get("actionable_advice", "")
                fallback_suggestions = search_result.get("fallback_suggestions", [])
                
                synthesis.append(f"⚠️ {error_message}")
                
                if actionable_advice:
                    synthesis.append(f"\n💡 **How to fix this:** {actionable_advice}")
                
                if fallback_suggestions:
                    synthesis.append(f"\n🔄 **What you can do instead:**")
                    for i, suggestion in enumerate(fallback_suggestions, 1):
                        synthesis.append(f"  {i}. {suggestion}")
                
                return "\n".join(synthesis)
            else:
                synthesis.append("❌ Web search failed. There may be a connection issue or the service is temporarily unavailable.")
                return "\n".join(synthesis)
        
        if search_result:
            # Check if this is a successful result with data
            if isinstance(search_result, dict):
                if search_result.get("status") == "SUCCESS":
                    data = search_result.get("data", {})
                    if isinstance(data, dict):
                        answer = data.get("answer", "")
                        sources = data.get("sources", [])
                        
                        if answer:
                            synthesis.append(f"📝 **Answer:** {answer}")
                        
                        if sources and len(sources) > 0:
                            synthesis.append(f"\n🔗 **Sources ({len(sources)} found):**")
                            for i, source in enumerate(sources[:5], 1):  # Show up to 5 sources
                                if isinstance(source, dict):
                                    title = source.get("title", "Unknown")
                                    url = source.get("url", "")
                                    synthesis.append(f"{i}. [{title}]({url})" if url else f"{i}. {title}")
                        else:
                            synthesis.append("🔍 Search completed successfully but no sources found.")
                    else:
                        synthesis.append("🔍 Search completed successfully.")
                else:
                    # Handle error status
                    error_msg = search_result.get("message", "Unknown error")
                    synthesis.append(f"❌ Search failed: {error_msg}")
            else:
                synthesis.append("🔍 Search completed.")
        else:
            synthesis.append("🔍 No search results available.")
        
        return "\n".join(synthesis)
    
    def _synthesize_create_jira_story(self, results: Dict[str, Any]) -> str:
        """Synthesize create Jira story results."""
        story_result = results.get("create_story", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🎫 **Jira Story Creation Results**")
        
        if story_result:
            story_data = story_result.get("data", {}) if isinstance(story_result, dict) else {}
            synthesis.append(f"📋 Story: {story_data.get('key', 'Unknown')} - {story_data.get('summary', 'No summary')}")
        else:
            synthesis.append("❌ Story creation failed")
        
        return "\n".join(synthesis)
    
    def _synthesize_create_user_story(self, results: Dict[str, Any]) -> str:
        """Synthesize create user story results."""
        story_result = results.get("create_user_story", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🎫 **User Story Creation Results**")
        
        if story_result:
            story_data = story_result.get("data", {}) if isinstance(story_result, dict) else {}
            synthesis.append(f"📋 Story: {story_data.get('key', 'Unknown')} - {story_data.get('summary', 'No summary')}")
        else:
            synthesis.append("❌ User story creation failed")
        
        return "\n".join(synthesis)
    
    def _synthesize_create_bug_ticket(self, results: Dict[str, Any]) -> str:
        """Synthesize create bug ticket results."""
        bug_result = results.get("create_bug", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🎫 **Bug Ticket Creation Results**")
        
        if bug_result:
            bug_data = bug_result.get("data", {}) if isinstance(bug_result, dict) else {}
            synthesis.append(f"📋 Bug: {bug_data.get('key', 'Unknown')} - {bug_data.get('summary', 'No summary')}")
        else:
            synthesis.append("❌ Bug ticket creation failed")
        
        return "\n".join(synthesis)
    
    def _synthesize_create_tech_debt_ticket(self, results: Dict[str, Any]) -> str:
        """Synthesize create technical debt ticket results."""
        tech_debt_result = results.get("create_tech_debt", {}).get("result", {})
        
        synthesis = []
        synthesis.append("🎫 **Technical Debt Ticket Creation Results**")
        
        if tech_debt_result:
            tech_debt_data = tech_debt_result.get("data", {}) if isinstance(tech_debt_result, dict) else {}
            synthesis.append(f"📋 Technical Debt: {tech_debt_data.get('key', 'Unknown')} - {tech_debt_data.get('summary', 'No summary')}")
        else:
            synthesis.append("❌ Technical debt ticket creation failed")
        
        return "\n".join(synthesis)
    
    def _generic_synthesis(self, results: Dict[str, Any]) -> str:
        """Generic synthesis for unknown workflow types."""
        successful_steps = [
            step_id for step_id, result in results.items() 
            if result.get("success", False)
        ]
        
        failed_steps = [
            step_id for step_id, result in results.items() 
            if not result.get("success", False)
        ]
        
        synthesis = []
        synthesis.append(f"🔄 **Workflow Complete**")
        
        if successful_steps:
            synthesis.append(f"✅ Successfully executed {len(successful_steps)} steps: {', '.join(successful_steps)}")
            
            for step_id in successful_steps:
                step_result = results[step_id]
                tool_name = step_result.get("tool_name", "Unknown")
                synthesis.append(f"  📌 {step_id} ({tool_name}): Success")
        
        if failed_steps:
            synthesis.append(f"\n⚠️ **Issues encountered in {len(failed_steps)} steps:**")
            
            for step_id in failed_steps:
                step_result = results[step_id].get("result", {})
                
                # Check if this is a configuration error
                if isinstance(step_result, dict) and step_result.get("error_type") == "ToolNotConfigured":
                    error_message = step_result.get("message", "Tool not configured")
                    actionable_advice = step_result.get("actionable_advice", "")
                    fallback_suggestions = step_result.get("fallback_suggestions", [])
                    
                    synthesis.append(f"  🔧 **{step_id}**: {error_message}")
                    
                    if actionable_advice:
                        synthesis.append(f"     💡 **Fix:** {actionable_advice}")
                    
                    if fallback_suggestions:
                        synthesis.append(f"     🔄 **Alternatives:**")
                        for suggestion in fallback_suggestions[:2]:  # Limit to 2 suggestions to keep it concise
                            synthesis.append(f"       • {suggestion}")
                else:
                    # Generic error handling
                    tool_name = results[step_id].get("tool_name", "Unknown")
                    synthesis.append(f"  ❌ {step_id} ({tool_name}): Failed")
        
        if not successful_steps and not failed_steps:
            synthesis.append("ℹ️ No steps were executed.")
        
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
        "search for", "find out", "tell me about", "weather", "tell me", "can you tell me"
    ],
    "create_jira_story": [
        "create story", "new story", "add story", "make story",
        "create ticket", "new ticket", "add ticket", "make ticket",
        "create issue", "new issue", "add issue", "make issue",
        "create task", "new task", "add task", "make task",
        "jira story", "jira ticket", "jira issue", "jira task"
    ],
    "create_user_story": [
        "create user story", "new user story", "add user story",
        "user story for", "as a user", "user wants", "user needs",
        "user story template", "structured story"
    ],
    "create_bug_ticket": [
        "create bug", "new bug", "add bug", "report bug",
        "bug ticket", "bug report", "bug issue", "fix bug",
        "broken", "error", "problem", "issue with"
    ],
    "create_tech_debt_ticket": [
        "create tech debt", "technical debt", "refactor",
        "cleanup", "improve code", "code improvement",
        "tech debt ticket", "refactoring task"
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
        if "detail" in query_lower or "deeper" in query_lower or "more" in query_lower or "expand" in query_lower:
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
    web_search_keywords = ["what is", "who is", "when", "how", "why", "google", "search", "find information", "look up", "research", "weather", "tell me", "can you tell me"]
    if any(keyword in query_lower for keyword in web_search_keywords):
        # Don't trigger for code-related searches
        if not any(target in query_lower for target in code_targets + github_keywords):
            log.info(f"Detected workflow intent: web_search from query: {user_query}")
            return "web_search"
    
    # Jira story creation requests
    create_keywords = ["create", "new", "add", "make"]
    story_keywords = ["story", "ticket", "issue", "task"]
    
    if any(create_word in query_lower for create_word in create_keywords) and any(story_word in query_lower for story_word in story_keywords):
        # Check for specific story types
        if "user story" in query_lower or "as a user" in query_lower:
            log.info(f"Detected workflow intent: create_user_story from query: {user_query}")
            return "create_user_story"
        elif any(bug_word in query_lower for bug_word in ["bug", "broken", "error", "problem", "fix"]):
            log.info(f"Detected workflow intent: create_bug_ticket from query: {user_query}")
            return "create_bug_ticket"
        elif any(tech_word in query_lower for tech_word in ["tech debt", "technical debt", "refactor", "cleanup"]):
            log.info(f"Detected workflow intent: create_tech_debt_ticket from query: {user_query}")
            return "create_tech_debt_ticket"
        else:
            # Generic story creation
            log.info(f"Detected workflow intent: create_jira_story from query: {user_query}")
            return "create_jira_story"
    
    # Fallback: check original specific patterns
    for workflow_type, patterns in WORKFLOW_PATTERNS.items():
        if workflow_type in ["repo_jira_comparison", "list_github_repos", "list_jira_tickets", "detailed_jira_tickets", "search_code", "web_search"]:
            continue  # Already handled above
            
        if any(pattern in query_lower for pattern in patterns):
            log.info(f"Detected workflow intent: {workflow_type} from query: {user_query}")
            return workflow_type
    
    return None 