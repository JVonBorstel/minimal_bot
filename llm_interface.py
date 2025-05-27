# --- FILE: llm_interface.py ---
import logging
from typing import List, Dict, Any, Optional, Iterable, Union, TypeAlias, TYPE_CHECKING
import time
import re

# Use google.api_core.exceptions for specific API errors
from google.api_core import exceptions as google_exceptions
from requests import exceptions as requests_exceptions

# Import the main Config class for type hinting and settings access
from config import Config # Assuming Config class is available

# Import ToolSelector for dynamic tool selection
from core_logic.tool_selector import ToolSelector

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
        
        self.tool_selector = ToolSelector(config)

        try:
            genai.configure(api_key=self.api_key)
            log.info(f"google-genai SDK configured successfully. Default Model: {self.model_name}, Request Timeout: {self.timeout}s")
            self.model = genai.GenerativeModel(
                self.model_name,
                system_instruction=self.config.DEFAULT_SYSTEM_PROMPT # Using DEFAULT_SYSTEM_PROMPT from Config
            )
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
            self.model = genai.GenerativeModel(
                model_name,
                system_instruction=self.config.DEFAULT_SYSTEM_PROMPT # Apply system instruction here as well
            )
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
 
                # Conditional description truncation (effectively disabled)
                if "description" in prop_details and isinstance(prop_details["description"], str):
                    orig_desc_len = len(prop_details["description"])
                    if orig_desc_len > max_desc_len:
                        prop_details["description"] = prop_details["description"][:max_desc_len-3] + "..."

                prop_type_info = prop_details.get("type")
                is_nullable = prop_details.get("nullable", False)
                primary_type_str = "string" 

                if isinstance(prop_type_info, str):
                    primary_type_str = prop_type_info
                    if primary_type_str.lower() == "null": 
                        is_nullable = True
                        primary_type_str = "string"
                elif isinstance(prop_type_info, list):
                    types_in_list = [str(t).lower() for t in prop_type_info] 
                    if "null" in types_in_list: 
                        is_nullable = True
                    non_null_types = [t for t in types_in_list if t != "null"]
                    if non_null_types: 
                        primary_type_str = non_null_types[0]
                    else: 
                        is_nullable = True
                        primary_type_str = "string"
                elif "anyOf" in prop_details and isinstance(prop_details.get("anyOf"), list):
                    any_of_types = []
                    for item in prop_details["anyOf"]:
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
                elif prop_type_info is None and 'anyOf' not in prop_details:
                    primary_type_str = "string"
                    is_nullable = True

                glm_type = self._get_glm_type_enum(primary_type_str)
                enum_values = prop_details.get("enum")
                if not enum_values and "anyOf" in prop_details and isinstance(prop_details.get("anyOf"), list):
                    for item in prop_details["anyOf"]:
                        if isinstance(item, dict) and "enum" in item and item.get("type") == primary_type_str:
                            enum_values = item["enum"]
                            if any(sub_item.get("type") == "null" for sub_item in prop_details["anyOf"] if isinstance(sub_item, dict)):
                                is_nullable = True
                            break
                
                # Conditional enum limiting (effectively disabled)
                if enum_values and isinstance(enum_values, list) and len(enum_values) > max_enum_vals:
                    enum_values = enum_values[:max_enum_vals]
                
                prop_schema_args = {
                    "type_": glm_type, 
                    "description": prop_details.get("description"),
                    "nullable": is_nullable, 
                }
                if enum_values is not None:
                    prop_schema_args["enum"] = enum_values
                
                if glm_type == glm.Type.OBJECT:
                    # Handle nested objects
                    if "properties" in prop_details and isinstance(prop_details["properties"], dict) and len(prop_details["properties"]) > max_nested_obj_props:
                        prop_schema_args["type_"] = glm.Type.STRING 
                        if "description" not in prop_schema_args or not prop_schema_args["description"]:
                             prop_schema_args["description"] = f"Complex object with {len(prop_details['properties'])} properties, simplified."
                        prop_schema_args.pop("properties", None)
                        prop_schema_args.pop("required", None)
                    else:
                        nested_schema = self._convert_parameters_to_schema(f"{tool_name}.{prop_name}", prop_details)
                        if nested_schema:
                            prop_schema_args["properties"] = nested_schema.properties
                            if nested_schema.required: 
                                prop_schema_args["required"] = nested_schema.required
                        else: 
                            prop_schema_args["properties"] = {}

                elif glm_type == glm.Type.ARRAY: 
                    items_details = None
                    if "items" in prop_details: 
                        items_details = prop_details["items"]
                    elif "anyOf" in prop_details and isinstance(prop_details["anyOf"], list):
                        for element in prop_details["anyOf"]:
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
                        log.warning(f"Tool '{tool_name}', Property '{prop_name}': Array type missing 'items' definition. Using string default.")
                        items_details = {"type": "string", "description": "Array item (type not specified)"}
                    
                    if items_details and isinstance(items_details, dict) and "type" in items_details:
                        items_type_str = items_details.get("type", "string")
                        items_glm_type = self._get_glm_type_enum(items_type_str)
                        items_schema_args = {
                            "type_": items_glm_type, 
                            "description": items_details.get("description"), 
                            "nullable": items_details.get("nullable", False)
                        }
                        items_enum_values = items_details.get("enum")
                        if items_enum_values is not None: 
                            items_schema_args["enum"] = items_enum_values

                        if items_glm_type == glm.Type.OBJECT:
                             nested_item_schema = self._convert_parameters_to_schema(f"{tool_name}.{prop_name}[items]", items_details)
                             if nested_item_schema:
                                 items_schema_args["properties"] = nested_item_schema.properties
                                 if nested_item_schema.required: 
                                     items_schema_args["required"] = nested_item_schema.required
                             else: 
                                 items_schema_args["properties"] = {}
                        
                        items_schema_args = {k: v for k, v in items_schema_args.items() if v is not None}
                        try:
                            prop_schema_args["items"] = glm.Schema(**items_schema_args)
                        except Exception as item_schema_ex:
                             log.warning(f"Tool '{tool_name}', Property '{prop_name}': Failed to create glm.Schema for items. Details: {item_schema_ex}. Using string fallback.", exc_info=True)
                             # CRITICAL FIX: Provide fallback items schema
                             prop_schema_args["items"] = glm.Schema(type_=glm.Type.STRING, description="Fallback string item")
                    else:
                        log.warning(f"Tool '{tool_name}', Property '{prop_name}': Could not create valid 'items' definition for array type. Using string fallback.")
                        # CRITICAL FIX: Always provide a fallback items schema for arrays
                        prop_schema_args["items"] = glm.Schema(type_=glm.Type.STRING, description="Fallback string item")

                prop_schema_args = {k: v for k, v in prop_schema_args.items() if v is not None}
                try:
                    schema_props[prop_name] = glm.Schema(**prop_schema_args)
                except Exception as prop_schema_ex:
                    log.error(f"Tool '{tool_name}', Property '{prop_name}': Failed to create property schema: {prop_schema_ex}. Skipping property.", exc_info=True)
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

    def generate_content_stream(
        self,
        messages: List[RuntimeContentType],
        app_state: AppState,
        tools: Optional[List[Dict[str, Any]]] = None,
        query: Optional[str] = None
    ) -> Iterable[GenerateContentResponseType]:
        if not messages:
            raise ValueError("No messages provided for LLM generation")
        if not self.model:
             raise RuntimeError("LLM model client is not initialized.")
        if not SDK_AVAILABLE:
            raise ImportError("google-genai SDK is required but not available.")

        current_config = get_config() # Get current config instance
        llm_call_id = start_llm_call() # Start LLM call context

        try:
            sdk_tool_obj: Optional[ToolType] = None
            if tools:
                # Pass app_state for permission checks in ToolSelector if it uses it
                sdk_tool_obj = self.prepare_tools_for_sdk(tools, query=query, app_state=app_state)

            generation_config = genai.types.GenerationConfig(candidate_count=1)
            safety_settings: Optional[Dict[Any, Any]] = None # Keep as None if not configuring specific safety
            
            final_contents = [] # System prompt is now part of model initialization
            final_contents.extend(messages)

            # Log LLM Request Payload if log_llm_interaction is True
            if current_config.settings.log_llm_interaction:
                # Construct a serializable request payload for logging
                # This is a simplified representation. Actual API request might be more complex.
                log_payload = {
                    "model_name": self.model_name,
                    "contents": final_contents, # This might contain complex objects
                    "tools": sdk_tool_obj, # This might contain complex objects
                    "generation_config": generation_config, # This might contain complex objects
                    "safety_settings": safety_settings,
                    "tool_config": {"function_calling_config": {"mode": "AUTO"}} if sdk_tool_obj else None,
                }
                # The 'contents' and 'tools' can be complex.
                # We need to make sure they are serializable or convert them to a serializable format.
                # For now, we'll rely on sanitize_data to handle this as best as it can.
                # A more robust solution might involve custom serializers for SDK objects.
                try:
                    # Attempt to serialize parts of the payload that might not be directly JSON-serializable
                    # For example, glm.Content objects in final_contents or glm.Tool in sdk_tool_obj
                    # This is a placeholder for more robust serialization if needed.
                    # For now, we'll pass it to sanitize_data which will attempt to convert.
                    
                    # Convert glm.Content to dict if possible
                    serializable_contents = []
                    for item in final_contents:
                        if hasattr(item, 'to_dict'): # Check if it's a new SDK object
                            serializable_contents.append(item.to_dict())
                        elif isinstance(item, dict): # Already a dict (OpenAI format)
                             serializable_contents.append(item)
                        else: # Fallback, might not be perfectly serializable by json.dumps
                            serializable_contents.append(str(item)) # Or a more specific conversion
                    log_payload["contents"] = serializable_contents

                    if sdk_tool_obj and hasattr(sdk_tool_obj, 'to_dict'): # For glm.Tool
                        log_payload["tools"] = sdk_tool_obj.to_dict()
                    elif sdk_tool_obj: # If not directly to_dict, maybe it's already a dict or needs specific handling
                        # For now, assume it's either already suitable or will be handled by sanitize_data's string conversion
                        pass


                    if generation_config and hasattr(generation_config, 'to_dict'):
                        log_payload["generation_config"] = generation_config.to_dict()
                    
                except Exception as e:
                    log.warning(f"Could not fully serialize LLM request payload for logging: {e}", exc_info=True)
                    # log_payload will contain what was serializable.

                sanitized_payload = sanitize_data(log_payload)
                log.info(
                    "LLM Request Details",
                    extra={"event_type": "llm_request_payload", "data": sanitized_payload}
                )

            if log.isEnabledFor(logging.DEBUG) and not current_config.settings.log_llm_interaction: # Avoid double logging if already done above
                log_messages_summary = []
                try:
                    for i, m_item in enumerate(final_contents):
                        item_role = 'unknown_role'
                        item_parts_summary = []
                        if isinstance(m_item, dict): # OpenAI like dicts
                            item_role = m_item.get('role', 'dict_unknown_role')
                            content_data = m_item.get('parts', m_item.get('content'))
                            if isinstance(content_data, list):
                                for part_item in content_data:
                                    if isinstance(part_item, dict) and 'text' in part_item: item_parts_summary.append(f"text({len(part_item['text'])}c)")
                                    elif isinstance(part_item, dict) and 'function_call' in part_item: item_parts_summary.append(f"fn_call:{part_item['function_call'].get('name')}")
                                    elif isinstance(part_item, dict) and 'function_response' in part_item: item_parts_summary.append(f"fn_resp:{part_item['function_response'].get('name')}")
                                    else: item_parts_summary.append(f"dict_part_type:{type(part_item)}")
                            elif isinstance(content_data, str): item_parts_summary.append(f"text({len(content_data)}c)")
                            else: item_parts_summary.append(f"dict_content_type:{type(content_data)}")
                        elif hasattr(m_item, 'parts') and hasattr(m_item, 'role'): # SDK glm.Content
                            item_role = m_item.role
                            for p_item in m_item.parts:
                                if hasattr(p_item, 'text') and p_item.text is not None: item_parts_summary.append(f"text({len(p_item.text)}c)")
                                elif hasattr(p_item, 'function_call') and p_item.function_call: item_parts_summary.append(f"fn_call:{p_item.function_call.name}")
                                elif hasattr(p_item, 'function_response') and p_item.function_response: item_parts_summary.append(f"fn_resp:{p_item.function_response.name}")
                                else: item_parts_summary.append(f"sdk_part_type:{type(p_item)}")
                        else:
                            item_parts_summary.append(f"unknown_msg_fmt:{type(m_item)}")
                        log_messages_summary.append(f"  [{i}] {item_role}: {', '.join(item_parts_summary) if item_parts_summary else '(no parts)'}")
                    log.debug(f"LLM Input Summary ({len(final_contents)} items):\n" + "\n".join(log_messages_summary))
                except Exception as debug_e: log.warning(f"Error generating LLM input summary: {debug_e}")


            log.info(f"Sending {len(final_contents)} content items to LLM ({self.model_name}), streaming. Tools provided: {bool(sdk_tool_obj)}")
            if sdk_tool_obj and hasattr(sdk_tool_obj, 'function_declarations'):
                log.debug(f"  Tool details: {len(sdk_tool_obj.function_declarations)} function declarations: {[fd.name for fd in sdk_tool_obj.function_declarations[:5]]}...") # Log first 5
            
            response_stream = self.model.generate_content(
                contents=final_contents,
                generation_config=generation_config,
                safety_settings=safety_settings,
                tools=sdk_tool_obj,
                tool_config={"function_calling_config": {"mode": "AUTO"}} if sdk_tool_obj else None,
                stream=True,
                request_options={'timeout': self.timeout}
            )
            log.debug(f"Received streaming response iterator from LLM: {self.model_name}")

            # Wrapper iterator to log response chunks
            def response_logging_iterator(stream):
                full_response_chunks = []
                try:
                    for chunk in stream:
                        if current_config.settings.log_llm_interaction:
                            # Log each chunk if verbose logging is on.
                            # Need to ensure 'chunk' is serializable or convert it.
                            # Similar to request, SDK objects might need to_dict()
                            try:
                                if hasattr(chunk, 'to_dict'):
                                    log_chunk_data = chunk.to_dict()
                                else:
                                    log_chunk_data = str(chunk) # Fallback
                                
                                # Storing for full response log later, before sanitization for that log
                                full_response_chunks.append(log_chunk_data)

                                # log.debug( # Changed to debug to avoid flooding logs for every chunk unless specifically needed
                                # "LLM Response Chunk",
                                # extra={"event_type": "llm_response_chunk", "data": sanitize_data(log_chunk_data)}
                                # )
                            except Exception as e:
                                log.warning(f"Could not serialize LLM response chunk for logging: {e}")
                        else:
                            # If not logging full interaction, we still might need to collect chunks
                            # if other logic depends on full_response_chunks (e.g. for a final summary log).
                            # For now, only collect if log_llm_interaction is true for the final log.
                            pass 
                        yield chunk
                finally:
                    if current_config.settings.log_llm_interaction and full_response_chunks:
                        # Log the complete aggregated response
                        sanitized_full_response = sanitize_data({"response_chunks": full_response_chunks})
                        log.info(
                            "LLM Full Response Details",
                            extra={"event_type": "llm_response_payload", "data": sanitized_full_response}
                        )
            
            return response_logging_iterator(response_stream)

        except google_exceptions.GoogleAPIError as e:
            log.error(f"Google API error during streaming call ({self.model_name}): {e}", exc_info=True)
            if isinstance(e, google_exceptions.ResourceExhausted): log.error("Quota limit likely reached.")
            elif isinstance(e, google_exceptions.PermissionDenied): log.error("Permission denied. Check API key permissions.")
            elif isinstance(e, google_exceptions.InvalidArgument): log.error(f"Invalid argument provided to API: {e}")
            raise e
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during LLM streaming call: {e}", exc_info=True)
            raise RuntimeError(f"Network error during LLM streaming call: {e}") from e 
        except Exception as e:
            log.error(f"Unexpected error during streaming LLM call ({self.model_name}): {e}", exc_info=True)
            raise RuntimeError(f"LLM stream generation failed: {e}") from e
        finally:
            clear_llm_call_id() # Clear LLM call ID in all cases