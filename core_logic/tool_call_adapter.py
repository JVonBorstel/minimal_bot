"""
Tool Call Adapter for bridging between LLM service-level tool calls and detailed internal tool implementations.

This module addresses the mismatch between the LLM's simplified tool calls (e.g., "github") and 
the internal detailed tool implementations (e.g., "github_get_repo_details").
"""

import asyncio
import logging
import inspect
import json
import uuid
from typing import Dict, List, Any, Optional, Callable, Tuple, Union, cast

from config import Config
from tools.tool_executor import ToolExecutor
from state_models import AppState  # ToolSelectionRecord moved to user_auth.models
from user_auth.models import ToolSelectionRecord # Import from new location
from bot_core.tool_management.tool_models import ToolCallResult, ToolCallRequest

log = logging.getLogger("core_logic.tool_call_adapter")

class ToolCallAdapter:
    """
    Adapts LLM service-level tool calls to actual detailed tool implementations.
    
    This adapter bridges the gap between:
    1. The LLM's simplified service-level tool calls (e.g., "github" with parameters)
    2. The actual internal detailed tool implementations (e.g., "github_get_repo_details")
    
    It uses parameter matching and historical success data to select the most appropriate 
    detailed tool for a given service-level call.
    """
    
    # Define parameter mappings at the class level for reuse
    DEFAULT_PARAM_MAPPINGS: Dict[str, List[str]] = {
        "owner": ["user", "username", "user_name", "org", "organization"],
        "repository_name": ["repo", "repo_name", "repository"],
        "issue_id": ["issue", "issue_number", "number", "ticket_id"],
        "branch_name": ["branch"],
        "file_path": ["file", "filename", "file_name", "path"],
        "message": ["description", "comment", "text", "content"],
        "query": ["search", "q", "search_query", "search_term"],
        # Add other common mappings as needed
    }
    
    # Maximum number of selection records to store to prevent unbounded growth
    MAX_SELECTION_RECORDS = 100
    
    # Maximum score bonus that can be awarded based on historical data (0.0-2.0)
    MAX_HISTORY_BONUS = 2.0
    
    # Maximum score bonus that can be awarded based on tool importance (0.0-1.5)
    MAX_IMPORTANCE_BONUS = 1.5
    
    # Number of similar tool calls required to reach maximum confidence factor
    HISTORY_CONFIDENCE_THRESHOLD = 5

    def __init__(self, tool_executor: ToolExecutor, config: Config):
        """
        Initialize the ToolCallAdapter.
        
        Args:
            tool_executor: The ToolExecutor instance that manages detailed tools.
            config: The application configuration.
        """
        self.tool_executor = tool_executor
        self.config = config
        self.tool_map = self._build_tool_map()
        self.param_mappings = self.DEFAULT_PARAM_MAPPINGS.copy()
        log.info(f"ToolCallAdapter initialized with {len(self.tool_map)} service mappings")
        for service, tools in self.tool_map.items():
            log.debug(f"Service '{service}' has {len(tools)} mapped tools")
    
    def _build_tool_map(self) -> Dict[str, List[str]]:
        """
        Maps simplified service names to lists of available detailed tool names.
        
        For example, "github" -> ["github_list_repositories", "github_get_repo", etc.]
        
        Returns:
            A dictionary mapping service names to lists of detailed tool names.
        """
        tool_map: Dict[str, List[str]] = {}
        
        for tool_name in self.tool_executor.get_available_tool_names():
            # Extract service name (e.g., "github" from "github_list_repositories")
            # Handle names without underscores as their own service
            service = tool_name.split('_')[0] if '_' in tool_name else tool_name
            
            if service not in tool_map:
                tool_map[service] = []
            tool_map[service].append(tool_name)
        
        return tool_map

    def _normalize_param_name(self, name: str) -> str:
        """Normalizes a parameter name for fuzzy matching by lowercasing and removing underscores/hyphens."""
        return name.lower().replace("_", "").replace("-", "")

    def _normalize_query_string(self, params: Dict[str, Any]) -> str:
        """
        Normalize parameters into a consistent query string for comparison.
        
        Args:
            params: The parameters to normalize
            
        Returns:
            A normalized query string
        """
        # Sort parameters by key to ensure consistent ordering
        query_params = sorted([f"{k}={v}" for k, v in params.items()])
        return "&".join(query_params)
    
    def _determine_success(self, tool_result: Any) -> bool:
        """
        Determine if a tool execution was successful based on the result.
        
        Args:
            tool_result: The result from tool execution
            
        Returns:
            True if success, False otherwise
        """
        if isinstance(tool_result, dict):
            return tool_result.get("status", "") == "success"
        elif isinstance(tool_result, ToolCallResult):
            return tool_result.status == "success"
        else:
            return False
    
    async def process_llm_tool_call(self, tool_call: Dict[str, Any], app_state: Optional[AppState]) -> Any:
        """
        Process an LLM service-level tool call and route to the correct implementation.
        
        Args:
            tool_call: The tool call from the LLM, including name (service) and parameters.
                Expected format: {"name": "service", "params": {...}}
            app_state: The current application state, for learning and context.
        
        Returns:
            The result from the selected detailed tool implementation.
        """
        # Extract service name and parameters from the LLM's tool call
        service = tool_call.get("name", "").lower()
        params = tool_call.get("params", {})
        
        if not service:
            log.error("Cannot process tool call: Missing service name")
            return {"status": "ERROR", "message": "Missing service name in tool call"}
        
        log.info(f"Processing tool call for service: '{service}' with {len(params)} parameters")
        log.debug(f"Parameters: {params}")
        
        # Check if the service exists in our mapping
        if service not in self.tool_map:
            log.warning(f"Unknown tool service: {service}")
            # Record failed selection if app_state is available (for overall metrics)
            if app_state:
                await self._record_selection_outcome(app_state, self._normalize_query_string(params), selected_tool=None, used_tool=None, success=False)
            return {"status": "ERROR", "message": f"Unknown tool service: {service}"}
        
        # Normalize query string for historical comparison
        query_string = self._normalize_query_string(params)
        
        # Keep original input for context
        original_input = {
            "service": service,
            "params": params.copy()
        }
        
        # Select the appropriate detailed tool based on service, parameters, and historical data
        selected_tool = await self._select_tool(service, params, query_string, app_state)
        if not selected_tool:
            log.warning(f"Could not determine specific tool for service '{service}' with params {params}")
            
            # Get list of candidate tools to include in error message
            candidate_tools = self.tool_map.get(service, [])
            tools_str = ", ".join(candidate_tools[:5])
            if len(candidate_tools) > 5:
                tools_str += f", ... ({len(candidate_tools) - 5} more)"
            
            # Record failed selection if app_state is available
            if app_state:
                await self._record_selection_outcome(app_state, query_string, selected_tool=None, used_tool=None, success=False)
                
            return {
                "status": "ERROR", 
                "message": f"Could not determine specific tool for {service} with the provided parameters. Available tools: {tools_str}",
                "original_input": original_input
            }
        
        log.info(f"Selected tool: '{selected_tool}' for service: '{service}'")
        
        # Execute the selected tool with the provided parameters
        # Parameters might need transformation depending on the selected tool
        transformed_params = self._transform_parameters(selected_tool, params)
        log.debug(f"Transformed parameters for '{selected_tool}': {transformed_params}")

        # Construct a ToolCallRequest for the executor
        # The 'tool_call' dict passed to process_llm_tool_call is expected to have an 'id' field (tool_call_id from LLM).
        original_call_id = tool_call.get("id")
        if not original_call_id:
            # Fallback if ID is missing, though LLMProcessor should provide it.
            original_call_id = f"adapter_gen_{uuid.uuid4().hex[:8]}"
            log.warning(f"Missing 'id' in tool_call for adapter, generated: {original_call_id}")

        request_for_executor = ToolCallRequest(
            tool_name=selected_tool,
            parameters=transformed_params,
            tool_call_id=original_call_id
        )
        
        tool_result = await self.tool_executor.execute_tool(
            tool_name=selected_tool, 
            tool_input=transformed_params
        )
        
        # Record the outcome if app_state is available
        if app_state:
            success = self._determine_success(tool_result)
            await self._record_selection_outcome(app_state, query_string, selected_tool, used_tool=selected_tool, success=success)
        
        # Enhance tool result with context of the original request and adapter decisions
        if isinstance(tool_result, dict):
            # Preserve all existing result data
            enhanced_result = tool_result.copy()
            
            # Add adapter context if not already present
            if "adapter_context" not in enhanced_result:
                enhanced_result["adapter_context"] = {
                    "original_service": service,
                    "selected_tool": selected_tool,
                    "parameter_transformation": {
                        "original": params,
                        "transformed": transformed_params
                    }
                }
            return enhanced_result
        
        # If result is not a dict (like ToolCallResult), return as is
        return tool_result
    
    async def _select_tool(self, service: str, params: Dict[str, Any], query_string: str, app_state: Optional[AppState]) -> Optional[str]:
        """
        Selects the most appropriate detailed tool for a given service and parameters.
        
        Args:
            service: The simplified service name (e.g., "github")
            params: The parameters provided by the LLM
            query_string: A normalized string representation of the parameters for historical comparison
            app_state: The current application state for fetching historical data.
        
        Returns:
            The selected detailed tool name, or None if no suitable tool is found.
        """
        candidate_tools = self.tool_map.get(service, [])
        if not candidate_tools:
            return None
        
        # Get tool definitions to analyze their parameters
        tool_defs = self.tool_executor.get_available_tool_definitions()
        tools_defs_dict = {t["name"]: t for t in tool_defs}
        
        # Score each candidate tool based on parameter match and historical success
        scores: Dict[str, float] = {}
        for tool_name in candidate_tools:
            tool_def = tools_defs_dict.get(tool_name)
            if not tool_def:
                continue
            
            # Basic parameter match score
            base_score = self._calculate_tool_match_score(tool_def, params)
            
            # Apply historical success bonus if app_state is available
            history_bonus = 0.0
            if app_state:
                history_bonus = await self._get_historical_success_bonus(tool_name, query_string, app_state)
            
            # Apply tool importance bonus
            importance_bonus = 0.0
            tool_metadata = tool_def.get("metadata", {})
            tool_importance = tool_metadata.get("importance", 5) # Default to mid-importance (5) if not specified
            importance_bonus = (tool_importance / 10.0) * self.MAX_IMPORTANCE_BONUS

            # Combine scores (base score plus history bonus and importance bonus)
            scores[tool_name] = base_score + history_bonus + importance_bonus
            log.debug(f"Tool '{tool_name}' match score: base={base_score:.2f}, history={history_bonus:.2f}, importance={importance_bonus:.2f}, total={scores[tool_name]:.2f}")
        
        # No tools with scores
        if not scores:
            return None
        
        # Find the tool with the highest score
        best_tool = max(scores.items(), key=lambda x: x[1])[0]
        best_score = scores[best_tool]
        
        # Only return the tool if it has a minimum viable score
        # (If the score is 0, it's not a viable match)
        if best_score <= 0:
            log.warning(f"Best tool '{best_tool}' has score 0, which indicates no viable parameter matches")
            return None
            
        return best_tool
    
    async def _get_historical_success_bonus(self, tool_name: str, query_string: str, app_state: AppState) -> float:
        """
        Calculates a score bonus based on historical success with this tool for similar queries.
        
        Args:
            tool_name: The detailed tool name being considered
            query_string: A normalized string representation of the current parameters
            app_state: The AppState object containing historical data.
        
        Returns:
            A score bonus (0.0-2.0) to add to the base match score
        """
        try:
            if not app_state or not app_state.current_user or not app_state.current_user.tool_adapter_metrics:
                return 0.0
                
            target_metrics = app_state.current_user.tool_adapter_metrics
            
            # Look for records with similar query parameters
            similar_records = [
                record for record in target_metrics.selection_records
                if record.query == query_string and tool_name in record.selected_tools
            ]
            
            if not similar_records:
                return 0.0
                
            # Calculate average success rate for this tool with similar parameters
            success_rates = [record.success_rate for record in similar_records if record.success_rate is not None]
            if not success_rates:
                return 0.0
                
            avg_success_rate = sum(success_rates) / len(success_rates)
            
            # Scale the bonus based on:
            # 1. Success rate (0.0-1.0)
            # 2. Number of records (more records = more confidence)
            confidence_factor = min(len(similar_records) / self.HISTORY_CONFIDENCE_THRESHOLD, 1.0)
            
            # Calculate bonus (0.0 to MAX_HISTORY_BONUS) 
            history_bonus = avg_success_rate * self.MAX_HISTORY_BONUS * confidence_factor
            
            log.debug(f"History bonus for '{tool_name}': {history_bonus:.2f} (based on {len(similar_records)} records, avg success {avg_success_rate:.2f})")
            return history_bonus
            
        except Exception as e:
            log.error(f"Error calculating historical success bonus: {e}", exc_info=True)
            return 0.0
    
    async def _record_selection_outcome(self, app_state: AppState, query_string: str, selected_tool: Optional[str], used_tool: Optional[str], success: bool) -> None:
        """
        Records the outcome of a tool selection for future learning.
        
        Args:
            app_state: The AppState object to update.
            query_string: A normalized string representation of the parameters
            selected_tool: The tool that was selected by the adapter (may be None if selection failed)
            used_tool: The tool that was actually used (may be None if execution failed)
            success: Whether the tool execution was successful
        """
        try:
            if not app_state or not app_state.current_user:
                return

            # Ensure tool_adapter_metrics exists on current_user (it should have a default_factory)
            if not hasattr(app_state.current_user, 'tool_adapter_metrics') or app_state.current_user.tool_adapter_metrics is None:
                log.error("UserProfile.tool_adapter_metrics is missing or None. Cannot record outcome.")
                # Potentially initialize it here if absolutely necessary, but default_factory should handle it.
                # from state_models import ToolSelectionMetrics # Would need this import if initializing here
                # app_state.current_user.tool_adapter_metrics = ToolSelectionMetrics()
                return

            target_metrics = app_state.current_user.tool_adapter_metrics
                
            # Prepare the selection record
            selection_record = ToolSelectionRecord(
                query=query_string,
                selected_tools=[selected_tool] if selected_tool else [],
                used_tools=[used_tool] if used_tool else [],
                success_rate=1.0 if success else 0.0
            )
            
            # Update metrics
            target_metrics.total_selections += 1
            if success:
                target_metrics.successful_selections += 1
            
            # Add to selection history (keep limited number)
            # Ensure selection_records list exists
            if not isinstance(target_metrics.selection_records, list):
                target_metrics.selection_records = []
                
            target_metrics.selection_records.append(selection_record) # Append first
            max_records = self.config.settings.get("tool_adapter_max_selection_records", self.MAX_SELECTION_RECORDS)
            if len(target_metrics.selection_records) > max_records:
                target_metrics.selection_records = target_metrics.selection_records[-max_records:]
            
            # Persist updated state - NO LONGER DONE HERE. Agent loop handles saving AppState.
            # The calling code will be responsible for saving UserProfile if metrics changed.
            # This method should probably return a flag if metrics were indeed updated.
            
            log.info(f"Recorded tool selection outcome for user {app_state.current_user.user_id}: {query_string} -> {selected_tool or 'None'} -> {success} (UserProfile metrics updated)")
            
        except Exception as e:
            log.error(f"Error recording selection outcome: {e}", exc_info=True)
    
    def _calculate_tool_match_score(self, tool_def: Dict[str, Any], params: Dict[str, Any]) -> float:
        """
        Calculate how well the provided parameters match a tool's expected parameters.
        
        Args:
            tool_def: The tool definition dictionary
            params: The parameters provided by the LLM
        
        Returns:
            A score indicating how well the parameters match (higher is better)
        """
        score = 0.0
        if "parameters" not in tool_def or "properties" not in tool_def["parameters"]:
            return 0.1 if not params else 0.0

        tool_expected_params_schema = tool_def["parameters"].get("properties", {})
        required_tool_params = tool_def["parameters"].get("required", [])

        # --- Determine effectively provided parameters (for required check) ---
        effectively_provided_params = set() # Stores canonical names of provided required params
        llm_params_normalized_map = {self._normalize_param_name(k): k for k in params.keys()}

        for req_param_canon in required_tool_params:
            # 1. Direct match with canonical name
            if req_param_canon in params:
                effectively_provided_params.add(req_param_canon)
                continue
            
            # 2. Check defined aliases
            found_by_alias = False
            for alias in self.param_mappings.get(req_param_canon, []):
                if alias in params:
                    effectively_provided_params.add(req_param_canon)
                    found_by_alias = True
                    break
            if found_by_alias:
                continue
            
            # 3. Check normalized canonical name against normalized LLM keys
            norm_req_param_canon = self._normalize_param_name(req_param_canon)
            if norm_req_param_canon in llm_params_normalized_map:
                llm_actual_key = llm_params_normalized_map[norm_req_param_canon]
                effectively_provided_params.add(req_param_canon)
                log.debug(f"Tool '{tool_def['name']}': Required param '{req_param_canon}' matched via normalization to LLM param '{llm_actual_key}'.")
                continue
        
        # Check if any required parameters are TRULY missing after all checks (including inference)
        truly_missing_required = []
        for req_param_canon in required_tool_params:
            if req_param_canon not in effectively_provided_params:
                can_be_inferred = False
                # Inference for 'repository_name' from 'owner'
                if req_param_canon == "repository_name":
                    owner_param_value = None
                    possible_owner_keys_direct = ["owner"] # Check canonical first
                    possible_owner_keys_alias = self.param_mappings.get("owner", [])
                    
                    # Check direct LLM param keys
                    for p_key in possible_owner_keys_direct + possible_owner_keys_alias:
                        if p_key in params:
                            owner_param_value = params[p_key]
                            break
                    # If not found by direct/alias, check normalized LLM keys
                    if owner_param_value is None:
                        norm_owner_canon = self._normalize_param_name("owner")
                        if norm_owner_canon in llm_params_normalized_map:
                             owner_param_value = params[llm_params_normalized_map[norm_owner_canon]]

                    if owner_param_value and isinstance(owner_param_value, str) and "/" in owner_param_value:
                        parts = owner_param_value.split("/", 1)
                        if len(parts) == 2 and parts[1]: 
                            can_be_inferred = True
                            log.debug(f"Tool '{tool_def['name']}': Required param '{req_param_canon}' provisionally inferred from 'owner' value '{owner_param_value}' for scoring.")
                
                if not can_be_inferred:
                    truly_missing_required.append(req_param_canon)
        
        if truly_missing_required:
            log.debug(f"Tool '{tool_def['name']}' effectively missing required parameters for scoring after all checks: {truly_missing_required} (Original LLM params: {list(params.keys())})")
            return 0.0

        # Start with a base score of 1.0 if all required parameters are present (or inferable)
        score = 1.0

        # Bonus for action/method parameter matching tool name
        action_param_from_llm = None
        # Check direct, alias, and normalized for "action" or "method"
        action_keys_to_check = ["action", "method"]
        normalized_action_keys = [self._normalize_param_name(k) for k in action_keys_to_check]

        for llm_key, llm_value in params.items():
            if llm_key in action_keys_to_check:
                action_param_from_llm = llm_value
                break
            if self._normalize_param_name(llm_key) in normalized_action_keys:
                action_param_from_llm = llm_value
                break
        
        if action_param_from_llm and isinstance(action_param_from_llm, str) and action_param_from_llm.lower() in tool_def["name"].lower():
            score += 2.0
        
        # --- Count matched parameters (direct, alias, or normalized) ---
        matched_param_count = 0
        # To avoid double counting if multiple tool params map to the same LLM param, or LLM sends redundant params
        llm_params_already_used_for_match = set()

        for tool_param_canon in tool_expected_params_schema.keys():
            matched_this_tool_param = False
            # 1. Direct match with canonical tool parameter name
            if tool_param_canon in params and tool_param_canon not in llm_params_already_used_for_match:
                matched_param_count += 1
                llm_params_already_used_for_match.add(tool_param_canon)
                matched_this_tool_param = True
            if matched_this_tool_param:
                continue

            # 2. Check defined aliases for the canonical tool parameter
            for alias in self.param_mappings.get(tool_param_canon, []):
                if alias in params and alias not in llm_params_already_used_for_match:
                    matched_param_count += 1
                    llm_params_already_used_for_match.add(alias)
                    matched_this_tool_param = True
                    break 
            if matched_this_tool_param:
                continue

            # 3. Check normalized canonical tool_param_name against normalized LLM keys
            norm_tool_param_canon = self._normalize_param_name(tool_param_canon)
            if norm_tool_param_canon in llm_params_normalized_map:
                original_llm_key = llm_params_normalized_map[norm_tool_param_canon]
                if original_llm_key not in llm_params_already_used_for_match:
                    matched_param_count += 1
                    llm_params_already_used_for_match.add(original_llm_key)
                    log.debug(f"Tool '{tool_def['name']}': Tool param '{tool_param_canon}' matched to LLM param '{original_llm_key}' via normalization for scoring count.")
                    # matched_this_tool_param = True # Not strictly needed here as we continue outer loop
                # We don't 'continue' here as this tool_param_canon is now considered matched.
                # The 'continue' statements above are to move to the next tool_param_canon.
                # This means if a param is matched by normalization, it's counted.
        
        # Add points for matched parameters
        score += matched_param_count
        return score
    
    def _transform_parameters(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform parameters from the LLM's format to match the selected tool's expected format.
        
        Args:
            tool_name: The name of the selected tool
            params: The parameters provided by the LLM
            
        Returns:
            Transformed parameters that match the tool's expected schema
        """
        tool_defs = self.tool_executor.get_available_tool_definitions()
        tool_def = next((t for t in tool_defs if t.get("name") == tool_name), None)

        if not tool_def or "parameters" not in tool_def or "properties" not in tool_def["parameters"]:
            log.warning(f"Tool '{tool_name}' has no parameter schema. Passing LLM params as-is.")
            return params.copy() 

        tool_expected_params_schema = tool_def["parameters"].get("properties", {})
        transformed: Dict[str, Any] = {}
        llm_params_used = set()
        
        # Track which required parameters are still missing after transformations
        required_params = tool_def["parameters"].get("required", [])
        missing_required_params = set(required_params)

        # 1. Exact matches for tool's expected parameters found in LLM params
        for tool_param_name in tool_expected_params_schema:
            if tool_param_name in params:
                transformed[tool_param_name] = params[tool_param_name]
                llm_params_used.add(tool_param_name)
                if tool_param_name in missing_required_params:
                    missing_required_params.remove(tool_param_name)
        
        # 2. Enhanced mapped variations for tool's expected parameters with type validation
        for tool_param_name, llm_variations in self.param_mappings.items():
            if tool_param_name in tool_expected_params_schema and tool_param_name not in transformed:
                for llm_var in llm_variations:
                    if llm_var in params and llm_var not in llm_params_used:
                        param_value = params[llm_var]
                        # Check parameter value against expected type
                        param_schema = tool_expected_params_schema.get(tool_param_name, {})
                        expected_type = param_schema.get("type")
                        
                        # Type validation and coercion
                        if expected_type == "string" and not isinstance(param_value, str):
                            log.debug(f"Converting parameter '{llm_var}' value to string for '{tool_param_name}'")
                            param_value = str(param_value)
                        elif expected_type == "integer" and isinstance(param_value, str) and param_value.isdigit():
                            log.debug(f"Converting string parameter '{llm_var}' value to integer for '{tool_param_name}'")
                            param_value = int(param_value)
                        elif expected_type == "boolean" and isinstance(param_value, str):
                            if param_value.lower() in ("true", "yes", "1"):
                                param_value = True
                            elif param_value.lower() in ("false", "no", "0"):
                                param_value = False
                        
                        transformed[tool_param_name] = param_value
                        llm_params_used.add(llm_var)
                        if tool_param_name in missing_required_params:
                            missing_required_params.remove(tool_param_name)
                        log.debug(f"Mapped LLM param '{llm_var}' to tool param '{tool_param_name}' for tool '{tool_name}'")
                        break
        
        # 3. Special parameters (action, method, operation)
        special_llm_params = ["action", "method", "operation"]
        for special_param_name in special_llm_params:
            if special_param_name in params and special_param_name in tool_expected_params_schema and special_param_name not in transformed:
                transformed[special_param_name] = params[special_param_name]
                llm_params_used.add(special_param_name)
                if special_param_name in missing_required_params:
                    missing_required_params.remove(special_param_name)
                log.debug(f"Copied LLM param '{special_param_name}' as it is expected by tool '{tool_name}'")

        # 4. Any remaining parameters that match the schema
        for llm_param_name, llm_param_value in params.items():
            if llm_param_name not in llm_params_used and llm_param_name in tool_expected_params_schema and llm_param_name not in transformed:
                transformed[llm_param_name] = llm_param_value
                if llm_param_name in missing_required_params:
                    missing_required_params.remove(llm_param_name)
                log.debug(f"Included additional LLM param '{llm_param_name}' as it is defined in tool '{tool_name}' schema and not yet transformed.")
        
        # 5. Default values for missing required parameters
        for param_name in missing_required_params.copy():
            # Check if the schema provides a default value
            param_schema = tool_expected_params_schema.get(param_name, {})
            if "default" in param_schema:
                transformed[param_name] = param_schema["default"]
                missing_required_params.remove(param_name)
                log.debug(f"Applied default value for required parameter '{param_name}' from schema")
        
        # 6. Context-aware parameter inference for common patterns
        if missing_required_params:
            for param_name in missing_required_params.copy():
                # Infer parameters from context when possible
                if param_name == "repository_name" and "owner" in transformed:
                    # Check if owner contains a repo reference like "owner/repo"
                    owner_val = transformed["owner"]
                    if isinstance(owner_val, str) and "/" in owner_val:
                        parts = owner_val.split("/", 1)
                        if len(parts) == 2 and parts[1]:
                            transformed["owner"] = parts[0]
                            transformed[param_name] = parts[1]
                            missing_required_params.remove(param_name)
                            log.debug(f"Inferred '{param_name}' from 'owner' parameter containing 'owner/repo' format")
                
                # Add more patterns as needed
        
        # 7. Log helpful debug information about any remaining missing parameters
        if missing_required_params:
            param_list_str = ", ".join(missing_required_params)
            log.warning(f"Tool '{tool_name}' is missing required parameters after transformation: {param_list_str}")
            
            # Suggest possible sources based on provided parameters
            for param_name in missing_required_params:
                potential_sources = []
                for llm_param, value in params.items():
                    if llm_param not in llm_params_used and isinstance(value, str):
                        if param_name.lower() in llm_param.lower() or param_name.replace("_", "").lower() in llm_param.replace("_", "").lower():
                            potential_sources.append(f"'{llm_param}'")
                
                if potential_sources:
                    sources_str = ", ".join(potential_sources)
                    log.info(f"Parameter '{param_name}' might be available in unused LLM parameters: {sources_str}")

        log.debug(f"Final transformed parameters for '{tool_name}': {transformed}")
        return transformed 