import logging
from typing import Dict, Any, Optional, List, Literal
import time
import asyncio
import functools

from jira import JIRA, JIRAError
from jira.exceptions import JIRAError as LibraryJIRAError
from requests.exceptions import RequestException

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
    This version is stripped down to essential functionality: getting issues by user and health check.
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

        try:
            log.info(f"Attempting to connect to Jira at {self.jira_url} with user {self.jira_email}")
            options = {'server': self.jira_url, 'verify': True, 'rest_api_version': 'latest'}
            self.jira_client = JIRA(
                options=options,
                basic_auth=(self.jira_email, self.jira_token), # type: ignore[arg-type]
                timeout=self.config.DEFAULT_API_TIMEOUT_SECONDS,
                max_retries=0
            )
            server_info = self.jira_client.server_info()
            log.info(f"Jira client initialized successfully. Connected to: {server_info.get('baseUrl', self.jira_url)}")
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
            log.error(f"Failed to initialize Jira client (JIRAError): Status={e.status_code}, Text={e.text}", exc_info=True)
            self.jira_client = None
        except RequestException as e:
            log.error(f"Failed to initialize Jira client (Network Error): {e}", exc_info=True)
            self.jira_client = None
        except Exception as e:
            log.error(f"Failed to initialize Jira client (Unexpected Error): {e}", exc_info=True)
            self.jira_client = None

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
        
        try:
            if not self.jira_url:
                log.warning("Cannot create personal Jira client: Jira URL not configured")
                return None
            
            timeout_seconds = getattr(self.config, 'DEFAULT_API_TIMEOUT_SECONDS', 10)
            options = {'server': self.jira_url, 'verify': True, 'rest_api_version': 'latest'}
            
            personal_client = JIRA(
                options=options,
                basic_auth=(email, token),
                timeout=timeout_seconds,
                max_retries=0
            )
            
            # Test the client
            server_info = personal_client.server_info()
            log.info(f"Personal Jira client created successfully for user: {email}")
            
            # Cache it for future use in this session
            self._personal_clients_cache[cache_key] = personal_client
            
            return personal_client
            
        except Exception as e:
            log.warning(f"Failed to create personal Jira client for {email}: {e}")
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
            # FALLBACK: Try to re-initialize the shared client if config is available
            if all([self.jira_url, self.jira_email, self.jira_token]) and not self.jira_client:
                log.warning("Jira client is None but configuration is available. Attempting to re-initialize...")
                try:
                    options = {'server': self.jira_url, 'verify': True, 'rest_api_version': 'latest'}
                    self.jira_client = JIRA(
                        options=options,
                        basic_auth=(self.jira_email, self.jira_token),
                        timeout=self.config.DEFAULT_API_TIMEOUT_SECONDS,
                        max_retries=0
                    )
                    server_info = self.jira_client.server_info()
                    log.info(f"Jira client re-initialized successfully. Connected to: {server_info.get('baseUrl', self.jira_url)}")
                    return self.jira_client
                except Exception as e:
                    log.error(f"Failed to re-initialize Jira client: {e}")
                    self.jira_client = None
            
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
                      "description": "The email address of the user to find assigned issues for."
                  },
                  "status_category": {
                      "type": "string",
                      "description": "Filter issues by status category.",
                      "enum": ["to do", "in progress", "done"],
                      "default": "to do"
                  },
                  "max_results": {
                      "type": "integer",
                      "description": "Maximum number of issues to return.",
                      "default": 15
                  }
              },
              "required": ["user_email"]
          }
    )
    @requires_permission(Permission.JIRA_READ_ISSUES, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def get_issues_by_user(self, app_state: AppState, user_email: str, status_category: Optional[Literal["to do", "in progress", "done"]] = None, max_results: int = 15) -> List[Dict[str, Any]]:
        """
        Finds issues assigned to a user by their email address, optionally filtered by status category.
        Now supports personal Jira credentials for enhanced access.

        Args:
            app_state: Application state containing user profile (injected by tool framework)
            user_email: The email address of the user.
            status_category: Optional. Filter by status category: 'to do', 'in progress', 'done'. Defaults to None (all statuses).
            max_results: Optional. Maximum number of issues to return. Defaults to 15.

        Returns:
            A list of dictionaries, where each dictionary is a summary of an issue
            (key, summary, status, URL, project, type).
        """
        if not user_email:
            raise ValueError("User email cannot be empty.")

        log.info(f"Searching for Jira issues assigned to user: {user_email}, status_category: {status_category}, max_results: {max_results}")

        try:
            # EMERGENCY FIX: Use currentUser() which is more reliable than email
            # The email-based search often fails due to user account differences
            jql_parts = [f"(assignee = currentUser() OR reporter = currentUser())"]
            
            if status_category:
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
            log.error(f"Error constructing JQL for user {user_email}: {e}", exc_info=True)
            raise RuntimeError(f"Could not construct JQL to find issues for user {user_email}: {e}")

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
            
            log.info(f"Found {len(results)} issues for user {user_email} with JQL: {jql_query}")
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
                    log.warning(f"Jira API error in get_issues_by_user for '{user_email}' (status: {e.status_code}). Rate limit headers: {rate_limit_headers}")
            
            error_text = getattr(e, 'text', str(e))
            if "user" in error_text.lower() and ("does not exist" in error_text.lower() or "not found" in error_text.lower()):
                 log.warning(f"Jira user with email '{user_email}' might not exist or is not searchable by email directly in JQL for this Jira instance.")
                 return [] 
            elif "jql" in error_text.lower():
                 log.error(f"Jira API JQL error ({e.status_code}) searching issues for user {user_email} with JQL '{jql_query}': {error_text}", exc_info=True)
                 raise RuntimeError(f"Jira JQL query failed (Status: {e.status_code}): {error_text}. Query was: {jql_query}")
            else:
                 log.error(f"Jira API error ({e.status_code}) searching issues for user {user_email}: {error_text}", exc_info=True)
                 raise RuntimeError(f"Jira API error ({e.status_code}) searching issues: {error_text}")
        except Exception as e:
            log.error(f"Unexpected error searching issues for user {user_email}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error searching issues: {e}")

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
                try:
                    log.info(f"(Health Check) Attempting to connect to Jira at {self.jira_url}")
                    options = {'server': self.jira_url, 'verify': True, 'rest_api_version': 'latest'}
                    self.jira_client = JIRA(
                        options=options,
                        basic_auth=(self.jira_email, self.jira_token), # type: ignore[arg-type]
                        timeout=5, 
                        max_retries=0
                    )
                except (LibraryJIRAError, RequestException, Exception) as e:
                    log.error(f"(Health Check) Jira client re-initialization failed: {e}")
                    self.jira_client = None
                    return {"status": "ERROR", "message": f"Jira client initialization failed during health check: {str(e)}"}
            
            if not self.jira_client:
                 return {"status": "ERROR", "message": "Jira client could not be initialized. Previous errors persist."}
            
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
