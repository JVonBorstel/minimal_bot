import logging
from typing import List, Dict, Any, Optional, Iterable, Union, TypeAlias, TYPE_CHECKING
import time
import re

# Use google.api_core.exceptions for specific API errors
from google.api_core import exceptions as google_exceptions
from requests import exceptions as requests_exceptions

# Import the main Config class for type hinting and settings access
from config import Config

# Import ToolSelector for dynamic tool selection
from core_logic.tool_selector import ToolSelector

# Import text utility functions
from core_logic.text_utils import is_greeting_or_chitchat

# Import AppState for type hinting
from state_models import AppState

# --- SDK Types Setup ---
SDK_AVAILABLE = False

# Define TypeAliases to Any. These will be the primary aliases used in the code.
# The TYPE_CHECKING block below will provide more specific types for the checker only.
GenerativeModelType: TypeAlias = Any
ToolType: TypeAlias = Any
PartType: TypeAlias = Any
FunctionDeclarationType: TypeAlias = Any
SchemaType: TypeAlias = Any
ContentType: TypeAlias = Union[Dict[str, Any], Any] # Allow Any for glm.Content fallback
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
    # These imports are only for static type checking hints inside functions if needed,
    # or for casting. The global TypeAliases above remain 'Any'.
    import google.ai.generativelanguage as glm_tc_

    # Example: if you needed to hint a variable as the specific SDK model type
    # my_model: genai_tc_.GenerativeModel = get_model()
    # The global GenerativeModelType alias remains 'Any' to avoid redeclaration.

    RuntimeContentType = Union[Dict[str, Any], glm_tc_.Content]
else:
    RuntimeContentType = Union[Dict[str, Any], Any]

# Attempt to import the actual SDK for runtime
try:
    import google.generativeai as actual_genai
    import google.ai.generativelanguage as actual_glm

    genai = actual_genai
    glm = actual_glm
    
    # Now that genai and glm are populated, we can refine the global TypeAliases
    # if we choose to, but it's often cleaner to keep them as `Any` globally
    # and use `cast` or more specific annotations within functions if necessary,
    # relying on the TYPE_CHECKING imports for those specific hints.
    # For simplicity here, we will update the global TypeAliases if SDK is available.
    # This might still cause issues with some type checkers if not handled perfectly.
    # A safer approach is to keep them Any and cast/annotate locally.

    # Let's try NOT redefining them globally here to avoid redeclaration issues.
    # The runtime `genai` and `glm` objects will have their correct types.

    SDK_AVAILABLE = True
    log_glm = logging.getLogger("google.ai.generativelanguage")
    log_glm.setLevel(logging.WARNING)

except ImportError:
    logging.getLogger(__name__).error(
        "google-generativeai SDK not found. Please install 'google-generativeai'. LLM functionality will be limited.",
        exc_info=False
    )

# Get the 'llm' section logger
log = logging.getLogger("llm")


