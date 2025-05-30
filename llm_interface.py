# --- FILE: llm_interface.py ---
import logging
import os
import uuid
import time
import json
import hashlib
import re
import asyncio
import random
from typing import Dict, List, Any, Optional, Union, TypeVar, AsyncIterable, Callable, Tuple, cast
from typing import Iterable, TypeAlias, TYPE_CHECKING

# Use google.api_core.exceptions for specific API errors
from google.api_core import exceptions as google_exceptions
from requests import exceptions as requests_exceptions

# Import the config module
from config import Config, get_config

# Import text utility functions
from core_logic.text_utils import is_greeting_or_chitchat

# Import AppState for type hinting
from state_models import AppState

# Import logging utilities
from utils.logging_config import get_logger, start_llm_call, clear_llm_call_id
from utils.log_sanitizer import sanitize_data

# Import function call utility
from utils.function_call_utils import safe_extract_function_call

# --- Safe SDK Object Representation for Logging ---
def _safe_sdk_object_repr_for_log(sdk_obj: Any, max_len: int = 500) -> str:
    """Safely convert SDK objects to string representations for logging purposes."""
    if sdk_obj is None:
        return "None"

    obj_type_name = type(sdk_obj).__name__

    # CRITICAL: Completely disable processing of function call objects and anything that might contain them
    # This is the most reliable way to avoid the "Could not convert to text" errors
    if hasattr(sdk_obj, 'function_call') or 'function' in obj_type_name.lower():
        return f"<{obj_type_name} [DISABLED_LOGGING]>"

    # Also disable any object that might contain function calls
    if hasattr(sdk_obj, 'parts') and isinstance(sdk_obj.parts, list):
        for part in sdk_obj.parts:
            if hasattr(part, 'function_call'):
                return f"<{obj_type_name} with parts containing function calls [DISABLED_LOGGING]>"

    # parts_to_join = [f"Type={obj_type_name}"] # Original was initialized but not used beyond this for main logic flow

    try:
        # Handle simple types directly and safely
        if isinstance(sdk_obj, (str, int, float, bool)):
            str_val = str(sdk_obj).replace('\n', ' ')
            return str_val[:max_len-3] + "..." if len(str_val) > max_len else str_val

        # For more complex types, just report basic metadata
        if isinstance(sdk_obj, list):
            return f"<List with {len(sdk_obj)} items>"
        elif isinstance(sdk_obj, dict):
            return f"<Dict with {len(sdk_obj)} keys>"
        elif hasattr(sdk_obj, 'text') and isinstance(sdk_obj.text, str):
            # Safe text extraction
            text_preview = sdk_obj.text.replace('\n', ' ')[:70]
            return f"<{obj_type_name} text='{text_preview}{'...' if len(sdk_obj.text) > 70 else ''}'>"
        else:
            # Generic safe representation for other types
            return f"<{obj_type_name}>"

    except Exception as e:
        return f"<{obj_type_name} [logging error: {str(e)[:50]}]>"

def _safe_log_debug(logger, message: str, obj: Any, obj_name: str = "object", llm_call_id: str = None) -> None:
    """
    Safely log an object with proper error handling to prevent logging errors from crashing the application.

    Args:
        logger: The logger to use
        message: The log message template (should contain {safe_repr} where object representation should go)
        obj: The object to log
        obj_name: Name of the object for error messages
        llm_call_id: Optional LLM call ID for context
    """
    try:
        safe_repr = _safe_sdk_object_repr_for_log(obj, max_len=500)
        id_prefix = f"LLM Call [{llm_call_id}] - " if llm_call_id else ""
        logger.debug(f"{id_prefix}{message.format(safe_repr=safe_repr)}")
    except Exception as log_err:
        id_prefix = f"LLM Call [{llm_call_id}] - " if llm_call_id else ""
        logger.debug(f"{id_prefix}Failed to log {obj_name} details: {log_err}")

# --- SDK Types Setup ---
SDK_AVAILABLE = False

# Try to import MapComposite for robust type handling
try:
    from proto.marshal.collections.maps import MapComposite
except ImportError:
    MapComposite = None # type: ignore

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
    NULL = "NULL" # Not typically in glm.Type but useful for schema conversion logic

class _MockGlm:
    Type = _MockGlmType()
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
    # Ensure these specific imports are present as they were in the original file
    from google.ai.generativelanguage import ToolConfig
    from google.ai.generativelanguage import FunctionCallingConfig

    genai = actual_genai
    glm = actual_glm

    SDK_AVAILABLE = True
    log_glm_sdk = logging.getLogger("google.ai.generativelanguage") # Renamed to avoid conflict with local 'log'
    log_glm_sdk.setLevel(logging.WARNING)

