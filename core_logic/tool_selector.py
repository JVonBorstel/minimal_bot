# AGENT: This file depends on config.py, numpy, sentence-transformers,
# and logging. Import these at the top.
# AGENT: If 'data/' directory does not exist, create it before saving
# embeddings.

# core_logic/tool_selector.py

"""
Tool Selection Intelligence Layer

This module provides the core functionality for tool selection, embedding
generation, and semantic search capabilities to dynamically select the most
relevant tools for a given query.
"""

import logging
import os
import json
import time
import re
from typing import Dict, List, Any, Optional, Union, Tuple

# Try to import ML dependencies, fallback gracefully if not available
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found] # noqa: E501
    ML_DEPENDENCIES_AVAILABLE = True
except ImportError:
    # Create mock objects for when dependencies aren't available
    np = None
    SentenceTransformer = None
    ML_DEPENDENCIES_AVAILABLE = False

# Project-specific imports
# AGENT: The import below assumes `config.py` is in the root and
# `core_logic` is a direct subdirectory.
# Adjust if your project structure is different.
from config import Config
from state_models import AppState # Added for type hinting
from user_auth.permissions import Permission # Added for converting string to Permission enum

log = logging.getLogger(__name__)


class ToolSelector:
    """
    Tool selection intelligence layer that manages tool metadata, embeddings,
    and performs semantic search to identify relevant tools.
    """

    def __init__(self, config: Config):
        """
        Initialize the ToolSelector.

        Args:
            config: Application configuration
        """
        self.config = config
        self.embedding_model = None
        # tool_name -> embedding (numpy array if available, list of floats otherwise)
        self.tool_embeddings: Dict[str, Union[Any, List[float]]] = {}
        # tool_name -> metadata
        self.tool_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Get configuration settings
        self.settings = config.TOOL_SELECTOR
        self.schema_settings = config.SCHEMA_OPTIMIZATION
        self.enabled = self.settings.get("enabled", True)
        self.similarity_threshold = self.settings.get("similarity_threshold", 0.3)
        self.max_tools = self.settings.get("max_tools", 15)
        self.always_include_tools = self.settings.get("always_include_tools", [])
        self.debug_logging = self.settings.get("debug_logging", False)
        self.default_fallback = self.settings.get("default_fallback", True)
        
        # Setup cache path
        self.embedding_cache_path = self.settings.get(
            "cache_path", 
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                # Moves up two levels from core_logic/tool_selector.py
                # to project root
                "data",
                "tool_embeddings.json"
            )
        )
        
        # Cache management
        self._cache_dirty = False  # Flag to track if embeddings have changed
        self._last_save_time = time.time()  # Track when we last saved embeddings
        self._auto_save_interval = self.settings.get("auto_save_interval_seconds", 300)  # Default 5 minutes
        
        # Initialize the embedding model
        self._initialize_embedding_model()
        
        # Load cached embeddings if available
        if not self._load_embeddings_cache() and self.settings.get("rebuild_cache_on_startup", False):
            log.info("No embedding cache found or rebuild requested. Will build on first tool selection.")
            # We'll build embeddings lazily when first needed

    def optimize_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize a tool schema to reduce complexity.

        Args:
            schema: Original tool schema (parameters section)

        Returns:
            Optimized schema with reduced complexity
        """
        if not schema or not isinstance(schema, dict):
            return schema

        # Skip optimization if disabled
        if not self.schema_settings.get("enabled", True):
            return schema

        optimized = schema.copy()

        # 1. Simplify property descriptions
        if "properties" in optimized and \
           isinstance(optimized["properties"], dict):
            for prop_name, prop_def in optimized["properties"].items():
                if isinstance(prop_def, dict):
                    # Truncate descriptions to max configured length
                    max_desc_length = self.schema_settings.get("max_description_length", 150)
                    if "description" in prop_def and \
                       isinstance(prop_def["description"], str):
                        if len(prop_def["description"]) > max_desc_length:
                            prop_def["description"] = (
                                prop_def["description"][:max_desc_length-3] + "..."
                            )

                    # Recursively optimize nested objects
                    if self.schema_settings.get("flatten_nested_objects", True) and \
                       prop_def.get("type") == "object" and \
                       "properties" in prop_def:
                        # AGENT NOTE: Ensure self.optimize_schema is called
                        # correctly
                        # Correctly assign the result of recursive optimization
                        optimized["properties"][prop_name] = self.optimize_schema(prop_def)
                        # Update local prop_def to the optimized version for any subsequent operations within this loop iteration
                        prop_def = optimized["properties"][prop_name]

                    # Limit enum values to configured max number
                    max_enum = self.schema_settings.get("max_enum_values", 7)
                    if "enum" in prop_def and \
                       isinstance(prop_def["enum"], list) and \
                       len(prop_def["enum"]) > max_enum:
                        # Keep most important enum values - assuming first
                        # ones are more important
                        prop_def["enum"] = prop_def["enum"][:max_enum]
                        # AGENT NOTE: Ensure log is defined or passed
                        if self.debug_logging:
                            log.debug(
                                f"Reduced enum size for {prop_name} to {max_enum} values")
                    
                    # Truncate long property names if enabled
                    if self.schema_settings.get("truncate_long_names", False):
                        max_name_length = self.schema_settings.get("max_name_length", 30)
                        if len(prop_name) > max_name_length:
                            # This is complex and could break references
                            # Just log for now as a potential issue
                            log.warning(f"Property name '{prop_name}' exceeds max length ({max_name_length})")

                    # Moved and adapted: Convert oneOf/anyOf for the current property
                    if self.schema_settings.get("simplify_complex_types", True):
                        for complex_key in ["oneOf", "anyOf"]:
                            if complex_key in prop_def and \
                               isinstance(prop_def[complex_key], list):
                                # If there's only one item, replace with that item
                                if len(prop_def[complex_key]) == 1:
                                    temp_schema_item = prop_def[complex_key][0].copy()
                                    del prop_def[complex_key] # Delete from current property definition
                                    for k_item, v_item in temp_schema_item.items():
                                        prop_def[k_item] = v_item # Add to current property definition
                                # If there are many items, keep just 3 (or a configured value)
                                elif len(prop_def[complex_key]) > 3:
                                    prop_def[complex_key] = prop_def[complex_key][:3]
                                    if self.debug_logging:
                                        log.debug(f"Reduced {complex_key} size for {prop_name} to 3 options")
                # End of 'if isinstance(prop_def, dict):'
            # End of 'for prop_name, prop_def in optimized["properties"].items():' loop

        # Note: The original block for '2. Convert oneOf/anyOf...' that was here is now removed
        # as its logic has been integrated into the properties loop above.
        return optimized

    def optimize_tool_definition(
        self, tool_def: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Optimize a full tool definition to reduce complexity.

        Args:
            tool_def: Original tool definition

        Returns:
            Optimized tool definition
        """
        if not tool_def or not isinstance(tool_def, dict):
            return tool_def

        # Skip optimization if disabled
        if not self.schema_settings.get("enabled", True):
            return tool_def

        optimized = tool_def.copy()

        # 1. Truncate overly long descriptions
        max_desc_length = self.schema_settings.get("max_description_length", 150)
        if "description" in optimized and \
           isinstance(optimized["description"], str):
            if len(optimized["description"]) > max_desc_length:
                optimized["description"] = (
                    optimized["description"][:max_desc_length-3] + "..."
                )

        # 2. Optimize the parameters schema
        if "parameters" in optimized and \
           isinstance(optimized["parameters"], dict):
            optimized["parameters"] = self.optimize_schema(
                optimized["parameters"]
            )

        return optimized

    def generate_tool_embedding(self, tool_def: Dict[str, Any]) -> Optional[Any]:
        """
        Generate an embedding vector for a tool definition.

        Args:
            tool_def: Tool definition dictionary

        Returns:
            numpy array containing the embedding vector, or None if ML dependencies unavailable
        """
        if not ML_DEPENDENCIES_AVAILABLE or not self.embedding_model:
            log.debug("Cannot generate embedding: ML dependencies or embedding model not available")
            return None

        # Create a rich text representation of the tool
        tool_text = self._create_tool_text_representation(tool_def)

        # Generate the embedding
        embedding = self.embedding_model.encode(tool_text)

        return embedding

    def _create_tool_text_representation(self, tool_def: Dict[str, Any]) -> str:  # noqa: E501
        """
        Create a rich text representation of a tool for embedding.

        Args:
            tool_def: Tool definition dictionary

        Returns:
            Text representation of the tool
        """
        parts = []

        # Add name
        name = tool_def.get("name", "")
        if name:
            parts.append(f"Tool Name: {name}")

        # Add description
        description = tool_def.get("description", "")
        if description:
            parts.append(f"Description: {description}")
            # Add "When not to use" if available in metadata
            metadata = tool_def.get("metadata", {})
            when_not_to_use = metadata.get("when_not_to_use")
            if when_not_to_use:
                parts.append(f"When Not To Use: {when_not_to_use}")

        # Add categories and tags
        metadata = tool_def.get("metadata", {}) # Ensure metadata is defined if not already
        categories = metadata.get("categories", [])
        if categories:
            parts.append(f"Categories: {', '.join(categories)}")

        tags = metadata.get("tags", [])
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")
            
        # Add keywords if available - these are used for direct matching
        keywords = metadata.get("keywords", [])
        if keywords:
            parts.append(f"Keywords: {', '.join(keywords)}")

        # Add parameter information
        params = tool_def.get("parameters", {})
        if params and isinstance(params, dict) and "properties" in params:
            props = params["properties"]
            if props:
                parts.append("Parameters:")
                for param_name, param_def in props.items():
                    param_desc = param_def.get("description", "")
                    param_type = param_def.get("type", "")
                    parts.append(
                        f"- {param_name} ({param_type}): {param_desc}"
                    )

        # Add examples if available
        examples = metadata.get("examples", [])
        if examples:
            parts.append("Examples:")
            for i, example in enumerate(examples[:3]):  # Increase examples from 2 to 3
                parts.append(f"Example {i+1}: {json.dumps(example)}")

        # Add importance information to boost specific tools
        importance = metadata.get("importance", 5)  # Default importance is medium (5)
        # Repeat the name and description based on importance to give more weight
        for _ in range(max(0, importance - 5)):  # Add extra repetitions for important tools
            if name:
                parts.append(f"Tool Name: {name}")
            if description:
                parts.append(f"Description: {description}")

        return "\n".join(parts)

    def _check_direct_keyword_match(self, query: str, tool_def: Dict[str, Any]) -> float:
        """
        Check if the query directly matches any keywords defined for the tool.
        
        Args:
            query: The user query
            tool_def: Tool definition dictionary
            
        Returns:
            A boost score between 0.0 and 0.5 based on keyword matching
        """
        # No boost by default
        boost = 0.0
        
        # Get keywords from metadata if available
        metadata = tool_def.get("metadata", {})
        keywords = metadata.get("keywords", [])
        if not keywords:
            return boost
            
        # Normalize query and keywords for matching
        query_lower = query.lower()
        
        # Check for exact keyword matches
        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Direct match gives highest boost
            if keyword_lower in query_lower:
                # Adjust boost based on how much of the query the keyword represents
                coverage = len(keyword_lower) / len(query_lower)
                boost = max(boost, 0.3 + 0.2 * coverage)  # Between 0.3 and 0.5
        
        return min(boost, 0.5)  # Cap at 0.5

    def _save_embeddings_cache(self) -> bool:
        """
        Save embeddings and metadata to cache file.
        
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Create the parent directory if it doesn't exist
            cache_dir = os.path.dirname(self.embedding_cache_path)
            if not os.path.exists(cache_dir):
                try:
                    os.makedirs(cache_dir, exist_ok=True)
                    log.info(f"Created cache directory: {cache_dir}")
                except PermissionError as pe:
                    log.error(f"Permission error creating cache directory {cache_dir}: {pe}")
                    return False
                except OSError as ose:
                    log.error(f"OS error creating cache directory {cache_dir}: {ose}")
                    return False

            # Convert numpy arrays to lists for serialization
            serializable_embeddings = {}
            for name, embedding in self.tool_embeddings.items():
                if ML_DEPENDENCIES_AVAILABLE and np and isinstance(embedding, np.ndarray):
                    serializable_embeddings[name] = embedding.tolist()
                else:
                    serializable_embeddings[name] = embedding

            cache_data = {
                "embeddings": serializable_embeddings,
                "metadata": self.tool_metadata,
                "timestamp": time.time(),
                "version": "1.1"  # Version tracking for cache format
            }

            # Use a temporary file to avoid corruption if writing is interrupted
            temp_file = f"{self.embedding_cache_path}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(cache_data, f)
            
            # Atomic rename to avoid partial writes
            if os.path.exists(self.embedding_cache_path):
                # Create a backup before overwriting
                backup_file = f"{self.embedding_cache_path}.bak"
                try:
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(self.embedding_cache_path, backup_file)
                except OSError as ose:
                    log.warning(f"Failed to create backup of embeddings cache: {ose}")
            
            # Now do the final rename
            os.rename(temp_file, self.embedding_cache_path)
            
            # Update state tracking
            self._cache_dirty = False
            self._last_save_time = time.time()

            log.info(f"Saved embeddings cache to {self.embedding_cache_path}")
            return True
            
        except Exception as e:
            log.error(f"Failed to save embeddings cache: {e}", exc_info=True)
            return False

    def _load_embeddings_cache(self) -> bool:
        """
        Load embeddings and metadata from cache file.

        Returns:
            bool: True if cache was loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(self.embedding_cache_path):
                log.info("No embeddings cache file found")
                return False
                
            # Check if cache file is empty or too small to be valid
            if os.path.getsize(self.embedding_cache_path) < 10:
                log.warning(f"Embeddings cache file is too small to be valid: {self.embedding_cache_path}")
                return False

            with open(self.embedding_cache_path, 'r') as f:
                try:
                    cache_data = json.load(f)
                except json.JSONDecodeError as jde:
                    log.error(f"Invalid JSON in embeddings cache: {jde}")
                    # Try loading backup if it exists
                    backup_file = f"{self.embedding_cache_path}.bak"
                    if os.path.exists(backup_file):
                        log.info(f"Attempting to load from backup cache file: {backup_file}")
                        try:
                            with open(backup_file, 'r') as bf:
                                cache_data = json.load(bf)
                            log.info("Successfully loaded embeddings from backup cache")
                        except Exception as backup_err:
                            log.error(f"Failed to load backup cache: {backup_err}")
                            return False
                    else:
                        return False

            if not isinstance(cache_data, dict):
                log.warning("Invalid embeddings cache format")
                return False

            # Extract the data
            self.tool_embeddings = cache_data.get("embeddings", {})
            self.tool_metadata = cache_data.get("metadata", {})
            
            # Validate the loaded data
            if not self.tool_embeddings or not self.tool_metadata:
                log.warning("Empty or incomplete embeddings cache")
                return False

            # Convert lists back to numpy arrays
            for name, embedding_list in self.tool_embeddings.items():
                if isinstance(embedding_list, list) and ML_DEPENDENCIES_AVAILABLE and np:
                    self.tool_embeddings[name] = np.array(embedding_list)

            log.info(
                f"Loaded embeddings for {len(self.tool_embeddings)} tools "
                f"from cache"
            )
            
            # Initialize state tracking after successful load
            self._cache_dirty = False
            self._last_save_time = time.time()
            
            return True
        except Exception as e:
            log.error(f"Failed to load embeddings cache: {e}", exc_info=True)
            return False
            
    def _check_auto_save(self) -> None:
        """Check if we should auto-save the embeddings cache based on time or changes."""
        current_time = time.time()
        time_since_last_save = current_time - self._last_save_time
        
        # Save if dirty and interval elapsed or very long time has passed
        if self._cache_dirty and (
            time_since_last_save > self._auto_save_interval or
            time_since_last_save > self._auto_save_interval * 5
        ):
            log.debug(f"Auto-saving embeddings cache after {time_since_last_save:.1f} seconds")
            self._save_embeddings_cache()

    def build_tool_embeddings(self, all_tools: List[Dict[str, Any]]) -> None:
        """
        Build embeddings for all tools.

        Args:
            all_tools: List of all tool definitions
        """
        log.info(f"Building embeddings for {len(all_tools)} tools")

        self.tool_metadata = {}
        self.tool_embeddings = {}
        self._cache_dirty = True

        for tool_def in all_tools:
            name = tool_def.get("name")
            if not name:
                continue

            try:
                # Store the optimized tool definition
                optimized_def = self.optimize_tool_definition(tool_def)
                self.tool_metadata[name] = optimized_def

                # Generate and store the embedding
                # Use original for embedding
                embedding = self.generate_tool_embedding(tool_def)
                # Convert to list for serialization
                self.tool_embeddings[name] = embedding.tolist()

                if self.debug_logging:
                    log.debug(f"Generated embedding for tool: {name}")
            except Exception as e:
                log.error(f"Failed to process tool {name}: {e}", exc_info=True)

        log.info(f"Built embeddings for {len(self.tool_embeddings)} tools")

        # Save embeddings to cache file
        self._save_embeddings_cache()

    def _initialize_embedding_model(self):
        """Initialize the embedding model for semantic search."""
        if not ML_DEPENDENCIES_AVAILABLE:
            log.warning(
                "ML dependencies (numpy, sentence-transformers) not available. "
                "Tool selection will use simple pattern matching fallback."
            )
            self.embedding_model = None
            return
            
        try:
            # Get model name from config
            model_name = self.settings.get("embedding_model", "all-MiniLM-L6-v2")
            self.embedding_model = SentenceTransformer(model_name)
            log.info(f"Initialized embedding model: {model_name}")
        except Exception as e:
            log.warning(
                f"Failed to initialize embedding model: {e}. "
                "Falling back to pattern matching tool selection."
            )
            self.embedding_model = None

    def select_tools(
        self,
        query: str,
        app_state: AppState,
        available_tools: Optional[List[Dict[str, Any]]] = None,
        max_tools: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Select the most relevant tools for a given query, considering user permissions.

        Args:
            query: The user's query or request
            app_state: The current application state, used for permission checking.
            available_tools: List of all available tool definitions (should include permission metadata)
            max_tools: Maximum number of tools to select (overrides config if provided)

        Returns:
            List of selected tool definitions that the user has permission to use.
        """
        # First check if we should auto-save the cache
        self._check_auto_save()
        
        # Check if tool selection is enabled
        if not self.enabled:
            log.info("Tool selection is disabled. Using all available tools.")
            # IMPORTANT CHANGE: Limit the maximum number of tools even when returning all
            if available_tools and len(available_tools) > 6:
                log.warning(f"Limiting returned tools from {len(available_tools)} to 6 to avoid API constraints")
                return available_tools[:6]
            return available_tools or []
            
        if not self.embedding_model:
            log.error("Embedding model not initialized. Cannot select tools.")
            if self.default_fallback:
                # IMPORTANT CHANGE: Limit the maximum number of tools in fallback
                if available_tools and len(available_tools) > 6:
                    log.warning(f"Limiting returned tools from {len(available_tools)} to 6 to avoid API constraints")
                    return available_tools[:6]
                return available_tools or []
            return []

        if not available_tools:
            log.warning("No available tools provided for selection")
            return []
            
        # Use max_tools from argument if provided, otherwise from config
        # IMPORTANT CHANGE: Cap max_tool_count to 6 regardless of config
        max_tool_count = min(max_tools if max_tools is not None else self.max_tools, 6)
        log.info(f"Tool selection using max_tool_count: {max_tool_count} (capped at 6)")
        
        # Check if we need to build embeddings
        if not self.tool_embeddings:
            log.info("Tool embeddings not loaded. Building embeddings...")
            self.build_tool_embeddings(available_tools)
            
        # Make a map of tool names to definitions for quick lookup
        tool_name_to_def = {
            tool.get("name", ""): tool
            for tool in available_tools if tool.get("name")
        }

        # Parse the query to identify entity mentions that match tool names or parameters
        entity_boosted_tools = self._identify_entity_mentions(query, tool_name_to_def)
        
        # Check for strong direct intent matches using regex patterns
        intent_matched_tools = self._identify_direct_intents(query, tool_name_to_def)
        
        # If this is a help command, return only the help tool
        if intent_matched_tools and intent_matched_tools[0] == "help":
            help_tool = tool_name_to_def.get("help")
            if help_tool:
                log.info("Help command detected. Returning only help tool.")
                return [help_tool]
        
        # CRITICAL FIX: For GitHub repository queries, always ensure GitHub tool is selected
        query_lower = query.lower()
        github_repo_keywords = ['repos', 'repositories', 'github', 'repository']
        if any(keyword in query_lower for keyword in github_repo_keywords):
            github_tool = tool_name_to_def.get('github_list_repositories')
            if github_tool and 'github_list_repositories' not in intent_matched_tools and 'github_list_repositories' not in entity_boosted_tools:
                log.info("GitHub repository query detected - forcing GitHub tool selection")
                entity_boosted_tools.append('github_list_repositories')
        
        # First, add any "always include" tools to the results
        always_include_names = set(self.always_include_tools)
        selected_tool_names = set(intent_matched_tools + entity_boosted_tools)
        for tool_name in always_include_names:
            if tool_name in tool_name_to_def:
                selected_tool_names.add(tool_name)
                if self.debug_logging:
                    log.debug(f"Always including tool: {tool_name}")

        # If we have enough tools from intent/entity matching, we can skip embedding similarity
        if len(selected_tool_names) >= max_tool_count:
            log.info(f"Found {len(selected_tool_names)} tools via direct pattern matching, skipping embedding similarity")
            selected_tools = []
            # Convert tool names to definitions (preserving order of importance)
            for tool_name in intent_matched_tools + entity_boosted_tools + list(always_include_names):
                if tool_name in tool_name_to_def and tool_name not in [t.get("name") for t in selected_tools]:
                    # Use the optimized definition if available from self.tool_metadata
                    if tool_name in self.tool_metadata and self.tool_metadata[tool_name]:
                        selected_tools.append(self.tool_metadata[tool_name])
                    else:
                        selected_tools.append(tool_name_to_def[tool_name])
                if len(selected_tools) >= max_tool_count:
                    break
            return selected_tools[:max_tool_count]

        # Generate embedding for the query
        if not ML_DEPENDENCIES_AVAILABLE or not self.embedding_model:
            log.info("ML dependencies not available. Using pattern matching tool selection only.")
            # Use only pattern-matched tools when ML is not available
            selected_tools = []
            for tool_name in intent_matched_tools + entity_boosted_tools + list(always_include_names):
                if tool_name in tool_name_to_def and tool_name not in [t.get("name") for t in selected_tools]:
                    if tool_name in self.tool_metadata and self.tool_metadata[tool_name]:
                        selected_tools.append(self.tool_metadata[tool_name])
                    else:
                        selected_tools.append(tool_name_to_def[tool_name])
                if len(selected_tools) >= max_tool_count:
                    break
            if not selected_tools and self.default_fallback:
                return available_tools[:min(max_tool_count, len(available_tools))]
            return selected_tools[:max_tool_count]
            
        query_embedding = self.embedding_model.encode(query)

        # Calculate similarity scores between query and all tools
        similarities = []
        if not self.tool_embeddings:
            log.warning(
                "Tool embeddings are not built or loaded. "
                "Cannot calculate similarities."
            )
            # Fallback: return all tools up to max_tools or an empty list
            # if none. This behavior might need adjustment based on
            # desired fallback strategy.
            if self.default_fallback:
                log.info("Using fallback: returning all available tools up to max limit.")
                return available_tools[:min(max_tool_count, len(available_tools))]
            return []

        # Then calculate similarity for remaining tools
        for tool_name, tool_embedding_data in self.tool_embeddings.items():
            # Skip if this tool is already in the selected set
            if tool_name in selected_tool_names:
                continue
                
            # Skip if tool is not in available tools
            if tool_name not in tool_name_to_def:
                continue

            # Only proceed with similarity if ML dependencies are available
            if not ML_DEPENDENCIES_AVAILABLE or not np:
                continue
                
            tool_embedding = np.array(tool_embedding_data) \
                if isinstance(tool_embedding_data, list) \
                else tool_embedding_data

            # Check if it's a valid numpy array
            if not isinstance(tool_embedding, np.ndarray) \
                    or tool_embedding.ndim == 0:
                log.warning(
                    f"Skipping tool {tool_name} due to invalid embedding "
                    f"format: {type(tool_embedding)}"
                )
                continue

            # Calculate cosine similarity
            # Ensure query_embedding is also a numpy array
            if not isinstance(query_embedding, np.ndarray):
                query_embedding_np = np.array(query_embedding)
            else:
                query_embedding_np = query_embedding

            # Check for zero vectors to avoid division by zero in norm
            norm_query = np.linalg.norm(query_embedding_np)
            norm_tool = np.linalg.norm(tool_embedding)

            if norm_query == 0 or norm_tool == 0:
                similarity = 0.0
            else:
                similarity = np.dot(query_embedding_np, tool_embedding) / \
                             (norm_query * norm_tool)

            # Apply keyword boost if available
            # This helps prioritize specific tools over general ones like search_web
            keyword_boost = self._check_direct_keyword_match(query, tool_name_to_def[tool_name])
            if keyword_boost > 0:
                similarity = similarity + keyword_boost 
                if self.debug_logging:
                    log.debug(f"Applied keyword boost of {keyword_boost} to {tool_name}, new score: {similarity:.4f}")

            # Special case: reduce prominence of search_web when more specific tools are available
            if tool_name == "search_web" or tool_name == "perplexity_web_search":
                if similarity > self.similarity_threshold:
                    # Slightly reduce the search_web score unless it's a very strong match
                    if similarity < 0.8:  # Still prioritize search for very explicit web search queries
                        adjusted_similarity = similarity * 0.85  # Reduce by 15%
                        similarity = adjusted_similarity
                        if self.debug_logging:
                            log.debug(f"Reduced score for {tool_name} to {similarity:.4f}")

            # Add boost for tools from already detected relevant categories
            categories = self._get_tool_categories(tool_name, tool_name_to_def[tool_name])
            if categories:
                for cat in categories:
                    # Increase similarity for tool if its category was detected in our entity matching
                    if cat.lower() in [c.lower() for c in self._extract_query_categories(query)]:
                        similarity += 0.1
                        if self.debug_logging:
                            log.debug(f"Added category boost to {tool_name} for category {cat}, new score: {similarity:.4f}")

            # Only consider tools that meet the threshold
            if similarity >= self.similarity_threshold:
                similarities.append((tool_name, float(similarity)))

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x[1], reverse=True)

        if self.debug_logging:
            log.debug(f"Top similarity scores: {similarities[:5]}")

        # Take top K results (minus the already included "always_include" tools)
        remaining_slots = max_tool_count - len(selected_tool_names) 
        if remaining_slots > 0:
            for tool_name, score in similarities[:remaining_slots]:
                selected_tool_names.add(tool_name)
                if self.debug_logging:
                    log.debug(f"Selected tool: {tool_name} (score: {score:.4f})")

        # Convert tool names to definitions
        selected_tools = []
        # First add intent-matched tools (highest priority)
        for tool_name in intent_matched_tools:
            if tool_name in tool_name_to_def and tool_name not in [t.get("name") for t in selected_tools]:
                if len(selected_tools) >= max_tool_count:
                    break
                if tool_name in self.tool_metadata and self.tool_metadata[tool_name]:
                    selected_tools.append(self.tool_metadata[tool_name])
                else:
                    selected_tools.append(tool_name_to_def[tool_name])
        
        # Then add entity-boosted tools
        for tool_name in entity_boosted_tools:
            if tool_name in tool_name_to_def and tool_name not in [t.get("name") for t in selected_tools]:
                if len(selected_tools) >= max_tool_count:
                    break
                if tool_name in self.tool_metadata and self.tool_metadata[tool_name]:
                    selected_tools.append(self.tool_metadata[tool_name])
                else:
                    selected_tools.append(tool_name_to_def[tool_name])
        
        # Then add always-include tools
        for tool_name in always_include_names:
            if tool_name in tool_name_to_def and tool_name not in [t.get("name") for t in selected_tools]:
                if len(selected_tools) >= max_tool_count:
                    break
                if tool_name in self.tool_metadata and self.tool_metadata[tool_name]:
                    selected_tools.append(self.tool_metadata[tool_name])
                else:
                    selected_tools.append(tool_name_to_def[tool_name])
        
        # Finally add embedding-matched tools
        for tool_name, score in similarities:
            if tool_name in tool_name_to_def and tool_name not in [t.get("name") for t in selected_tools]:
                if len(selected_tools) >= max_tool_count:
                    break
                if tool_name in self.tool_metadata and self.tool_metadata[tool_name]:
                    selected_tools.append(self.tool_metadata[tool_name])
                else:
                    selected_tools.append(tool_name_to_def[tool_name])

        log.info(
            f"Selected {len(selected_tools)} tools from "
            f"{len(available_tools)} available based on query similarity."
        )
        
        # If no tools were selected and default_fallback is enabled,
        # return all tools up to the max limit
        if not selected_tools and self.default_fallback:
            log.warning("No tools selected. Using fallback: all tools up to max limit.")
            # Fallback tools also need permission filtering
            relevant_tools = available_tools[:min(max_tool_count, len(available_tools) if available_tools else 0)]
        else:
            relevant_tools = selected_tools

        # --- BEGIN PERMISSION FILTERING ---
        if not app_state or not app_state.current_user:
            log.warning("Cannot filter tools by permission: AppState or current_user is missing. Using permission-free fallback.")
            # When user context is missing, provide basic tools that don't require specific permissions
            permission_free_tools = []
            for tool_def in relevant_tools:
                tool_name = tool_def.get("name", "unknown_tool")
                metadata = tool_def.get("metadata", {})
                required_permission_name_str = metadata.get("required_permission_name")
                
                # If no permission is required, include the tool
                if not required_permission_name_str:
                    permission_free_tools.append(tool_def)
                    if self.debug_logging:
                        log.debug(f"Including permission-free tool: {tool_name}")
                # Include basic utility tools that should always be available
                elif tool_name in ["help", "list_dir", "read_file", "health_check"]:
                    permission_free_tools.append(tool_def)
                    if self.debug_logging:
                        log.debug(f"Including basic utility tool: {tool_name}")
            
            if permission_free_tools:
                log.info(f"Returning {len(permission_free_tools)} permission-free tools due to missing user context.")
                return permission_free_tools
            else:
                log.warning("No permission-free tools available. Returning empty list.")
                return []

        final_permitted_tools: List[Dict[str, Any]] = []
        for tool_def in relevant_tools:
            tool_name = tool_def.get("name", "unknown_tool")
            metadata = tool_def.get("metadata", {})
            required_permission_name_str = metadata.get("required_permission_name") # e.g., "GITHUB_READ_REPO"

            if not required_permission_name_str:
                # If a tool definition has no permission metadata, assume it's accessible by default (e.g. help tool)
                # This policy can be made stricter if needed (e.g., require explicit PUBLIC_ACCESS permission)
                log.debug(f"Tool '{tool_name}' has no required_permission_name in metadata. Assuming accessible.")
                final_permitted_tools.append(tool_def)
                continue

            try:
                permission_enum_member = Permission[required_permission_name_str]
                if app_state.has_permission(permission_enum_member):
                    final_permitted_tools.append(tool_def)
                    if self.debug_logging:
                        log.debug(f"User has permission for tool '{tool_name}' ({required_permission_name_str}). Adding to final list.")
                else:
                    if self.debug_logging:
                        log.debug(f"User LACKS permission for tool '{tool_name}' ({required_permission_name_str}). Filtering out.")
            except KeyError:
                log.warning(f"Tool '{tool_name}' has an invalid required_permission_name '{required_permission_name_str}' in metadata. Filtering out.")
            except Exception as e:
                log.error(f"Error checking permission for tool '{tool_name}' ({required_permission_name_str}): {e}. Filtering out.", exc_info=True)
        
        log.info(f"After permission filtering, {len(final_permitted_tools)} tools selected out of {len(relevant_tools)} relevant tools.")
        # --- END PERMISSION FILTERING ---
            
        return final_permitted_tools
    
    def _identify_entity_mentions(self, query: str, tool_dict: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        Identifies entity mentions in the query using simple keyword matching.
        This is more reliable than complex regex patterns.
        
        Args:
            query: The user query
            tool_dict: Dictionary mapping tool names to definitions
            
        Returns:
            List of tool names that match entity mentions (ordered by relevance)
        """
        boosted_tools = []
        query_lower = query.lower()
        
        # Simple keyword-based GitHub detection
        github_keywords = ['repos', 'repositories', 'github', 'repository']
        list_keywords = ['list', 'show', 'get', 'my']
        
        # If query contains GitHub keywords AND list keywords → trigger GitHub tool
        if any(keyword in query_lower for keyword in github_keywords) and \
           any(keyword in query_lower for keyword in list_keywords):
            if 'github_list_repositories' in tool_dict:
                boosted_tools.append('github_list_repositories')
        
        # Simple Jira detection
        jira_keywords = ['jira', 'tickets', 'issues', 'ticket', 'issue']
        my_keywords = ['my', 'mine']
        
        if any(keyword in query_lower for keyword in jira_keywords) and \
           any(keyword in query_lower for keyword in my_keywords):
            if 'jira_get_issues_by_user' in tool_dict:
                boosted_tools.append('jira_get_issues_by_user')
        
        # Simple code search detection
        code_keywords = ['code', 'function', 'method', 'class', 'search code', 'find code']
        if any(keyword in query_lower for keyword in code_keywords):
            for tool in ['greptile_search_code', 'github_search_code']:
                if tool in tool_dict and tool not in boosted_tools:
                    boosted_tools.append(tool)
        
        # Simple web search detection  
        web_keywords = ['weather', 'news', 'current', 'latest', 'online', 'web search']
        if any(keyword in query_lower for keyword in web_keywords):
            if 'perplexity_web_search' in tool_dict and 'perplexity_web_search' not in boosted_tools:
                boosted_tools.append('perplexity_web_search')
        
        # File operations
        if 'read file' in query_lower or 'open file' in query_lower:
            if 'read_file' in tool_dict:
                boosted_tools.append('read_file')
        if 'list files' in query_lower or 'list directory' in query_lower:
            if 'list_dir' in tool_dict:
                boosted_tools.append('list_dir')
        
        # Jira project issue listing
        jira_project_keywords = ['project issues', 'issues in project', 'tickets in project']
        # Attempt to match typical project key format (e.g., PROJ, DEV, TESTKEY)
        project_key_pattern = r'\b[A-Z][A-Z0-9_]{1,15}\b' # Starts with letter, then letters/numbers/underscores
        
        if any(keyword in query_lower for keyword in jira_project_keywords) or \
           (any(keyword in query_lower for keyword in jira_keywords) and re.search(project_key_pattern, query)): # query, not query_lower for regex on keys
            if 'jira_get_issues_by_project' in tool_dict and 'jira_get_issues_by_project' not in boosted_tools:
                boosted_tools.append('jira_get_issues_by_project')

        return boosted_tools

    def _identify_direct_intents(self, query: str, tool_dict: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        Identifies direct tool selection intents using simple keyword matching.
        This is much more reliable than complex regex patterns.
        
        Args:
            query: The user query
            tool_dict: Dictionary mapping tool names to definitions
            
        Returns:
            List of tool names that strongly match direct intents (ordered by confidence)
        """
        direct_tools = []
        query_lower = query.lower()
        
        # Help commands
        help_phrases = ['help', 'what can you do', 'commands', 'capabilities']
        if any(phrase in query_lower for phrase in help_phrases):
            if 'help' in tool_dict:
                return ['help']  # Return only help tool for help commands
        
        # GitHub repository requests
        if ('repos' in query_lower or 'repositories' in query_lower) and \
           ('my' in query_lower or 'list' in query_lower or 'show' in query_lower):
            if 'github_list_repositories' in tool_dict:
                direct_tools.append('github_list_repositories')
        
        # Jira ticket requests  
        if ('jira' in query_lower or 'tickets' in query_lower or 'issues' in query_lower) and \
           ('my' in query_lower):
            if 'jira_get_issues_by_user' in tool_dict:
                direct_tools.append('jira_get_issues_by_user')
        
        # Jira project listing requests
        if (('jira' in query_lower or 'tickets' in query_lower or 'issues' in query_lower) and 
            ('project' in query_lower or re.search(r'\b[A-Z][A-Z0-9_]{1,15}\b', query))) and not \
            any(kw in query_lower for kw in my_keywords): # Avoid clash with "my issues"
            if 'jira_get_issues_by_project' in tool_dict and 'jira_get_issues_by_project' not in direct_tools:
                direct_tools.append('jira_get_issues_by_project')
        
        # Code search requests
        if 'search' in query_lower and 'code' in query_lower:
            for tool in ['greptile_search_code', 'github_search_code']:
                if tool in tool_dict and tool not in direct_tools:
                    direct_tools.append(tool)
        
        # Web search requests
        if any(phrase in query_lower for phrase in ['what is', 'tell me about', 'search for']):
            if 'perplexity_web_search' in tool_dict:
                direct_tools.append('perplexity_web_search')
        
        return direct_tools
    
    def _extract_query_categories(self, query: str) -> List[str]:
        """
        Extract likely categories from the query.
        
        Args:
            query: The user query
            
        Returns:
            List of category names
        """
        categories = []
        query_lower = query.lower()
        
        # Category patterns
        category_patterns = {
            'github': [r'github', r'repo', r'pull request', r'pr', r'issue', r'commit'],
            'jira': [r'jira', r'ticket', r'issue', r'sprint', r'story', r'epic'],
            'greptile': [r'code search', r'codebase', r'search code', r'semantic search'],
            'perplexity': [r'search online', r'web search', r'internet', r'latest', r'current'],
            'file_operations': [r'file', r'read file', r'write file', r'directory'],
            'database': [r'database', r'sql', r'query', r'table']
        }
        
        for category, patterns in category_patterns.items():
            if any(re.search(pattern, query_lower) for pattern in patterns):
                categories.append(category)
        
        return categories
    
    def _get_tool_categories(self, tool_name: str, tool_def: Dict[str, Any]) -> List[str]:
        """
        Get categories for a tool from its metadata.
        
        Args:
            tool_name: Name of the tool
            tool_def: Tool definition dictionary
            
        Returns:
            List of category names
        """
        categories = []
        
        # First check metadata
        metadata = tool_def.get('metadata', {})
        if metadata and 'categories' in metadata and isinstance(metadata['categories'], list):
            categories.extend(metadata['categories'])
        
        # Fallback: Infer from name prefix
        if not categories and '_' in tool_name:
            prefix = tool_name.split('_')[0]
            if prefix in ['github', 'jira', 'greptile', 'perplexity']:
                categories.append(prefix)
        
        return categories

    def find_similar_tools(
        self, 
        query: str, 
        threshold: float = 0.3, 
        max_results: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find tools similar to a query based on embedding similarity.
        
        Args:
            query: The search query
            threshold: Minimum similarity score to include a tool
            max_results: Maximum number of results to return
            
        Returns:
            List of (tool_name, similarity_score) tuples
        """
        if not ML_DEPENDENCIES_AVAILABLE or not self.embedding_model:
            log.warning("ML dependencies not available or embedding model not initialized. Cannot find similar tools.")
            return []
        
        # Handle empty embeddings dictionary
        if not self.tool_embeddings:
            log.warning("Tool embeddings not loaded. Cannot find similar tools.")
            return []
            
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query)
        
        # Calculate similarity for all tools
        similarities = []
        for tool_name, tool_embedding_data in self.tool_embeddings.items():
            if not np:
                continue
                
            tool_embedding = np.array(tool_embedding_data) \
                if isinstance(tool_embedding_data, list) \
                else tool_embedding_data
                
            # Skip invalid embeddings
            if not isinstance(tool_embedding, np.ndarray) or tool_embedding.ndim == 0:
                continue
                
            # Calculate cosine similarity
            norm_query = np.linalg.norm(query_embedding)
            norm_tool = np.linalg.norm(tool_embedding)
            
            if norm_query == 0 or norm_tool == 0:
                similarity = 0.0
            else:
                similarity = np.dot(query_embedding, tool_embedding) / (norm_query * norm_tool)
                
            if similarity >= threshold:
                similarities.append((tool_name, float(similarity)))
                
        # Sort by similarity (highest first) and return top results
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:max_results]
