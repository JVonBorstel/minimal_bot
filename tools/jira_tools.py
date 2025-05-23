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

log = logging.getLogger("tools.jira")
logging.getLogger('jira').setLevel(logging.INFO)

class JiraTools:
    """
    Provides tools for interacting with the Jira API using the python-jira library.
    This version is stripped down to essential functionality: getting issues by user and health check.
    Requires JIRA_API_URL, JIRA_API_EMAIL, and JIRA_API_TOKEN configuration.
    """
    jira_client: Optional[JIRA] = None

    def __init__(self, config: Config):
        """Initializes the Jira client."""
        self.config = config
        self.jira_url = self.config.get_env_value('JIRA_API_URL')
        self.jira_email = self.config.get_env_value('JIRA_API_EMAIL')
        self.jira_token = self.config.get_env_value('JIRA_API_TOKEN')

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

    def _check_jira_client(self):
        """Checks if the Jira client is initialized, raising ValueError if not."""
        if not self.jira_client:
            log.error("Jira client not initialized. Configuration might be missing or incorrect.")
            raise ValueError("Jira client not initialized. Please check Jira API configuration (URL, Email, Token).")

    def _search_issues_sync(self, jql_query: str, max_results: int, fields_to_retrieve: str) -> List[Dict[str, Any]]:
        """Synchronous helper method to search Jira issues."""
        self._check_jira_client()
        
        if self.jira_client is None:
            raise ValueError("Jira client is not initialized.")

        issues_found = self.jira_client.search_issues(
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
    async def get_issues_by_user(self, user_email: str, status_category: Optional[Literal["to do", "in progress", "done"]] = "to do", max_results: int = 15) -> List[Dict[str, Any]]:
        """
        Finds issues assigned to a user by their email address, optionally filtered by status category.
        This is a simplified version focusing on user-centric issue retrieval.

        Args:
            user_email: The email address of the user.
            status_category: Optional. Filter by status category: 'to do', 'in progress', 'done'. Defaults to 'to do'.
            max_results: Optional. Maximum number of issues to return. Defaults to 15.

        Returns:
            A list of dictionaries, where each dictionary is a summary of an issue
            (key, summary, status, URL, project, type).
        """
        if not user_email:
            raise ValueError("User email cannot be empty.")

        log.info(f"Searching for Jira issues assigned to user: {user_email}, status_category: {status_category}, max_results: {max_results}")

        try:
            jql_parts = [f"assignee = \"{user_email}\" OR assignee = currentUser() AND reporter = \"{user_email}\""]
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

    def health_check(self) -> Dict[str, Any]:
        """
        Performs a health check on the Jira API connection and authentication.
        Tries to fetch basic server information.

        Returns:
            A dictionary with 'status' ('OK', 'ERROR', 'NOT_CONFIGURED') and 'message'.
        """
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

        try:
            start_time = time.time()
            server_info = self.jira_client.server_info() # type: ignore[optional-member-access]
            latency_ms = int((time.time() - start_time) * 1000)
            
            rate_limit_info = "Rate limit status not actively checked by this health_check."

            log.info(f"Jira health check successful. Server: {server_info.get('baseUrl', self.jira_url)}, Version: {server_info.get('version', 'N/A')}. Latency: {latency_ms}ms.")
            return {
                "status": "OK", 
                "message": f"Successfully connected to Jira: {server_info.get('serverTitle', 'N/A')} ({server_info.get('baseUrl', self.jira_url)}). Version: {server_info.get('version', 'N/A')}. Latency: {latency_ms}ms. {rate_limit_info}"
            }
        except LibraryJIRAError as e:
            error_message = f"Jira API error during health check: Status={e.status_code}, Text={e.text}"
            if e.status_code == 401:
                error_message = "Jira authentication failed (401). Check API token and email."
            elif e.status_code == 403:
                 error_message = "Jira access forbidden (403). Check user permissions for the API."
            log.error(error_message, exc_info=False)
            return {"status": "ERROR", "message": error_message}
        except RequestException as e:
            log.error(f"Jira health check failed: Network error - {e}", exc_info=True)
            return {"status": "ERROR", "message": f"Jira connection error: {str(e)}"}
        except Exception as e:
            log.error(f"Jira health check failed: Unexpected error - {e}", exc_info=True)
            return {"status": "ERROR", "message": f"Unexpected error during Jira health check: {str(e)}"}
