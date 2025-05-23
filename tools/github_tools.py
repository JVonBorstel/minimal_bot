# --- FILE: tools/github_tools.py ---
import logging
from typing import Dict, Any, List, Optional, Union, Literal
import datetime
import asyncio

from github import Github, GithubException, UnknownObjectException, RateLimitExceededException
from github.Repository import Repository
from github.NamedUser import NamedUser
from github.Organization import Organization
from requests.exceptions import RequestException

from config import Config
from . import tool
from user_auth.tool_access import requires_permission
from user_auth.permissions import Permission
from state_models import AppState

log = logging.getLogger("tools.github")

MAX_LIST_RESULTS = 25
MAX_SEARCH_RESULTS = 15

class GitHubTools:
    """
    Provides tools for interacting with the GitHub API using PyGithub.
    This version is stripped down to list repositories and search code.
    Supports multiple GitHub accounts and GitHub Enterprise.
    """
    github_client: Optional[Github] = None
    authenticated_user_login: Optional[str] = None
    active_account_name: Optional[str] = None
    github_clients: Dict[str, Github] = {}

    def __init__(self, config: Config, app_state: Optional[AppState] = None, testing_mode: bool = False):
        log.info("Initializing GitHub Tools")
        self.config = config
        self.app_state = app_state
        self.github_client = None
        self.authenticated_user_login = None
        self.active_account_name = None
        self.github_clients = {}

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
                github_client = Github(
                    login_or_token=token,
                    base_url=str(base_url),
                    timeout=timeout_seconds,
                    retry=3
                )
            else:
                github_client = Github(
                    login_or_token=token,
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
        """
        if kwargs.get('read_only_mode') is True:
            log.info(f"Executing get_account_client in read-only mode (account: {account_name or 'default active'}).")

        if account_name:
            if account_name in self.github_clients:
                return self.github_clients[account_name]
            else:
                log.warning(f"Requested GitHub account '{account_name}' not found or not initialized. Using active account if available.")
                return self.github_client
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