import logging
from typing import Dict, Any, Optional, List, Literal
import time
import asyncio
import functools

from jira import JIRA, JIRAError
from jira.exceptions import JIRAError as LibraryJIRAError
from requests.exceptions import RequestException
import requests

from config import Config
from . import tool
from user_auth.tool_access import requires_permission
from user_auth.permissions import Permission
from state_models import AppState

log = logging.getLogger("tools.jira")
logging.getLogger('jira').setLevel(logging.INFO)

class JiraTools:
    """
    Provides tools for interacting with the Jira API using the python-jira library.
    Now supports both OAuth 2.0 (for scoped tokens) and Basic Auth (for unscoped tokens).
    Supports both shared credentials (from config) and personal user credentials.
    """
    jira_client: Optional[JIRA] = None
    # Cache for temporary personal clients to avoid recreating them
    _personal_clients_cache: Dict[str, JIRA] = {}

    def __init__(self, config: Config):
        """Initializes the Jira client with shared credentials from config."""
        self.config = config
        self.jira_url = self.config.get_env_value('JIRA_API_URL')
        self.jira_email = self.config.get_env_value('JIRA_API_EMAIL')
        self.jira_token = self.config.get_env_value('JIRA_API_TOKEN')
        self._personal_clients_cache = {}

        log.debug(f"Jira URL: {'FOUND' if self.jira_url else 'NOT FOUND'}")
        log.debug(f"Jira Email: {'FOUND' if self.jira_email else 'NOT FOUND'}")
        log.debug(f"Jira Token: {'FOUND' if self.jira_token else 'NOT FOUND'}")

        if not all([self.jira_url, self.jira_email, self.jira_token]):
            log.warning("Jira configuration is incomplete. Jira tools will not be functional.")
            self.jira_client = None
            return

        # Try to create client with automatic auth method detection
        self.jira_client = self._create_jira_client(self.jira_email, self.jira_token)

    def _is_scoped_token(self, token: str) -> bool:
        """
        Detect if a token is scoped or unscoped.
        Scoped tokens typically start with 'ATATT3xFf' and are longer.
        Both types use basic authentication - scopes are enforced server-side.
        """
        if not token:
            return False
        
        # Scoped tokens are typically longer and have a specific format
        return len(token) > 100 and token.startswith('ATATT3xFf')

    def _create_jira_client(self, email: str, token: str) -> Optional[JIRA]:
        """
        Create a Jira client using the appropriate authentication method.
        Both scoped and unscoped tokens use basic authentication - the difference is 
        that scopes are enforced server-side by Atlassian Cloud.
        """
        try:
            log.info(f"Attempting to connect to Jira at {self.jira_url} with user {email}")
            options = {'server': self.jira_url, 'verify': True, 'rest_api_version': 'latest'}
            
            token_type = "scoped" if self._is_scoped_token(token) else "unscoped"
            log.info(f"Detected {token_type} API token - using Basic authentication (scopes enforced server-side)")
            
            # Both scoped and unscoped tokens use basic auth
            # The difference is that scoped tokens have permissions enforced by Atlassian Cloud
            jira_client = JIRA(
                options=options,
                basic_auth=(email, token),
                timeout=self.config.settings.default_api_timeout_seconds,
                max_retries=self.config.settings.default_api_max_retries
            )
            
            # Test the connection
            server_info = jira_client.server_info()
            log.info(f"Jira client initialized successfully using Basic Auth with {token_type} token. Connected to: {server_info.get('baseUrl', self.jira_url)}")
            return jira_client
            
        except LibraryJIRAError as e:
            rate_limit_headers = {}
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'headers'):
                headers = e.response.headers
                rate_limit_headers['X-RateLimit-Limit'] = headers.get('X-RateLimit-Limit')
                rate_limit_headers['X-RateLimit-Remaining'] = headers.get('X-RateLimit-Remaining')
                rate_limit_headers['X-RateLimit-Reset'] = headers.get('X-RateLimit-Reset')
                rate_limit_headers['Retry-After'] = headers.get('Retry-After')
                rate_limit_headers = {k: v for k, v in rate_limit_headers.items() if v is not None}
                if rate_limit_headers:
                    log.warning(f"Jira client initialization error (status: {e.status_code}). Rate limit headers: {rate_limit_headers}")
            
            # Provide better error messages for scoped token issues
            if self._is_scoped_token(token):
                if e.status_code == 401:
                    log.error(f"Authentication failed with scoped token. Check if token has required scopes: Status={e.status_code}, Text={e.text}")
                elif e.status_code == 403:
                    log.error(f"Access forbidden with scoped token. Missing required permissions/scopes: Status={e.status_code}, Text={e.text}")
                else:
                    log.error(f"Scoped token error: Status={e.status_code}, Text={e.text}")
            else:
                log.error(f"Failed to initialize Jira client (JIRAError): Status={e.status_code}, Text={e.text}", exc_info=True)
            return None
        except RequestException as e:
            log.error(f"Failed to initialize Jira client (Network Error): {e}", exc_info=True)
            return None
        except Exception as e:
            log.error(f"Failed to initialize Jira client (Unexpected Error): {e}", exc_info=True)
            return None

    def _get_personal_credentials(self, app_state: AppState) -> Optional[tuple[str, str]]:
        """
        Extract personal Jira credentials (email, token) from user profile if available.
        
        Args:
            app_state: Application state containing current user profile
            
        Returns:
            Tuple of (email, token) if found, None otherwise
        """
        if not app_state or not hasattr(app_state, 'current_user') or not app_state.current_user:
            return None
        
        user_profile = app_state.current_user
        profile_data = getattr(user_profile, 'profile_data', None) or {}
        personal_creds = profile_data.get('personal_credentials', {})
        
        jira_email = personal_creds.get('jira_email')
        jira_token = personal_creds.get('jira_token')
        
        if (jira_email and jira_email.strip() and jira_email.lower() not in ['none', 'skip', 'n/a'] and
            jira_token and jira_token.strip() and jira_token.lower() not in ['none', 'skip', 'n/a']):
            log.debug(f"Found personal Jira credentials for user {user_profile.user_id}")
            return (jira_email.strip(), jira_token.strip())
        
        return None

    def _create_personal_client(self, email: str, token: str) -> Optional[JIRA]:
        """
        Create a temporary Jira client for personal credentials.
        Now supports both OAuth 2.0 and Basic Auth based on token type.
        
        Args:
            email: Personal Jira email
            token: Personal Jira API token
            
        Returns:
            JIRA client instance or None if creation failed
        """
        # Create a cache key from credentials
        cache_key = f"{email}:{token[:8]}..."  # Use partial token for security
        
        # Check cache first
        if cache_key in self._personal_clients_cache:
            log.debug("Using cached personal Jira client")
            return self._personal_clients_cache[cache_key]
        
        if not self.jira_url:
            log.warning("Cannot create personal Jira client: Jira URL not configured")
            return None
        
        log.debug(f"Creating personal Jira client for {email}")
        personal_client = self._create_jira_client(email, token)
        
        if personal_client:
            log.info(f"Personal Jira client created successfully for user: {email}")
            # Cache it for future use in this session
            self._personal_clients_cache[cache_key] = personal_client
            return personal_client
        else:
            log.warning(f"Failed to create personal Jira client for {email}")
            return None

    def _get_jira_client(self, app_state: AppState) -> Optional[JIRA]:
        """
        Get the appropriate Jira client, prioritizing personal credentials over shared ones.
        
        Args:
            app_state: Application state containing current user profile
            
        Returns:
            JIRA client instance or None if no client available
        """
        # First, try personal credentials
        personal_creds = self._get_personal_credentials(app_state)
        if personal_creds:
            email, token = personal_creds
            log.debug("Attempting to use personal Jira credentials")
            personal_client = self._create_personal_client(email, token)
            if personal_client:
                log.info("Using personal Jira client for authenticated user")
                return personal_client
            else:
                log.warning("Personal Jira credentials failed, falling back to shared credentials")
        
        # Fall back to shared credentials
        if self.jira_client:
            log.debug("Using shared Jira client")
            return self.jira_client
        
        log.warning("No Jira client available (neither personal nor shared)")
        return None

    def _check_jira_client(self, app_state: AppState):
        """Checks if a Jira client is available, raising ValueError if not."""
        client = self._get_jira_client(app_state)
        if not client:
            log.error("No Jira client available. Configuration might be missing or incorrect.")
            raise ValueError("Jira client not available. Please check Jira API configuration or provide personal credentials.")
        return client

    def _search_issues_sync(self, app_state: AppState, jql_query: str, max_results: int, fields_to_retrieve: str) -> List[Dict[str, Any]]:
        """Synchronous helper method to search Jira issues."""
        jira_client = self._check_jira_client(app_state)
        
        issues_found = jira_client.search_issues(
            jql_query,
            maxResults=max_results,
            fields=fields_to_retrieve,
            json_result=False 
        )
        
        results = []
        for issue in issues_found:
            results.append({
                "key": issue.key,
                "url": issue.permalink(),
                "summary": issue.fields.summary,
                "status": issue.fields.status.name,
                "project_key": issue.fields.project.key,
                "project_name": issue.fields.project.name,
                "issue_type": issue.fields.issuetype.name,
                "assignee": getattr(issue.fields.assignee, 'displayName', None) if issue.fields.assignee else None,
                "reporter": getattr(issue.fields.reporter, 'displayName', None) if issue.fields.reporter else None,
                "updated": issue.fields.updated,
                "priority": getattr(issue.fields.priority, 'name', None) if hasattr(issue.fields, 'priority') and issue.fields.priority else None,
                "due_date": getattr(issue.fields, 'duedate', None),
                "labels": getattr(issue.fields, 'labels', [])
            })
        
        return results

    @tool(name="jira_get_issues_by_user",
          description="Finds issues assigned to a user (by email), optionally filtering by status category (e.g., 'To Do', 'In Progress', 'Done'). Returns summaries.",
          parameters_schema={
              "type": "object",
              "properties": {
                  "user_email": {
                      "type": "string",
                      "description": "The email address of the user to find assigned issues for. If not provided, defaults to the current authenticated user's email."
                  },
                  "status_category": {
                      "type": "string",
                      "description": "Filter issues by status category. Leave empty to search all statuses.",
                      "enum": ["to do", "in progress", "done", "all"],
                      "default": "all"
                  },
                  "max_results": {
                      "type": "integer",
                      "description": "Maximum number of issues to return.",
                      "default": 15
                  }
              },
              "required": []
          }
    )
    @requires_permission(Permission.JIRA_READ_ISSUES, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def get_issues_by_user(self, app_state: AppState, user_email: Optional[str] = None, status_category: Optional[Literal["to do", "in progress", "done", "all"]] = "all", max_results: int = 15) -> List[Dict[str, Any]]:
        """
        Finds issues assigned to a user by their email address, optionally filtered by status category.
        Now supports personal Jira credentials for enhanced access.
        If user_email is not provided, it attempts to use the email of the current user in app_state.

        Args:
            app_state: Application state containing user profile (injected by tool framework)
            user_email: Optional. The email address of the user. Defaults to current user's email.
            status_category: Optional. Filter by status category: 'to do', 'in progress', 'done', 'all'. Defaults to 'all'.
            max_results: Optional. Maximum number of issues to return. Defaults to 15.

        Returns:
            A list of dictionaries, where each dictionary is a summary of an issue
            (key, summary, status, URL, project, type).
        """
        effective_user_email = user_email
        if not effective_user_email:
            if app_state and app_state.current_user and app_state.current_user.email:
                effective_user_email = app_state.current_user.email
                log.info(f"User email not provided for get_issues_by_user. Using current user's email: {effective_user_email}")
            else:
                raise ValueError("User email not provided and could not be determined from the current user session.")

        if not effective_user_email: # Double check after potential derivation
            raise ValueError("User email cannot be empty.")

        log.info(f"Searching for Jira issues assigned to user: {effective_user_email}, status_category: {status_category}, max_results: {max_results}")

        try:
            jql_parts = [f"assignee = \"{effective_user_email}\""]
            
            if status_category and status_category.lower() != "all":
                status_map = {
                    "to do": "To Do",
                    "in progress": "In Progress",
                    "done": "Done"
                }
                jql_status_category = status_map.get(status_category.lower())
                if jql_status_category:
                    jql_parts.append(f"statusCategory = \"{jql_status_category}\"")
                else:
                    log.warning(f"Invalid status_category: {status_category}. Ignoring this filter.")
            
            jql_query = " AND ".join(jql_parts) + " ORDER BY updated DESC"
            log.debug(f"Constructed JQL query: {jql_query}")

        except Exception as e:
            log.error(f"Error constructing JQL for user {effective_user_email}: {e}", exc_info=True)
            raise RuntimeError(f"Could not construct JQL to find issues for user {effective_user_email}: {e}")

        try:
            fields_to_retrieve = "summary,status,project,issuetype,assignee,reporter,updated,priority,duedate,labels"
            
            # Run the blocking Jira API call in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, 
                self._search_issues_sync,
                app_state,  # Pass app_state to helper method
                jql_query,
                max_results,
                fields_to_retrieve
            )
            
            log.info(f"Found {len(results)} issues for user {effective_user_email} with JQL: {jql_query}")
            return results

        except JIRAError as e:
            rate_limit_headers = {}
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'headers'):
                headers = e.response.headers
                rate_limit_headers['X-RateLimit-Limit'] = headers.get('X-RateLimit-Limit')
                rate_limit_headers['X-RateLimit-Remaining'] = headers.get('X-RateLimit-Remaining')
                rate_limit_headers['X-RateLimit-Reset'] = headers.get('X-RateLimit-Reset')
                rate_limit_headers['Retry-After'] = headers.get('Retry-After')
                rate_limit_headers = {k: v for k, v in rate_limit_headers.items() if v is not None}
                if rate_limit_headers:
                    log.warning(f"Jira API error in get_issues_by_user for '{effective_user_email}' (status: {e.status_code}). Rate limit headers: {rate_limit_headers}")
            
            error_text = getattr(e, 'text', str(e))
            if "user" in error_text.lower() and ("does not exist" in error_text.lower() or "not found" in error_text.lower()):
                 log.warning(f"Jira user with email '{effective_user_email}' might not exist or is not searchable by email directly in JQL for this Jira instance. JQL: {jql_query}")
                 raise RuntimeError(f"The Jira user '{effective_user_email}' was not found or could not be searched. Please check the email address.")
            elif "jql" in error_text.lower():
                 log.error(f"Jira API JQL error ({e.status_code}) searching issues for user {effective_user_email} with JQL '{jql_query}': {error_text}", exc_info=True)
                 raise RuntimeError(f"Jira JQL query failed (Status: {e.status_code}): {error_text}. Query was: {jql_query}")
            else:
                 log.error(f"Jira API error ({e.status_code}) searching issues for user {effective_user_email}: {error_text}", exc_info=True)
                 raise RuntimeError(f"Jira API error ({e.status_code}) searching issues: {error_text}")
        except Exception as e:
            log.error(f"Unexpected error searching issues for user {effective_user_email}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error searching issues: {e}")

    @tool(name="jira_get_issues_by_project",
          description="Lists issues within a specific Jira project using its project key (e.g., 'PROJ', 'DEV'). Optionally filters by status category. Returns summaries.",
          parameters_schema={
              "type": "object",
              "properties": {
                  "project_key": {
                      "type": "string",
                      "description": "The Jira project key (e.g., 'PROJ', 'DEV'). This is required."
                  },
                  "status_category": {
                      "type": "string",
                      "description": "Filter issues by status category. Leave empty or use 'all' to search all statuses.",
                      "enum": ["to do", "in progress", "done", "all"],
                      "default": "all"
                  },
                  "max_results": {
                      "type": "integer",
                      "description": "Maximum number of issues to return.",
                      "default": 15
                  }
              },
              "required": ["project_key"]
          }
    )
    @requires_permission(Permission.JIRA_SEARCH_ISSUES, fallback_permission=Permission.JIRA_READ_ISSUES)
    async def get_issues_by_project(self, app_state: AppState, project_key: str, status_category: Optional[Literal["to do", "in progress", "done", "all"]] = "all", max_results: int = 15) -> List[Dict[str, Any]]:
        """
        Lists issues within a specific Jira project by its key, optionally filtered by status category.

        Args:
            app_state: Application state containing user profile (injected by tool framework)
            project_key: The Jira project key (e.g., 'PROJ', 'DEV').
            status_category: Optional. Filter by status category: 'to do', 'in progress', 'done', 'all'. Defaults to 'all'.
            max_results: Optional. Maximum number of issues to return. Defaults to 15.

        Returns:
            A list of dictionaries, where each dictionary is a summary of an issue.
        """
        if not project_key or not project_key.strip():
            raise ValueError("Project key cannot be empty.")

        log.info(f"Searching for Jira issues in project: {project_key}, status_category: {status_category}, max_results: {max_results}")

        try:
            jql_parts = [f'project = "{project_key.strip().upper()}"' ] # Project keys are often uppercase
            if status_category and status_category.lower() != "all":
                status_map = {
                    "to do": "To Do",
                    "in progress": "In Progress",
                    "done": "Done"
                }
                jql_status_category = status_map.get(status_category.lower())
                if jql_status_category:
                    jql_parts.append(f'statusCategory = "{jql_status_category}"')
                else:
                    log.warning(f"Invalid status_category: {status_category}. Ignoring this filter for project search.")
            
            jql_query = " AND ".join(jql_parts) + " ORDER BY updated DESC"
            log.debug(f"Constructed JQL query for project search: {jql_query}")

        except Exception as e:
            log.error(f"Error constructing JQL for project {project_key}: {e}", exc_info=True)
            raise RuntimeError(f"Could not construct JQL to find issues for project {project_key}: {e}")

        try:
            fields_to_retrieve = "summary,status,project,issuetype,assignee,reporter,updated,priority,duedate,labels"
            
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, 
                self._search_issues_sync,
                app_state,
                jql_query,
                max_results,
                fields_to_retrieve
            )
            
            log.info(f"Found {len(results)} issues for project {project_key} with JQL: {jql_query}")
            return results

        except JIRAError as e:
            rate_limit_headers = {}
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'headers'):
                headers = e.response.headers
                rate_limit_headers['X-RateLimit-Limit'] = headers.get('X-RateLimit-Limit')
                rate_limit_headers['X-RateLimit-Remaining'] = headers.get('X-RateLimit-Remaining')
                rate_limit_headers['X-RateLimit-Reset'] = headers.get('X-RateLimit-Reset')
                rate_limit_headers['Retry-After'] = headers.get('Retry-After')
                rate_limit_headers = {k: v for k, v in rate_limit_headers.items() if v is not None}
                if rate_limit_headers:
                    log.warning(f"Jira API error in get_issues_by_project for '{project_key}' (status: {e.status_code}). Rate limit headers: {rate_limit_headers}")
            
            error_text = getattr(e, 'text', str(e))
            if e.status_code == 400 and "project" in error_text.lower() and ("does not exist" in error_text.lower() or "not found" in error_text.lower()):
                 log.warning(f"Jira project with key '{project_key}' might not exist. JQL: {jql_query}")
                 raise RuntimeError(f"The Jira project '{project_key}' was not found. Please check the project key.")
            elif "jql" in error_text.lower():
                 log.error(f"Jira API JQL error ({e.status_code}) searching issues for project {project_key} with JQL '{jql_query}': {error_text}", exc_info=True)
                 raise RuntimeError(f"Jira JQL query failed (Status: {e.status_code}): {error_text}. Query was: {jql_query}")
            else:
                 log.error(f"Jira API error ({e.status_code}) searching issues for project {project_key}: {error_text}", exc_info=True)
                 raise RuntimeError(f"Jira API error ({e.status_code}) searching issues: {error_text}")
        except Exception as e:
            log.error(f"Unexpected error searching issues for project {project_key}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error searching issues for project {project_key}: {e}")

    def health_check(self, app_state: Optional[AppState] = None) -> Dict[str, Any]:
        """
        Performs a health check on the Jira API connection and authentication.
        Tries to fetch basic server information.
        Now supports testing personal credentials if provided.

        Args:
            app_state: Optional application state for personal credential testing

        Returns:
            A dictionary with 'status' ('OK', 'ERROR', 'NOT_CONFIGURED') and 'message'.
        """
        # If app_state is provided, try personal credentials first
        jira_client_to_test = None
        credential_type = "shared"
        
        if app_state:
            personal_creds = self._get_personal_credentials(app_state)
            if personal_creds:
                email, token = personal_creds
                personal_client = self._create_personal_client(email, token)
                if personal_client:
                    jira_client_to_test = personal_client
                    credential_type = "personal"
                    log.debug("Health check using personal Jira credentials")
        
        # Fall back to shared credentials if no personal ones or they failed
        if not jira_client_to_test:
            if not all([self.jira_url, self.jira_email, self.jira_token]):
                return {"status": "NOT_CONFIGURED", "message": "Jira API URL, Email, or Token not configured."}

            if not self.jira_client:
                log.info(f"(Health Check) Attempting to connect to Jira at {self.jira_url}")
                self.jira_client = self._create_jira_client(self.jira_email, self.jira_token)
                
                if not self.jira_client:
                    return {"status": "ERROR", "message": "Jira client initialization failed during health check"}
            
            jira_client_to_test = self.jira_client
            credential_type = "shared"

        try:
            start_time = time.time()
            server_info = jira_client_to_test.server_info() # type: ignore[optional-member-access]
            latency_ms = int((time.time() - start_time) * 1000)
            
            credential_info = f" (using {credential_type} credentials)"
            rate_limit_info = "Rate limit status not actively checked by this health_check."

            log.info(f"Jira health check successful{credential_info}. Server: {server_info.get('baseUrl', self.jira_url)}, Version: {server_info.get('version', 'N/A')}. Latency: {latency_ms}ms.")
            return {
                "status": "OK", 
                "message": f"Successfully connected to Jira: {server_info.get('serverTitle', 'N/A')} ({server_info.get('baseUrl', self.jira_url)}). Version: {server_info.get('version', 'N/A')}. Latency: {latency_ms}ms{credential_info}. {rate_limit_info}"
            }
        except LibraryJIRAError as e:
            error_message = f"Jira API error during health check{' ('+credential_type+' credentials)' if credential_type else ''}: Status={e.status_code}, Text={e.text}"
            if e.status_code == 401:
                error_message = f"Jira authentication failed (401){' with '+credential_type+' credentials' if credential_type else ''}. Check API token and email."
            elif e.status_code == 403:
                 error_message = f"Jira access forbidden (403){' with '+credential_type+' credentials' if credential_type else ''}. Check user permissions for the API."
            log.error(error_message, exc_info=False)
            return {"status": "ERROR", "message": error_message}
        except RequestException as e:
            log.error(f"Jira health check failed{' ('+credential_type+' credentials)' if credential_type else ''}: Network error - {e}", exc_info=True)
            return {"status": "ERROR", "message": f"Jira connection error: {str(e)}"}
        except Exception as e:
            log.error(f"Jira health check failed{' ('+credential_type+' credentials)' if credential_type else ''}: Unexpected error - {e}", exc_info=True)
            return {"status": "ERROR", "message": f"Unexpected error during Jira health check: {str(e)}"}

    def _create_issue_sync(self, app_state: AppState, issue_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous helper method to create Jira issues."""
        jira_client = self._check_jira_client(app_state)
        
        try:
            new_issue = jira_client.create_issue(fields=issue_dict)
            
            # Return comprehensive issue info
            return {
                "key": new_issue.key,
                "id": new_issue.id,
                "url": new_issue.permalink(),
                "summary": issue_dict.get("summary", ""),
                "project_key": issue_dict.get("project", {}).get("key", ""),
                "issue_type": issue_dict.get("issuetype", {}).get("name", ""),
                "status": "To Do",  # Default status for new issues
                "created": True
            }
        except Exception as e:
            log.error(f"Failed to create Jira issue: {e}")
            raise

    @tool(name="jira_create_story",
          description="Creates a new Jira story/issue with intelligent defaults and template support. Can extract details from natural language descriptions.",
          parameters_schema={
              "type": "object",
              "properties": {
                  "summary": {
                      "type": "string",
                      "description": "The story title/summary. Should be concise and descriptive."
                  },
                  "description": {
                      "type": "string", 
                      "description": "Detailed description of the story. Can include acceptance criteria, background, etc."
                  },
                  "project_key": {
                      "type": "string",
                      "description": "The Jira project key (e.g., 'PROJ', 'DEV'). If not provided, uses default from config."
                  },
                  "issue_type": {
                      "type": "string",
                      "description": "Type of issue to create.",
                      "enum": ["Story", "Task", "Bug", "Epic"],
                      "default": "Story"
                  },
                  "priority": {
                      "type": "string",
                      "description": "Priority level for the story.",
                      "enum": ["Highest", "High", "Medium", "Low", "Lowest"],
                      "default": "Medium"
                  },
                  "assignee_email": {
                      "type": "string",
                      "description": "Email of the person to assign this story to. Leave empty for unassigned."
                  },
                  "labels": {
                      "type": "array",
                      "items": {"type": "string"},
                      "description": "Labels/tags to apply to the story (e.g., ['frontend', 'api', 'urgent'])"
                  },
                  "story_points": {
                      "type": "integer",
                      "description": "Story points estimation (typically 1, 2, 3, 5, 8, 13, 21)",
                      "minimum": 1,
                      "maximum": 100
                  },
                  "template": {
                      "type": "string", 
                      "description": "Use a predefined template for the story.",
                      "enum": ["user_story", "bug_fix", "tech_debt", "research", "custom"],
                      "default": "custom"
                  }
              },
              "required": ["summary"]
          }
    )
    @requires_permission(Permission.JIRA_CREATE_ISSUE, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def create_story(
        self, 
        app_state: AppState, 
        summary: str,
        description: Optional[str] = None,
        project_key: Optional[str] = None,
        issue_type: str = "Story",
        priority: str = "Medium", 
        assignee_email: Optional[str] = None,
        labels: Optional[List[str]] = None,
        story_points: Optional[int] = None,
        template: str = "custom"
    ) -> Dict[str, Any]:
        """
        Creates a new Jira story with intelligent defaults and template support.
        
        Args:
            app_state: Application state containing user profile
            summary: The story title/summary
            description: Detailed description of the story
            project_key: Jira project key (uses default if not provided)
            issue_type: Type of issue (Story, Task, Bug, Epic)
            priority: Priority level
            assignee_email: Email of assignee (optional)
            labels: List of labels to apply
            story_points: Story points estimation
            template: Template to use for story structure
            
        Returns:
            Dictionary with created story details including key, URL, etc.
        """
        log.info(f"Creating Jira {issue_type}: '{summary}' with template '{template}'")
        
        # Use default project if not provided
        effective_project_key = project_key or self.config.get_env_value('JIRA_DEFAULT_PROJECT_KEY')
        if not effective_project_key:
            raise ValueError("No project key provided and no default project configured. Please specify project_key.")
        
        # Apply template-based enhancements
        enhanced_description = self._apply_story_template(template, summary, description or "")
        
        # Build the issue dictionary
        issue_dict = {
            "project": {"key": effective_project_key},
            "summary": summary,
            "description": enhanced_description,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority}
        }
        
        # Add optional fields
        if assignee_email:
            # Try to find user by email
            try:
                jira_client = self._check_jira_client(app_state)
                # Search for user by email
                users = jira_client.search_assignable_users_for_projects(assignee_email, [effective_project_key])
                if users:
                    issue_dict["assignee"] = {"accountId": users[0].accountId}
                    log.info(f"Assigned story to user: {assignee_email}")
                else:
                    log.warning(f"Could not find Jira user with email: {assignee_email}")
            except Exception as e:
                log.warning(f"Failed to set assignee {assignee_email}: {e}")
        
        if labels:
            issue_dict["labels"] = labels
            
        # Add story points if supported (custom field varies by Jira instance)
        if story_points:
            # Common story points field names
            story_point_fields = ["customfield_10016", "customfield_10004", "customfield_10002"]
            for field in story_point_fields:
                try:
                    jira_client = self._check_jira_client(app_state)
                    # Try to get field info to see if it exists
                    fields = jira_client.fields()
                    field_exists = any(f["id"] == field for f in fields)
                    if field_exists:
                        issue_dict[field] = story_points
                        log.info(f"Added story points ({story_points}) using field {field}")
                        break
                except Exception as e:
                    log.debug(f"Could not set story points field {field}: {e}")
                    continue
        
        try:
            # Create the issue
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._create_issue_sync,
                app_state,
                issue_dict
            )
            
            log.info(f"Successfully created {issue_type} {result['key']}: {summary}")
            
            # Enhance result with additional context
            result.update({
                "template_used": template,
                "project_key": effective_project_key,
                "priority": priority,
                "labels": labels or [],
                "story_points": story_points,
                "assignee_email": assignee_email
            })
            
            return result
            
        except JIRAError as e:
            error_text = getattr(e, 'text', str(e))
            log.error(f"Jira API error creating {issue_type}: Status={e.status_code}, Text={error_text}")
            raise RuntimeError(f"Failed to create {issue_type}: {error_text}")
        except Exception as e:
            log.error(f"Unexpected error creating {issue_type}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error creating {issue_type}: {e}")

    def _apply_story_template(self, template: str, summary: str, description: str) -> str:
        """Apply predefined templates to enhance story descriptions."""
        
        if template == "user_story":
            # User story template with acceptance criteria
            base_template = f"""
**User Story:**
{description if description else "As a user, I want to [action] so that [benefit]."}

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2 
- [ ] Criterion 3

**Definition of Done:**
- [ ] Code is written and tested
- [ ] Code review completed
- [ ] Documentation updated
- [ ] Deployed to staging environment
"""

        elif template == "bug_fix":
            # Bug fix template
            base_template = f"""
**Bug Description:**
{description if description else "Describe the bug and its impact."}

**Steps to Reproduce:**
1. Step 1
2. Step 2
3. Step 3

**Expected Behavior:**
What should happen instead.

**Actual Behavior:**
What actually happens.

**Environment:**
- Browser/Device:
- Version:
- Additional context:

**Fix Verification:**
- [ ] Bug is reproduced
- [ ] Fix is implemented
- [ ] Fix is tested
- [ ] No regression introduced
"""

        elif template == "tech_debt":
            # Technical debt template
            base_template = f"""
**Technical Debt Description:**
{description if description else "Describe the technical issue and why it needs to be addressed."}

**Current Impact:**
- Performance impact
- Maintainability issues
- Security concerns

**Proposed Solution:**
Describe the approach to resolve this technical debt.

**Benefits:**
- Improved performance
- Better code maintainability
- Reduced future development time

**Acceptance Criteria:**
- [ ] Technical issue resolved
- [ ] Code quality improved
- [ ] No functionality broken
- [ ] Documentation updated
"""

        elif template == "research":
            # Research/spike template
            base_template = f"""
**Research Objective:**
{description if description else "What needs to be investigated or researched."}

**Questions to Answer:**
- Question 1
- Question 2
- Question 3

**Research Tasks:**
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

**Success Criteria:**
- [ ] Research questions answered
- [ ] Findings documented
- [ ] Recommendations provided
- [ ] Next steps identified

**Time Box:**
[Specify time limit for research]
"""

        else:  # custom or any other template
            # Simple custom template
            base_template = f"""
**Description:**
{description if description else summary}

**Tasks:**
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2
"""

        return base_template.strip()