class LLMInterface:
    """
    Handles interactions with the configured Google Gemini LLM API
    using the google-generativeai SDK.
    """

    def __init__(self, config: Config):
        """
        Initializes the LLMInterface using settings from the validated Config object.

        Args:
            config: The application configuration object (validated by Pydantic).

        Raises:
            ImportError: If the google-generativeai SDK is required but not installed.
            RuntimeError: If SDK configuration fails despite availability.
        """
        if not SDK_AVAILABLE:
            raise ImportError("google-generativeai SDK is required but not installed.")

        self.config = config
        self.api_key: str = config.GEMINI_API_KEY # Required by config validation
        self.model_name: str = config.GEMINI_MODEL # Default from config
        self.timeout: int = config.DEFAULT_API_TIMEOUT_SECONDS
        
        # Initialize the ToolSelector
        self.tool_selector = ToolSelector(config)

        try:
            # Configure the SDK globally. This is usually done once.
            genai.configure(api_key=self.api_key)
            log.info(f"google-genai SDK configured successfully. Default Model: {self.model_name}, Request Timeout: {self.timeout}s")
            # Instantiate the model client now
            self.model = genai.GenerativeModel(
                self.model_name,
                system_instruction=self.config.DEFAULT_SYSTEM_PROMPT
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
        """
        Updates the Gemini model used by the interface.

        Args:
            model_name: The new Gemini model name (e.g., "models/gemini-1.5-pro-latest").
            
        Raises:
            ValueError: If the model name is invalid or inaccessible.
            RuntimeError: For other unexpected errors during model update.
        """
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
            # Re-initialize the model client with the new name
            # SDK configuration with API key is global and doesn't need reset
            self.model = genai.GenerativeModel(
                model_name,
                system_instruction=self.config.DEFAULT_SYSTEM_PROMPT # Apply system instruction here as well
            )
            self.model_name = model_name
            log.info(f"Successfully updated LLM client to use model: {self.model_name}")
        except (google_exceptions.NotFound, google_exceptions.InvalidArgument) as e:
             log.error(f"Failed to update to model '{model_name}'. It might be invalid or inaccessible: {e}", exc_info=True)
             # Keep the previous model client
             log.warning(f"Reverting to previous model: {prev_model_name}")
             self.model = prev_model
             self.model_name = prev_model_name
             raise ValueError(f"Invalid or inaccessible model name: {model_name}") from e
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during model update to '{model_name}': {e}", exc_info=True)
            # Revert to previous model
            log.warning(f"Reverting to previous model: {prev_model_name}")
            self.model = prev_model
            self.model_name = prev_model_name
            raise RuntimeError(f"Network failure during model update: {e}") from e
        except Exception as e:
            log.error(f"Unexpected error updating model client to '{model_name}': {e}", exc_info=True)
             # Attempt to revert
            log.warning(f"Reverting to previous model: {prev_model_name}")
            self.model = prev_model
            self.model_name = prev_model_name
            raise RuntimeError(f"Failed to update LLM model client: {e}") from e

    def _get_glm_type_enum(self, type_str: str) -> Any:
        """
        Maps JSON schema type strings to google.ai.generativelanguage.Type enum.
        
        Args:
            type_str: The JSON schema type string to convert
            
        Returns:
            The corresponding glm.Type enum value
        """
        type_mapping = {
            "string": glm.Type.STRING,
            "number": glm.Type.NUMBER,
            "integer": glm.Type.INTEGER,
            "boolean": glm.Type.BOOLEAN,
            "object": glm.Type.OBJECT,
            "array": glm.Type.ARRAY,
            # Add other mappings if necessary
        }
        # Default to STRING if type is unknown or invalid
        default_type = glm.Type.STRING
        glm_type = type_mapping.get(type_str.lower(), default_type)
        if glm_type == default_type and type_str.lower() not in type_mapping:
            log.warning(f"Unsupported schema type '{type_str}'. Defaulting to {default_type.name}.")
        return glm_type

    def _convert_parameters_to_schema(self, tool_name: str, parameters: Dict[str, Any]) -> Optional[SchemaType]:
        """
        Helper to recursively convert JSON Schema parameter definitions (dict)
        into a google.ai.generativelanguage.Schema object.
        
        Args:
            tool_name: The name of the tool these parameters belong to (for logging).
            parameters: The JSON Schema parameters dictionary to convert
            
        Returns:
            A SchemaType object representing the parameters, or None if invalid/empty

        Note: Advanced JSON schema keywords such as 'oneOf', 'allOf', and 'format'
              are not currently processed by this function.
        """
        # Validate input structure
        if not parameters:
            log.debug("No parameters provided, returning None for schema.")
            return None # No parameters defined
            
        if not isinstance(parameters, dict):
            log.warning(f"Invalid parameters format (not a dict): {type(parameters)}. Returning None.")
            return None

        # Expecting OpenAI-like structure: {"type": "object", "properties": {...}, "required": [...]}
        if parameters.get("type") != "object" or "properties" not in parameters:
            log.warning(f"Invalid parameter structure. Expected 'type: object' with 'properties'. Got: {parameters}")
            # Return an empty object schema as a fallback
            return glm.Schema(type_=glm.Type.OBJECT, properties={})

        try:
            # Get schema optimization settings from config
            schema_opt_config = self.config.SCHEMA_OPTIMIZATION
            max_tool_props = schema_opt_config.get("max_tool_schema_properties", 12) 
            max_desc_len = schema_opt_config.get("max_tool_description_length", 150)
            max_enum_vals = schema_opt_config.get("max_tool_enum_values", 8)
            max_nested_obj_props = schema_opt_config.get("max_nested_object_properties", 5)
            max_array_item_obj_props = schema_opt_config.get("max_array_item_properties", 4)
            # simplify_complex_obj = schema_opt_config.get("flatten_nested_objects", False) # Not directly used here, but for context

            schema_props = {}
            required_params = parameters.get("required", [])
            props = parameters.get("properties", {})

            if not isinstance(props, dict):
                log.warning(f"Properties is not a dictionary: {type(props)}. Returning empty schema.")
                return glm.Schema(type_=glm.Type.OBJECT, properties={})

            # Maximum property count for the tool's schema
            if len(props) > max_tool_props:
                log.warning(f"Tool '{tool_name}' has too many properties ({len(props)}). Limiting to {max_tool_props} to reduce complexity.")
                # Keep only required properties first, then add others up to limit
                required_props_dict = {k: props[k] for k in props if k in required_params and k in props}
                other_props_dict = {k: props[k] for k in props if k not in required_params and k in props}
                
                reduced_props = {}
                reduced_props.update(required_props_dict)
                
                remaining_slots = max_tool_props - len(reduced_props)
                for k, v in list(other_props_dict.items())[:remaining_slots]:
                    reduced_props[k] = v
                props = reduced_props # Replace original props with reduced set
                log.info(f"Tool '{tool_name}' properties reduced from {len(parameters.get('properties', {}))} to {len(props)}")


            for prop_name, prop_details in props.items():
                if not isinstance(prop_details, dict):
                    log.warning(f"Tool '{tool_name}': Skipping invalid property '{prop_name}'. Reason: Not a dict. Details: {prop_details}")
                    continue
 
                # Aggressively truncate description length
                if "description" in prop_details and isinstance(prop_details["description"], str):
                    orig_desc_len = len(prop_details["description"])
                    if orig_desc_len > max_desc_len:
                        prop_details["description"] = prop_details["description"][:max_desc_len-3] + "..."
                        log.debug(f"Tool '{tool_name}': Truncated description for property '{prop_name}' from {orig_desc_len} to {max_desc_len} chars")

                # Determine primary type and nullability
                prop_type_info = prop_details.get("type")
                is_nullable = prop_details.get("nullable", False)
                primary_type_str = "string" # Default

                if isinstance(prop_type_info, str):
                    primary_type_str = prop_type_info
                    if primary_type_str.lower() == "null":
                        is_nullable = True
                        primary_type_str = "string" 
                        log.warning(f"Property '{prop_name}' only specifies 'type: null'. Interpreting as nullable string.")
                elif isinstance(prop_type_info, list): # Handle potential ['string', 'null']
                    types_in_list = [str(t).lower() for t in prop_type_info] 
                    if "null" in types_in_list:
                        is_nullable = True
                    non_null_types = [t for t in types_in_list if t != "null"]
                    if non_null_types:
                        primary_type_str = non_null_types[0]
                        if len(non_null_types) > 1:
                            log.warning(f"Property '{prop_name}' has multiple non-null types in list: {non_null_types}. Using '{primary_type_str}'.")
                    else: 
                        is_nullable = True
                        primary_type_str = "string"
                        log.warning(f"Property '{prop_name}' specifies 'type: [\"null\"]'. Interpreting as nullable string.")
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
                        if len(any_of_types) > 1:
                            log.warning(f"Property '{prop_name}' has multiple non-null types in anyOf: {any_of_types}. Using '{primary_type_str}'.")
                    else: 
                        is_nullable = True
                        primary_type_str = "string"
                        log.warning(f"Property '{prop_name}' only specifies 'type: null' within anyOf. Interpreting as nullable string.")
                elif prop_type_info is None and 'anyOf' not in prop_details:
                    log.warning(f"Property '{prop_name}' has no type definition. Defaulting to nullable string.")
                    primary_type_str = "string"
                    is_nullable = True

                glm_type = self._get_glm_type_enum(primary_type_str)

                enum_values = prop_details.get("enum")
                if not enum_values and "anyOf" in prop_details and isinstance(prop_details.get("anyOf"), list):
                    for item in prop_details["anyOf"]:
                        if isinstance(item, dict) and "enum" in item and item.get("type") == primary_type_str:
                            enum_values = item["enum"]
                            if any(sub_item.get("type") == "null" for sub_item in prop_details["anyOf"] if isinstance(sub_item, dict)):\
                                is_nullable = True
                            break

                # Limit enum values
                if enum_values and isinstance(enum_values, list) and len(enum_values) > max_enum_vals:
                    orig_enum_len = len(enum_values) 
                    enum_values = enum_values[:max_enum_vals]
                    log.debug(f"Tool '{tool_name}': Reduced enum size for property '{prop_name}' from {orig_enum_len} to {max_enum_vals}")
                
                prop_schema_args = {
                    "type_": glm_type, 
                    "description": prop_details.get("description"),
                    "nullable": is_nullable, 
                }
                if enum_values is not None:
                    prop_schema_args["enum"] = enum_values
                
                if glm_type == glm.Type.OBJECT:
                    if "properties" in prop_details and isinstance(prop_details["properties"], dict) and len(prop_details["properties"]) > max_nested_obj_props:
                        log.warning(f"Tool '{tool_name}': Simplifying complex nested object for property '{prop_name}' with {len(prop_details['properties'])} sub-properties (limit {max_nested_obj_props})")
                        prop_schema_args["type_"] = glm.Type.STRING # Simplify to string
                        if "description" not in prop_schema_args or not prop_schema_args["description"]:
                             prop_schema_args["description"] = f"Complex object with {len(prop_details['properties'])} properties, simplified."
                        # Remove properties and required keys if we simplify to string
                        prop_schema_args.pop("properties", None)
                        prop_schema_args.pop("required", None)
                    else:
                        nested_schema = self._convert_parameters_to_schema(tool_name, prop_details)
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
                    
                    if items_details and isinstance(items_details, dict):
                        # Simplify complex array item object
                        if items_details.get("type") == "object" and "properties" in items_details and isinstance(items_details["properties"], dict) and len(items_details["properties"]) > max_array_item_obj_props:
                            log.warning(f"Tool '{tool_name}': Simplifying complex array item object for property '{prop_name}' (item props limit {max_array_item_obj_props})")
                            items_details = {"type": "string", "description": "Simplified array item (was complex object)"}
                    
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
                             nested_item_schema = self._convert_parameters_to_schema(tool_name, items_details) 
                             if nested_item_schema:
                                 items_schema_args["properties"] = nested_item_schema.properties
                                 if nested_item_schema.required:
                                     items_schema_args["required"] = nested_item_schema.required
                             else:
                                 items_schema_args["properties"] = {}
                        
                        items_schema_args = {k: v for k, v in items_schema_args.items() if v is not None}
                        try:
                            items_schema_object = glm.Schema(**items_schema_args)
                            prop_schema_args["items"] = items_schema_object
                            log.debug(f"Tool '{tool_name}', Property '{prop_name}': Created items schema: {items_schema_object}")
                        except Exception as item_schema_ex:
                             log.warning(f"Tool '{tool_name}', Property '{prop_name}': Failed to create glm.Schema for items. Details: {item_schema_ex}. API call may fail.", exc_info=True)
                             prop_schema_args.pop("items", None)
                    else:
                        log.warning(f"Tool '{tool_name}', Property '{prop_name}': Could not find valid 'items' definition for array type. Skipping items. API call will likely fail.")
                        prop_schema_args.pop("items", None)

                prop_schema_args = {k: v for k, v in prop_schema_args.items() if v is not None}
                schema_props[prop_name] = glm.Schema(**prop_schema_args)

            final_schema_args = {
                "type_": glm.Type.OBJECT, 
                "properties": schema_props
            }
            if required_params: # Only add 'required' if it's not empty
                final_schema_args["required"] = required_params
                
            final_schema = glm.Schema(**final_schema_args)
            return final_schema

        except Exception as e:
            log.error(f"Error converting parameters dictionary to glm.Schema: {e}\nParameters: {parameters}", exc_info=True)
            return glm.Schema(type_=glm.Type.OBJECT, properties={})

    def _extract_common_parameters_for_service(self, service_name: str, tools_in_service: List[Dict[str, Any]]) -> Optional[SchemaType]:
        """
        Extracts and consolidates common parameters for a given service's tools
        into a single glm.Schema object.
        This aims to provide the LLM with a unified parameter interface for the service.
        """
        log.debug(f"Extracting common parameters for service: {service_name}")
        
        # Consolidate all properties from all tools in the service
        all_properties = {}
        # Keep track of how many tools define each parameter to prioritize
        param_counts = {}
        # Collect all required parameters across all tools in the service
        # This is tricky because a param might be required for one tool but not another.
        # For now, we'll consider a parameter "somewhat required for the service" if it's
        # required by at least one tool. This needs refinement.
        service_level_required = set()

        for tool_dict in tools_in_service:
            tool_params_schema = tool_dict.get("parameters")
            if not tool_params_schema or tool_params_schema.get("type") != "object":
                continue

            props = tool_params_schema.get("properties", {})
            required_for_this_tool = tool_params_schema.get("required", [])

            for param_name, param_def in props.items():
                # Skip config injection parameters from service-level schema
                if param_name == 'config' and param_def.get('type') == 'object' and 'Config' in param_def.get('description', ''): # Heuristic
                    log.debug(f"Skipping 'config' parameter for service '{service_name}' common schema.")
                    continue

                if param_name not in all_properties:
                    # Store the first encountered definition of the parameter
                    # We might need a more sophisticated merging strategy for descriptions, types later
                    all_properties[param_name] = param_def 
                    param_counts[param_name] = 0
                param_counts[param_name] += 1
                
                if param_name in required_for_this_tool:
                    service_level_required.add(param_name)

        if not all_properties:
            log.debug(f"No common parameters found for service: {service_name}")
            return glm.Schema(type_=glm.Type.OBJECT, properties={}) # Return empty object schema

        # Filter parameters: keep those that are frequent or marked as service-level required.
        # This is a heuristic and might need tuning.
        # For instance, keep params that appear in >50% of tools OR are required by at least one.
        final_properties_for_service_schema = {}
        num_tools_in_service = len(tools_in_service)
        
        # Prioritize parameters that are required by at least one tool
        # Then add frequently occurring ones up to a limit (e.g. MAX_PROPERTIES from _convert_parameters_to_schema)
        
        # Start with parameters that are required in any tool of the service
        for param_name in service_level_required:
            if param_name in all_properties:
                 final_properties_for_service_schema[param_name] = all_properties[param_name]
        
        # Add other parameters based on frequency, up to MAX_PROPERTIES
        # This is a simplified selection; a more robust approach might score parameters.
        MAX_SERVICE_PROPERTIES = self.config.MAX_SERVICE_SCHEMA_PROPERTIES # Get from config
        
        sorted_by_freq = sorted(param_counts.items(), key=lambda item: item[1], reverse=True)
        
        for param_name, count in sorted_by_freq:
            if len(final_properties_for_service_schema) >= MAX_SERVICE_PROPERTIES:
                log.debug(f"Reached max ({MAX_SERVICE_PROPERTIES}) properties for service '{service_name}' schema. Skipping '{param_name}'.")
                break
            if param_name not in final_properties_for_service_schema and param_name in all_properties:
                 # Only add if it's not already added (e.g. from required set)
                 final_properties_for_service_schema[param_name] = all_properties[param_name]
        
        if not final_properties_for_service_schema:
             log.warning(f"No parameters selected for service '{service_name}' after filtering. LLM may lack parameter context.")
             return glm.Schema(type_=glm.Type.OBJECT, properties={})

        # Now, convert this consolidated 'final_properties_for_service_schema' 
        # and 'service_level_required' (only those present in final_properties)
        # into a glm.Schema object, similar to _convert_parameters_to_schema.
        
        # Construct the input dict for _convert_parameters_to_schema
        consolidated_parameters_dict = {
            "type": "object",
            "properties": final_properties_for_service_schema,
            # Only include 'required' if there are any, and they exist in the final_properties
            "required": [p for p in service_level_required if p in final_properties_for_service_schema] or [] 
        }
        
        log.debug(f"Consolidated parameters dict for service '{service_name}': {consolidated_parameters_dict}")

        # Reuse _convert_parameters_to_schema for the actual glm.Schema conversion
        # The tool_name arg here is for logging within _convert_parameters_to_schema
        service_schema = self._convert_parameters_to_schema(
            tool_name=f"service_{service_name}", # Pass a representative name
            parameters=consolidated_parameters_dict
        )
        
        if service_schema:
            log.info(f"Successfully created common parameter schema for service: {service_name} with {len(service_schema.properties or {})} properties.")
        else:
            log.warning(f"_convert_parameters_to_schema returned None or empty for service: {service_name}. Using default empty schema.")
            # Fallback to an empty object schema
            return glm.Schema(type_=glm.Type.OBJECT, properties={})
            
        return service_schema

    def prepare_tools_for_sdk(self, tool_definitions: List[Dict[str, Any]], query: Optional[str] = None, app_state: Optional[AppState] = None) -> Optional[ToolType]:
        """
        Converts a list of tool definitions (dictionaries following OpenAPI subset)
        into a google.ai.generativelanguage.Tool object for the SDK.
        This version groups tools by service and creates one function declaration per service.

        Args:
            tool_definitions: List of tool definitions.
            query: Optional user query for relevance-based selection.
            app_state: Optional AppState for permission-based filtering in ToolSelector.
        """
        if not tool_definitions:
            return None
        if not SDK_AVAILABLE:
            log.error("Cannot prepare tools: google-genai SDK not available.")
            return None
            
        # PRODUCTION FIX: Remove aggressive gatekeeping - let the ToolSelector and LLM handle intelligence
        # The old approach of blocking based on simple text patterns was too rigid for natural conversation.
        # Now we trust the semantic intelligence layers and let the LLM decide when to use tools.
        
        # Only block truly empty queries or obvious non-requests
        if query:
            query_stripped = query.strip().lower()
            # Only block very obvious non-requests (extremely minimal gatekeeping)
            obvious_non_requests = [".", "..", "?", "??", "test", "testing"]
            if query_stripped in obvious_non_requests:
                log.info(f"Detected obvious non-request: '{query}'. Not providing tools.")
                return None
            
        # If the tool selector is enabled and we have a query, select relevant tools FIRST
        # This selection should still operate on the detailed tool_definitions
        if query and self.tool_selector.enabled:
            log.info(f"Using ToolSelector for query: {query[:50]}...")
            selected_detailed_tools = self.tool_selector.select_tools(
                query, 
                app_state=app_state, # Pass app_state here
                available_tools=tool_definitions # Pass all detailed tools to selector
            )
            
            if selected_detailed_tools:
                log.info(f"ToolSelector selected {len(selected_detailed_tools)} of {len(tool_definitions)} detailed tools.")
                # Work with the subset of detailed tools selected
                # Do NOT assign back to tool_definitions yet, as category filtering might happen on ALL tools
            else:
                log.warning("Tool selection returned no tools. Proceeding with category/importance filtering on all tools.")
                selected_detailed_tools = [] # Ensure it's an empty list, not None
        else:
            log.debug(f"Tool selection not used (query: {bool(query)}, enabled: {self.tool_selector.enabled}). Using all tool definitions initially.")
            selected_detailed_tools = [] # No pre-selection by relevance

        # Determine the set of tools to actually process for declaration generation
        # If relevance selection yielded tools, use those. Otherwise, start with all tools
        # and let category/importance filtering narrow them down.
        processing_tools = selected_detailed_tools if selected_detailed_tools else tool_definitions

        # Apply category and importance filtering
        # These filters should operate on the potentially pre-selected 'processing_tools' or all tools
        if len(processing_tools) > self.config.MAX_TOOLS_BEFORE_FILTERING: # e.g., 20
            log.info(f"More than {self.config.MAX_TOOLS_BEFORE_FILTERING} tools available ({len(processing_tools)}), applying category filtering.")
            processing_tools = self._filter_tools_by_category(processing_tools, query)
            log.info(f"After category filtering: {len(processing_tools)} tools.")

        if len(processing_tools) > self.config.MAX_FUNCTION_DECLARATIONS: # e.g., 6-10 (this is now for SERVICES)
            log.warning(f"Still too many tools ({len(processing_tools)}) after category filtering. Applying importance-based selection.")
            processing_tools = self._select_most_important_tools(processing_tools, query, self.config.MAX_FUNCTION_DECLARATIONS * 3) # Select more detailed tools initially
            log.info(f"After importance filtering: {len(processing_tools)} tools to consider for service grouping.")

        # --- Group detailed tools by service name ---
        grouped_tools_by_service: Dict[str, List[Dict[str, Any]]] = {}
        for tool_dict in processing_tools: # Use the filtered list of detailed tools
            if not isinstance(tool_dict, dict) or "name" not in tool_dict:
                log.warning(f"Skipping invalid tool definition (not a dict or missing 'name'): {tool_dict}")
                continue
            
            # Derive service name (e.g., "github" from "github_list_repositories")
            # Handle names without underscores as their own service
            service_name = tool_dict["name"].split('_')[0] if '_' in tool_dict["name"] else tool_dict["name"]
            
            if service_name not in grouped_tools_by_service:
                grouped_tools_by_service[service_name] = []
            grouped_tools_by_service[service_name].append(tool_dict)

        if not grouped_tools_by_service:
            log.warning("No tools available after filtering and grouping by service.")
            return None
            
        # Limit the number of distinct service declarations
        # This is important if many services each have only one tool after filtering
        if len(grouped_tools_by_service) > self.config.MAX_FUNCTION_DECLARATIONS:
            log.warning(f"Too many distinct services ({len(grouped_tools_by_service)}) to declare. Selecting top {self.config.MAX_FUNCTION_DECLARATIONS} services by tool count/importance.")
            # Simple heuristic: sort services by number of tools (more tools = potentially more important service)
            # A more sophisticated ranking could use aggregated importance scores of tools within the service.
            sorted_services = sorted(grouped_tools_by_service.items(), key=lambda item: len(item[1]), reverse=True)
            grouped_tools_by_service = dict(sorted_services[:self.config.MAX_FUNCTION_DECLARATIONS])
            log.info(f"Reduced to {len(grouped_tools_by_service)} services for function declaration.")


        # --- Create one FunctionDeclaration per service ---
        service_function_declarations = []
        for service_name, tools_in_service in grouped_tools_by_service.items():
            log.debug(f"Preparing service-level function declaration for: {service_name} (based on {len(tools_in_service)} detailed tools)")
            try:
                # 1. Construct a comprehensive description for the service
                # Mentioning key methods available within the service
                method_details = []
                for tool_dict in tools_in_service:
                    # Extract method part of the name, or use full name if no underscore
                    method_name_part = tool_dict["name"].split('_', 1)[1] if '_' in tool_dict["name"] else tool_dict["name"]
                    desc = tool_dict.get("description", f"{method_name_part} operation.")
                    # Keep it concise for the service description
                    desc_preview = desc[:60] + "..." if len(desc) > 60 else desc
                    method_details.append(f"{method_name_part}: {desc_preview}")
                
                service_description = (
                    f"Provides access to {service_name.capitalize()} related functionalities. "
                    f"Available actions include: {'; '.join(method_details)}. "
                    "Specify parameters to clarify your intent for the desired action."
                )
                if len(service_description) > 500: # Truncate if too long
                    service_description = service_description[:497] + "..."

                # 2. Extract and consolidate common parameters for this service
                # This is a new helper method we need to define carefully
                common_params_schema: Optional[SchemaType] = self._extract_common_parameters_for_service(service_name, tools_in_service)

                # 3. Create the glm.FunctionDeclaration for the service
                service_func_decl = glm.FunctionDeclaration(
                    name=service_name, # Use the simplified service name
                    description=service_description,
                    parameters=common_params_schema # Schema of common/representative params
                )
                log.debug(f"  - Created FunctionDeclaration for service '{service_name}': {service_func_decl.name}, Desc: '{service_func_decl.description[:100]}...'")
                service_function_declarations.append(service_func_decl)

            except Exception as e:
                log.error(f"Failed to prepare service-level function declaration for '{service_name}': {e}", exc_info=True)
                continue 

        if not service_function_declarations:
            log.warning("No valid service-level function declarations could be prepared.")
            return None
        
        log.info(f"Prepared {len(service_function_declarations)} service-level function declarations for SDK: {[d.name for d in service_function_declarations]}")
        return glm.Tool(function_declarations=service_function_declarations)
            
    def _filter_tools_by_category(self, tools: List[Dict[str, Any]], query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Filter tools based on categories determined from the query.
        
        Args:
            tools: List of tool definitions
            query: Optional user query to determine relevant categories
            
        Returns:
            Filtered list of tool definitions
        """
        if not tools:
            return []
            
        # Always include these basic/essential tools
        essential_tools = ["help", "perplexity_web_search"]
        
        # Define tool categories with ACTUAL tool names
        categories = {
            "file_operations": [
                # Assuming these are actual tool names if they exist, or need to be verified
                "read_file", "write_file", "list_files", "create_directory", "delete_file"
            ],
            "git": [
                # Placeholder - actual git tool names if they exist
                "git_commit", "git_push", "git_pull", "git_status", "git_checkout"
            ],
            "github": [
                "github_list_repositories", "github_get_repository_details", "github_list_contributors", 
                "github_get_repo_contents", "github_get_file_content", "github_list_branches", 
                "github_list_commits", "github_get_commit_details", "github_get_diff", 
                "github_list_tags", "github_list_releases", "github_get_issue_details", 
                "github_get_pull_request_details", "github_search_repositories", "github_search_code", 
                "github_search_issues_prs", "github_list_workflow_runs", "github_list_organization_teams", 
                "github_create_issue", "github_add_comment_issue_pr", "github_summarize_repo", 
                "github_summarize_directory", "github_summarize_file", "github_list_collaborators", 
                "github_get_user_contribution_summary", "github_get_org_activity_feed", "github_get_pr_diff", 
                "github_get_branch_diff_summary", "github_get_changed_files_summary", "github_trigger_workflow", 
                "github_get_workflow_status", "github_get_latest_release", "github_get_release_notes", 
                "github_search_files", "github_find_symbol_definitions", "github_list_secrets", 
                "github_get_visibility_status", "github_list_large_files", "github_get_file_preview"
                # Add other key GitHub tools as needed (39 total)
            ],
            "jira": [
                "jira_get_issue", "jira_get_issue_changelog", "jira_get_comments", 
                "jira_get_attachments", "jira_get_linked_issues", "jira_get_custom_fields", 
                "jira_get_field_options", "jira_get_worklogs", "jira_get_issue_transitions", 
                "jira_search_issues", "jira_get_issues_by_user", "jira_get_project_list", 
                "jira_get_project_metadata", "jira_get_issue_types", "jira_get_user_account_id", 
                "jira_create_issue", "jira_add_comment", "jira_assign_issue", 
                "jira_update_issue_field", "jira_link_issues", "jira_create_subtask", 
                "jira_get_sprint_report", "jira_create_sprint", "jira_add_issues_to_sprint", 
                "jira_transition_issue", "jira_get_rate_limit_status"
                # Add other key Jira tools as needed (26 total)
            ],
            "greptile": [ # Adding Greptile category
                "greptile_query_codebase", "greptile_search_code", "greptile_search_code_in_path",
                "greptile_list_files", "greptile_get_file_summary", "greptile_get_symbol_info",
                "greptile_get_repo_metadata", "greptile_summarize_repo", "greptile_summarize_directory",
                "greptile_summarize_file", "greptile_batch_query", "greptile_chain_query",
                "greptile_validate_repo_url", "greptile_get_index_status", "greptile_get_rate_limit_status"
            ],
            "perplexity": [ # Adding Perplexity category
                "perplexity_web_search", "perplexity_multi_search", "perplexity_chain_query",
                "perplexity_domain_search", "perplexity_summarize_topic", "perplexity_get_sources",
                "perplexity_compare_answers", "perplexity_detect_conflicts", "perplexity_get_rate_limit_status",
                "perplexity_structured_search", "perplexity_date_range_search", "perplexity_image_search"
            ],
            "workflows": ["start_story_builder_workflow", "workflow_feedback"],
            "data_analysis": ["analyze_data", "generate_chart", "summarize_data"],
            "database": ["query_database", "update_database", "get_schema"],
            "web": ["perplexity_web_search", "fetch_webpage", "scrape_content"],
            "utility": ["help", "summarize", "translate", "timestamp", "calculator"]
        }
        
        # If no query, pick a default subset of categories
        if not query:
            # Include utility, file_operations and web by default
            default_categories = ["utility", "file_operations", "web"]
            allowed_tools = set(essential_tools)
            for cat in default_categories:
                allowed_tools.update(categories.get(cat, []))
                
            # Filter tools by the allowed set
            filtered_tools = [t for t in tools if t.get("name") in allowed_tools]
            
            # If still too many tools, just pick the first 6
            if len(filtered_tools) > 6:
                filtered_tools = filtered_tools[:6]
                
            return filtered_tools
        
        # With a query, try to determine relevant categories
        query_lower = query.lower()
        
        # Map keywords to categories
        keyword_category_map = {
            # File operations
            "file": "file_operations", "read": "file_operations", "write": "file_operations",
            "directory": "file_operations", "folder": "file_operations", "create file": "file_operations",
            "list files": "file_operations", "delete file": "file_operations",
            
            # Git
            "git": "git", "commit": "git", "branch": "git", "repository": "github", "repo": "github",
            "pull request": "github", "pr": "github",
            
            # GitHub
            "github": "github", "gh": "github", "issue": "github", "commit": "github", 
            "diff": "github", "pull request": "github", "pr": "github", "repo": "github",
            "contributors": "github", "workflow": "github", "release": "github", "tag": "github",
            "code search": "github", "repository": "github", "org": "github", "organization": "github",
            
            # Jira
            "jira": "jira", "ticket": "jira", "story": "jira", "epic": "jira", "jia": "jira",
            "sprint": "jira", "board": "jira", "project": "jira", "kanban": "jira",
            "issue key": "jira", "assignee": "jira", "worklog": "jira", "status": "jira",
            
            # Greptile
            "greptile": "greptile", "codebase": "greptile", "semantic search": "greptile",
            "code search": "greptile", "code analysis": "greptile", "find in code": "greptile",
            "search code": "greptile", "search repository": "greptile", "symbol": "greptile",

            # Perplexity
            "perplexity": "perplexity", "web search": "perplexity", "internet search": "perplexity", 
            "find online": "perplexity", "search online": "perplexity", "current": "perplexity",
            "latest": "perplexity", "news": "perplexity", "weather": "perplexity", 
            "internet": "perplexity", "web": "perplexity",
            
            # Workflows
            "workflow": "workflows", "story builder": "workflows", "story board": "workflows",
            "create ticket": "workflows", "new ticket": "workflows", "build story": "workflows",
            
            # Data analysis
            "analyze": "data_analysis", "chart": "data_analysis", "graph": "data_analysis",
            "data": "data_analysis", "statistics": "data_analysis", "metrics": "data_analysis",
            
            # Database
            "database": "database", "sql": "database", "query": "database", "db": "database",
            "table": "database", "schema": "database",
            
            # Web
            "search": "web", "internet": "web", "website": "web", "web": "web",
            "online": "web", "browser": "web", "visit": "web", "webpage": "web",
            
            # Utility
            "help": "utility", "summarize": "utility", "translate": "utility", 
            "calculate": "utility", "calc": "utility", "convert": "utility"
        }
        
        # Determine relevant categories from the query
        relevant_categories = set()
        
        # Check for direct category mentions
        for keyword, category in keyword_category_map.items():
            if keyword in query_lower:
                relevant_categories.add(category)
                
        # Always add utility category as a fallback
        relevant_categories.add("utility")
        
        # Check for specific tools by name (partial matches)
        specifically_mentioned_tools = set()
        for tool in tools:
            tool_name = tool.get("name", "").lower()
            if tool_name and tool_name in query_lower:
                specifically_mentioned_tools.add(tool.get("name"))
                # Also add the tool's category
                for category, tool_list in categories.items():
                    if tool.get("name") in tool_list:
                        relevant_categories.add(category)
        
        # Check for indirect references to GitHub resources
        github_patterns = [
            r"PR\s*#?\d+", r"issue\s*#?\d+", r"pull\s*request\s*#?\d+", 
            r"commit\s*[a-f0-9]{7,40}", r"@[\w-]+\/[\w-]+"
        ]
        if any(re.search(pattern, query_lower) for pattern in github_patterns):
            relevant_categories.add("github")
        
        # Check for Jira ticket references (e.g., PROJ-123)
        jira_patterns = [r"[A-Z]+-\d+"]
        if any(re.search(pattern, query) for pattern in jira_patterns):
            relevant_categories.add("jira")
        
        # Special case: Check for weather, news or similar perplexity-suitable queries
        web_search_indicators = [
            "weather", "news", "latest", "current", "today", "recent", 
            "how to", "what is", "who is", "when did", "where is",
            "find information", "lookup", "look up", "search for"
        ]
        if any(indicator in query_lower for indicator in web_search_indicators):
            relevant_categories.add("web")
            relevant_categories.add("perplexity")
        
        # Look for code-related queries that might need Greptile
        code_patterns = [
            "find function", "search codebase", "code example", "implementation of",
            "where is this defined", "how is this implemented", "function definition"
        ]
        if any(pattern in query_lower for pattern in code_patterns):
            relevant_categories.add("greptile")
        
        # Collect allowed tools based on relevant categories
        allowed_tools = set(essential_tools)
        allowed_tools.update(specifically_mentioned_tools)
        
        for category in relevant_categories:
            allowed_tools.update(categories.get(category, []))
            
        # Filter tools by the allowed set
        filtered_tools = [t for t in tools if t.get("name") in allowed_tools]
        
        # Log the decision process
        log.debug(f"Query: '{query}'")
        log.debug(f"Detected categories: {relevant_categories}")
        log.debug(f"Specifically mentioned tools: {specifically_mentioned_tools}")
        log.debug(f"Selected {len(filtered_tools)} tools out of {len(tools)}")
        
        # If still too many tools, use a more intelligent selection
        if len(filtered_tools) > 10:
            # Prioritize specifically mentioned tools
            priority_tools = [t for t in filtered_tools if t.get("name") in specifically_mentioned_tools]
            
            # Then prioritize by specificity of category (prefer specific api tools over general utility)
            category_priority = {
                "github": 5, "jira": 5, "greptile": 5,  # High priority for API tools
                "perplexity": 4, "web": 3,              # Medium priority for web tools
                "file_operations": 3, "data_analysis": 3, "database": 3,  # Medium
                "utility": 1                           # Low priority for utility tools
            }
            
            # Score each tool based on its category
            scored_tools = []
            for tool in filtered_tools:
                if tool in priority_tools:
                    continue  # Skip already included tools
                
                tool_name = tool.get("name", "")
                score = 0
                
                # Find which category this tool belongs to
                for category, tools_list in categories.items():
                    if tool_name in tools_list:
                        score = category_priority.get(category, 0)
                        break
                
                # Further boost tools whose name matches a keyword in the query
                for keyword in query_lower.split():
                    if keyword in tool_name.lower():
                        score += 2
                
                scored_tools.append((tool, score))
            
            # Sort by score (highest first)
            scored_tools.sort(key=lambda x: x[1], reverse=True)
            
            # Combine priority tools with highest scored tools, up to 6 total
            remaining_slots = 6 - len(priority_tools)
            selected_tools = priority_tools + [t[0] for t in scored_tools[:remaining_slots]]
            
            log.debug(f"Reduced to {len(selected_tools)} tools based on priority scoring")
            return selected_tools[:6]
        
        # Otherwise, if we have a reasonable number, return them
        if 1 <= len(filtered_tools) <= 6:
            return filtered_tools
        
        # If we have too few or too many tools (edge case), add key tools like search
        if len(filtered_tools) == 0:
            log.warning(f"Query '{query}' resulted in 0 tools. Adding essential tools.")
            # Add essential tools: help and web search
            default_tools = [t for t in tools if t.get("name") in essential_tools]
            return default_tools[:6]
        
        # Final catch-all: if we have more than 6 tools, take the first 6
        return filtered_tools[:6]
        
    def _select_most_important_tools(self, tools: List[Dict[str, Any]], query: Optional[str], max_count: int = 6) -> List[Dict[str, Any]]:
        """
        Select the most important tools for the current context, ensuring critical tools are always included.
        
        Args:
            tools: List of tool definitions
            query: Optional user query to help determine importance
            max_count: Maximum number of tools to select
            
        Returns:
            List of the most important tool definitions
        """
        if len(tools) <= max_count:
            return tools
            
        # 1. First extract basic utility tools that should always be available
        basic_tools = [t for t in tools if t.get('name') in ['help', 'perplexity_web_search']]
        remaining_slots = max_count - len(basic_tools)
        
        if remaining_slots <= 0:
            # If we've already filled all slots with basic tools, return them
            return basic_tools[:max_count]
            
        # 2. Try to extract tools that match the query context
        remaining_tools = [t for t in tools if t.get('name') not in ['help', 'perplexity_web_search']]
        
        # If we have a query, try to find the most relevant tools
        if query:
            # Simple relevance scoring based on word matching
            query_words = set(query.lower().split())
            scored_tools = []
            
            for tool in remaining_tools:
                tool_name = tool.get('name', '')
                tool_desc = tool.get('description', '')
                
                # Calculate a simple relevance score
                score = 0
                # Check tool name for query word matches
                for word in query_words:
                    if word in tool_name.lower():
                        score += 3  # Higher weight for name matches
                    if word in tool_desc.lower():
                        score += 1  # Lower weight for description matches
                
                # Tool metadata often contains categories
                metadata = tool.get('metadata', {})
                categories = metadata.get('categories', [])
                for category in categories:
                    for word in query_words:
                        if word in category.lower():
                            score += 2  # Medium weight for category matches
                
                # Add the scored tool to our list
                scored_tools.append((tool, score))
            
            # Sort by score descending
            scored_tools.sort(key=lambda x: x[1], reverse=True)
            
            # Select top scoring tools up to remaining slots
            context_tools = [t[0] for t in scored_tools[:remaining_slots]]
            
            # Combine basic tools with context-relevant tools
            result = basic_tools + context_tools
            return result
        
        # If no query or tool selector was unable to find relevant tools,
        # just return the first max_count tools (including basics)
        return basic_tools + remaining_tools[:remaining_slots]

    def health_check(self) -> Dict[str, Any]:
        """
        Checks if the configured Gemini model is accessible via the SDK.
        
        Returns:
            A dictionary containing health check results with status, message, and details
        """
        start_time = time.monotonic()
        log.debug(f"Performing health check for Gemini model: {self.model_name}")
        if not SDK_AVAILABLE:
            return {"status": "ERROR", "message": "google-genai SDK not available.", "component": "LLM"}

        try:
            # Use the SDK's get_model for a specific availability check.
            # The model_client was initialized in __init__ or update_model
            # Re-fetching confirms current accessibility with the configured API key.
            model_info = genai.get_model(self.model_name) # Fetches model details

            elapsed = time.monotonic() - start_time
            log.info(f"Gemini health check successful for model: {self.model_name} (took {elapsed:.3f}s)")
            # Optionally include more details from model_info if needed
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
        except google_exceptions.GoogleAPIError as e: # Catch other specific Google errors
            log.error(f"Gemini health check failed for '{self.model_name}' with API error: {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Gemini SDK API error: {str(e)}", "component": "LLM"}
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during Gemini health check: {e}", exc_info=True) 
            return {"status": "DOWN", "message": f"Network error: {str(e)}", "component": "LLM"}
        except Exception as e: # Catch-all for other unexpected errors
            log.error(f"Unexpected error during Gemini health check for '{self.model_name}': {e}", exc_info=True)
            return {"status": "DOWN", "message": f"Unexpected SDK error: {str(e)}", "component": "LLM"}

    def get_system_prompt_for_persona(self, persona_name: str) -> str:
        """
        Returns the appropriate system prompt for the given persona.
        
        Args:
            persona_name: The name of the persona to get the system prompt for
            
        Returns:
            The system prompt string for the specified persona
        """
        if not persona_name or not isinstance(persona_name, str):
            log.warning(f"Invalid persona name provided: {persona_name}. Using default system prompt.")
            return self.config.DEFAULT_SYSTEM_PROMPT
            
        # Get persona-specific system prompt from config
        if hasattr(self.config, 'PERSONA_SYSTEM_PROMPTS') and isinstance(self.config.PERSONA_SYSTEM_PROMPTS, dict):
            prompt = self.config.PERSONA_SYSTEM_PROMPTS.get(persona_name)
            if prompt:
                log.debug(f"Using system prompt for persona: {persona_name}")
                return prompt
                
        # If persona not found in config or PERSONA_SYSTEM_PROMPTS not available
        log.warning(f"No system prompt found for persona: {persona_name}. Using default.")
        return self.config.DEFAULT_SYSTEM_PROMPT

    def generate_content_stream(
        self,
        messages: List[RuntimeContentType],
        app_state: AppState, # Added app_state
        tools: Optional[List[Dict[str, Any]]] = None,
        query: Optional[str] = None
    ) -> Iterable[GenerateContentResponseType]:
        """
        Sends messages to the configured Gemini model and streams the response.

        Args:
            messages: A list of message dictionaries or glm.Content objects,
                      formatted correctly by the calling code (e.g., chat_logic.py).
            tools: An optional list of tool definitions (OpenAPI subset dicts).
            query: Optional user query to use for tool selection.

        Returns:
            An iterable stream of GenerateContentResponse objects from the SDK.

        Raises:
            ValueError: If required configuration is missing or inputs invalid.
            ImportError: If the google-genai SDK is not available.
            RuntimeError: For SDK configuration issues or unexpected errors.
            google.api_core.exceptions.GoogleAPIError: For API-level errors from Google.
        """
        # Validate inputs
        if not messages:
            raise ValueError("No messages provided for LLM generation")
            
        if not self.model: # Check if model client is initialized
             raise RuntimeError("LLM model client is not initialized.")
        if not SDK_AVAILABLE:
            raise ImportError("google-genai SDK is required but not available.")

        # CRITICAL FIX: Convert the input list of tool dicts to the SDK's Tool object
        sdk_tool_obj: Optional[ToolType] = None
        if tools:
            # Pass the query for tool selection
            sdk_tool_obj = self.prepare_tools_for_sdk(tools, query=query, app_state=app_state) # Pass app_state here

        # Prepare generation config (can customize temperature, top_p, etc.)
        generation_config = genai.types.GenerationConfig(
            # temperature=0.7, # Example customization
            candidate_count=1,
            # max_output_tokens=2048, # Example limit
        )

        # Prepare safety settings (optional, configure as needed)
        safety_settings: Dict[glm_tc_.HarmCategory, glm_tc_.SafetySetting.HarmBlockThreshold] = {
            # Example: Block harmful content with higher threshold
            # glm.HarmCategory.HARM_CATEGORY_HARASSMENT: glm.SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            # glm.HarmCategory.HARM_CATEGORY_HATE_SPEECH: glm.SafetySetting.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }

        # Prepare the final list of contents for the API call
        final_contents = []
        # if system_prompt: # Removed: System prompt is now handled by the model constructor
        #     # Prepend system instruction as the first element
        #     try:
        #          # We need the glm.Content type here
        #          if SDK_AVAILABLE:
        #              # Ensure parts is a list containing a Part object
        #              system_part = glm.Part(text=system_prompt)
        #              final_contents.append(glm.Content(parts=[system_part], role="system"))
        #          else:
        #              # Fallback if SDK not available (shouldn't happen here)
        #              final_contents.append({'role': 'system', 'parts': [{'text': system_prompt}]})
        #          log.debug(f"Prepended system prompt: {system_prompt[:100]}...")
        #     except Exception as sys_prompt_err:
        #          log.error(f"Failed to create system prompt content object: {sys_prompt_err}", exc_info=True)
        #          raise ValueError("Failed to format system prompt for API call") from sys_prompt_err

        # Append the user/model messages
        # Ensure messages are in the correct format (list of Content objects or compatible dicts)
        # Add validation or conversion if necessary, based on what chat_logic provides
        final_contents.extend(messages) # Add the rest of the messages

        # --- Logging for Debugging --- 
        if log.isEnabledFor(logging.DEBUG):
            log_messages = []
            try:
                for i, m in enumerate(final_contents):
                    parts_summary = []
                    role = 'unknown'
                    if isinstance(m, dict):
                        # Handle dict case (e.g., OpenAI format or fallback)
                        role = m.get('role', 'unknown')
                        content_data = m.get('parts') or m.get('content')
                        if isinstance(content_data, list):
                            for part_item in content_data:
                                if isinstance(part_item, dict) and 'text' in part_item:
                                    parts_summary.append(f"text({len(part_item['text'])} chars)")
                                elif isinstance(part_item, str): # case parts=['text'] ?
                                     parts_summary.append(f"str({len(part_item)} chars)")
                                else:
                                    parts_summary.append(f"unknown_dict_part({type(part_item)})")
                        elif isinstance(content_data, str):
                             parts_summary.append(f"str({len(content_data)} chars)")
                    elif hasattr(m, 'parts') and hasattr(m, 'role'):
                        # Handle SDK glm.Content-like object
                        role = m.role
                        if isinstance(m.parts, list):
                            for p in m.parts:
                                if hasattr(p, 'text') and p.text is not None:
                                    parts_summary.append(f"text({len(p.text)} chars)")
                                elif hasattr(p, 'function_call') and p.function_call:
                                    parts_summary.append(f"function_call({p.function_call.name})")
                                elif hasattr(p, 'function_response') and p.function_response:
                                    parts_summary.append(f"function_response({p.function_response.name})")
                                elif hasattr(p, 'inline_data') and p.inline_data:
                                    parts_summary.append(f"inline_data({p.inline_data.mime_type}, {len(p.inline_data.data)} bytes)")
                                elif hasattr(p, 'file_data') and p.file_data:
                                    parts_summary.append(f"file_data({p.file_data.mime_type}, {p.file_data.file_uri})")
                                else:
                                    parts_summary.append(f"unknown_sdk_part({type(p)})")
                        else:
                            # Fix: Don't label as "sdk_content_no_parts" since this confuses the LLM
                            # Just describe it in a way that doesn't look like a specific input message
                            parts_summary.append(f"content_with_no_parts")
                    else:
                        role = 'unknown_format'
                        parts_summary.append(f"type={type(m)}")

                    log_messages.append(f"  [{i}] {role}: {', '.join(parts_summary) if parts_summary else '(empty)'}")

                # Fix: Display a more clear debugging message that won't be mistaken for an input
                log.debug(f"Debug info: Preparing {len(final_contents)} content items for LLM API:")
                log.debug("\n".join(log_messages))
            except Exception as debug_e:
                log.warning(f"Error generating detailed debug info for contents: {debug_e}")

        log.info(f"Sending content to LLM (streaming): {self.model_name}")
        log.debug(f"Final Contents structure (type): {[type(m) for m in final_contents]}")
        log.debug(f"Tools object: {type(sdk_tool_obj).__name__ if sdk_tool_obj else 'None'} with {len(sdk_tool_obj.function_declarations) if sdk_tool_obj and hasattr(sdk_tool_obj, 'function_declarations') else 0} functions")

        # Additional debug logging for function calling configuration
        if sdk_tool_obj:
            log.info(f"Function calling enabled with AUTO mode for {len(sdk_tool_obj.function_declarations)} tools")
            for i, func_decl in enumerate(sdk_tool_obj.function_declarations[:3]):  # Log first 3 tools
                log.debug(f"Tool {i+1}: {func_decl.name} - {func_decl.description[:100]}...")
        else:
            log.info("No tools provided - text-only response expected")

        try:
            # Use the SDK's generate_content method with streaming enabled.
            response_stream = self.model.generate_content(
                contents=final_contents, # Pass the list including system prompt
                generation_config=generation_config,
                safety_settings=safety_settings if safety_settings else None,
                tools=sdk_tool_obj, # Pass the converted SDK Tool object
                tool_config={"function_calling_config": {"mode": "AUTO"}} if sdk_tool_obj else None, # Mode AUTO encourages proper tool usage
                stream=True,
                request_options={'timeout': self.timeout} # Pass timeout via request_options
            )
            log.debug(f"Received streaming response iterator from LLM: {self.model_name}")
            return response_stream

        except google_exceptions.GoogleAPIError as e:
            log.error(f"Google API error during streaming call ({self.model_name}): {e}", exc_info=True)
            # Specific handling based on error type could be added here
            if isinstance(e, google_exceptions.ResourceExhausted):
                log.error("Quota limit likely reached.")
            elif isinstance(e, google_exceptions.PermissionDenied):
                log.error("Permission denied. Check API key permissions.")
            elif isinstance(e, google_exceptions.InvalidArgument):
                 log.error(f"Invalid argument provided to API: {e}")
            # Re-raise the original exception after logging
            raise e
        except (requests_exceptions.RequestException, TimeoutError) as e:
            log.error(f"Network error during LLM streaming call: {e}", exc_info=True)
            raise RuntimeError(f"Network error during LLM streaming call: {e}") from e 
        except Exception as e:
            # Catch other potential errors (e.g., type errors in message format)
            log.error(f"Unexpected error during streaming LLM call ({self.model_name}): {e}", exc_info=True)
            # Wrap in a RuntimeError or re-raise depending on desired handling
            raise RuntimeError(f"LLM stream generation failed: {e}") from e