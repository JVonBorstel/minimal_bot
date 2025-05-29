# --- FILE: llm_interface.py ---
import logging
from typing import List, Dict, Any, Optional, Iterable, Union, TypeAlias, TYPE_CHECKING, AsyncIterable
import time
import re
import asyncio
import random
import uuid
import hashlib
import json

# Use google.api_core.exceptions for specific API errors
from google.api_core import exceptions as google_exceptions
from requests import exceptions as requests_exceptions

# Import the main Config class for type hinting and settings access
from config import Config # Assuming Config class is available

# Import text utility functions
from core_logic.text_utils import is_greeting_or_chitchat

# Import AppState for type hinting
from state_models import AppState

# Import logging utilities
from utils.logging_config import get_logger, start_llm_call, clear_llm_call_id
from utils.log_sanitizer import sanitize_data
from config import get_config # To access log_llm_interaction flag

# --- SDK Types Setup ---
SDK_AVAILABLE = False

# Define TypeAliases to Any. These will be the primary aliases used in the code.
GenerativeModelType: TypeAlias = Any
ToolType: TypeAlias = Any
PartType: TypeAlias = Any
FunctionDeclarationType: TypeAlias = Any
SchemaType: TypeAlias = Any
ContentType: TypeAlias = Union[Dict[str, Any], Any]
GenerateContentResponseType: TypeAlias = Any

# Runtime fallbacks for genai and glm modules
class _MockGlmType:
    STRING = "STRING"
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    OBJECT = "OBJECT"
    ARRAY = "ARRAY"
    NULL = "NULL"

class _MockGlm:
    Type = _MockGlmType
    Content: Any = None
    Tool: Any = None
    Part: Any = None
    FunctionDeclaration: Any = None
    Schema: Any = None

glm: Any = _MockGlm()
genai: Any = None

if TYPE_CHECKING:
    import google.ai.generativelanguage as glm_tc_
    RuntimeContentType = Union[Dict[str, Any], glm_tc_.Content]
else:
    RuntimeContentType = Union[Dict[str, Any], Any]

try:
    import google.generativeai as actual_genai
    import google.ai.generativelanguage as actual_glm

    genai = actual_genai
    glm = actual_glm
    
    SDK_AVAILABLE = True
    log_glm = logging.getLogger("google.ai.generativelanguage")
    log_glm.setLevel(logging.WARNING)

except ImportError:
    logging.getLogger(__name__).error(
        "google-generativeai SDK not found. Please install 'google-generativeai'. LLM functionality will be limited.",
        exc_info=False
    )

log = get_logger("llm_interface") # Use get_logger