except ImportError:
    logging.getLogger(__name__).error(
        "google-generativeai SDK not found. Please install 'google-generativeai'. LLM functionality will be limited.",
        exc_info=False
    )

log = get_logger("llm_interface")

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

        try:
            from core_logic.tool_selector import ToolSelector # Lazy import
            self.tool_selector = ToolSelector(config)
        except ImportError as e:
            log.warning(f"Could not import ToolSelector: {e}. Tool selection will be disabled.")
            class MockToolSelector: # type: ignore
                def __init__(self, *args, **kwargs): # type: ignore
                    self.enabled = False
                def select_tools(self, *args, **kwargs): # type: ignore
                    return []
            self.tool_selector = MockToolSelector(config) # type: ignore

        self.response_cache: Dict[str, List[Dict[str,Any]]] = {}
        self.CACHE_MAX_SIZE = 50
        self.CACHE_ENABLED = True

        try:
            genai.configure(api_key=self.api_key)
            log.info(f"google-genai SDK configured successfully. Default Model: {self.model_name}, Request Timeout: {self.timeout}s")

            self.generation_config = genai.types.GenerationConfig( # Use SDK type
                temperature=0.7,
                top_p=0.95,
                top_k=32,
                max_output_tokens=1024,
                candidate_count=1
            )

            supports_system_instructions = any(
                model_pattern in self.model_name
                for model_pattern in ["gemini-1.5", "gemini-pro"]
            )

            if supports_system_instructions:
                try:
                    self.model = genai.GenerativeModel(
                        self.model_name,
                        system_instruction=self.config.DEFAULT_SYSTEM_PROMPT,
                        generation_config=self.generation_config
                    )
                    log.info(f"Model {self.model_name} initialized with system instruction")
                except Exception as e_sys:
                    log.warning(f"Failed to create model {self.model_name} with system_instruction: {e_sys}. Creating without.")
                    self.model = genai.GenerativeModel(
                        self.model_name,
                        generation_config=self.generation_config
                    )
                    log.info(f"Model {self.model_name} initialized without system instruction")
            else:
                self.model = genai.GenerativeModel(
                    self.model_name,
                    generation_config=self.generation_config
                )
                log.info(f"Model {self.model_name} initialized without system instruction (not supported or not configured for it)")

        except google_exceptions.GoogleAPIError as e:
            log.error(f"google-genai SDK configuration failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to configure google-genai SDK: {e}") from e
        except (requests_exceptions.RequestException, TimeoutError) as e: # Python's TimeoutError
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
            supports_system_instructions = any(
                model_pattern in model_name
                for model_pattern in ["gemini-1.5", "gemini-pro"]
            )

            if supports_system_instructions:
                try:
                    self.model = genai.GenerativeModel(
                        model_name,
                        system_instruction=self.config.DEFAULT_SYSTEM_PROMPT,
                        generation_config=self.generation_config
                    )
                    log.debug(f"Model {model_name} updated with system instruction")
                except Exception as e_sys:
                    log.warning(f"Failed to update model {model_name} with system_instruction: {e_sys}. Creating without.")
                    self.model = genai.GenerativeModel(
                        model_name,
                        generation_config=self.generation_config
                    )
                    log.debug(f"Model {model_name} updated without system instruction")
            else:
                self.model = genai.GenerativeModel(
                    model_name,
                    generation_config=self.generation_config
                )
                log.debug(f"Model {model_name} updated without system instruction (not supported)")

            self.model_name = model_name
            log.info(f"Successfully updated LLM client to use model: {self.model_name}")
        except (google_exceptions.NotFound, google_exceptions.InvalidArgument) as e:
             log.error(f"Failed to update to model '{model_name}'. It might be invalid or inaccessible: {e}", exc_info=True)
             log.warning(f"Reverting to previous model: {prev_model_name}")
             self.model = prev_model
             self.model_name = prev_model_name
             raise ValueError(f"Invalid or inaccessible model name: {model_name}") from e
        except (requests_exceptions.RequestException, TimeoutError) as e: # Python's TimeoutError
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
            "string": glm.Type.STRING, "number": glm.Type.NUMBER,
            "integer": glm.Type.INTEGER, "boolean": glm.Type.BOOLEAN,
            "object": glm.Type.OBJECT, "array": glm.Type.ARRAY,
        }
        default_type = glm.Type.STRING
        glm_type_val = type_mapping.get(str(type_str).lower(), default_type) # Ensure type_str is string
        if glm_type_val == default_type and str(type_str).lower() not in type_mapping:
            log.warning(f"Unsupported schema type '{type_str}'. Defaulting to {getattr(default_type, 'name', default_type)}.")
        return glm_type_val

    def _convert_parameters_to_schema(self, tool_name: str, parameters: Dict[str, Any]) -> Optional[SchemaType]:
        if not parameters:
            log.debug(f"Tool '{tool_name}': No parameters provided, returning None for schema.")
            return None
        if not isinstance(parameters, dict):
            log.warning(f"Tool '{tool_name}': Invalid parameters format (not a dict): {type(parameters)}. Returning None.")
            return None

        if "anyOf" in parameters or "oneOf" in parameters or "allOf" in parameters:
            return self._convert_individual_parameter_to_schema(tool_name, parameters)

        if parameters.get("type") != "object" or "properties" not in parameters:
            log.warning(f"Tool '{tool_name}': Invalid param structure. Expected 'type: object' with 'properties'. Got: {_safe_sdk_object_repr_for_log(parameters)}. Returning empty schema.")
            try:
                return glm.Schema(type_=glm.Type.OBJECT, properties={})
            except (AttributeError, TypeError): # Fallback for newer SDK style
                if hasattr(glm, 'Schema') and hasattr(glm, 'Type'):
                    try: return glm.Schema(type=glm.Type.OBJECT, properties={}) # type: ignore
                    except Exception as e_empty: log.error(f"Tool '{tool_name}': Failed to create empty schema: {e_empty}"); return None
                else: log.error(f"Tool '{tool_name}': No compatible Schema type for empty schema."); return None

        try:
            schema_props: Dict[str, SchemaType] = {}
            required_params: List[str] = parameters.get("required", [])
            props: Dict[str, Any] = parameters.get("properties", {})

            if not isinstance(props, dict):
                log.warning(f"Tool '{tool_name}': Properties is not a dictionary: {type(props)}. Returning empty schema.")
                try: return glm.Schema(type_=glm.Type.OBJECT, properties={})
                except: # Fallback
                    if hasattr(glm, 'Schema') and hasattr(glm, 'Type'): return glm.Schema(type=glm.Type.OBJECT, properties={}) # type: ignore
                    else: return None

            for prop_name, prop_details in props.items():
                if not isinstance(prop_details, dict):
                    log.warning(f"Tool '{tool_name}': Property '{prop_name}' has invalid type: {type(prop_details)}. Skipping.")
                    continue
                try:
                    prop_schema = self._convert_individual_parameter_to_schema(f"{tool_name}.{prop_name}", prop_details)
                    if prop_schema: schema_props[prop_name] = prop_schema
                except Exception as e_prop:
                    log.error(f"Tool '{tool_name}': Failed to convert property '{prop_name}': {e_prop}")

            final_schema_args = {"properties": schema_props}
            current_schema_instance: Optional[SchemaType] = None

            try: # Gemini 1.5 style first with type_
                current_schema_instance = glm.Schema(type_=glm.Type.OBJECT, **final_schema_args)
            except (AttributeError, TypeError): # Try Gemini 2.0+ style with type
                if hasattr(glm, 'Schema') and hasattr(glm, 'Type'):
                    current_schema_instance = glm.Schema(type=glm.Type.OBJECT, **final_schema_args) # type: ignore
                else:
                    log.error(f"Tool '{tool_name}': Schema creation failed: no compatible Schema class found."); return None
            
            if current_schema_instance is None: # Should not happen if previous block worked
                 log.error(f"Tool '{tool_name}': Failed to instantiate schema object."); return None

            # Add required fields if any (SyntaxError was here, now fixed)
            valid_required_list = [r for r in required_params if r in schema_props]
            if valid_required_list: # Only attempt to set if there are valid required params
                if hasattr(current_schema_instance, 'required'):
                    current_schema_instance.required = valid_required_list
                else: # Fallback for SDKs where 'required' might be a direct attribute post-init
                    try: setattr(current_schema_instance, 'required', valid_required_list)
                    except Exception as e_set_req: log.warning(f"Could not set 'required' on schema for {tool_name}: {e_set_req}")
            return current_schema_instance
        except Exception as e:
            log.error(f"Tool '{tool_name}': Overall schema conversion failed: {e}", exc_info=True)
            return None

    def _convert_individual_parameter_to_schema(self, param_name: str, param_details: Dict[str, Any]) -> Optional[SchemaType]:
        try:
            primary_type_str = "string"
            is_nullable = param_details.get("nullable", False)
            param_type_info = param_details.get("type")

            if isinstance(param_type_info, str):
                primary_type_str = param_type_info.lower()
                if primary_type_str == "null": is_nullable = True; primary_type_str = "string"
            elif isinstance(param_type_info, list):
                types_in_list = [str(t).lower() for t in param_type_info]
                if "null" in types_in_list: is_nullable = True
                non_null_types = [t for t in types_in_list if t != "null"]
                primary_type_str = non_null_types[0] if non_null_types else "string"
            elif "anyOf" in param_details and isinstance(param_details["anyOf"], list):
                any_of_schemas = param_details["anyOf"]
                found_types = []
                for item_schema in any_of_schemas:
                    if isinstance(item_schema, dict) and "type" in item_schema:
                        item_type_str = str(item_schema["type"]).lower()
                        if item_type_str == "null": is_nullable = True
                        else: found_types.append(item_type_str)
                primary_type_str = found_types[0] if found_types else "string"
            elif param_type_info is None and 'anyOf' not in param_details:
                 primary_type_str = "string"; is_nullable = True

            glm_type_actual = self._get_glm_type_enum(primary_type_str)
            prop_schema_args: Dict[str, Any] = {
                "description": param_details.get("description"),
                "nullable": is_nullable,
            }
            
            # Handle 'type_' vs 'type' for SDK compatibility
            try: prop_schema_args["type_"] = glm_type_actual # Prefer 'type_'
            except AttributeError: prop_schema_args["type"] = glm_type_actual # Fallback to 'type'
            

            enum_values = param_details.get("enum")
            if not enum_values and "anyOf" in param_details and isinstance(param_details["anyOf"], list):
                for item_schema in param_details["anyOf"]:
                    if isinstance(item_schema, dict) and item_schema.get("type") == primary_type_str and "enum" in item_schema:
                        enum_values = item_schema["enum"]; break
            if enum_values is not None: prop_schema_args["enum"] = enum_values

            if glm_type_actual == glm.Type.OBJECT:
                nested_props_details = param_details.get("properties")
                if isinstance(nested_props_details, dict):
                    nested_props_converted: Dict[str, SchemaType] = {}
                    for name, details in nested_props_details.items():
                        if isinstance(details, dict):
                           nested_schema_item = self._convert_individual_parameter_to_schema(f"{param_name}.{name}", details)
                           if nested_schema_item: nested_props_converted[name] = nested_schema_item
                    prop_schema_args["properties"] = nested_props_converted
                    nested_req = param_details.get("required", [])
                    if nested_req and any(r in nested_props_converted for r in nested_req):
                        prop_schema_args["required"] = [r for r in nested_req if r in nested_props_converted]
                else:
                    try: prop_schema_args["type_"] = glm.Type.STRING # type: ignore
                    except: prop_schema_args["type"] = glm.Type.STRING # type: ignore
                    if not prop_schema_args.get("description"): prop_schema_args["description"] = "Object parameter (simplified to string)"

            elif glm_type_actual == glm.Type.ARRAY:
                items_param_details = param_details.get("items")
                if isinstance(items_param_details, dict):
                    items_schema_converted = self._convert_individual_parameter_to_schema(f"{param_name}[items]", items_param_details)
                    if items_schema_converted: prop_schema_args["items"] = items_schema_converted
                    else: prop_schema_args["items"] = glm.Schema(type_=glm.Type.STRING, description="Fallback string item")
                else:
                    log.warning(f"Parameter '{param_name}': Array type missing valid 'items' definition. Using string default.")
                    prop_schema_args["items"] = glm.Schema(type_=glm.Type.STRING, description="Array item (type not specified or invalid)")

            prop_schema_args_cleaned = {k: v for k, v in prop_schema_args.items() if v is not None}
            return glm.Schema(**prop_schema_args_cleaned)
        except Exception as e:
            log.error(f"Parameter '{param_name}': Failed to create schema: {e}. Using string fallback.", exc_info=True)
            return glm.Schema(type_=glm.Type.STRING, description=param_details.get("description", f"Error processing schema for {param_name}"), nullable=True)

    def prepare_tools_for_sdk(self, tool_definitions: List[Dict[str, Any]], query: Optional[str] = None, app_state: Optional[AppState] = None) -> Optional[ToolType]:
        # (Implementation from previous corrected version, ensuring ToolSelector check is safe)
        if not tool_definitions: log.debug("No tool definitions to prepare_tools_for_sdk."); return None
        if not SDK_AVAILABLE: log.error("SDK not available for prepare_tools_for_sdk."); return None
        if query and is_greeting_or_chitchat(query.strip().lower()): log.info(f"Greeting/chitchat query '{query}', no tools."); return None

        processing_tools: List[Dict[str, Any]]
        if query and self.tool_selector and hasattr(self.tool_selector, 'enabled') and self.tool_selector.enabled:
            selected_detailed_tools = self.tool_selector.select_tools(query, app_state=app_state, available_tools=tool_definitions)
            processing_tools = selected_detailed_tools if selected_detailed_tools else tool_definitions
            log.info(f"ToolSelector selected {len(processing_tools)} tools.")
        else:
            processing_tools = tool_definitions

        max_declarations = getattr(self.config, 'MAX_FUNCTION_DECLARATIONS', 64)
        if len(processing_tools) > max_declarations:
            log.warning(f"Truncating tools from {len(processing_tools)} to {max_declarations}")
            processing_tools = processing_tools[:max_declarations]
        if not processing_tools: log.warning("No tools after filtering for SDK prep."); return None

        declarations: List[FunctionDeclarationType] = []
        for tool_dict in processing_tools:
            if not (isinstance(tool_dict, dict) and "name" in tool_dict and "description" in tool_dict):
                log.warning(f"Skipping invalid tool def: {_safe_sdk_object_repr_for_log(tool_dict)}"); continue
            name, desc = tool_dict["name"], tool_dict["description"]
            params_schema = self._convert_parameters_to_schema(name, tool_dict.get("parameters", {})) if tool_dict.get("parameters") else None
            try:
                decl_args = {"name": name, "description": desc}
                if params_schema: decl_args["parameters"] = params_schema
                # Ensure parameters is at least an empty object if not None, for some SDK versions
                elif 'parameters' not in decl_args :
                     try: decl_args["parameters"] = glm.Schema(type=glm.Type.OBJECT, properties={}) # type: ignore
                     except: pass # If this fails, it means parameters=None is acceptable

                declarations.append(glm.FunctionDeclaration(**decl_args)) # type: ignore
            except Exception as e: log.error(f"Failed FunctionDeclaration for '{name}': {e}", exc_info=True)
        
        if not declarations: log.warning("No valid function declarations prepared."); return None
        log.info(f"Prepared {len(declarations)} declarations: {[d.name for d in declarations]}")
        try: return glm.Tool(function_declarations=declarations)
        except Exception as e: log.error(f"Failed to create Tool object: {e}", exc_info=True); return None

    def health_check(self) -> Dict[str, Any]:
        start_time = time.monotonic()
        log.debug(f"Performing health check for Gemini model: {self.model_name}")
        if not SDK_AVAILABLE:
            return {"status": "ERROR", "message": "google-genai SDK not available.", "component": "LLM"}
        try:
            model_path = f"models/{self.model_name}" if not self.model_name.startswith("models/") else self.model_name
            model_info = genai.get_model(model_path)
            elapsed = time.monotonic() - start_time
            log.info(f"Gemini health check successful for model: {self.model_name} (took {elapsed:.3f}s)")
            return {
                "status": "OK", "message": f"Model '{self.model_name}' available via SDK.", "component": "LLM",
                "details": {"display_name": getattr(model_info, 'display_name', 'N/A'), "version": getattr(model_info, 'version', 'N/A')}
            }
        except google_exceptions.NotFound as e:
            log.warning(f"Gemini health check: Model '{self.model_name}' not found. Error: {e}", exc_info=False)
            return {"status": "DOWN", "message": f"Model '{self.model_name}' not found.", "component": "LLM"}
        except google_exceptions.PermissionDenied as e: # Added from original error handling
            log.error(f"Gemini health check failed for '{self.model_name}' due to permissions: {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Permission denied for model '{self.model_name}'. Check API key.", "component": "LLM"}
        except google_exceptions.ResourceExhausted as e: # Added from original
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
            log.warning(f"Invalid persona name: {persona_name}. Using default prompt.")
            return self.config.DEFAULT_SYSTEM_PROMPT
        prompts = getattr(self.config, 'PERSONA_SYSTEM_PROMPTS', {})
        prompt = prompts.get(persona_name, self.config.DEFAULT_SYSTEM_PROMPT)
        if prompt == self.config.DEFAULT_SYSTEM_PROMPT and persona_name not in prompts:
            log.warning(f"No prompt for persona '{persona_name}'. Using default.")
        else:
            log.debug(f"Using prompt for persona: {persona_name}")
        return prompt

    def _create_cache_key(self, messages: List[RuntimeContentType], tools: Optional[List[Dict[str,Any]]] = None, model_name: Optional[str] = None) -> str:
        # Simplified version from previous response, ensure robustness if original was more complex and needed.
        # The key is to make this deterministic and avoid errors.
        try:
            msg_digests = []
            for msg in messages:
                role = str(getattr(msg, 'role', msg.get('role') if isinstance(msg, dict) else 'unknown_role'))
                parts_content = ""
                msg_parts = getattr(msg, 'parts', msg.get('parts') if isinstance(msg, dict) else [])
                if isinstance(msg_parts, list):
                    for part_item in msg_parts:
                        parts_content += str(getattr(part_item, 'text', part_item.get('text') if isinstance(part_item, dict) else ''))
                msg_digests.append(f"r:{role[:1]}_c:{hashlib.md5(parts_content.encode()).hexdigest()[:8]}")

            tool_names_str = "no_tools"
            if tools:
                tool_names_str = ",".join(sorted([t.get("name","") for t in tools]))

            key_string = f"m:{model_name or self.model_name}|msgs:{'|'.join(msg_digests)}|t:{tool_names_str}"
            return hashlib.sha256(key_string.encode('utf-8')).hexdigest()
        except Exception as e:
            log.warning(f"Error creating cache key, using fallback: {e}")
            return f"fallback_key_{time.time()}" # Basic fallback

    async def generate_content(
        self, messages: List[RuntimeContentType], app_state: Optional[AppState] = None,
        tools: Optional[List[Dict[str, Any]]] = None, query: Optional[str] = None
    ) -> Any:
        if not SDK_AVAILABLE: raise RuntimeError("LLM SDK not available")
        class SimpleResponse:
            text: str; tool_calls: List[Any]
            def __init__(self): self.text = ""; self.tool_calls = []
        response = SimpleResponse()
        try:
            async for chunk in self.generate_content_stream(messages, app_state or AppState(), tools, query): # Ensure AppState is passed
                if chunk.get("type") == "text_chunk": response.text += chunk.get("content", "")
                elif chunk.get("type") == "tool_calls": response.tool_calls.extend(chunk.get("content", []))
                elif chunk.get("type") == "error": raise RuntimeError(f"LLM generation failed: {chunk.get('content', 'Unknown error')}")
            return response
        except Exception as e: raise RuntimeError(f"Failed to generate content: {e}") from e

    async def generate_content_stream(
        self, messages: List[RuntimeContentType], app_state: AppState,
        tools: Optional[List[Dict[str, Any]]] = None, query: Optional[str] = None
    ) -> AsyncIterable[Dict[str, Any]]:

        if not SDK_AVAILABLE:
            log.error("LLMInterface: google-genai SDK not available.")
            yield {"type": "error", "content": "LLM SDK not available.", "code": "SDK_UNAVAILABLE", "retryable": False}; return

        llm_call_id = start_llm_call(self.model_name)
        log.info(f"LLM Call [{llm_call_id}] - Starting generate_content_stream. Model: {self.model_name}")

        cache_key: Optional[str] = None
        if self.CACHE_ENABLED:
            try:
                cache_key = self._create_cache_key(messages, tools, self.model_name)
                if cache_key in self.response_cache:
                    log.info(f"LLM Call [{llm_call_id}] - Cache HIT: {cache_key[:10]}...")
                    for event_part in self.response_cache[cache_key]: yield event_part
                    self.response_cache[cache_key] = self.response_cache.pop(cache_key)
                    clear_llm_call_id(); return
                log.info(f"LLM Call [{llm_call_id}] - Cache MISS: {cache_key[:10]}...")
            except Exception as e_cache: log.warning(f"LLM Call [{llm_call_id}] - Cache error: {e_cache}. Proceeding without.", exc_info=True); cache_key = None

        prepared_tools_sdk: Optional[ToolType] = None
        if tools:
            try:
                prepared_tools_sdk = self.prepare_tools_for_sdk(tools, query=query, app_state=app_state)
                if prepared_tools_sdk and hasattr(prepared_tools_sdk, 'function_declarations'): log.info(f"LLM Call [{llm_call_id}] - Tools for SDK: {[decl.name for decl in prepared_tools_sdk.function_declarations]}") # type: ignore
                else: log.info(f"LLM Call [{llm_call_id}] - No tools prepared for SDK.")
            except Exception as e_tool_prep:
                log.error(f"LLM Call [{llm_call_id}] - Error preparing tools: {e_tool_prep}", exc_info=True)
                yield {"type": "error", "content": f"Tool prep error: {e_tool_prep}", "code": "TOOL_PREP_ERROR", "retryable": False}; clear_llm_call_id(); return

        current_generation_config = self.generation_config
        max_retries = self.config.DEFAULT_API_MAX_RETRIES if hasattr(self.config, 'DEFAULT_API_MAX_RETRIES') else 2 # Default to 2 if not set
        base_retry_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                log.info(f"LLM Call [{llm_call_id}] - Attempt {attempt + 1}/{max_retries + 1} to generate_content.")
                # SDK Message Preparation
                sdk_messages: List[Any] = []
                for msg in messages:
                    if isinstance(msg, dict) and "role" in msg and "parts" in msg: sdk_messages.append(msg)
                    elif hasattr(msg, 'role') and hasattr(msg, 'parts'): sdk_messages.append(msg)
                    else: log.error(f"LLM Call [{llm_call_id}] - Invalid message format: {type(msg)}. Skipping."); continue
                if not sdk_messages:
                    log.error(f"LLM Call [{llm_call_id}] - No valid messages.");
                    yield {"type": "error", "content": "No valid messages.", "code": "NO_VALID_MESSAGES", "retryable": False}; clear_llm_call_id(); return

                tool_config_for_api = None
                if prepared_tools_sdk and hasattr(glm, 'ToolConfig') and hasattr(glm, 'FunctionCallingConfig'):
                    tool_config_for_api = glm.ToolConfig(function_calling_config=glm.FunctionCallingConfig(mode=glm.FunctionCallingConfig.Mode.AUTO))

                api_response_stream = self.model.generate_content(
                    sdk_messages,
                    generation_config=current_generation_config,
                    tools=prepared_tools_sdk,
                    stream=True,
                    request_options={"timeout": self.timeout},
                    tool_config=tool_config_for_api
                )

                all_chunks_for_cache: List[Dict[str, Any]] = []
                for sdk_response_chunk_obj in api_response_stream: # sdk_response_chunk_obj is GenerateContentResponse
                    try:
                        # Convert the entire GenerateContentResponse chunk from SDK to dict immediately
                        response_chunk_dict = sdk_response_chunk_obj.to_dict() if hasattr(sdk_response_chunk_obj, 'to_dict') else {}

                        # Now operate on response_chunk_dict
                        text_from_chunk = response_chunk_dict.get('text')
                        if text_from_chunk: # Check if text key exists and is not empty
                            event = {"type": "text_chunk", "content": text_from_chunk}
                            all_chunks_for_cache.append(event); yield event
                        
                        candidates_list_from_dict = response_chunk_dict.get('candidates')
                        if candidates_list_from_dict: # Check if candidates key exists and is not empty
                            for candidate_dict in candidates_list_from_dict: # candidate_dict is a dict from a Candidate
                                content_dict = candidate_dict.get('content', {}) # content_dict is a dict from a Content
                                list_of_part_dicts = content_dict.get('parts', []) # list_of_part_dicts is list of dicts from Parts
                                
                                for part_dict in list_of_part_dicts: # part_dict is a dict from a Part
                                    # ---- SAFE processing of each part_dict (from user's original fix) ----
                                    try:
                                        fc_dict = part_dict.get("functionCall")  # camel-case in SDK
                                        if fc_dict:
                                            # ---------- it really is a function-call part ----------
                                            fn_name = fc_dict.get("name")
                                            if fn_name:
                                                args_dict = safe_extract_function_call(
                                                    fc_dict.get("args", {})
                                                )
                                                fc_event = {
                                                    "id": f"tc_{uuid.uuid4().hex[:8]}",
                                                    "function": {"name": fn_name, "arguments": args_dict},
                                                }
                                                event = {"type": "tool_calls", "content": [fc_event]}
                                                all_chunks_for_cache.append(event)
                                                yield event
                                                log.info(
                                                    f"LLM Call [{llm_call_id}] - Processed tool call: {fn_name}"
                                                )
                                            # If fn_name missing, just ignore—malformed but harmless
                                            continue  # go to next part_dict

                                        # ---------- plain text (or something else) ----------
                                        text_payload = part_dict.get("text")
                                        if text_payload:
                                            event = {"type": "text_chunk", "content": text_payload}
                                            all_chunks_for_cache.append(event)
                                            yield event

                                        # Anything else (images, citations, etc.) is skipped for now.

                                    except Exception as e_inner_part_processing:
                                        # Absolutely no fatal exits here—log and continue
                                        log.error(
                                            f"LLM Call [{llm_call_id}] - Skipped a response part_dict due to "
                                            f"parsing error: {e_inner_part_processing}",
                                            exc_info=True, # Keep exc_info=True for detailed debugging
                                        )
                                        continue
                                    # --------------------------------------------------------------------
                    except Exception as e_stream_part_iteration: # Outer catch for errors during chunk iteration/processing
                        err_str = str(e_stream_part_iteration)
                        log.error(f"LLM Call [{llm_call_id}] - Error processing streamed GenerateContentResponse chunk: {err_str}", exc_info=True)
                        # If this outer exception is hit, it might be due to sdk_response_chunk_obj.to_dict() failing
                        # or some other issue not caught by the inner part processing.
                        # Avoid re-throwing "function_call" errors if they somehow still occur here,
                        # as the primary goal is robust handling of those.
                        if "functionCall" not in err_str and "function_call" not in err_str:
                            recovery_msg = "Problem processing LLM response stream chunk."
                            # Use a more specific error code if this path is hit.
                            error_event = {"type": "error", "content": {"code": "STREAM_CHUNK_PROCESSING_ERROR", "message": recovery_msg}}
                            all_chunks_for_cache.append(error_event); yield error_event
                        # No critical stop here to allow other parts of the stream (if any) to be processed if possible,
                        # unless the error is from the .to_dict() call itself, in which case the loop might break.

                if self.CACHE_ENABLED and cache_key and all_chunks_for_cache:
                    if len(self.response_cache) >= self.CACHE_MAX_SIZE:
                        try: self.response_cache.pop(next(iter(self.response_cache)))
                        except: pass
                    self.response_cache[cache_key] = all_chunks_for_cache
                    log.info(f"LLM Call [{llm_call_id}] - Response cached: {cache_key[:10]}...")
                log.info(f"LLM Call [{llm_call_id}] - Stream completed successfully.")
                yield {"type": "completed", "content": {"status": "COMPLETED_OK"}}
                clear_llm_call_id(); return

            except google_exceptions.RetryError as e: code, msg = "API_RETRY_ERROR", str(e); log.warning(f"LLM Call [{llm_call_id}] - SDK RetryError: {msg}", exc_info=True)
            except google_exceptions.DeadlineExceeded as e: code, msg = "API_TIMEOUT", str(e); log.warning(f"LLM Call [{llm_call_id}] - DeadlineExceeded: {msg}", exc_info=True)
            except google_exceptions.ServiceUnavailable as e: code, msg = "API_SERVICE_UNAVAILABLE", str(e); log.warning(f"LLM Call [{llm_call_id}] - ServiceUnavailable: {msg}", exc_info=True)
            except google_exceptions.ResourceExhausted as e: code, msg = "API_RATE_LIMIT", str(e); base_retry_delay = 5.0; log.warning(f"LLM Call [{llm_call_id}] - ResourceExhausted: {msg}", exc_info=True)
            except (google_exceptions.InvalidArgument, google_exceptions.PermissionDenied, google_exceptions.Unauthenticated, google_exceptions.NotFound) as e:
                log.error(f"LLM Call [{llm_call_id}] - Non-retryable API error: {e}", exc_info=True)
                yield {"type": "error", "content": f"LLM API client/auth error: {e}", "code": "API_CLIENT_ERROR", "retryable": False}; clear_llm_call_id(); return
            except (requests_exceptions.ConnectionError, requests_exceptions.Timeout, TimeoutError) as e: code, msg = "NETWORK_TIMEOUT_ERROR", str(e); log.warning(f"LLM Call [{llm_call_id}] - Network/Timeout error: {msg}", exc_info=True)
            except Exception as e:
                log.error(f"LLM Call [{llm_call_id}] - Unexpected error in API call attempt {attempt + 1}: {e}", exc_info=True)
                yield {"type": "error", "content": f"Unexpected error in LLM stream init: {e}", "code": "UNEXPECTED_LLM_ERROR", "retryable": False}; clear_llm_call_id(); return

            if attempt >= max_retries:
                log.error(f"LLM Call [{llm_call_id}] - Max retries for {code}. Error: {msg}") # type: ignore
                yield {"type": "error", "content": f"LLM API op failed: {msg}", "code": code, "retryable": True, "final_attempt": True}; clear_llm_call_id(); return # type: ignore
            
            wait = (base_retry_delay * (2 ** attempt)) + random.uniform(0, 0.5)
            log.info(f"LLM Call [{llm_call_id}] - Retrying in {wait:.2f}s...")
            await asyncio.sleep(wait)

        log.error(f"LLM Call [{llm_call_id}] - All retries failed.")
        yield {"type": "error", "content": "LLM op failed after all retries.", "code": "API_MAX_RETRIES_EXCEEDED", "retryable": True, "final_attempt": True}
        clear_llm_call_id()