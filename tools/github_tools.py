# --- FILE: tools/github_tools.py ---
import logging
from typing import Dict, Any, List, Optional, Union, Literal
import datetime
import asyncio

from github import Github, GithubException, UnknownObjectException, RateLimitExceededException, Auth
from github.Repository import Repository
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.PullRequest import PullRequest
from github.PullRequestReview import PullRequestReview
from requests.exceptions import RequestException

from config import Config
from . import tool
from user_auth.tool_access import requires_permission
from user_auth.permissions import Permission
from state_models import AppState

# Import get_logger from logging_config
from utils.logging_config import get_logger

log = get_logger("tools.github") # Use get_logger

MAX_LIST_RESULTS = 25
MAX_SEARCH_RESULTS = 15

class GitHubTools:
    """
    Provides tools for interacting with the GitHub API using PyGithub.
    This version is stripped down to list repositories and search code.
    Supports multiple GitHub accounts, GitHub Enterprise, and personal user credentials.
    """
    github_client: Optional[Github] = None
    authenticated_user_login: Optional[str] = None
    active_account_name: Optional[str] = None
    github_clients: Dict[str, Github] = {}
    # Cache for temporary personal clients to avoid recreating them
    _personal_clients_cache: Dict[str, Github] = {}

    def __init__(self, config: Config, app_state: Optional[AppState] = None, testing_mode: bool = False):
        log.info("Initializing GitHub Tools")
        self.config = config
        self.app_state = app_state
        self.github_client = None
        self.authenticated_user_login = None
        self.active_account_name = None
        self.github_clients = {}
        self._personal_clients_cache = {}

        if not hasattr(self.config.settings, 'github_accounts') or not self.config.settings.github_accounts:
            log.warning("No GitHub accounts configured in settings. Add accounts in config.")
            return

        for account in self.config.settings.github_accounts:
            success = self._init_single_client(
                token=account.token,
                base_url=str(account.base_url) if account.base_url else None,
                account_name=account.name,
                testing_mode=testing_mode
            )
            if success and (self.active_account_name is None or
                            (hasattr(self.config.settings, 'github_default_account_name') and
                             account.name == self.config.settings.github_default_account_name)):
                if testing_mode:
                     self.github_client = self.github_clients[account.name]
                     self.active_account_name = account.name
                     self.authenticated_user_login = "test_user"
                else:
                    self._set_active_account(account.name, testing_mode=False)

        if hasattr(self.config.settings, 'github_accounts') and self.config.settings.github_accounts and not self.github_clients:
             log.error("No working GitHub clients could be initialized from configuration. Check tokens and network access.")
        elif not self.github_clients:
             log.info("No GitHub clients initialized (no accounts configured or testing mode active without config).")

    def _get_personal_credentials(self, app_state: AppState) -> Optional[str]:
        """
        Extract personal GitHub token from user profile if available.
        
        Args:
            app_state: Application state containing current user profile
            
        Returns:
            Personal GitHub token if found, None otherwise
        """
        if not app_state or not hasattr(app_state, 'current_user') or not app_state.current_user:
            return None
        
        user_profile = app_state.current_user
        profile_data = getattr(user_profile, 'profile_data', None) or {}
        personal_creds = profile_data.get('personal_credentials', {})
        
        github_token = personal_creds.get('github_token')
        if github_token and github_token.strip() and github_token.lower() not in ['none', 'skip', 'n/a']:
            log.debug(f"Found personal GitHub token for user {user_profile.user_id}")
            return github_token.strip()
        
        return None

    def _create_personal_client(self, token: str) -> Optional[Github]:
        """
        Create a temporary GitHub client for personal credentials.
        
        Args:
            token: Personal GitHub token
            
        Returns:
            GitHub client instance or None if creation failed
        """
        # Check cache first
        if token in self._personal_clients_cache:
            log.debug("Using cached personal GitHub client")
            return self._personal_clients_cache[token]
        
        try:
            timeout_seconds = getattr(self.config, 'DEFAULT_API_TIMEOUT_SECONDS', 10)
            
            # Create client using the same configuration as shared clients
            # For now, assume personal tokens are for github.com (not enterprise)
            auth = Auth.Token(token)
            personal_client = Github(
                auth=auth,
                timeout=timeout_seconds,
                retry=3
            )
            
            # Test the client
            user = personal_client.get_user()
            log.info(f"Personal GitHub client created successfully for user: {user.login}")
            
            # Cache it for future use in this session
            self._personal_clients_cache[token] = personal_client
            
            return personal_client
            
        except Exception as e:
            log.warning(f"Failed to create personal GitHub client: {e}")
            return None

    def _init_single_client(self, token: str, base_url: Optional[str], account_name: str, testing_mode: bool = False) -> bool:
        """
        Initializes a single GitHub client and adds it to the github_clients dictionary.
        """
        if not token:
            log.warning(f"GitHub token for account '{account_name}' is empty or not configured.")
            return False

        enterprise_info = f" (Enterprise URL: {base_url})" if base_url else ""
        log.debug(f"Attempting to initialize GitHub client for account '{account_name}'{enterprise_info}")

        try:
            timeout_seconds = getattr(self.config, 'DEFAULT_API_TIMEOUT_SECONDS', 10)
            if base_url:
                auth = Auth.Token(token)
                github_client = Github(
                    auth=auth,
                    base_url=str(base_url),
                    timeout=timeout_seconds,
                    retry=3
                )
            else:
                auth = Auth.Token(token)
                github_client = Github(
                    auth=auth,
                    timeout=timeout_seconds,
                    retry=3
                )

            if not testing_mode:
                user = github_client.get_user()
                user_login = user.login
                log.info(f"GitHub client for account '{account_name}' initialized successfully. Authenticated as: {user_login}")
            else:
                user_login = "test_user"
                log.info(f"GitHub client for account '{account_name}' initialized successfully in testing mode.")

            self.github_clients[account_name] = github_client
            return True

        except RateLimitExceededException as e:
            reset_time_unix = e.headers.get('X-RateLimit-Reset') if e.headers else None
            reset_time_str = "unknown"
            if reset_time_unix:
                try:
                    reset_time_str = datetime.datetime.fromtimestamp(int(reset_time_unix)).isoformat()
                except ValueError:
                    pass
            log.error(f"GitHub Rate Limit Exceeded during initialization of account '{account_name}'. Limit resets around {reset_time_str}.", exc_info=False)
            return False

        except GithubException as e:
            message = f"Failed to initialize GitHub client for account '{account_name}' (API Error Status: {e.status})."
            error_data = e.data.get('message', 'No specific error message provided.')
            if e.status == 401: 
                message += f" Authentication failed (Bad credentials). Check token validity. Details: {error_data}"
            elif e.status == 403: 
                message += f" Permission denied. Check token scopes (e.g., 'repo', 'read:org') or organization/repo permissions. Details: {error_data}"
            elif e.status == 404: 
                message += f" Resource not found (unexpected during init). Details: {error_data}"
            elif e.status == 422: 
                message += f" Validation failed. Details: {error_data}"
            else: 
                message += f" Details: {error_data}"
            log.error(message, exc_info=True)
            return False

        except RequestException as e:
            log.error(f"Failed to initialize GitHub client for account '{account_name}' (Network Error): {e}", exc_info=True)
            return False

        except Exception as e:
            log.error(f"Failed to initialize GitHub client for account '{account_name}' (Unexpected Error): {e}", exc_info=True)
            return False

    def _set_active_account(self, account_name: str, testing_mode: bool = False) -> bool:
        """
        Sets the active GitHub client to use for operations.
        """
        if account_name not in self.github_clients:
            log.error(f"GitHub account '{account_name}' not found in configured and initialized accounts.")
            return False

        self.github_client = self.github_clients[account_name]
        self.active_account_name = account_name

        try:
            if testing_mode:
                self.authenticated_user_login = "test_user"
                log.info(f"Active GitHub account set to '{account_name}' in testing mode (authenticated as: {self.authenticated_user_login})")
            else:
                user = self.github_client.get_user()
                self.authenticated_user_login = user.login
                log.info(f"Active GitHub account set to '{account_name}' (authenticated as: {self.authenticated_user_login})")

            return True
        except Exception as e:
            log.error(f"Error verifying or getting user info after setting active account '{account_name}'. Account may be invalid. Details: {e}", exc_info=True)
            self.authenticated_user_login = None
            self.github_client = None
            self.active_account_name = None
            return False

    @requires_permission(Permission.GITHUB_READ_REPO, fallback_permission=Permission.READ_ONLY_ACCESS)
    def get_account_client(self, app_state: AppState, account_name: Optional[str] = None, **kwargs) -> Optional[Github]:
        """
        Gets a GitHub client for a specific account, or the default active client.
        Now supports personal credentials from user profiles with fallback to shared credentials.
        """
        if kwargs.get('read_only_mode') is True:
            log.info(f"Executing get_account_client in read-only mode (account: {account_name or 'default active'}).")

        # First, try to get personal credentials from user profile
        personal_token = self._get_personal_credentials(app_state)
        if personal_token:
            log.debug("Attempting to use personal GitHub credentials")
            personal_client = self._create_personal_client(personal_token)
            if personal_client:
                log.info("Using personal GitHub client for authenticated user")
                return personal_client
            else:
                log.warning("Personal GitHub credentials failed, falling back to shared credentials")

        # Fall back to shared credentials
        if account_name:
            if account_name in self.github_clients:
                log.debug(f"Using shared GitHub client for account: {account_name}")
                return self.github_clients[account_name]
            else:
                log.warning(f"Requested GitHub account '{account_name}' not found or not initialized. Using active account if available.")
                return self.github_client
        
        log.debug(f"Using default active GitHub client: {self.active_account_name or 'none'}")
        return self.github_client

    async def _get_repo(self, app_state: AppState, owner: str, repo: str, account_name: Optional[str] = None, **kwargs) -> Repository:
        """
        Helper to get the repository object, raising appropriate errors.
        """
        if not owner or not repo:
             raise ValueError("Repository owner and name must be provided.")

        client = self.get_account_client(app_state, account_name, **kwargs)
        if not client:
            raise RuntimeError("GitHub client not initialized. Ensure configuration is correct.")

        current_owner = owner
        parsed_default_owner = None
        default_repo_config = getattr(self.config.settings, 'github_default_repo', None)
        if default_repo_config and isinstance(default_repo_config, str) and '/' in default_repo_config:
            parsed_default_owner = default_repo_config.split('/')[0]
        
        if parsed_default_owner and owner == repo and owner != parsed_default_owner:
            log.warning(f"Owner parameter ('{owner}') matches repo name ('{repo}') and differs from parsed default owner ('{parsed_default_owner}') from GITHUB_DEFAULT_REPO. Overriding owner with '{parsed_default_owner}'.")
            current_owner = parsed_default_owner
        elif parsed_default_owner and owner.lower() in ['my', 'personal', self.config.settings.github_default_account_name.lower() if hasattr(self.config.settings, 'github_default_account_name') else '']:
            log.warning(f"Owner parameter ('{owner}') seems generic or matches default account name. Overriding with parsed default owner '{parsed_default_owner}' from GITHUB_DEFAULT_REPO.")
            current_owner = parsed_default_owner

        repo_full_name = f"{current_owner}/{repo}"
        log.debug(f"Fetching repository object for '{repo_full_name}' using account '{self.active_account_name or 'default'}' (Original owner param: '{owner}', Resolved owner: '{current_owner}')")

        try:
            return await asyncio.to_thread(client.get_repo, repo_full_name)
        except UnknownObjectException:
            raise RuntimeError(f"GitHub repository '{repo_full_name}' not found (404). Check owner and repository name.") from None
        except RateLimitExceededException as e:
            reset_time_unix = e.headers.get('X-RateLimit-Reset') if e.headers else None
            reset_time_str = "unknown"
            if reset_time_unix:
                try:
                    reset_time_str = datetime.datetime.fromtimestamp(int(reset_time_unix)).isoformat()
                except ValueError: pass
            log.error(f"GitHub Rate Limit Exceeded accessing repo '{repo_full_name}'. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded accessing repo '{repo_full_name}'. Limit resets around {reset_time_str}. Please wait.") from e
        except GithubException as e:
             error_details = e.data.get('message', 'No specific error message.')
             message = f"GitHub API error ({e.status}) accessing repo '{repo_full_name}': {error_details}"
             if e.status == 403: message += " (Check token scopes for repo access?)"
             log.error(message, exc_info=True)
             raise RuntimeError(message) from e
        except RequestException as e:
             log.error(f"Network error accessing repo '{repo_full_name}': {e}", exc_info=True)
             raise RuntimeError(f"Network error accessing repo '{repo_full_name}': {e}") from e
        except Exception as e:
             log.error(f"Unexpected error accessing repo '{repo_full_name}': {e}", exc_info=True)
             raise RuntimeError(f"Unexpected error accessing repo '{repo_full_name}': {e}") from e

    @tool(
        name="github_list_repositories",
        description=f"Lists repositories accessible to the authenticated user or for a specified user/organization. Limited to {MAX_LIST_RESULTS} results.",
    )
    @requires_permission(Permission.GITHUB_READ_REPO, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def list_repositories(self, app_state: AppState, user_or_org: Optional[str] = None, repo_type: Literal["all", "owner", "public", "private", "member"] = "owner", sort: Literal["created", "updated", "pushed", "full_name"] = "pushed", direction: Literal["asc", "desc"] = "desc", **kwargs) -> List[Dict[str, Any]]:
        """
        Lists repositories for the authenticated user or a specified user/org.
        """
        if kwargs.get('read_only_mode') is True:
            log.info(f"Executing list_repositories in read-only mode for '{user_or_org or self.authenticated_user_login}'.")

        if not self.github_client: 
            raise ValueError("GitHub client not initialized. Ensure configuration is correct.")
        target_name = user_or_org or self.authenticated_user_login
        if not target_name:
            raise ValueError("Authenticated user login is not available and no user/org specified.")

        log.info(f"Listing repositories for '{target_name}' (type: {repo_type}, sort: {sort} {direction})")
        try:
            target_entity: Union[NamedUser, Organization]
            try:
                 target_entity = await asyncio.to_thread(self.github_client.get_user, target_name)
            except UnknownObjectException:
                 try:
                     target_entity = await asyncio.to_thread(self.github_client.get_organization, target_name)
                 except UnknownObjectException:
                     raise RuntimeError(f"GitHub user or organization '{target_name}' not found (404).") from None

            log.info(f"Retrieved target entity '{target_name}', getting repositories...")
            repos_paginated = await asyncio.to_thread(target_entity.get_repos, type=repo_type, sort=sort, direction=direction)

            results = []
            for i, repo in enumerate(repos_paginated):
                if i >= MAX_LIST_RESULTS:
                    log.debug(f"MAX_LIST_RESULTS ({MAX_LIST_RESULTS}) reached, stopping repository list iteration.")
                    break

                try:
                    updated_at_val = getattr(repo, 'updated_at', None)
                    repo_details = {
                        "name": getattr(repo, 'name', 'N/A'),
                        "full_name": getattr(repo, 'full_name', 'N/A'),
                        "description": getattr(repo, 'description', '') or "",
                        "url": getattr(repo, 'html_url', 'N/A'),
                        "private": getattr(repo, 'private', False),
                        "language": getattr(repo, 'language', None),
                        "stars": getattr(repo, 'stargazers_count', 0),
                        "updated_at": updated_at_val.isoformat() if updated_at_val else None,
                    }
                    results.append(repo_details)
                    log.debug(f"Added repo {i+1}: {repo_details['full_name']}")

                except Exception as repo_error:
                    repo_name_fallback = getattr(repo, 'full_name', f"Index {i+1}")
                    log.error(f"Error processing repo '{repo_name_fallback}': {repo_error}", exc_info=True)
                    results.append({
                        "name": f"Error processing repo {i+1}",
                        "full_name": repo_name_fallback,
                        "error": str(repo_error)
                    })

            log.info(f"Finished listing repositories for '{target_name}'. Found {len(results)} results (max {MAX_LIST_RESULTS}).")
            return results
        except UnknownObjectException:
            raise RuntimeError(f"GitHub user or organization '{target_name}' not found (404).") from None
        except RateLimitExceededException as e:
            reset_time_unix = e.headers.get('X-RateLimit-Reset') if e.headers else None
            reset_time_str = "unknown"
            if reset_time_unix:
                try:
                    reset_time_str = datetime.datetime.fromtimestamp(int(reset_time_unix)).isoformat()
                except ValueError: pass
            log.error(f"GitHub Rate Limit Exceeded listing repositories for '{target_name}'. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded listing repositories. Limit resets around {reset_time_str}. Please wait.") from e
        except GithubException as e:
            message = f"API error ({e.status}) listing repositories for '{target_name}': {e.data.get('message', 'Failed')}"
            if e.status == 403: message += " (Check token scopes? e.g., 'read:org' for organization repos)"
            log.error(message, exc_info=True)
            raise RuntimeError(message) from e
        except RequestException as e:
            log.error(f"Network error listing repositories for '{target_name}': {e}", exc_info=True)
            raise RuntimeError(f"Network error listing repositories: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error in list_repositories for '{target_name}': {str(e)}", exc_info=True)
            raise RuntimeError(f"Unexpected error listing repos: {e}") from e

    @tool(
        name="github_search_code",
        description=f"Finds occurrences of specific, indexable code terms (e.g., function/variable names) within files on GitHub. Can be scoped to a repository or user/organization. Ignores common/short terms. Results capped at {MAX_SEARCH_RESULTS}.",
    )
    @requires_permission(Permission.GITHUB_SEARCH_CODE, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def search_code(self, app_state: AppState, query: str, owner: Optional[str] = None, repo: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Searches code within GitHub files for specific, indexable terms. Can be scoped to a repository or user/organization.
        """
        client = self.get_account_client(app_state, **kwargs)
        if not client:
            raise ValueError("GitHub client not initialized. Ensure configuration is correct.")
        
        if not query or len(query.strip()) < 3:
             raise ValueError("Code search query must be at least 3 characters (GitHub may ignore common words).")
        if repo and not owner:
             raise ValueError("Cannot specify repository without specifying the owner.")

        qualifiers_list = []
        if owner and repo: 
            qualifiers_list.append(f"repo:{owner}/{repo}")
        elif owner: 
            qualifiers_list.append(f"user:{owner}")

        full_query_parts = qualifiers_list + [query]
        full_query = " ".join(full_query_parts).strip()

        if kwargs.get('read_only_mode') is True:
            log.info(f"Executing search_code in read-only mode with query: '{full_query}'")
        else:
            log.info(f"Searching GitHub code with query: '{full_query}'")
        
        try:
            paginated_list = await asyncio.to_thread(client.search_code, query=full_query)

            results = []
            count = 0
            for item in paginated_list:
                if count >= MAX_SEARCH_RESULTS:
                    log.debug(f"MAX_SEARCH_RESULTS ({MAX_SEARCH_RESULTS}) reached for code search, stopping iteration.")
                    break
                try:
                    repo_name_val = item.repository.full_name if hasattr(item, 'repository') and item.repository else "N/A"
                    results.append({
                        "name": item.name,
                        "path": item.path,
                        "repository": repo_name_val,
                        "url": item.html_url,
                        "git_url": item.git_url,
                    })
                    log.debug(f"Added code search result {count+1}: {item.path} in {repo_name_val}")
                    count += 1
                except Exception as result_error:
                     log.warning(f"Error processing code search result {count+1} ('{getattr(item, 'path', 'Unknown')}'): {result_error}", exc_info=True)
                     count += 1
            log.info(f"Finished code search for query '{full_query}'. Found {len(results)} results (max {MAX_SEARCH_RESULTS}).")
            return results
        except RateLimitExceededException as e:
            reset_time_unix = e.headers.get('X-RateLimit-Reset') if e.headers else None
            reset_time_str = "unknown"
            if reset_time_unix:
                try: 
                    reset_time_str = datetime.datetime.fromtimestamp(int(reset_time_unix)).isoformat()
                except ValueError: 
                    pass
            log.error(f"GitHub Search Rate Limit Exceeded during code search ('{full_query}'). Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub Search API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            message = f"API error ({e.status}) during code search: {e.data.get('message', 'Search failed.')}"
            if e.status == 403: 
                message += " (Rate limit or insufficient scopes?)"
            if e.status == 422: 
                message = f"GitHub code search validation error (422): Invalid query. Details: {e.data.get('message', 'Invalid query.')}"
            log.error(message, exc_info=True)
            raise RuntimeError(message) from e
        except RequestException as e:
             log.error(f"Network error during code search ('{full_query}'): {e}", exc_info=True)
             raise RuntimeError(f"Network error during code search: {e}") from e
        except Exception as e:
             log.error(f"An unexpected error during code search ('{full_query}'): {e}", exc_info=True)
             raise RuntimeError(f"An unexpected error during code search: {e}") from e

    def health_check(self) -> Dict[str, Any]:
        """
        Performs a health check on the GitHub API connection and authentication.
        """
        if not self.github_clients:
            return {"status": "NOT_CONFIGURED", "message": "No GitHub accounts configured."}

        if not self.github_client:
            return {"status": "ERROR", "message": "No active GitHub client available."}

        try:
            user = self.github_client.get_user()
            log.info(f"GitHub health check successful. Authenticated as: {user.login}")
            return {
                "status": "OK", 
                "message": f"Successfully connected to GitHub. Authenticated as: {user.login}"
            }
        except RateLimitExceededException as e:
            reset_time_unix = e.headers.get('X-RateLimit-Reset') if e.headers else None
            reset_time_str = "unknown"
            if reset_time_unix:
                try:
                    reset_time_str = datetime.datetime.fromtimestamp(int(reset_time_unix)).isoformat()
                except ValueError:
                    pass
            error_message = f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}."
            log.error(error_message, exc_info=False)
            return {"status": "ERROR", "message": error_message}
        except GithubException as e:
            error_message = f"GitHub API error during health check: Status={e.status}, Text={e.data.get('message', 'Unknown error')}"
            if e.status == 401:
                error_message = "GitHub authentication failed (401). Check API token."
            elif e.status == 403:
                 error_message = "GitHub access forbidden (403). Check user permissions for the API."
            log.error(error_message, exc_info=False)
            return {"status": "ERROR", "message": error_message}
        except RequestException as e:
            log.error(f"GitHub health check failed: Network error - {e}", exc_info=True)
            return {"status": "ERROR", "message": f"GitHub connection error: {str(e)}"}
        except Exception as e:
            log.error(f"GitHub health check failed: Unexpected error - {e}", exc_info=True)
            return {"status": "ERROR", "message": f"Unexpected error during GitHub health check: {str(e)}"}

    @tool(
        name="github_create_issue",
        description="Creates a new issue in a specified GitHub repository.",
    )
    @requires_permission(Permission.GITHUB_WRITE_ISSUES)
    async def create_issue(self, app_state: AppState, owner: str, repo: str, title: str, body: Optional[str] = None, labels: Optional[List[str]] = None, assignee: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Creates a new issue in the specified repository.
        """
        log.info(f"Attempting to create issue in {owner}/{repo} with title: '{title}'")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            params = {}
            if body:
                params['body'] = body
            if labels:
                params['labels'] = labels
            if assignee:
                params['assignee'] = assignee
            
            issue = await asyncio.to_thread(repository.create_issue, title=title, **params)
            log.info(f"Successfully created issue #{issue.number} in {owner}/{repo}")
            return {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "url": issue.html_url,
                "assignee": issue.assignee.login if issue.assignee else None,
                "body": issue.body
            }
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded creating issue in {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) creating issue in {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error creating issue: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error creating issue in {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error creating issue: {e}") from e

    @tool(
        name="github_get_issue_by_number",
        description="Retrieves details for a specific issue by its number from a repository.",
    )
    @requires_permission(Permission.GITHUB_READ_ISSUES, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def get_issue_by_number(self, app_state: AppState, owner: str, repo: str, issue_number: int, **kwargs) -> Dict[str, Any]:
        """
        Retrieves details for a specific issue by its number.
        """
        log.info(f"Attempting to retrieve issue #{issue_number} from {owner}/{repo}")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            issue = await asyncio.to_thread(repository.get_issue, number=issue_number)
            log.info(f"Successfully retrieved issue #{issue.number} from {owner}/{repo}")
            return {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "url": issue.html_url,
                "creator": issue.user.login,
                "assignee": issue.assignee.login if issue.assignee else None,
                "body": issue.body,
                "created_at": issue.created_at.isoformat(),
                "updated_at": issue.updated_at.isoformat(),
                "comments_count": issue.comments,
                "labels": [label.name for label in issue.labels],
            }
        except UnknownObjectException:
            log.warning(f"Issue #{issue_number} not found in {owner}/{repo}.")
            raise RuntimeError(f"Issue #{issue_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded retrieving issue #{issue_number} from {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) retrieving issue #{issue_number} from {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error retrieving issue: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error retrieving issue #{issue_number} from {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error retrieving issue: {e}") from e

    @tool(
        name="github_create_comment_on_issue",
        description="Adds a comment to an existing issue in a repository.",
    )
    @requires_permission(Permission.GITHUB_WRITE_ISSUES)
    async def create_comment_on_issue(self, app_state: AppState, owner: str, repo: str, issue_number: int, body: str, **kwargs) -> Dict[str, Any]:
        """
        Adds a comment to an existing issue.
        """
        log.info(f"Attempting to create comment on issue #{issue_number} in {owner}/{repo}")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            issue = await asyncio.to_thread(repository.get_issue, number=issue_number)
            comment = await asyncio.to_thread(issue.create_comment, body)
            log.info(f"Successfully created comment ID {comment.id} on issue #{issue_number} in {owner}/{repo}")
            return {
                "id": comment.id,
                "user": comment.user.login,
                "body": comment.body,
                "created_at": comment.created_at.isoformat(),
                "url": comment.html_url,
            }
        except UnknownObjectException:
            log.warning(f"Issue #{issue_number} not found in {owner}/{repo} when trying to create comment.")
            raise RuntimeError(f"Issue #{issue_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded creating comment on issue #{issue_number} in {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) creating comment on issue #{issue_number} in {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error creating comment: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error creating comment on issue #{issue_number} in {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error creating comment: {e}") from e

    @tool(
        name="github_get_issue_comments",
        description="Retrieves all comments for a specific issue from a repository.",
    )
    @requires_permission(Permission.GITHUB_READ_ISSUES, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def get_issue_comments(self, app_state: AppState, owner: str, repo: str, issue_number: int, **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieves all comments for a specific issue.
        """
        log.info(f"Attempting to retrieve comments for issue #{issue_number} from {owner}/{repo}")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            issue = await asyncio.to_thread(repository.get_issue, number=issue_number)
            comments_paginated = await asyncio.to_thread(issue.get_comments)
            
            results = []
            for comment in comments_paginated:
                results.append({
                    "id": comment.id,
                    "user": comment.user.login,
                    "body": comment.body,
                    "created_at": comment.created_at.isoformat(),
                    "updated_at": comment.updated_at.isoformat(),
                    "url": comment.html_url,
                })
            log.info(f"Successfully retrieved {len(results)} comments for issue #{issue_number} from {owner}/{repo}")
            return results
        except UnknownObjectException:
            log.warning(f"Issue #{issue_number} not found in {owner}/{repo} when trying to retrieve comments.")
            raise RuntimeError(f"Issue #{issue_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded retrieving comments for issue #{issue_number} from {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) retrieving comments for issue #{issue_number} from {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error retrieving comments: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error retrieving comments for issue #{issue_number} from {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error retrieving comments: {e}") from e

    @tool(
        name="github_update_issue_state",
        description="Updates the state of an issue (e.g., 'open' or 'closed').",
    )
    @requires_permission(Permission.GITHUB_WRITE_ISSUES)
    async def update_issue_state(self, app_state: AppState, owner: str, repo: str, issue_number: int, state: Literal["open", "closed"], **kwargs) -> Dict[str, Any]:
        """
        Updates the state of an existing issue.
        """
        if state not in ["open", "closed"]:
            raise ValueError("Invalid state. Must be 'open' or 'closed'.")

        log.info(f"Attempting to update state of issue #{issue_number} in {owner}/{repo} to '{state}'")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            issue = await asyncio.to_thread(repository.get_issue, number=issue_number)
            await asyncio.to_thread(issue.edit, state=state)
            # Re-fetch to confirm state change, as edit() might not return the full updated object or confirm state directly
            updated_issue = await asyncio.to_thread(repository.get_issue, number=issue_number)
            log.info(f"Successfully updated state of issue #{updated_issue.number} to '{updated_issue.state}' in {owner}/{repo}")
            return {
                "number": updated_issue.number,
                "title": updated_issue.title,
                "state": updated_issue.state,
                "url": updated_issue.html_url,
            }
        except UnknownObjectException:
            log.warning(f"Issue #{issue_number} not found in {owner}/{repo} when trying to update state.")
            raise RuntimeError(f"Issue #{issue_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded updating state for issue #{issue_number} in {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) updating state for issue #{issue_number} in {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error updating issue state: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error updating state for issue #{issue_number} in {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error updating issue state: {e}") from e

    @tool(
        name="github_create_pull_request",
        description="Creates a new pull request in a specified GitHub repository.",
    )
    @requires_permission(Permission.GITHUB_WRITE_PRS)
    async def create_pull_request(self, app_state: AppState, owner: str, repo: str, title: str, body: str, head: str, base: str, draft: bool = False, maintainer_can_modify: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Creates a new pull request.
        Args:
            app_state: The application state.
            owner: The owner of the repository.
            repo: The name of the repository.
            title: The title of the pull request.
            body: The body/description of the pull request.
            head: The name of the branch where your changes are implemented. (e.g., "feature-branch")
            base: The name of the branch you want the changes pulled into. (e.g., "main" or "develop")
            draft: Whether the pull request is a draft. Defaults to False.
            maintainer_can_modify: Whether maintainers can modify the PR. Defaults to True.
        """
        log.info(f"Attempting to create pull request in {owner}/{repo}: '{title}' from {head} to {base}")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            pr = await asyncio.to_thread(
                repository.create_pull,
                title=title,
                body=body,
                head=head,
                base=base,
                draft=draft,
                maintainer_can_modify=maintainer_can_modify
            )
            log.info(f"Successfully created pull request #{pr.number} in {owner}/{repo}")
            return {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "url": pr.html_url,
                "user": pr.user.login,
                "head_branch": pr.head.ref,
                "base_branch": pr.base.ref,
                "draft": pr.draft,
                "mergeable_state": pr.mergeable_state,
            }
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded creating PR in {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            error_message = e.data.get('message', 'Failed')
            if e.status == 422 and 'errors' in e.data: # More specific error for PR creation
                error_details = "; ".join([err.get('message', '') for err in e.data['errors'] if err.get('message')])
                error_message = f"{error_message} Details: {error_details}"
            log.error(f"GitHub API error ({e.status}) creating PR in {owner}/{repo}: {error_message}", exc_info=True)
            raise RuntimeError(f"GitHub API error creating PR: {error_message}") from e
        except Exception as e:
            log.error(f"Unexpected error creating PR in {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error creating PR: {e}") from e

    @tool(
        name="github_get_pull_request_by_number",
        description="Retrieves details for a specific pull request by its number.",
    )
    @requires_permission(Permission.GITHUB_READ_PRS, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def get_pull_request_by_number(self, app_state: AppState, owner: str, repo: str, pr_number: int, **kwargs) -> Dict[str, Any]:
        """
        Retrieves details for a specific pull request.
        """
        log.info(f"Attempting to retrieve PR #{pr_number} from {owner}/{repo}")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            pr = await asyncio.to_thread(repository.get_pull, number=pr_number)
            log.info(f"Successfully retrieved PR #{pr.number} from {owner}/{repo}")
            return {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state, # open, closed
                "url": pr.html_url,
                "user": pr.user.login,
                "body": pr.body,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
                "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                "head_branch": pr.head.ref,
                "base_branch": pr.base.ref,
                "commits_count": pr.commits,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "draft": pr.draft,
                "merged": pr.merged,
                "mergeable": pr.mergeable,
                "mergeable_state": pr.mergeable_state, # e.g., 'clean', 'dirty', 'unknown', 'blocked', 'behind'
                "merged_by": pr.merged_by.login if pr.merged_by else None,
                "labels": [label.name for label in pr.labels],
                "assignees": [assignee.login for assignee in pr.assignees],
                "reviewers": [reviewer.login for reviewer in pr.requested_reviewers],
            }
        except UnknownObjectException:
            log.warning(f"PR #{pr_number} not found in {owner}/{repo}.")
            raise RuntimeError(f"PR #{pr_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded retrieving PR #{pr_number} from {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) retrieving PR #{pr_number} from {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error retrieving PR: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error retrieving PR #{pr_number} from {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error retrieving PR: {e}") from e

    @tool(
        name="github_list_pull_requests",
        description="Lists pull requests for a repository. Can be filtered by state, base/head branch.",
    )
    @requires_permission(Permission.GITHUB_READ_PRS, fallback_permission=Permission.READ_ONLY_ACCESS)
    async def list_pull_requests(self, app_state: AppState, owner: str, repo: str, state: Literal["open", "closed", "all"] = "open", sort: Literal["created", "updated", "popularity", "long-running"] = "created", direction: Literal["asc", "desc"] = "desc", base: Optional[str] = None, head: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Lists pull requests for a repository.
        """
        log.info(f"Listing PRs for {owner}/{repo} (state: {state}, sort: {sort} {direction}, base: {base}, head: {head})")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            params = {'state': state, 'sort': sort, 'direction': direction}
            if base:
                params['base'] = base
            if head:
                params['head'] = head
            
            prs_paginated = await asyncio.to_thread(repository.get_pulls, **params)
            
            results = []
            for i, pr in enumerate(prs_paginated):
                if i >= MAX_LIST_RESULTS: # Using MAX_LIST_RESULTS similar to list_repositories
                    log.debug(f"MAX_LIST_RESULTS ({MAX_LIST_RESULTS}) reached, stopping PR list iteration.")
                    break
                results.append({
                    "number": pr.number,
                    "title": pr.title,
                    "state": pr.state,
                    "url": pr.html_url,
                    "user": pr.user.login,
                    "created_at": pr.created_at.isoformat(),
                    "updated_at": pr.updated_at.isoformat(),
                    "head_branch": pr.head.ref,
                    "base_branch": pr.base.ref,
                })
            log.info(f"Successfully retrieved {len(results)} PRs for {owner}/{repo} (max {MAX_LIST_RESULTS}).")
            return results
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded listing PRs for {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) listing PRs for {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error listing PRs: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error listing PRs for {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error listing PRs: {e}") from e

    @tool(
        name="github_create_pull_request_review",
        description="Creates a review for a pull request (e.g., approve, request changes, or comment).",
    )
    @requires_permission(Permission.GITHUB_WRITE_PRS) # Requires write access to PRs
    async def create_pull_request_review(self, app_state: AppState, owner: str, repo: str, pr_number: int, event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"], body: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Creates a review for a pull request.
        Args:
            event: The review action. Must be one of: "APPROVE", "REQUEST_CHANGES", "COMMENT".
            body: The review comment body. Required for "COMMENT" and "REQUEST_CHANGES", optional for "APPROVE".
        """
        if event not in ["APPROVE", "REQUEST_CHANGES", "COMMENT"]:
            raise ValueError("Invalid event type. Must be 'APPROVE', 'REQUEST_CHANGES', or 'COMMENT'.")
        if event in ["REQUEST_CHANGES", "COMMENT"] and not body:
            raise ValueError(f"Body is required for event type '{event}'.")

        log.info(f"Attempting to create review (event: {event}) on PR #{pr_number} in {owner}/{repo}")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            pr = await asyncio.to_thread(repository.get_pull, number=pr_number)
            review_params = {}
            if body:
                review_params['body'] = body
            
            # PyGithub's create_review takes event as a string, and body.
            # It doesn't directly take commit_id, but it's usually associated with the latest commit on the PR head.
            review = await asyncio.to_thread(pr.create_review, event=event, **review_params)
            log.info(f"Successfully created review ID {review.id} (state: {review.state}) on PR #{pr_number} in {owner}/{repo}")
            return {
                "id": review.id,
                "user": review.user.login,
                "body": review.body,
                "state": review.state, # e.g., "APPROVED", "CHANGES_REQUESTED", "COMMENTED"
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
                "url": review.html_url,
            }
        except UnknownObjectException:
            log.warning(f"PR #{pr_number} not found in {owner}/{repo} when trying to create review.")
            raise RuntimeError(f"PR #{pr_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded creating review on PR #{pr_number} in {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e:
            log.error(f"GitHub API error ({e.status}) creating review on PR #{pr_number} in {owner}/{repo}: {e.data.get('message', 'Failed')}", exc_info=True)
            raise RuntimeError(f"GitHub API error creating review: {e.data.get('message', 'Failed')}") from e
        except Exception as e:
            log.error(f"Unexpected error creating review on PR #{pr_number} in {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error creating review: {e}") from e

    @tool(
        name="github_merge_pull_request",
        description="Merges a pull request.",
    )
    @requires_permission(Permission.GITHUB_WRITE_PRS) # Requires write access to PRs
    async def merge_pull_request(self, app_state: AppState, owner: str, repo: str, pr_number: int, commit_title: Optional[str] = None, commit_message: Optional[str] = None, merge_method: Literal["merge", "squash", "rebase"] = "merge", **kwargs) -> Dict[str, Any]:
        """
        Merges an existing pull request.
        Args:
            commit_title: Title for the merge commit.
            commit_message: Extra detail to append to automatic commit message.
            merge_method: Merge method to use. Can be 'merge', 'squash', or 'rebase'. Defaults to 'merge'.
        """
        if merge_method not in ["merge", "squash", "rebase"]:
            raise ValueError("Invalid merge_method. Must be 'merge', 'squash', or 'rebase'.")

        log.info(f"Attempting to merge PR #{pr_number} in {owner}/{repo} using method '{merge_method}'")
        repository = await self._get_repo(app_state, owner, repo, **kwargs)
        try:
            pr = await asyncio.to_thread(repository.get_pull, number=pr_number)
            
            if not pr.mergeable:
                mergeable_state = pr.mergeable_state
                log.warning(f"PR #{pr_number} in {owner}/{repo} is not mergeable. State: {mergeable_state}")
                raise RuntimeError(f"Pull Request #{pr_number} is not mergeable. Current state: {mergeable_state}. Please resolve conflicts or checks.")

            merge_status = await asyncio.to_thread(
                pr.merge,
                commit_title=commit_title,
                commit_message=commit_message,
                merge_method=merge_method
            )
            
            if merge_status.merged:
                log.info(f"Successfully merged PR #{pr_number} in {owner}/{repo}. SHA: {merge_status.sha}")
                return {
                    "merged": True,
                    "sha": merge_status.sha,
                    "message": merge_status.message, # Typically "Pull Request successfully merged"
                    "pr_number": pr_number,
                    "url": pr.html_url # URL of the now merged (and likely closed) PR
                }
            else:
                log.error(f"Failed to merge PR #{pr_number} in {owner}/{repo}. Message: {merge_status.message}")
                raise RuntimeError(f"Failed to merge PR #{pr_number}. Reason: {merge_status.message}")

        except UnknownObjectException:
            log.warning(f"PR #{pr_number} not found in {owner}/{repo} when trying to merge.")
            raise RuntimeError(f"PR #{pr_number} not found in {owner}/{repo}.") from None
        except RateLimitExceededException as e:
            reset_time_str = datetime.datetime.fromtimestamp(int(e.headers.get('X-RateLimit-Reset', 0))).isoformat() if e.headers.get('X-RateLimit-Reset') else "unknown"
            log.error(f"GitHub Rate Limit Exceeded merging PR #{pr_number} in {owner}/{repo}. Limit resets around {reset_time_str}.", exc_info=False)
            raise RuntimeError(f"GitHub API rate limit exceeded. Limit resets around {reset_time_str}.") from e
        except GithubException as e: # PyGithub often raises GithubException for merge failures (e.g., 405 Method Not Allowed if not mergeable, 409 Conflict)
            error_message = e.data.get('message', 'Merge failed')
            log.error(f"GitHub API error ({e.status}) merging PR #{pr_number} in {owner}/{repo}: {error_message}", exc_info=True)
            if e.status == 405: # Method Not Allowed
                 raise RuntimeError(f"Cannot merge PR #{pr_number}. It might not be mergeable or already merged/closed. API Message: {error_message}") from e
            elif e.status == 409: # Conflict
                 raise RuntimeError(f"Cannot merge PR #{pr_number} due to a conflict. API Message: {error_message}") from e
            raise RuntimeError(f"GitHub API error merging PR: {error_message}") from e
        except Exception as e:
            log.error(f"Unexpected error merging PR #{pr_number} in {owner}/{repo}: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected error merging PR: {e}") from e

