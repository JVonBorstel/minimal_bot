import requests
import json
import logging
from typing import Dict, Any, Optional, List, Tuple, Union
import time
import asyncio
from unittest.mock import MagicMock
import sys

# Import the Config class for type hinting and settings access
from config import Config
# Import the tool decorator
from . import tool

log = logging.getLogger("tools.greptile")

# Default API URL if not overridden by config
DEFAULT_GREPTILE_API_URL = "https://api.greptile.com/v2"

class GreptileTools:
    """
    Provides tools for interacting with the Greptile API (v2) for codebase intelligence.
    This version is stripped down to 3 core tools: query_codebase, search_code, and summarize_repo.
    Requires a GREPTILE_API_KEY to be configured.
    """
    session: requests.Session
    default_repo: Optional[str]

    def __init__(self, config: Config):
        """Initializes the GreptileTools with configuration."""
        self.config = config
        
        # Get required values directly using the utility method
        self.api_key = self.config.get_env_value('GREPTILE_API_KEY')
        
        # Get optional values with defaults
        raw_api_url = self.config.get_env_value('GREPTILE_API_URL')
        raw_default_repo = self.config.get_env_value('GREPTILE_DEFAULT_REPO')
        github_token = self.config.get_env_value('GREPTILE_GITHUB_TOKEN')
        
        # Save GitHub token as an instance variable
        self.github_token = github_token if github_token else None
        
        # Process and sanitize the API URL
        if raw_api_url:
            # Remove surrounding quotes, inline quotes, and comments
            self.api_url = self._sanitize_value(raw_api_url)
            if not self.api_url.endswith(("/v2", "/v2/")):
                log.warning(f"Configured GREPTILE_API_URL ('{self.api_url}') does not appear to be a v2 URL. Defaulting to {DEFAULT_GREPTILE_API_URL}.")
                self.api_url = DEFAULT_GREPTILE_API_URL
        else:
            log.info(f"GREPTILE_API_URL not found in config, using default: {DEFAULT_GREPTILE_API_URL}")
            self.api_url = DEFAULT_GREPTILE_API_URL
            
        # Process and sanitize the default repo URL
        if raw_default_repo:
            self.default_repo = self._sanitize_github_url(raw_default_repo)
        else:
            self.default_repo = None
            
        self.timeout = self.config.DEFAULT_API_TIMEOUT_SECONDS

        # Debug log the values
        log.debug(f"Greptile API key: {'FOUND' if self.api_key else 'NOT FOUND'}")
        log.debug(f"Greptile API URL: {self.api_url}")
        log.debug(f"Greptile default repo: {'FOUND' if self.default_repo else 'NOT FOUND'}")
        log.debug(f"GitHub token for Greptile: {'FOUND' if self.github_token else 'NOT FOUND'}")
        if not self.github_token:
            log.warning("GREPTILE_GITHUB_TOKEN is not configured. Access to private repositories or indexing operations via Greptile may be limited or fail.")

        if not self.api_key:
            log.warning("Greptile API key is not configured. Greptile tools will not be functional.")

        # Use a session for potential connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json",
            "X-GitHub-Token": self.github_token if self.github_token else ""
        })
        log.info(f"Greptile tools initialized. API URL: {self.api_url}")

    def _sanitize_value(self, value: str) -> str:
        """General sanitization for configuration values."""
        if not value:
            return value
            
        # Remove surrounding quotes if present
        value = value.strip('"\'')
        
        # Remove any inline double quotes
        value = value.replace('"', '')
        
        # Remove trailing comment if present (everything after #)
        if '#' in value:
            value = value.split('#')[0].strip()
            
        return value.strip()
            
    def _sanitize_github_url(self, url: str) -> str:
        """
        Sanitizes GitHub URLs to ensure compatibility with Greptile API.
        Removes quotes, comments, .git suffix and trailing slashes.
        """
        if not url:
            return url
            
        # First apply general sanitization
        url = self._sanitize_value(url)
            
        # Remove .git suffix if present
        if url.endswith('.git'):
            url = url[:-4]
            
        # Remove trailing slash if present
        if url.endswith('/'):
            url = url[:-1]
            
        return url.strip()

    async def _send_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retries: int = 2,
        include_headers: bool = False
    ) -> Dict[str, Any]:
        """
        Send a request to the Greptile API with proper error handling and retries.
        """
        # Ensure the API URL has the right format
        api_url = self.api_url.rstrip("/")
        if not api_url.endswith("/v2"):
            log.warning(f"Greptile API URL is configured to '{api_url}', which does not end with '/v2'. Ensure this is intended for the Greptile v2 API.")
        
        # Build the full endpoint URL
        url = f"{api_url}/{endpoint.lstrip('/')}"
        
        # Prepare headers with authentication
        request_headers = {"Authorization": f"Bearer {self.api_key}"}
        if headers:
            request_headers.update(headers)
            
        # Add GitHub token header if available
        if self.github_token:
            request_headers["X-GitHub-Token"] = self.github_token
            
        # Start with fresh session
        session = self.session
        
        # Configure timeout
        timeout = self.timeout
        
        # Set up logging for the request
        method_str = method.upper()
        params_str = f", params={params}" if params else ""
        data_str = f", data={json.dumps(data)[:100]}..." if data else ""
        log.info(f"Greptile API Request: Method={method_str}, URL={url}, Params={params_str}, Data={data_str}, Headers={request_headers}")
        
        attempt = 0
        last_error = None
        
        while attempt <= retries:
            try:
                if method.upper() == "GET":
                    response = session.get(url, params=params, headers=request_headers, timeout=timeout)
                elif method.upper() == "POST":
                    response = session.post(url, json=data, headers=request_headers, timeout=timeout)
                elif method.upper() == "PUT":
                    response = session.put(url, json=data, headers=request_headers, timeout=timeout)
                elif method.upper() == "DELETE":
                    response = session.delete(url, headers=request_headers, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                    
                log.info(f"Greptile API Response: Status={response.status_code}, Headers={dict(response.headers)}")

                # Check rate limits
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining and int(remaining) <= 5:
                    log.warning(f"Greptile API rate limit running low: {remaining} requests remaining")
                    
                # Handle non-2xx responses
                if response.status_code >= 400:
                    error_message = f"Greptile API error ({response.status_code}): {response.text}"
                    log.error(f"Greptile API Error Details: URL={url}, Status={response.status_code}, Response Body={response.text[:500]}, Response Headers={dict(response.headers)}")
                    
                    # Handle specific error cases
                    if response.status_code == 401:
                        raise RuntimeError(f"Authentication error: Invalid or missing API key")
                    elif response.status_code == 403:
                        raise RuntimeError(f"Authorization error: Not authorized to access this repository or endpoint")
                    elif response.status_code == 404:
                        raise RuntimeError(f"Not found: The requested resource or repository does not exist")
                    elif response.status_code == 429:
                        # Rate limit exceeded - check if we should retry
                        if attempt < retries:
                            retry_after = int(response.headers.get("Retry-After", 2))
                            log.warning(f"Rate limit exceeded, retrying after {retry_after} seconds")
                            await asyncio.sleep(retry_after)
                            attempt += 1
                            continue
                        else:
                            raise RuntimeError(f"Rate limit exceeded. Try again later.")
                    else:
                        raise RuntimeError(error_message)
                
                # Parse JSON response
                try:
                    response_json = response.json()
                    if include_headers:
                        return {"data": response_json, "headers": dict(response.headers)}
                    return response_json
                except json.JSONDecodeError:
                    error_message = f"Invalid JSON response from Greptile API: {response.text[:200]}"
                    log.error(error_message)
                    raise RuntimeError(error_message)
                    
            except (requests.RequestException, ConnectionError, TimeoutError) as e:
                last_error = str(e)
                
                # Check if we should retry
                if attempt < retries:
                    backoff = 2 ** attempt  # Exponential backoff
                    log.warning(f"Request failed, retrying in {backoff} seconds: {str(e)}")
                    await asyncio.sleep(backoff)
                    attempt += 1
                else:
                    log.error(f"Request failed after {retries} retries: {str(e)}")
                    raise RuntimeError(f"Failed to connect to Greptile API: {str(e)}")
        
        # This should only be reached if all retries fail
        raise RuntimeError(f"Request failed after {retries} retries: {last_error}")

    def _extract_owner_repo(self, github_url: str) -> Tuple[str, str]:
        """
        Extract the owner and repository name from a GitHub URL.
        """
        url = self._sanitize_github_url(github_url)
        parts = url.split('/')
        
        if len(parts) < 5 or parts[2] != 'github.com':
            raise ValueError(f"Invalid GitHub URL format: {github_url}. Expected: https://github.com/owner/repo")
        
        owner = parts[3]
        repo = parts[4]
        
        return owner, repo

    def _create_repo_object(self, repo_url: str, context: Optional[str] = None, branch: str = "main") -> Dict[str, Any]:
        """
        Creates a repository object for API requests.
        The Greptile API requires a "branch" field in the repository object.
        """
        try:
            owner, repo = self._extract_owner_repo(repo_url)
            repo_obj = {
                "remote": "github",
                "repository": f"{owner}/{repo}",
                "branch": branch  # Required by Greptile API
            }
            
            if context:
                repo_obj["context"] = context
                
            return repo_obj
        except Exception as e:
            log.error(f"Error creating repo object for {repo_url}: {e}")
            raise ValueError(f"Invalid repository URL: {repo_url}")

    @tool(
        name="greptile_query_codebase",
        description="Answers natural language questions about a targeted GitHub repository using Greptile's AI analysis. Can focus queries on specific files/directories. Requires repository URL.",
    )
    async def query_codebase(
        self, query: str, github_repo_url: str, focus_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answers natural language questions about a targeted GitHub repository using Greptile's AI analysis.
        Can optionally focus the query on specific files or directories within the repository.
        """
        if not query:
            return {
                "answer": "Error: Query cannot be empty.",
                "status": "ERROR",
                "data": {"status": "ERROR", "error": "Query cannot be empty."}
            }
            
        if not github_repo_url:
            return {
                "answer": "Error: GitHub repository URL is required.",
                "status": "ERROR",
                "data": {"status": "ERROR", "error": "GitHub repository URL is required."}
            }
            
        # Sanitize GitHub URL (remove trailing slashes, etc.)
        repo_url = self._sanitize_github_url(github_repo_url)
        log.info(f"Querying Greptile about: '{query}' for repo: {repo_url}")
        
        # Create payload
        payload = {
            "query": query,
            "repositories": [self._create_repo_object(repo_url, focus_path)]
        }
        
        try:
            response = await self._send_request(endpoint="query", method="POST", data=payload)
            log.info(f"Received answer from Greptile for query on {repo_url}")
            
            # Use the message field as the answer
            answer = response.get("message", "No answer was provided by Greptile.")
            
            # Extract additional fields if present
            related_snippets = response.get("related_snippets")
            metadata = response.get("metadata")
            references = response.get("references")
            
            # Construct the result dictionary with all available fields
            result = {
                "answer": answer,
                "repo_url": repo_url,
                "status": "SUCCESS",
                "data": {
                    "status": "SUCCESS",
                    "answer": answer,
                    "repo_url": repo_url
                }
            }
            
            # Add additional fields if they exist
            if related_snippets is not None:
                result["related_snippets"] = related_snippets
                result["data"]["related_snippets"] = related_snippets
            if metadata is not None:
                result["metadata"] = metadata
                result["data"]["metadata"] = metadata
            if references is not None:
                result["references"] = references
                result["data"]["references"] = references
                
            return result
        except Exception as e:
            error_msg = f"Failed to get answer from Greptile: {str(e)}"
            log.error(error_msg)
            return {
                "answer": error_msg,
                "status": "ERROR",
                "data": {"status": "ERROR", "error": str(e)}
            }

    @tool(
        name="greptile_search_code",
        description="Performs semantic search for code snippets related to a query within a specific GitHub repository (if provided) or across Greptile's public index.",
    )
    def search_code(
        self,
        query: str,
        github_repo_url: Optional[str] = None,
        limit: int = 10,
        language: Optional[str] = None,
        max_tokens: Optional[int] = None,
        score_threshold: Optional[float] = None,
        path_prefix: Optional[str] = None,
        file_name_contains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Performs semantic search for code snippets related to a query.
        NOTE: Search endpoint is not available in Greptile API v2.
        """
        log.warning("Greptile search_code called, but search endpoint is not available in API v2")
        
        # Return a helpful error message explaining the limitation
        return {
            "status": "ERROR",
            "error": "Search endpoint is not available in Greptile API v2. Use greptile_query_codebase instead for code analysis.",
            "query": query,
            "suggestion": "Try using greptile_query_codebase with a natural language query about the code you're looking for."
        }

    @tool(
        name="greptile_summarize_repo",
        description="Provides a high-level overview of a Greptile-indexed repository's architecture, key modules, and entrypoints using an AI query. Requires repository URL.",
    )
    async def summarize_repo(self, repo_url: str) -> Dict[str, Any]:
        """
        Provides a high-level overview of a repository's architecture, key modules, and entrypoints.
        """
        if not repo_url:
            return {
                "status": "ERROR",
                "error": "Repository URL is required"
            }

        # Sanitize the GitHub URL
        repo_url = self._sanitize_github_url(repo_url)

        # Use the query_codebase method with a specialized query
        summary_query = "Provide a high-level overview of this repository's architecture, key modules, main entry points, and overall purpose. What are the main directories and their responsibilities?"

        log.info(f"Generating repository summary for: {repo_url}")
        
        try:
            result = await self.query_codebase(summary_query, repo_url)
            
            if result.get("status") == "SUCCESS":
                return {
                    "status": "SUCCESS",
                    "repo_url": repo_url,
                    "summary": result.get("answer", ""),
                    "metadata": result.get("metadata"),
                    "references": result.get("references")
                }
            else:
                return {
                    "status": "ERROR",
                    "repo_url": repo_url,
                    "error": result.get("data", {}).get("error", "Unknown error occurred")
                }
        except Exception as e:
            log.error(f"Error generating repository summary for {repo_url}: {e}")
            return {
                "status": "ERROR",
                "repo_url": repo_url,
                "error": str(e)
            }

    def health_check(self) -> Dict[str, Any]:
        """
        Performs a health check on the Greptile API connection and authentication.
        """
        if not self.api_key:
            return {"status": "NOT_CONFIGURED", "message": "Greptile API key not configured."}

        try:
            # The health endpoint returns plain text "Healthy!" not JSON, so we need to handle this specially
            api_url = self.api_url.rstrip("/")
            url = f"{api_url}/health"
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            if self.github_token:
                headers["X-GitHub-Token"] = self.github_token
            
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            
            log.info(f"Greptile health check response: Status={response.status_code}, Text='{response.text}'")
            
            if response.status_code == 200:
                # Greptile health endpoint returns plain text "Healthy!"
                rate_limit_remaining = response.headers.get("X-RateLimit-Remaining", "Unknown")
                
                log.info("Greptile health check successful.")
                return {
                    "status": "OK", 
                    "message": f"Successfully connected to Greptile API. Response: {response.text.strip()}. Rate limit remaining: {rate_limit_remaining}",
                    "api_url": self.api_url
                }
            else:
                error_message = f"Greptile health check failed with status {response.status_code}: {response.text}"
                log.error(error_message)
                return {"status": "ERROR", "message": error_message}
                
        except Exception as e:
            error_message = f"Greptile health check failed: {str(e)}"
            log.error(error_message, exc_info=True)
            return {"status": "ERROR", "message": error_message}
