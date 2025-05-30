import requests
import json
import logging
from typing import Dict, Any, Optional, List, Literal
import time
import re

# Import the Config class for type hinting and settings access
from config import Config, AVAILABLE_PERPLEXITY_MODELS_REF
# Import the tool decorator
from . import tool

log = logging.getLogger("tools.perplexity")

# Default API URL if not overridden by config
DEFAULT_PERPLEXITY_API_URL = "https://api.perplexity.ai"


class PerplexityTools:
    """
    Provides tools for interacting with the Perplexity API for online search and Q&A.
    Requires a PERPLEXITY_API_KEY to be configured.
    Uses models capable of accessing current web information.
    """
    session: requests.Session

    def __init__(self, config: Config):
        """Initializes the PerplexityTools with configuration."""
        self.config = config

        # Get required values directly using the utility method
        self.api_key = self.config.get_env_value('PERPLEXITY_API_KEY')
        # Get optional values with defaults
        api_url = self.config.get_env_value('PERPLEXITY_API_URL')
        self.api_url = api_url if api_url else DEFAULT_PERPLEXITY_API_URL
        self.default_model = self.config.get_env_value('PERPLEXITY_MODEL')
        self.timeout = self.config.DEFAULT_API_TIMEOUT_SECONDS

        # Debug log the values
        log.debug(
            f"Perplexity API key: {'FOUND' if self.api_key else 'NOT FOUND'}")
        log.debug(f"Perplexity API URL: {self.api_url}")
        log.debug(
            f"Perplexity model: {'FOUND' if self.default_model else 'NOT FOUND'}")

        if not self.api_key:
            log.warning(
                "Perplexity API key is not configured. Perplexity tools will not be functional.")

        # Use a session for potential connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        log.info(
            f"Perplexity tools initialized. API URL: {self.api_url}, Default Model: {self.default_model}")

    def _send_request(self,
                      endpoint: str,
                      method: str = "POST",
                      data: Optional[Dict[str,
                                          Any]] = None,
                      include_headers: bool = False) -> Dict[str,
                                                             Any]:
        """Internal helper to send authenticated requests to the Perplexity API."""
        if not self.api_key:
            raise ValueError("Perplexity API key is missing.")

        # Fix URL construction to avoid double slashes
        base_url = self.api_url.rstrip('/')
        endpoint_clean = endpoint.lstrip('/')
        url = f"{base_url}/{endpoint_clean}"
        
        log.debug(f"Sending {method} request to Perplexity: {url}")
        log.debug(
            f"Perplexity request data keys: {list(data.keys()) if data else 'None'}")

        try:
            response = self.session.request(
                method, url, json=data, timeout=self.timeout
            )
            response.raise_for_status()

            response_data = response.json()
            response_headers = dict(response.headers)

            # Extract rate limit headers if available
            rate_limit_headers = {
                header: response_headers[header]
                for header in response_headers
                if header.lower().startswith('x-ratelimit-')
            }

            if include_headers:
                return {
                    "data": response_data,
                    "headers": response_headers,
                    "rate_limit": rate_limit_headers}
            else:
                return response_data
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            error_text = e.response.text[:500]
            log.error(
                f"Perplexity API HTTP error ({status_code}) for {method} {url}: {error_text}",
                exc_info=False)
            error_details = f"Perplexity API returned HTTP {status_code}."

            try:
                error_body = e.response.json()

                # Handle different error response structures
                if 'error' in error_body:
                    error_obj = error_body.get('error', {})
                    if isinstance(error_obj, dict):
                        message = error_obj.get(
                            'message', error_obj.get(
                                'type', 'No detail provided.'))
                    else:
                        message = str(error_obj)
                    error_details += f" Error: {message}"
                elif 'detail' in error_body:
                    detail_obj = error_body.get('detail', {})
                    if isinstance(detail_obj, dict):
                        message = detail_obj.get(
                            'message', 'No detail provided.')
                    else:
                        message = str(detail_obj)
                    error_details += f" Detail: {message}"
                elif 'message' in error_body:
                    error_details += f" Message: {error_body['message']}"
                else:
                    error_details += f" Response: {json.dumps(error_body)[:200]}"

            except json.JSONDecodeError:
                error_details += f" Response: {error_text}"

            # Special handling for common status codes
            if status_code == 401:
                error_details = "Perplexity API authentication failed (401). Check API Key."
            elif status_code == 429:
                error_details = "Perplexity API rate limit exceeded (429). Check rate limits in your account."
            elif status_code == 400:
                error_details = f"Perplexity API bad request (400): {error_details}"
            elif status_code == 403:
                error_details = "Perplexity API request forbidden (403). Check account permissions and tier level."

            raise RuntimeError(error_details) from e
        except requests.exceptions.RequestException as e:
            log.error(
                f"Perplexity API request failed ({method} {url}): {e}",
                exc_info=True)
            raise e  # Re-raise for decorator
        except Exception as e:
            log.error(
                f"Unexpected error during Perplexity API request ({method} {url}): {e}",
                exc_info=True)
            raise RuntimeError(
                f"Unexpected error during Perplexity API request: {e}") from e

    def _extract_answer(self,
                        response_data: Dict[str,
                                            Any],
                        default_answer: str = "[Could not retrieve an answer from Perplexity.]") -> str:
        """
        Extract the answer text from a Perplexity API response.
        Handles multiple possible response structures.
        """
        try:
            # 1. Standard structure: choices[0].message.content
            if response_data.get("choices") and isinstance(
                    response_data["choices"], list) and len(
                    response_data["choices"]) > 0:
                first_choice = response_data["choices"][0]
                if first_choice.get(
                        "message") and first_choice["message"].get("content"):
                    return first_choice["message"]["content"]

            # 2. Alternative structure: output[0].content[0].text
            if response_data.get("output") and isinstance(
                    response_data["output"], list) and len(
                    response_data["output"]) > 0:
                first_output = response_data["output"][0]

                # 2a. Check content array for text
                if first_output.get("content") and isinstance(
                        first_output["content"], list) and len(
                        first_output["content"]) > 0:
                    content_item = first_output["content"][0]
                    if content_item.get("text"):
                        return content_item["text"]

                # 2b. Check for direct text field
                elif first_output.get("text"):
                    return first_output["text"]

            # If we get here, no answer was found
            log.warning(
                f"Could not find answer in response structure. Keys: {list(response_data.keys())}")
            return default_answer

        except Exception as e:
            log.warning(
                f"Error extracting answer from response: {e}",
                exc_info=True)
            return default_answer

    def _extract_sources(
            self, response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract source citations from a Perplexity API response.
        Handles multiple possible response structures and normalizes source format.
        """
        sources = []

        try:
            # Try different known locations where sources might be found

            # 1. Check in usage.references (standard location)
            if response_data.get(
                    "usage") and response_data["usage"].get("references"):
                sources = response_data["usage"]["references"]
                log.debug(f"Found {len(sources)} sources in usage.references.")

            # 2. Check in annotations (alternative location)
            elif response_data.get("annotations"):
                sources = response_data["annotations"]
                log.debug(f"Found {len(sources)} sources in annotations.")

            # 3. Check in output[0].content[x].annotations for newer API structure
            elif response_data.get("output") and isinstance(response_data["output"], list) and len(response_data["output"]) > 0:
                first_output = response_data["output"][0]
                if first_output.get("content") and isinstance(
                        first_output["content"], list):
                    for content_item in first_output["content"]:
                        if content_item.get("annotations") and isinstance(
                                content_item["annotations"], list):
                            sources = content_item["annotations"]
                            log.debug(
                                f"Found {len(sources)} sources in output[0].content[x].annotations.")
                            break

            # 4. Check in response.citations for yet another possibility
            elif response_data.get("citations"):
                sources = response_data["citations"]
                log.debug(f"Found {len(sources)} sources in citations.")

            # Process and standardize source format
            processed_sources = []
            for source in sources:
                # Some source formats might need normalization
                if isinstance(source, dict):
                    if "title" in source and "url" in source:
                        processed_sources.append(source)
                    elif "title" in source and "link" in source:
                        processed_sources.append({
                            "title": source["title"],
                            "url": source["link"]
                        })
                    elif "text" in source and "href" in source:
                        processed_sources.append({
                            "title": source["text"],
                            "url": source["href"]
                        })
                    else:
                        processed_sources.append(source)
                elif isinstance(source, str) and (source.startswith("http://") or source.startswith("https://")):
                    processed_sources.append({
                        "title": f"Source: {source}",
                        "url": source
                    })
                else:
                    processed_sources.append(source)

            return processed_sources

        except Exception as e:
            log.warning(
                f"Error extracting sources from response: {e}",
                exc_info=True)
            return []

    @tool(name="perplexity_web_search",
          description="Answers questions or researches topics using Perplexity Sonar models with access to current web information. Ideal for focused queries needing up-to-date online data.",
          parameters_schema={
              "type": "object",
              "properties": {
                  "query": {
                      "type": "string",
                      "description": "The search query or question (e.g., 'Latest updates on Python 4 release?'). If not provided, will use a default general news request."
                  },
                  "model_name": {
                      "type": "string",
                      "description": "Specify a Perplexity model (e.g., 'sonar-pro', 'sonar-reasoning-pro'). Defaults to the configured one."
                  },
                  "search_context_size": {
                      "type": "string",
                      "description": "Amount of search context to retrieve - 'low', 'medium', or 'high'. Low minimizes context for cost savings, high maximizes for comprehensive answers.",
                      "enum": ["low", "medium", "high"]
                  },
                  "recency_filter": {
                      "type": "string",
                      "description": "Filter results based on publication time - 'day', 'week', 'month', or 'year'. Use for time-sensitive queries where recent information is preferred.",
                      "enum": ["day", "week", "month", "year"]
                  }
              },
              "required": []
          }
    )
    def web_search(
        self,
        query: Optional[str] = None,
        model_name: Optional[str] = None,
        search_context_size: Optional[Literal["low", "medium", "high"]] = None,
        recency_filter: Optional[Literal["day", "week", "month", "year"]] = None
    ) -> Dict[str, Any]:
        """
        Performs an online search/Q&A using a Perplexity model like Sonar.
        """
        if self.config.MOCK_MODE:
            log.warning("Perplexity web_search running in mock mode.")
            return {
                "answer": f"Mock answer for query: {query or 'top news today'}",
                "model": model_name or self.default_model,
                "sources": []}

        # Set a default query if none is provided
        if not query:
            log.warning(
                "No query provided for perplexity_web_search. Using default query 'top news stories today'.")
            query = "top news stories today"

        pplx_model = model_name or self.default_model
        # Ensure a valid model is used
        if pplx_model not in AVAILABLE_PERPLEXITY_MODELS_REF:
            log.warning(
                f"Specified Perplexity model '{pplx_model}' is not in AVAILABLE_PERPLEXITY_MODELS_REF. Using 'sonar' instead.")
            pplx_model = "sonar"

        log.info(
            f"Performing Perplexity web search with model: {pplx_model}. Query: '{query[:100]}...'")

        # Create a system prompt optimized for the type of query and model
        system_prompt = "You are an AI assistant specialized in providing accurate, concise, and up-to-date answers based on real-time web search results. Always cite your sources with relevant URLs where information was found. Focus on delivering factual information rather than opinions."

        # Check if query is likely asking for current events or time-sensitive info
        time_sensitive_keywords = [
            "recent", "latest", "current", "today", "this week", "this month", 
            "this year", "news", "update"]
        is_time_sensitive = any(keyword in query.lower()
                                for keyword in time_sensitive_keywords)

        # Enhance system prompt for time-sensitive queries
        if is_time_sensitive and not recency_filter:
            system_prompt += " For time-sensitive information, prioritize the most recent sources and clearly indicate publication dates when available."
            recency_filter = "month"

        payload: Dict[str, Any] = {
            "model": pplx_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
        }

        # Add recency filter if specified
        if recency_filter:
            payload["search_recency_filter"] = recency_filter

        # Add web_search_options if any context parameters are provided
        if search_context_size:
            web_search_options: Dict[str, Any] = {}
            if search_context_size not in ["low", "medium", "high"]:
                log.warning(
                    f"Invalid search_context_size '{search_context_size}'. Must be 'low', 'medium', or 'high'. Defaulting to 'low'.")
                search_context_size = "low"
            web_search_options["search_context_size"] = search_context_size
            payload["web_search_options"] = web_search_options
            log.debug(f"Using web_search_options: {web_search_options}")

        # Let exceptions from _send_request propagate to the decorator
        response_data = self._send_request(
            "chat/completions", method="POST", data=payload)

        # The try-except block below is for parsing issues, not API call failures.
        # API call failures are now handled by the decorator via exceptions from _send_request.
        try:
            # Use helper methods to extract answer and sources
            answer = self._extract_answer(response_data)
            sources = self._extract_sources(response_data)

            log.info(
                f"Successfully retrieved answer from Perplexity model {pplx_model} with {len(sources)} sources.")

        except Exception as e:
            # This catches errors during parsing of a successful API response.
            # We'll wrap this in a RuntimeError to be caught by the decorator.
            log.warning(
                f"Could not extract answer or sources from Perplexity response: {e}",
                exc_info=True)
            # It's better to raise an error here so the decorator can standardize it.
            # The LLM should know if parsing failed.
            raise RuntimeError(f"Failed to parse the successful response from Perplexity: {e}") from e

        return {"answer": answer, "model": pplx_model, "sources": sources}

    @tool(
        name="perplexity_summarize_topic",
        description="Given a broad topic, returns a concise summary using Perplexity's Sonar models with web information access.",
    )
    def summarize_topic(
        self,
        topic: str,
        model_name: Optional[str] = None,
        search_context_size: Optional[Literal["low", "medium", "high"]] = "medium",
        recency_filter: Optional[Literal["day", "week", "month", "year"]] = None,
        format: Optional[Literal["default", "bullet_points", "key_sections"]] = "default"
    ) -> Dict[str, Any]:
        """
        Summarizes a topic using a Perplexity model with web search capabilities.
        """
        if self.config.MOCK_MODE:
            log.warning("Perplexity summarize_topic running in mock mode.")
            return {
                "topic": topic,
                "summary": f"Mock summary for topic: {topic}",
                "model": model_name or self.default_model,
                "sources": []}

        if not topic:
            log.error("Perplexity summarize_topic failed: Topic cannot be empty.")
            # This ValueError will be caught and standardized by the @tool decorator
            raise ValueError("Topic cannot be empty.")

        # Removed manual API key check here - decorator will handle it
        # if not self.api_key:
        #     log.warning(
        #         "Perplexity API key is not configured. summarize_topic tool is not functional.")
        #     return {
        #         "topic": topic,
        #         "summary": "Perplexity API key is not configured.",
        #         "model": model_name or self.default_model,
        #         "sources": []}

        pplx_model = model_name or self.default_model

        if pplx_model not in AVAILABLE_PERPLEXITY_MODELS_REF:
            log.warning(
                f"Specified Perplexity model '{pplx_model}' is not in AVAILABLE_PERPLEXITY_MODELS_REF. Using 'sonar' instead.")
            pplx_model = "sonar"

        log.info(
            f"Performing Perplexity summarize_topic with model: {pplx_model}. Topic: '{topic}'")

        # Create format-specific system prompt
        if format == "bullet_points":
            system_prompt = "You are an AI assistant specialized in providing concise, well-structured topic summaries in bullet point format. Research the topic thoroughly and organize your findings into clear, informative bullet points that capture the key aspects, recent developments, major perspectives, and notable applications. Include introduction and conclusion paragraphs to provide context."
        elif format == "key_sections":
            system_prompt = "You are an AI assistant specialized in creating comprehensive topic summaries organized into key sections. Research the topic thoroughly and create a well-structured summary with clear headings for different aspects (e.g., Overview, History, Current Developments, Applications, Challenges, Future Directions). Provide a balanced perspective from reliable sources."
        else:  # default narrative format
            system_prompt = "You are an AI assistant specialized in providing accurate, structured, and concise topic summaries based on current web search results. Research the topic thoroughly and create a well-written narrative summary that covers key concepts, historical context, current state, and future directions. Balance depth with readability, and cite important sources."

        # Format query to encourage a concise, informative summary
        summary_query = f"Provide a comprehensive summary of the topic: {topic}. Include key concepts, recent developments, major perspectives, and notable applications or implications."

        # For topics likely requiring recent information, specify recency
        time_sensitive_keywords = [
            "trends", "developments", "latest", "current", "emerging", 
            "recent", "new", "future", "outlook"]
        is_time_sensitive = any(keyword in topic.lower()
                                for keyword in time_sensitive_keywords)

        if is_time_sensitive and not recency_filter:
            recency_filter = "month"
            summary_query += " Focus on the most recent developments and current state of knowledge."

        payload: Dict[str, Any] = {
            "model": pplx_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": summary_query}
            ]
        }

        # Add recency filter if specified
        if recency_filter:
            if recency_filter not in ["day", "week", "month", "year"]:
                log.warning(
                    f"Invalid recency_filter '{recency_filter}'. Must be 'day', 'week', 'month', or 'year'. Parameter will be ignored.")
            else:
                payload["search_recency_filter"] = recency_filter

        # Add web_search_options if any context parameters are provided
        if search_context_size:
            web_search_options: Dict[str, Any] = {}
            if search_context_size not in ["low", "medium", "high"]:
                log.warning(
                    f"Invalid search_context_size '{search_context_size}'. Must be 'low', 'medium', or 'high'. Defaulting to 'low'.")
                search_context_size = "low"
            web_search_options["search_context_size"] = search_context_size
            payload["web_search_options"] = web_search_options
            log.debug(f"Using web_search_options: {web_search_options}")

        # Let exceptions from _send_request propagate to the decorator
        response_data = self._send_request(
            "chat/completions", method="POST", data=payload)

        try:
            answer = self._extract_answer(response_data)
            sources = self._extract_sources(response_data)
            log.info(
                f"Successfully retrieved summary from Perplexity model {pplx_model} with {len(sources)} sources.")
        except Exception as e:
            log.warning(
                f"Could not extract answer or sources from Perplexity summary response: {e}",
                exc_info=True)
            # Raise RuntimeError for parsing errors to be standardized by the decorator
            raise RuntimeError(f"Failed to parse the successful summary response from Perplexity: {e}") from e

        return {
            "topic": topic,
            "summary": answer,
            "model": pplx_model,
            "sources": sources
        }

    @tool(
        name="perplexity_structured_search",
        description="Performs a web search and returns results in a structured format (JSON schema or regex pattern).",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or question."
                },
                "format_type": {
                    "type": "string",
                    "description": "The type of structured output format to use ('json_schema' or 'regex').",
                    "enum": ["json_schema", "regex"]
                },
                "schema": {
                    "type": "object",
                    "properties": {},
                    "description": "JSON schema object defining the structure (required when format_type is 'json_schema')."
                },
                "regex_pattern": {
                    "type": "string",
                    "description": "Regular expression pattern for output matching (required when format_type is 'regex')."
                },
                "model_name": {
                    "type": "string",
                    "description": "The Perplexity model to use. Defaults to the configured default model."
                },
                "temperature": {
                    "type": "number",
                    "description": "Controls randomness (0.0-1.5). Lower values produce more deterministic outputs, which is typically preferred for structured data.",
                    "default": 0.1
                },
                "search_context_size": {
                    "type": "string",
                    "description": "Amount of search context to retrieve - 'low', 'medium', or 'high'.",
                    "enum": ["low", "medium", "high"]
                }
            },
            "required": ["query", "format_type"],
            "oneOf": [
                {
                    "properties": {
                        "format_type": {"enum": ["json_schema"]}
                    },
                    "required": ["schema"]
                },
                {
                    "properties": {
                        "format_type": {"enum": ["regex"]}
                    },
                    "required": ["regex_pattern"]
                }
            ]
        }
    )
    def structured_search(
        self,
        query: str,
        format_type: Literal["json_schema", "regex"],
        schema: Optional[Dict[str, Any]] = None,
        regex_pattern: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.1,
        search_context_size: Optional[Literal["low", "medium", "high"]] = None
    ) -> Dict[str, Any]:
        """
        Performs a web search and returns results in a structured format (JSON schema or regex pattern).
        The main validation for schema/regex_pattern based on format_type is handled by Pydantic in the decorator.
        """
        if self.config.MOCK_MODE:
            log.warning("Perplexity structured_search running in mock mode.")
            return {
                "query": query,
                "format_type": format_type,
                "structured_data": {"mock_field": "Mock structured data for your query"},
                "model": model_name or self.default_model,
                "sources": []
            }

        # API key check is now handled by the @tool decorator's is_tool_configured

        # Parameter validation for schema/regex_pattern based on format_type
        # is primarily handled by Pydantic schema in the decorator.
        # However, a runtime check here can be a safeguard or for logic not expressible in JSON schema.
        if format_type == "json_schema" and not schema:
            raise ValueError("The 'schema' parameter is required when 'format_type' is 'json_schema'.")
        if format_type == "regex" and not regex_pattern:
            raise ValueError("The 'regex_pattern' parameter is required when 'format_type' is 'regex'.")

        pplx_model = model_name or self.default_model
        if pplx_model not in AVAILABLE_PERPLEXITY_MODELS_REF:
            log.warning(
                f"Specified Perplexity model '{pplx_model}' is not in AVAILABLE_PERPLEXITY_MODELS_REF. Using 'sonar' instead.")
            pplx_model = "sonar"

        log.info(
            f"Performing Perplexity structured_search with model: {pplx_model}. Query: '{query[:100]}...', Format: {format_type}")

        # System prompt instructing the model to provide structured output
        if format_type == "json_schema":
            system_prompt = f"You are an AI assistant that extracts structured data from web search results. Respond ONLY with a valid JSON object matching the following schema. Do not include any other text, explanations, or markdown. Schema:\n```json\n{json.dumps(schema)}\n```"
        elif format_type == "regex":
            system_prompt = f"You are an AI assistant that extracts specific information matching a regex pattern from web search results. Respond ONLY with the text that matches the pattern. Do not include any other text or explanations. Pattern: {regex_pattern}"
        else:
            # Should not happen due to Literal type hint and Pydantic validation
            raise ValueError(f"Invalid format_type: {format_type}. Must be 'json_schema' or 'regex'.")

        payload: Dict[str, Any] = {
            "model": pplx_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            "temperature": temperature
        }

        if format_type == "json_schema":
            payload["response_format"] = {"type": "json_object"} # For models that support it

        # Add recency filter (if we decide to add this param to structured_search)
        # Add web_search_options (if we decide to add this param to structured_search)
        if search_context_size:
            web_search_options: Dict[str, Any] = {}
            if search_context_size not in ["low", "medium", "high"]:
                log.warning(
                    f"Invalid search_context_size '{search_context_size}'. Must be 'low', 'medium', or 'high'. Defaulting to 'medium'.")
                search_context_size = "medium"
            web_search_options["search_context_size"] = search_context_size
            payload["web_search_options"] = web_search_options
            log.debug(f"Using web_search_options: {web_search_options}")

        # Let exceptions from _send_request propagate
        response_data = self._send_request(
            "chat/completions", method="POST", data=payload)

        try:
            answer_content = self._extract_answer(response_data, default_answer="") # Get raw content
            sources = self._extract_sources(response_data)
            structured_data: Any = None

            if not answer_content:
                raise ValueError("Perplexity model returned an empty response.")

            if format_type == "json_schema":
                try:
                    # Attempt to parse the answer content as JSON
                    # Remove potential markdown code block fences if present
                    cleaned_json_string = re.sub(r"^```json\n|\n```$", "", answer_content.strip(), flags=re.MULTILINE)
                    structured_data = json.loads(cleaned_json_string)
                    # Basic validation against the top-level keys of the schema could be added here if needed,
                    # but Pydantic in the LLM should do deeper validation if the schema is complex.
                except json.JSONDecodeError as je:
                    log.error(f"Failed to decode JSON from Perplexity response for structured_search: {je}. Response content: {answer_content[:500]}")
                    raise RuntimeError(f"Perplexity response was not valid JSON: {je}. Content: {answer_content[:200]}...") from je
            elif format_type == "regex":
                # For regex, the answer_content *is* the structured data (or should be)
                # No further parsing needed here, but could add regex validation if desired.
                structured_data = answer_content 
            
            log.info(f"Successfully retrieved and parsed structured data for '{query[:500]}'")
            return {
                "query": query,
                "format_type": format_type,
                "structured_data": structured_data,
                "model": pplx_model,
                "sources": sources
            }

        except Exception as e:
            # Catch any parsing related errors or the ValueError from empty response
            log.warning(
                f"Could not extract or parse structured data from Perplexity response: {e}",
                exc_info=True)
            raise RuntimeError(f"Failed to process Perplexity response for structured_search: {e}") from e

    def health_check(self) -> Dict[str, Any]:
        """
        Checks Perplexity API health and authentication.
        """
        if not self.api_key:
            return {"status": "NOT_CONFIGURED",
                    "message": "PERPLEXITY_API_KEY not set."}

        health_check_model = "sonar"
        if self.default_model in AVAILABLE_PERPLEXITY_MODELS_REF:
            health_check_model = self.default_model

        payload = {
            "model": health_check_model,
            "messages": [{"role": "user", "content": "Health check."}],
            "max_tokens": 1,
            "web_search_options": {"search_context_size": "low"}
        }

        try:
            log.debug(
                f"Health check: Sending request to Perplexity with model '{health_check_model}'")

            start_time = time.time()
            response_data = self._send_request(
                "chat/completions", method="POST", data=payload, include_headers=True)
            latency_ms = int((time.time() - start_time) * 1000)

            # Check for basic presence of API response
            is_response_valid = False
            response_structure = []

            # For API responses with include_headers=True, the actual response data is in the "data" field
            api_response = response_data.get("data", response_data)

            if api_response:
                response_structure = list(api_response.keys())
                log.debug(f"API response structure keys: {response_structure}")

                # Check various known response formats
                if ("choices" in api_response and isinstance(api_response["choices"], list) and len(api_response["choices"]) > 0) or \
                   ("output" in api_response and isinstance(api_response["output"], list) and len(api_response["output"]) > 0) or \
                   ("model" in api_response and "usage" in api_response) or \
                   ("id" in api_response or "completion_id" in api_response):
                    is_response_valid = True

            if is_response_valid:
                log.info(
                    f"Perplexity health check successful using model '{health_check_model}'. Latency: {latency_ms}ms")
                return {
                    "status": "OK",
                    "message": f"API connection successful using model '{health_check_model}'.",
                    "model_tested": health_check_model,
                    "latency_ms": latency_ms}
            else:
                log.warning(
                    f"Perplexity health check response has unexpected format. Response keys: {response_structure}")
                return {
                    "status": "UNKNOWN",
                    "message": f"API responded but response format was unexpected. Found keys: {', '.join(response_structure)}",
                    "model_tested": health_check_model,
                    "latency_ms": latency_ms}

        except requests.exceptions.RequestException as e:
            log.error(
                f"Perplexity health check failed: Network error - {e}",
                exc_info=True)
            return {
                "status": "DOWN",
                "message": f"API connection error: {str(e)}",
                "model_tested": health_check_model
            }
        except RuntimeError as e:
            log.error(f"Perplexity health check failed: {e}", exc_info=False)

            if "401" in str(e):
                return {
                    "status": "AUTH_FAILED",
                    "message": f"API authentication failed. Please check your API key.",
                    "model_tested": health_check_model}
            elif "429" in str(e):
                return {
                    "status": "RATE_LIMITED",
                    "message": f"API request rate limited. Please try again later.",
                    "model_tested": health_check_model}
            else:
                return {
                    "status": "DOWN",
                    "message": str(e),
                    "model_tested": health_check_model
                }
        except Exception as e:
            log.error(
                f"Perplexity health check failed: Unexpected error: {e}",
                exc_info=True)
            return {
                "status": "ERROR",
                "message": f"Unexpected error during health check: {str(e)}",
                "model_tested": health_check_model
            } 