class LLMInterface:
    """
    Handles interactions with the configured Google Gemini LLM API
    using the google-generativeai SDK.
    """

    def __init__(self, config: Config):
        if not SDK_AVAILABLE:
            raise ImportError("google-generativeai SDK is required but not installed.")

        self.config = config
        self.api_key: str = config.GEMINI_API_KEY
        self.model_name: str = config.GEMINI_MODEL
        self.timeout: int = config.DEFAULT_API_TIMEOUT_SECONDS
        
        # Lazy import ToolSelector to avoid circular imports
        try:
            from core_logic.tool_selector import ToolSelector
            self.tool_selector = ToolSelector(config)
        except ImportError as e:
            log.warning(f"Could not import ToolSelector: {e}. Tool selection will be disabled.")
            # Create a mock tool selector with minimal interface
            class MockToolSelector:
                def __init__(self):
                    self.enabled = False
                def select_tools(self, *args, **kwargs):
                    return []
            self.tool_selector = MockToolSelector()
            
        self.response_cache: Dict[str, List[Dict[str,Any]]] = {} # In-memory cache for full responses
        self.CACHE_MAX_SIZE = 50 # Simple max size for the cache
        self.CACHE_ENABLED = True # TODO: Make this configurable via self.config if needed

        try:
            genai.configure(api_key=self.api_key)
            log.info(f"google-genai SDK configured successfully. Default Model: {self.model_name}, Request Timeout: {self.timeout}s")
            
            # Try to create model with system instruction first
            try:
                self.model = genai.GenerativeModel(
                    self.model_name,
                    system_instruction=self.config.DEFAULT_SYSTEM_PROMPT
                )
                log.info("Model initialized with system instruction")
            except Exception as e:
                # If system_instruction fails, create model without it
                log.warning(f"Failed to create model with system_instruction: {e}. Creating without system instruction.")
                self.model = genai.GenerativeModel(self.model_name)
                log.info("Model initialized without system instruction")
                
        except google_exceptions.GoogleAPIError as e:
            log.error(f"google-genai SDK configuration failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to configure google-genai SDK: {e}") from e
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during SDK configuration: {e}", exc_info=True)
            raise RuntimeError(f"Network failure during SDK configuration: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error during SDK configuration: {e}", exc_info=True)
            raise RuntimeError(f"Failed to configure google-genai SDK: {e}") from e

    def update_model(self, model_name: str) -> None:
        if not model_name or not isinstance(model_name, str) or model_name.strip() == "":
            log.warning("Attempted to set an empty or invalid model name. No change made.")
            return

        if model_name == self.model_name:
            log.debug(f"Model '{model_name}' is already selected.")
            return

        log.info(f"Updating LLM model from '{self.model_name}' to '{model_name}'")
        prev_model = self.model
        prev_model_name = self.model_name
        
        try:
            # Try to create model with system instruction first
            try:
                self.model = genai.GenerativeModel(
                    model_name,
                    system_instruction=self.config.DEFAULT_SYSTEM_PROMPT
                )
                log.debug("Model updated with system instruction")
            except Exception as e:
                # If system_instruction fails, create model without it
                log.warning(f"Failed to update model with system_instruction: {e}. Creating without system instruction.")
                self.model = genai.GenerativeModel(model_name)
                log.debug("Model updated without system instruction")
                
            self.model_name = model_name
            log.info(f"Successfully updated LLM client to use model: {self.model_name}")
        except (google_exceptions.NotFound, google_exceptions.InvalidArgument) as e:
             log.error(f"Failed to update to model '{model_name}'. It might be invalid or inaccessible: {e}", exc_info=True)
             log.warning(f"Reverting to previous model: {prev_model_name}")
             self.model = prev_model
             self.model_name = prev_model_name
             raise ValueError(f"Invalid or inaccessible model name: {model_name}") from e
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during model update to '{model_name}': {e}", exc_info=True)
            log.warning(f"Reverting to previous model: {prev_model_name}")
            self.model = prev_model
            self.model_name = prev_model_name
            raise RuntimeError(f"Network failure during model update: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error updating model client to '{model_name}': {e}", exc_info=True)
            log.warning(f"Reverting to previous model: {prev_model_name}")
            self.model = prev_model
            self.model_name = prev_model_name
            raise RuntimeError(f"Failed to update LLM model client: {e}") from e

    def _get_glm_type_enum(self, type_str: str) -> Any:
        type_mapping = {
            "string": glm.Type.STRING,
            "number": glm.Type.NUMBER,
            "integer": glm.Type.INTEGER,
            "boolean": glm.Type.BOOLEAN,
            "object": glm.Type.OBJECT,
            "array": glm.Type.ARRAY,
        }
        default_type = glm.Type.STRING
        glm_type = type_mapping.get(type_str.lower(), default_type)
        if glm_type == default_type and type_str.lower() not in type_mapping:
            log.warning(f"Unsupported schema type '{type_str}'. Defaulting to {default_type.name}.")
        return glm_type

    def _convert_parameters_to_schema(self, tool_name: str, parameters: Dict[str, Any]) -> Optional[SchemaType]:
        if not parameters:
            log.debug(f"Tool '{tool_name}': No parameters provided, returning None for schema.")
            return None
            
        if not isinstance(parameters, dict):
            log.warning(f"Tool '{tool_name}': Invalid parameters format (not a dict): {type(parameters)}. Returning None.")
            return None

        # Handle individual parameter schemas (those with anyOf, oneOf, etc.)
        if "anyOf" in parameters or "oneOf" in parameters or "allOf" in parameters:
            # This is an individual parameter schema, not a full parameters object
            return self._convert_individual_parameter_to_schema(tool_name, parameters)

        # Handle top-level parameters schema
        if parameters.get("type") != "object" or "properties" not in parameters:
            log.warning(f"Tool '{tool_name}': Invalid parameter structure. Expected 'type: object' with 'properties'. Got: {parameters}. Returning empty object schema.")
            return glm.Schema(type_=glm.Type.OBJECT, properties={})

        try:
            # Access schema optimization settings from config
            schema_opt_config = self.config.SCHEMA_OPTIMIZATION
            max_tool_props = 999 # Effectively disable property limit for now
            max_desc_len = 9999 # Effectively disable description truncation for now
            max_enum_vals = 999 # Effectively disable enum limiting for now
            max_nested_obj_props = 99 # Effectively disable nested object limits for now
            max_array_item_obj_props = 99 # Effectively disable array item limits for now
            
            schema_props = {}
            required_params = parameters.get("required", [])
            props = parameters.get("properties", {})

            if not isinstance(props, dict):
                log.warning(f"Tool '{tool_name}': Properties is not a dictionary: {type(props)}. Returning empty schema.")
                return glm.Schema(type_=glm.Type.OBJECT, properties={})

            for prop_name, prop_details in props.items():
                # CRITICAL FIX: Skip AppState and other complex state parameters
                if prop_name in ['app_state', 'config', 'tool_config'] or 'state' in prop_name.lower():
                    log.debug(f"Tool '{tool_name}': Skipping complex state parameter '{prop_name}'")
                    continue
                    
                if not isinstance(prop_details, dict):
                    log.warning(f"Tool '{tool_name}': Skipping invalid property '{prop_name}'. Reason: Not a dict. Details: {prop_details}")
                    continue

                # Convert individual parameter schema to glm.Schema
                try:
                    param_schema = self._convert_individual_parameter_to_schema(f"{tool_name}.{prop_name}", prop_details)
                    if param_schema:
                        schema_props[prop_name] = param_schema
                except Exception as e:
                    log.error(f"Tool '{tool_name}', Property '{prop_name}': Failed to create property schema: {e}. Skipping property.", exc_info=True)
                    continue

            final_schema_args = {"type_": glm.Type.OBJECT, "properties": schema_props}
            if required_params: 
                # Filter required params to only include properties that were actually added
                valid_required = [req for req in required_params if req in schema_props]
                if valid_required:
                    final_schema_args["required"] = valid_required
                
            return glm.Schema(**final_schema_args)

        except Exception as e:
            log.error(f"Tool '{tool_name}': Error converting parameters dictionary to glm.Schema: {e}\nParameters: {parameters}", exc_info=True)
            return glm.Schema(type_=glm.Type.OBJECT, properties={}) # Fallback to empty object schema

    def _convert_individual_parameter_to_schema(self, param_name: str, param_details: Dict[str, Any]) -> Optional[SchemaType]:
        """
        Convert an individual parameter schema to a glm.Schema.
        Handles both simple types and complex schemas with anyOf/oneOf/allOf.
        """
        try:
            # Conditional description truncation (effectively disabled)
            max_desc_len = 9999
            max_enum_vals = 999
            max_nested_obj_props = 99
            max_array_item_obj_props = 99
            
            if "description" in param_details and isinstance(param_details["description"], str):
                orig_desc_len = len(param_details["description"])
                if orig_desc_len > max_desc_len:
                    param_details["description"] = param_details["description"][:max_desc_len-3] + "..."

            param_type_info = param_details.get("type")
            is_nullable = param_details.get("nullable", False)
            primary_type_str = "string" 

            if isinstance(param_type_info, str):
                primary_type_str = param_type_info
                if primary_type_str.lower() == "null": 
                    is_nullable = True
                    primary_type_str = "string"
            elif isinstance(param_type_info, list):
                types_in_list = [str(t).lower() for t in param_type_info] 
                if "null" in types_in_list: 
                    is_nullable = True
                non_null_types = [t for t in types_in_list if t != "null"]
                if non_null_types: 
                    primary_type_str = non_null_types[0]
                else: 
                    is_nullable = True
                    primary_type_str = "string"
            elif "anyOf" in param_details and isinstance(param_details.get("anyOf"), list):
                any_of_types = []
                for item in param_details["anyOf"]:
                    if isinstance(item, dict) and "type" in item:
                        item_type = str(item["type"]).lower()
                        if item_type == "null": 
                            is_nullable = True
                        else: 
                            any_of_types.append(item_type)
                if any_of_types: 
                    primary_type_str = any_of_types[0]
                else: 
                    is_nullable = True
                    primary_type_str = "string"
            elif param_type_info is None and 'anyOf' not in param_details:
                primary_type_str = "string"
                is_nullable = True

            glm_type = self._get_glm_type_enum(primary_type_str)
            enum_values = param_details.get("enum")
            if not enum_values and "anyOf" in param_details and isinstance(param_details.get("anyOf"), list):
                for item in param_details["anyOf"]:
                    if isinstance(item, dict) and "enum" in item and item.get("type") == primary_type_str:
                        enum_values = item["enum"]
                        if any(sub_item.get("type") == "null" for sub_item in param_details["anyOf"] if isinstance(sub_item, dict)):
                            is_nullable = True
                        break
            
            # Conditional enum limiting (effectively disabled)
            if enum_values and isinstance(enum_values, list) and len(enum_values) > max_enum_vals:
                enum_values = enum_values[:max_enum_vals]
            
            prop_schema_args = {
                "type_": glm_type, 
                "description": param_details.get("description"),
                "nullable": is_nullable, 
            }
            if enum_values is not None:
                prop_schema_args["enum"] = enum_values
            
            if glm_type == glm.Type.OBJECT:
                # Handle nested objects
                if "properties" in param_details and isinstance(param_details["properties"], dict):
                    if len(param_details["properties"]) > max_nested_obj_props:
                        prop_schema_args["type_"] = glm.Type.STRING 
                        if "description" not in prop_schema_args or not prop_schema_args["description"]:
                             prop_schema_args["description"] = f"Complex object with {len(param_details['properties'])} properties, simplified."
                        prop_schema_args.pop("properties", None)
                        prop_schema_args.pop("required", None)
                    else:
                        # Convert nested object properties
                        nested_props = {}
                        for nested_prop_name, nested_prop_details in param_details["properties"].items():
                            if isinstance(nested_prop_details, dict):
                                nested_schema = self._convert_individual_parameter_to_schema(
                                    f"{param_name}.{nested_prop_name}", nested_prop_details
                                )
                                if nested_schema:
                                    nested_props[nested_prop_name] = nested_schema
                        prop_schema_args["properties"] = nested_props
                        
                        # Handle required fields for nested object
                        nested_required = param_details.get("required", [])
                        if nested_required and any(req in nested_props for req in nested_required):
                            valid_nested_required = [req for req in nested_required if req in nested_props]
                            if valid_nested_required:
                                prop_schema_args["required"] = valid_nested_required
                else:
                    # Object type but no properties - convert to string for simplicity
                    prop_schema_args["type_"] = glm.Type.STRING
                    if "description" not in prop_schema_args or not prop_schema_args["description"]:
                        prop_schema_args["description"] = "Object parameter (simplified to string)"

            elif glm_type == glm.Type.ARRAY: 
                items_details = None
                if "items" in param_details: 
                    items_details = param_details["items"]
                elif "anyOf" in param_details and isinstance(param_details["anyOf"], list):
                    for element in param_details["anyOf"]:
                        if isinstance(element, dict) and element.get("type") == "array" and "items" in element:
                            items_details = element["items"]
                            break 
                
                # CRITICAL FIX: Ensure all arrays have valid items schemas
                if items_details and isinstance(items_details, dict):
                    # Handle complex array item objects
                    if items_details.get("type") == "object" and "properties" in items_details and isinstance(items_details["properties"], dict) and len(items_details["properties"]) > max_array_item_obj_props:
                        items_details = {"type": "string", "description": "Simplified array item (was complex object)"}
                elif items_details is None:
                    # CRITICAL FIX: Provide default items schema if missing
                    log.warning(f"Parameter '{param_name}': Array type missing 'items' definition. Using string default.")
                    items_details = {"type": "string", "description": "Array item (type not specified)"}
                
                if items_details and isinstance(items_details, dict):
                    items_schema = self._convert_individual_parameter_to_schema(f"{param_name}[items]", items_details)
                    if items_schema:
                        prop_schema_args["items"] = items_schema
                    else:
                        # Fallback items schema
                        prop_schema_args["items"] = glm.Schema(type_=glm.Type.STRING, description="Fallback string item")
                else:
                    log.warning(f"Parameter '{param_name}': Could not create valid 'items' definition for array type. Using string fallback.")
                    # CRITICAL FIX: Always provide a fallback items schema for arrays
                    prop_schema_args["items"] = glm.Schema(type_=glm.Type.STRING, description="Fallback string item")

            # Remove None values before creating schema
            prop_schema_args = {k: v for k, v in prop_schema_args.items() if v is not None}
            return glm.Schema(**prop_schema_args)
            
        except Exception as e:
            log.error(f"Parameter '{param_name}': Failed to create schema: {e}. Using string fallback.", exc_info=True)
            # Return a simple string schema as fallback
            return glm.Schema(
                type_=glm.Type.STRING, 
                description=param_details.get("description", f"Error processing schema for {param_name}"),
                nullable=True
            )

    def prepare_tools_for_sdk(self, tool_definitions: List[Dict[str, Any]], query: Optional[str] = None, app_state: Optional[AppState] = None) -> Optional[ToolType]:
        """
        Converts a list of tool definitions (dictionaries following OpenAPI subset)
        into a google.ai.generativelanguage.Tool object for the SDK.
        This version creates one FunctionDeclaration per individual tool.
        """
        if not tool_definitions:
            log.debug("No tool definitions provided to prepare_tools_for_sdk.")
            return None
        if not SDK_AVAILABLE:
            log.error("Cannot prepare tools: google-genai SDK not available.")
            return None
            
        if query:
            query_stripped = query.strip().lower()
            obvious_non_requests = [".", "..", "?", "??", "test", "testing", "hi", "hello", "thanks", "thank you"]
            if query_stripped in obvious_non_requests or is_greeting_or_chitchat(query_stripped): # Use text_utils
                log.info(f"Detected greeting or obvious non-request: '{query}'. Not providing tools for this turn.")
                return None
            
        # Use ToolSelector if enabled and query is present
        processing_tools: List[Dict[str, Any]]
        if query and self.tool_selector.enabled:
            log.info(f"Using ToolSelector for query: {query[:50]}...")
            selected_detailed_tools = self.tool_selector.select_tools(
                query, 
                app_state=app_state,
                available_tools=tool_definitions
            )
            if selected_detailed_tools:
                log.info(f"ToolSelector selected {len(selected_detailed_tools)} of {len(tool_definitions)} tools.")
                processing_tools = selected_detailed_tools
            else:
                log.warning("ToolSelector returned no tools. Proceeding with all tools (or category filtering if applicable).")
                processing_tools = tool_definitions # Fallback to all if selector returns none
        else:
            log.debug(f"Tool selection not used (query: {bool(query)}, enabled: {self.tool_selector.enabled}). Using all provided tool definitions initially.")
            processing_tools = tool_definitions

        # Apply category filtering if still too many tools
        # Note: MAX_FUNCTION_DECLARATIONS now applies to *individual tools*, not services.
        if len(processing_tools) > self.config.MAX_FUNCTION_DECLARATIONS:
            log.info(f"More than {self.config.MAX_FUNCTION_DECLARATIONS} tools selected/available ({len(processing_tools)}), applying category/importance filtering.")
            # _filter_tools_by_category and _select_most_important_tools could be used or refined here
            # For now, let's apply a simple truncation to the MAX_FUNCTION_DECLARATIONS if too many.
            # A more sophisticated approach might be to use the original _filter_tools_by_category if desired.
            log.warning(f"Truncating list of processing tools from {len(processing_tools)} to {self.config.MAX_FUNCTION_DECLARATIONS}")
            processing_tools = processing_tools[:self.config.MAX_FUNCTION_DECLARATIONS]

        if not processing_tools:
            log.warning("No tools available after filtering/selection for SDK preparation.")
            return None
            
        individual_function_declarations: List[FunctionDeclarationType] = []
        log.debug(f"Preparing {len(processing_tools)} individual tools for SDK FunctionDeclaration.")

        for tool_dict in processing_tools:
            if not isinstance(tool_dict, dict) or "name" not in tool_dict or "description" not in tool_dict:
                log.warning(f"Skipping invalid tool definition (missing name or description): {tool_dict}")
                continue
            
            tool_name = tool_dict["name"]
            tool_description = tool_dict["description"]
            parameters_dict = tool_dict.get("parameters") # This is the JSON schema for parameters

            try:
                # Convert the tool's JSON schema parameters to a glm.Schema object
                tool_params_schema: Optional[SchemaType] = None
                if parameters_dict:
                    tool_params_schema = self._convert_parameters_to_schema(tool_name, parameters_dict)
                
                # If _convert_parameters_to_schema returns None (e.g., no params),
                # it's okay, the FunctionDeclaration can be created without `parameters`.
                
                func_decl = glm.FunctionDeclaration(
                    name=tool_name,
                    description=tool_description,
                    parameters=tool_params_schema if tool_params_schema else None # Pass None if no parameters
                )
                individual_function_declarations.append(func_decl)
                log.debug(f"  Successfully created FunctionDeclaration for tool: '{tool_name}'")

            except Exception as e:
                log.error(f"Failed to prepare FunctionDeclaration for tool '{tool_name}': {e}", exc_info=True)
                continue 

        if not individual_function_declarations:
            log.warning("No valid individual function declarations could be prepared from the tool definitions.")
            return None
        
        log.info(f"Prepared {len(individual_function_declarations)} individual function declarations for SDK: {[d.name for d in individual_function_declarations]}")
        return glm.Tool(function_declarations=individual_function_declarations)

    def _filter_tools_by_category(self, tools: List[Dict[str, Any]], query: Optional[str] = None) -> List[Dict[str, Any]]:
        # This method can be kept as is or refined.
        # For now, it will be less critical if ToolSelector is effective and MAX_FUNCTION_DECLARATIONS is reasonable.
        # For brevity, I'm collapsing the original implementation here but it should be present if used.
        # Placeholder:
        log.debug(f"Executing _filter_tools_by_category (original logic can be restored here if needed). Input tools: {len(tools)}")
        # ... (original implementation of _filter_tools_by_category)
        # For now, let's assume it just returns the tools if not many, or a subset.
        if len(tools) > self.config.MAX_FUNCTION_DECLARATIONS * 2: # If significantly more tools than max declarations
            # This is where more aggressive category filtering logic would go.
            # For now, we rely on ToolSelector and the subsequent truncation.
            pass
        return tools

    def _select_most_important_tools(self, tools: List[Dict[str, Any]], query: Optional[str], max_count: int = 6) -> List[Dict[str, Any]]:
        # This method can be kept as is or refined.
        # Placeholder:
        log.debug(f"Executing _select_most_important_tools (original logic can be restored here). Max count: {max_count}, Input tools: {len(tools)}")
        # ... (original implementation of _select_most_important_tools)
        if len(tools) > max_count:
            return tools[:max_count]
        return tools

    def health_check(self) -> Dict[str, Any]:
        start_time = time.monotonic()
        log.debug(f"Performing health check for Gemini model: {self.model_name}")
        if not SDK_AVAILABLE:
            return {"status": "ERROR", "message": "google-genai SDK not available.", "component": "LLM"}

        try:
            model_info = genai.get_model(self.model_name) 
            elapsed = time.monotonic() - start_time
            log.info(f"Gemini health check successful for model: {self.model_name} (took {elapsed:.3f}s)")
            return {
                "status": "OK",
                "message": f"Model '{self.model_name}' available via SDK.",
                "component": "LLM",
                "details": {
                    "display_name": getattr(model_info, 'display_name', 'N/A'),
                    "version": getattr(model_info, 'version', 'N/A'),
                }
            }
        except google_exceptions.NotFound as e:
            log.warning(f"Gemini health check: Model '{self.model_name}' not found via SDK. Error: {e}", exc_info=False)
            return {"status": "DOWN", "message": f"Model '{self.model_name}' not found.", "component": "LLM"}
        except google_exceptions.PermissionDenied as e:
            log.error(f"Gemini health check failed for '{self.model_name}' due to permissions: {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Permission denied for model '{self.model_name}'. Check API key.", "component": "LLM"}
        except google_exceptions.ResourceExhausted as e:
            log.error(f"Gemini health check failed for '{self.model_name}' due to quota limit: {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Resource exhausted (quota likely) for model '{self.model_name}'.", "component": "LLM"}
        except google_exceptions.GoogleAPIError as e:
            log.error(f"Gemini health check failed for '{self.model_name}' with API error: {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Gemini SDK API error: {str(e)}", "component": "LLM"}
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during Gemini health check: {e}", exc_info=True) 
            return {"status": "DOWN", "message": f"Network error: {str(e)}", "component": "LLM"}
        except Exception as e:
            log.error(f"Unexpected error during Gemini health check for '{self.model_name}': {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Unexpected SDK error: {str(e)}", "component": "LLM"}

    def get_system_prompt_for_persona(self, persona_name: str) -> str:
        if not persona_name or not isinstance(persona_name, str):
            log.warning(f"Invalid persona name provided: {persona_name}. Using default system prompt.")
            return self.config.DEFAULT_SYSTEM_PROMPT
            
        if hasattr(self.config, 'PERSONA_SYSTEM_PROMPTS') and isinstance(self.config.PERSONA_SYSTEM_PROMPTS, dict):
            prompt = self.config.PERSONA_SYSTEM_PROMPTS.get(persona_name)
            if prompt:
                log.debug(f"Using system prompt for persona: {persona_name}")
                return prompt
        log.warning(f"No system prompt found for persona: {persona_name}. Using default.")
        return self.config.DEFAULT_SYSTEM_PROMPT

    def _create_cache_key(self, messages: List[RuntimeContentType], tools: Optional[ToolType] = None, model_name: Optional[str] = None) -> str:
        """Creates a hashable cache key from messages, tools, and model name."""
        # Serialize messages. glm.Content needs careful handling.
        serializable_messages = []
        for msg in messages:
            try:
                # Check if it's a Google AI SDK Content object
                if hasattr(msg, 'role') and hasattr(msg, 'parts'):
                    # Handle Google AI SDK Content objects
                    msg_dict = {
                        "role": str(msg.role) if hasattr(msg.role, 'name') else str(msg.role),
                        "parts": []
                    }
                    
                    # Process parts safely
                    if hasattr(msg, 'parts') and msg.parts:
                        for part in msg.parts:
                            if hasattr(part, 'text') and part.text:
                                msg_dict["parts"].append({"text": str(part.text)})
                            elif isinstance(part, dict):
                                # Handle dict-style parts
                                if 'text' in part:
                                    msg_dict["parts"].append({"text": str(part['text'])})
                                elif 'type' in part and part.get('type') == 'text':
                                    msg_dict["parts"].append({"text": str(part.get('text', ''))})
                            else:
                                # Fallback for unknown part types
                                msg_dict["parts"].append({"text": f"[{type(part).__name__}]"})
                    
                    serializable_messages.append(msg_dict)
                elif isinstance(msg, dict):
                    # Handle dict messages
                    serializable_messages.append(msg)
                elif hasattr(msg, 'to_dict'):
                    # Try to_dict method for other objects
                    try:
                        serializable_messages.append(msg.to_dict())
                    except Exception as to_dict_error:
                        log.debug(f"to_dict() failed for message type {type(msg)}: {to_dict_error}")
                        # Fallback to basic representation
                        serializable_messages.append({
                            "role": str(getattr(msg, 'role', 'unknown')),
                            "content_type": type(msg).__name__
                        })
                else:
                    # Fallback for any other type
                    serializable_messages.append({
                        "role": str(getattr(msg, 'role', 'unknown')), 
                        "content_type": type(msg).__name__
                    })
            except Exception as msg_error:
                log.debug(f"Error processing message for cache key: {msg_error}")
                # Ultra-safe fallback
                serializable_messages.append({"content_type": type(msg).__name__, "error": True})
        
        # Serialize tools. glm.Tool needs careful handling.
        serializable_tools = None
        if tools:
            try:
                # Check if it's a Google AI SDK Tool object
                if hasattr(tools, 'function_declarations'):
                    serializable_tools = {
                        "type": "glm_tool",
                        "functions": [decl.name for decl in tools.function_declarations] if tools.function_declarations else []
                    }
                elif hasattr(tools, 'to_dict'):
                    try:
                        serializable_tools = tools.to_dict()
                    except Exception as to_dict_error:
                        log.debug(f"to_dict() failed for tools type {type(tools)}: {to_dict_error}")
                        serializable_tools = {"type": type(tools).__name__, "error": True}
                elif isinstance(tools, (list, dict)):
                    serializable_tools = tools
                else:
                    serializable_tools = {"type": type(tools).__name__}
            except Exception as tools_error:
                log.debug(f"Error processing tools for cache key: {tools_error}")
                serializable_tools = {"type": type(tools).__name__, "error": True}

        key_content = {
            "messages": serializable_messages,
            "tools": serializable_tools,
            "model_name": model_name or self.model_name
        }
        
        try:
            serialized_content = json.dumps(key_content, sort_keys=True)
        except TypeError as e:
            log.warning(f"Could not fully serialize content for cache key due to TypeError: {e}. Using simplified key.")
            # More robust fallback with better error handling
            try:
                simplified_messages = []
                for m in serializable_messages:
                    if isinstance(m, dict):
                        simplified_messages.append({
                            "role": m.get("role", "unknown"),
                            "parts_count": len(m.get("parts", [])),
                            "has_text": any("text" in part for part in m.get("parts", []) if isinstance(part, dict))
                        })
                    else:
                        simplified_messages.append({"type": type(m).__name__})
                
                simplified_tools_info = None
                if serializable_tools:
                    if isinstance(serializable_tools, dict):
                        simplified_tools_info = {
                            "type": serializable_tools.get("type", "unknown"),
                            "functions_count": len(serializable_tools.get("functions", []))
                        }
                    elif isinstance(serializable_tools, list):
                        simplified_tools_info = {"type": "list", "count": len(serializable_tools)}
                    else:
                        simplified_tools_info = {"type": type(serializable_tools).__name__}
                
                simplified_key_content = {
                    "messages_summary": simplified_messages,
                    "tools_summary": simplified_tools_info,
                    "model_name": model_name or self.model_name
                }
                serialized_content = json.dumps(simplified_key_content, sort_keys=True)
            except Exception as fallback_error:
                log.warning(f"Even simplified cache key serialization failed: {fallback_error}. Using basic hash.")
                # Ultimate fallback - just use basic info
                basic_content = f"model:{model_name or self.model_name}_msgs:{len(messages)}_tools:{bool(tools)}"
                serialized_content = basic_content
        
        return hashlib.sha256(serialized_content.encode('utf-8')).hexdigest()

    async def generate_content(
        self,
        messages: List[RuntimeContentType],
        app_state: Optional[AppState] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        query: Optional[str] = None
    ) -> Any:
        """
        Non-streaming wrapper around generate_content_stream.
        Returns a response object with .text attribute for compatibility.
        """
        if not SDK_AVAILABLE:
            log.error("LLMInterface: google-genai SDK not available. Cannot generate content.")
            raise RuntimeError("LLM SDK not available")

        # Create a simple response object to match expected interface
        class SimpleResponse:
            def __init__(self):
                self.text = ""
                self.tool_calls = []
                
        response = SimpleResponse()
        
        try:
            # Collect all chunks from the stream
            async for chunk in self.generate_content_stream(messages, app_state or AppState(), tools, query):
                if chunk.get("type") == "text_chunk":
                    response.text += chunk.get("content", "")
                elif chunk.get("type") == "tool_calls":
                    response.tool_calls.extend(chunk.get("content", []))
                elif chunk.get("type") == "error":
                    error_msg = chunk.get("content", "Unknown error")
                    log.error(f"Error in generate_content stream: {error_msg}")
                    raise RuntimeError(f"LLM generation failed: {error_msg}")
            
            return response
            
        except Exception as e:
            log.error(f"Error in generate_content: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate content: {e}") from e

    async def generate_content_stream(
        self,
        messages: List[RuntimeContentType],
        app_state: AppState,
        tools: Optional[List[Dict[str, Any]]] = None,
        query: Optional[str] = None # Query is used by prepare_tools_for_sdk for selection
    ) -> AsyncIterable[Dict[str, Any]]: # Changed return type for clarity
        """
        Generates content from the LLM, supporting streaming and tool use,
        with enhanced error handling and retries.
        Yields dictionaries: e.g., {"type": "text_chunk", "content": "..."}
                                or {"type": "tool_calls", "content": [...]}
                                or {"type": "error", "content": "...", ...}
        """
        if not SDK_AVAILABLE:
            log.error("LLMInterface: google-genai SDK not available. Cannot generate content.")
            yield {"type": "error", "content": "LLM SDK not available.", "code": "SDK_UNAVAILABLE", "retryable": False}
            return

        llm_call_id = start_llm_call(self.model_name) # Start LLM call logging context
        log.info(f"LLM Call [{llm_call_id}] - Starting generate_content_stream. Model: {self.model_name}")
        
        # --- Caching Logic --- 
        cache_key: Optional[str] = None
        if self.CACHE_ENABLED:
            try:
                cache_key = self._create_cache_key(messages, tools if 'tools' in locals() else None)
                if cache_key in self.response_cache:
                    log.info(f"LLM Call [{llm_call_id}] - Cache HIT for key: {cache_key[:10]}...")
                    cached_response_events = self.response_cache[cache_key]
                    for event_part in cached_response_events:
                        yield event_part
                    # Move accessed item to end for pseudo-LRU (if cache grows large)
                    self.response_cache[cache_key] = self.response_cache.pop(cache_key)
                    clear_llm_call_id()
                    return
                log.info(f"LLM Call [{llm_call_id}] - Cache MISS for key: {cache_key[:10]}...")
            except Exception as e_cache_key:
                log.warning(f"LLM Call [{llm_call_id}] - Error creating cache key: {e_cache_key}. Proceeding without cache for this call.", exc_info=True)
                cache_key = None # Ensure no caching if key creation failed
        # --- End Caching Logic ---

        prepared_tools_sdk: Optional[ToolType] = None
        if tools:
            try:
                prepared_tools_sdk = self.prepare_tools_for_sdk(tools, query=query, app_state=app_state)
                if prepared_tools_sdk:
                    log.info(f"LLM Call [{llm_call_id}] - Tools prepared for SDK: {[decl.name for decl in prepared_tools_sdk.function_declarations]}")
                else:
                    log.info(f"LLM Call [{llm_call_id}] - No tools prepared for SDK (either none selected or preparation failed).")
            except Exception as e_tool_prep:
                log.error(f"LLM Call [{llm_call_id}] - Error preparing tools for SDK: {e_tool_prep}", exc_info=True)
                yield {"type": "error", "content": f"Error preparing tools: {e_tool_prep}", "code": "TOOL_PREP_ERROR", "retryable": False}
                clear_llm_call_id()
                return

        generation_config = genai.types.GenerationConfig(
            candidate_count=1,
            # temperature=0.7, # Example, can be made configurable
            # top_p=1.0,
            # top_k=50,
        )
        if app_state and hasattr(app_state, 'selected_model_settings') and app_state.selected_model_settings:
            # TODO: Apply selected_model_settings (temperature, top_p, etc.) to generation_config
            # For now, this is a placeholder for future enhancement.
            pass

        max_retries = self.config.DEFAULT_API_MAX_RETRIES if self.config else 3
        base_retry_delay = 1.0  # seconds

        for attempt in range(max_retries + 1):
            try:
                log.info(f"LLM Call [{llm_call_id}] - Attempt {attempt + 1}/{max_retries + 1} to call generate_content.")
                if get_config().settings.log_llm_interaction: # Check if full logging is enabled
                    log.debug(f"LLM Call [{llm_call_id}] - Request Messages: {sanitize_data(messages)}")
                    if prepared_tools_sdk:
                        log.debug(f"LLM Call [{llm_call_id}] - Request Tools: {sanitize_data(prepared_tools_sdk)}")
                
                # Ensure messages are in the correct format (glm.Content if not dicts)
                sdk_messages = []
                for msg in messages:
                    if isinstance(msg, dict) and "role" in msg and "parts" in msg:
                        # Convert dict to glm.Content if needed by SDK
                        # For now, assuming the SDK handles dicts or glm.Content interchangeably
                        # or that messages are already pre-formatted if necessary.
                        sdk_messages.append(msg)
                    elif hasattr(msg, 'role') and hasattr(msg, 'parts'): # Is already glm.Content like
                        sdk_messages.append(msg)
                    else:
                        log.error(f"LLM Call [{llm_call_id}] - Invalid message format: {type(msg)}. Skipping message.")
                        continue # Skip malformed message

                if not sdk_messages:
                    log.error(f"LLM Call [{llm_call_id}] - No valid messages to send after formatting.")
                    yield {"type": "error", "content": "No valid messages to send to LLM.", "code": "NO_VALID_MESSAGES", "retryable": False}
                    clear_llm_call_id()
                    return

                api_response_stream = self.model.generate_content(
                    sdk_messages,
                    generation_config=generation_config,
                    tools=prepared_tools_sdk if prepared_tools_sdk else None,
                    stream=True,
                    request_options={"timeout": self.timeout}
                )

                # Need to collect all yielded chunks if we intend to cache the full response stream events
                all_chunks_for_cache: List[Dict[str, Any]] = [] 

                for part_response in api_response_stream:
                    if get_config().settings.log_llm_interaction:
                        log.debug(f"LLM Call [{llm_call_id}] - Stream Part Received: {sanitize_data(part_response)}")
                    
                    # Process streaming response parts carefully
                    # Check if there's text content first
                    if hasattr(part_response, 'text') and part_response.text:
                        event_to_yield = {"type": "text_chunk", "content": part_response.text}
                        all_chunks_for_cache.append(event_to_yield)
                        yield event_to_yield
                    
                    # Check for function calls (tool calls) in candidates
                    if hasattr(part_response, 'candidates') and part_response.candidates:
                        for candidate in part_response.candidates:
                            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                                for content_part in candidate.content.parts:
                                    # Handle text parts
                                    if hasattr(content_part, 'text') and content_part.text:
                                        event_to_yield = {"type": "text_chunk", "content": content_part.text}
                                        all_chunks_for_cache.append(event_to_yield)
                                        yield event_to_yield
                                    # Handle function calls
                                    elif hasattr(content_part, 'function_call') and content_part.function_call:
                                        fc = content_part.function_call
                                        event_to_yield = {
                                            "type": "tool_calls", 
                                            "content": [{
                                                "id": f"call_{uuid.uuid4().hex[:8]}", # Generate a unique call ID
                                                "type": "function",
                                                "function": {"name": fc.name, "arguments": dict(fc.args) if hasattr(fc, 'args') else {}}
                                            }]
                                        }
                                        all_chunks_for_cache.append(event_to_yield)
                                        yield event_to_yield
                
                # --- Cache successful response --- 
                if self.CACHE_ENABLED and cache_key and all_chunks_for_cache:
                    if len(self.response_cache) >= self.CACHE_MAX_SIZE:
                        # Simple FIFO eviction if cache is full
                        try:
                            oldest_key = next(iter(self.response_cache))
                            self.response_cache.pop(oldest_key, None)
                            log.debug(f"LLM Call [{llm_call_id}] - Cache full, evicted oldest key: {oldest_key[:10]}...")
                        except StopIteration: # Should not happen if cache size >= 1
                            pass 
                    self.response_cache[cache_key] = all_chunks_for_cache # Store list of event dicts
                    log.info(f"LLM Call [{llm_call_id}] - Response stored in cache with key: {cache_key[:10]}...")
                # --- End Cache successful response --- 

                log.info(f"LLM Call [{llm_call_id}] - Stream successfully completed and processed.")
                # Yield collected chunks first IF NOT ALREADY YIELDED (this needs refinement based on streaming vs full response caching)
                # For now, assuming the cache stores the yielded events. If it stores full text, this would differ.
                # The current cache stores List[Dict[str,Any]] which are the events.

                yield {"type": "completed", "content": {"status": "COMPLETED_OK"}} 
                clear_llm_call_id()
                return # Exit after successful stream

            except google_exceptions.RetryError as e:
                log.warning(f"LLM Call [{llm_call_id}] - Google SDK RetryError (will be retried by this loop if attempts left): {e}", exc_info=True)
                if attempt >= max_retries:
                    log.error(f"LLM Call [{llm_call_id}] - Max retries reached for Google SDK RetryError. Error: {e}")
                    yield {"type": "error", "content": f"LLM API retry error: {e}", "code": "API_RETRY_ERROR", "retryable": True, "final_attempt": True}
                    clear_llm_call_id()
                    return
                # Fall through to wait and retry for RetryError
            except google_exceptions.DeadlineExceeded as e:
                log.warning(f"LLM Call [{llm_call_id}] - DeadlineExceeded: {e}", exc_info=True)
                if attempt >= max_retries:
                    log.error(f"LLM Call [{llm_call_id}] - Max retries reached for DeadlineExceeded. Error: {e}")
                    yield {"type": "error", "content": f"LLM API request timed out: {e}", "code": "API_TIMEOUT", "retryable": True, "final_attempt": True}
                    clear_llm_call_id()
                    return
                # Fall through to wait and retry
            except google_exceptions.ServiceUnavailable as e: # Typically 503
                log.warning(f"LLM Call [{llm_call_id}] - ServiceUnavailable: {e}", exc_info=True)
                if attempt >= max_retries:
                    log.error(f"LLM Call [{llm_call_id}] - Max retries reached for ServiceUnavailable. Error: {e}")
                    yield {"type": "error", "content": f"LLM service unavailable: {e}", "code": "API_SERVICE_UNAVAILABLE", "retryable": True, "final_attempt": True}
                    clear_llm_call_id()
                    return
                # Fall through to wait and retry
            except google_exceptions.ResourceExhausted as e: # Typically 429 Rate Limiting
                log.warning(f"LLM Call [{llm_call_id}] - ResourceExhausted (Rate Limit?): {e}", exc_info=True)
                # Check if the error specifically indicates to wait (e.g., from metadata)
                # For now, assume it's retryable with longer backoff if attempts left
                if attempt >= max_retries:
                    log.error(f"LLM Call [{llm_call_id}] - Max retries reached for ResourceExhausted. Error: {e}")
                    yield {"type": "error", "content": f"LLM API resource exhausted (rate limit?): {e}", "code": "API_RATE_LIMIT", "retryable": True, "final_attempt": True}
                    clear_llm_call_id()
                    return
                base_retry_delay = 5.0 # Use a longer base delay for rate limits
            except (google_exceptions.InvalidArgument, google_exceptions.PermissionDenied, google_exceptions.Unauthenticated, google_exceptions.NotFound) as e:
                log.error(f"LLM Call [{llm_call_id}] - Non-retryable API error: {e}", exc_info=True)
                yield {"type": "error", "content": f"LLM API client/auth error: {e}", "code": "API_CLIENT_ERROR", "retryable": False}
                clear_llm_call_id()
                return
            except (requests_exceptions.ConnectionError, requests_exceptions.Timeout, TimeoutError) as e: # Python's TimeoutError
                log.warning(f"LLM Call [{llm_call_id}] - Network/Timeout error: {e}", exc_info=True)
                if attempt >= max_retries:
                    log.error(f"LLM Call [{llm_call_id}] - Max retries reached for Network/Timeout error. Error: {e}")
                    yield {"type": "error", "content": f"Network/Timeout error communicating with LLM: {e}", "code": "NETWORK_TIMEOUT_ERROR", "retryable": True, "final_attempt": True}
                    clear_llm_call_id()
                    return
                # Fall through to wait and retry
            except Exception as e: # Catch-all for unexpected errors from the SDK or logic
                log.error(f"LLM Call [{llm_call_id}] - Unexpected error during generate_content_stream (Attempt {attempt + 1}): {e}", exc_info=True)
                # For a general exception, don't retry unless specifically known to be transient.
                yield {"type": "error", "content": f"Unexpected error in LLM stream: {e}", "code": "UNEXPECTED_LLM_ERROR", "retryable": False}
                clear_llm_call_id()
                return
            
            # If we are here, it means a retryable error occurred and we have attempts left
            wait_seconds = (base_retry_delay * (2 ** attempt)) + random.uniform(0, 0.5)
            log.info(f"LLM Call [{llm_call_id}] - Retrying in {wait_seconds:.2f} seconds...")
            await asyncio.sleep(wait_seconds)

        # If loop finishes, all retries were exhausted for some retryable error
        log.error(f"LLM Call [{llm_call_id}] - All retries failed for generate_content_stream.")
        # This path should ideally be covered by specific error yields with final_attempt=True
        yield {"type": "error", "content": "LLM operation failed after all retries.", "code": "API_MAX_RETRIES_EXCEEDED", "retryable": True, "final_attempt": True}
        clear_llm_call_id()