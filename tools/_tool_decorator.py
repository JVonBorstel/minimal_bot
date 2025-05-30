# --- FILE: tools/_tool_decorator.py ---
import time
import asyncio
import functools
import inspect
import logging
import json
import sys
from typing import (
    Optional, Dict, Any, List, Callable, Union, get_origin, get_args, Literal, Tuple
)
from pydantic import BaseModel, Field, model_validator
# Union, Literal are imported from typing on line 9. ForwardRef was unused.
from docstring_parser import parse, DocstringStyle
from github.GithubObject import NotSet, _NotSetType
from requests.exceptions import (
    Timeout as RequestsTimeout, ConnectionError as RequestsConnectionError
)

# Import mock types for custom JSON encoding
from unittest.mock import MagicMock, NonCallableMagicMock, PropertyMock

# Custom JSON Encoder for handling MagicMock and related mock types
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, (MagicMock, NonCallableMagicMock, PropertyMock)):
            return repr(o)  # Convert mock objects to their string representation
        if isinstance(o, _NotSetType):
            return None
        # Let the base class default method raise the TypeError for other types
        return super().default(o)

# Import the main Config class for type hinting and accessing settings
from config import Config  # Assuming config.py exists and defines Config

# Use the 'tools' section logger
log = logging.getLogger("tools.decorator")

# Define common network exceptions to catch for retries
# Ensure these are tuples for the except block
NETWORK_EXCEPTIONS = (
    RequestsTimeout,
    RequestsConnectionError,
    # Add other common network errors if needed, e.g.,
    # from specific SDKs if not inheriting from RequestException
)


# --- Helper Functions ---

def _resolve_ref_in_schema(schema: Dict[str, Any], defs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively resolves $ref references in a JSON schema using the provided definitions.
    
    Args:
        schema: The schema dict that may contain $ref references
        defs: The definitions dict containing referenced schemas
        
    Returns:
        The schema with all $ref references resolved inline
    """
    if not isinstance(schema, dict):
        return schema
        
    # If this schema has a $ref, resolve it
    if '$ref' in schema:
        ref_path = schema['$ref']
        if ref_path.startswith('#/$defs/'):
            def_name = ref_path.replace('#/$defs/', '')
            if def_name in defs:
                # Resolve the reference by copying the definition
                resolved_schema = defs[def_name].copy()
                # Recursively resolve any references in the resolved schema
                resolved_schema = _resolve_ref_in_schema(resolved_schema, defs)
                
                # Merge any additional properties from the original schema (excluding $ref)
                schema_without_ref = {k: v for k, v in schema.items() if k != '$ref'}
                resolved_schema.update(schema_without_ref)
                
                return resolved_schema
            else:
                log.warning(f"Could not resolve $ref '{ref_path}': definition '{def_name}' not found in $defs")
                # Return a fallback schema
                return {"type": "object", "description": f"Unresolved reference: {ref_path}"}
        else:
            log.warning(f"Unsupported $ref format: {ref_path} (only '#/$defs/' format supported)")
            return {"type": "object", "description": f"Unsupported reference: {ref_path}"}
    
    # Recursively resolve references in nested structures
    resolved_schema = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            resolved_schema[key] = _resolve_ref_in_schema(value, defs)
        elif isinstance(value, list):
            resolved_schema[key] = [
                _resolve_ref_in_schema(item, defs) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            resolved_schema[key] = value
            
    return resolved_schema


def _map_py_type_to_json_schema(py_type: Any, tool_name_for_log: str = "unknown_tool", param_name_for_log: str = "unknown_param") -> Optional[Dict[str, Any]]:
    """
    Maps Python types to a JSON schema dictionary.
    Excludes Config, AppState, Message, UserProfile from schema.
    If an item type in List[T] or Tuple[T,...] is excluded, the parameter is excluded from the schema.
    """
    # Direct exclusion for Config and specific state model names
    type_name_str = getattr(py_type, '__name__', str(py_type))
    excluded_types_by_name = ['AppState', 'Message', 'UserProfile', 'Config'] # Add other internal objects if necessary
    if py_type is Config or any(excluded_name in type_name_str for excluded_name in excluded_types_by_name):
        log.debug(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Type '{type_name_str}' excluded from schema.")
        return None # Explicitly exclude these types

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin is tuple or origin is Tuple:
        if args:
            # If any item type is excluded, exclude the whole tuple
            for arg_item_type in args:
                item_schema = _map_py_type_to_json_schema(arg_item_type, tool_name_for_log, f"{param_name_for_log}[tuple_item]")
                if item_schema is None:
                    log.debug(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Tuple contains excluded type. Excluding parameter.")
                    return None
            # If all items are mappable, proceed as before
            item_schemas = [_map_py_type_to_json_schema(arg_item_type, tool_name_for_log, f"{param_name_for_log}[tuple_item]") for arg_item_type in args]
            return {
                "type": "array",
                "items": item_schemas[0] if len(item_schemas) == 1 else item_schemas,
                "minItems": len(args),
                "maxItems": len(args)
            }
        log.warning(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Tuple type '{py_type}' items could not be fully mapped or empty. Excluding parameter.")
        return None

    if origin is Literal:
        if args:
            first_arg_type = type(args[0])
            json_type = "string"
            if first_arg_type is int: json_type = "integer"
            elif first_arg_type is bool: json_type = "boolean"
            elif first_arg_type is float: json_type = "number"
            return {"type": json_type, "enum": list(args)}
        return {"type": "string"}

    if origin is Union:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if not non_none_args: return {"type": "null"}
        is_optional = len(args) > len(non_none_args)
        sub_schemas = [_map_py_type_to_json_schema(arg, tool_name_for_log, f"{param_name_for_log}[union_option]") for arg in non_none_args]
        valid_sub_schemas = [s for s in sub_schemas if s]
        if not valid_sub_schemas: # All options were excluded
            return {"type": "null"} if is_optional else None # If not optional and all excluded, exclude the param
        final_schema_choices = valid_sub_schemas
        if is_optional: final_schema_choices.append({"type": "null"})
        if len(final_schema_choices) == 1: return final_schema_choices[0]
        return {"anyOf": final_schema_choices}

    elif origin in (list, List):
        if args:
            resolved_item_schema = _map_py_type_to_json_schema(args[0], tool_name_for_log, f"{param_name_for_log}[list_item]")
            if resolved_item_schema is not None:
                return {"type": "array", "items": resolved_item_schema}
            else:
                log.debug(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': List item type is excluded. Excluding parameter.")
                return None
        return {"type": "array", "items": {"type": "string"}}

    elif origin in (dict, Dict):
        if args and len(args) == 2:
            val_schema = _map_py_type_to_json_schema(args[1], tool_name_for_log, f"{param_name_for_log}[dict_value]")
            if val_schema is not None:
                return {"type": "object", "additionalProperties": val_schema}
            else:
                log.debug(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Dict value type is excluded. Excluding parameter.")
                return None
        return {"type": "object", "additionalProperties": True}

    elif py_type is str: return {"type": "string"}
    elif py_type is int: return {"type": "integer"}
    elif py_type is float: return {"type": "number"}
    elif py_type is bool: return {"type": "boolean"}
    elif py_type is Any or py_type is inspect.Parameter.empty: return {"type": "string", "description": "Any type."}
    elif py_type is type(None): return {"type": "null"}

    if hasattr(py_type, 'model_json_schema') and callable(py_type.model_json_schema):
        try:
            log.debug(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Using Pydantic schema for '{type_name_str}'.")
            full_schema = py_type.model_json_schema()
            main_schema = {k: v for k, v in full_schema.items() if k != '$defs'}
            defs = full_schema.get('$defs', {})
            return _resolve_ref_in_schema(main_schema, defs) if defs else main_schema
        except Exception as e:
            log.warning(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Failed to get Pydantic schema for '{type_name_str}': {e}. Defaulting to object.", exc_info=False)
            return {"type": "object", "description": f"Complex object: {type_name_str}"}

    log.warning(f"Tool '{tool_name_for_log}', Param '{param_name_for_log}': Unsupported type '{py_type}' for schema. Defaulting to string.")
    return {"type": "string"}


def _extract_param_details_from_docstring(
    docstring: Optional[str]
) -> Dict[str, str]:
    """
    Parses a docstring (Google style) to extract parameter descriptions.

    Args:
        docstring: The function docstring to parse

    Returns:
        Dict mapping parameter names to their descriptions
    """
    descriptions: Dict[str, str] = {}
    if not docstring:
        return descriptions
    try:
        # Use DocstringStyle.google (lowercase) as it's the enum member name
        # type: ignore[attr-defined]
        parsed_docstring = parse(
            docstring, style=DocstringStyle.GOOGLE
        )
        for param in parsed_docstring.params:
            if param.arg_name:
                descriptions[param.arg_name] = param.description or ""
    except Exception as e:
        # Use exc_info=False to avoid logging traceback for common parse
        # errors
        log.warning(
            f"Failed to parse docstring for parameter descriptions: {e}",
            exc_info=False
        )
    return descriptions

# --- Schema Preprocessing Helpers ---

def _ensure_dict_schema_has_type(
    schema_dict: Dict[str, Any],
    tool_name_for_log: str,
    param_path_for_log: str
):
    """
    Ensures a dictionary representing a JSON schema has a 'type' field.
    Modifies schema_dict in place.
    """
    if 'type' not in schema_dict:
        if any(k in schema_dict for k in ['anyOf', 'oneOf', 'allOf']):
            # If anyOf, oneOf, or allOf is present, these keywords define the type.
            # Do not automatically set type to 'object'.
            # The Gemini SDK expects the 'type' field to be absent or correctly derived
            # from the contents of anyOf/oneOf/allOf if they represent simple type choices.
            # If they represent choices between complex objects, then the individual schemas
            # within anyOf/oneOf/allOf should themselves have type: 'object' and properties.
            pass # Let the structure be defined by anyOf/oneOf/allOf
        elif 'properties' in schema_dict: # If it has properties, it's an object
            schema_dict['type'] = 'object'
        elif 'items' in schema_dict: # If it has items, it's an array
            schema_dict['type'] = 'array'
        else:
            # Default for unspecified or truly typeless schemas (should be rare)
            schema_dict['type'] = 'string'
            log.warning(
                f"Tool '{tool_name_for_log}', param '{param_path_for_log}': "
                f"Schema missing 'type' and complex keywords/structure. "
                f"Defaulting to 'string'. Schema: {schema_dict}"
            )
    elif not isinstance(schema_dict['type'], str):
        # If 'type' exists but is not a string (e.g., a list of types, which is not standard JSON schema for 'type' field)
        original_type_val = schema_dict['type']
        log.warning(
            f"Tool '{tool_name_for_log}', param '{param_path_for_log}': "
            f"'type' field is {original_type_val} (not a string). Coercing. "
            f"Schema: {schema_dict}"
        )
        # Heuristic to pick a type string
        if 'properties' in schema_dict:
            schema_dict['type'] = 'object'
        elif 'items' in schema_dict:
            schema_dict['type'] = 'array'
        elif any(k in schema_dict for k in ['anyOf', 'oneOf', 'allOf']):
             schema_dict['type'] = 'object' # Placeholder for complex union/intersection
        else: # Fallback
            schema_dict['type'] = 'string'

def _recursively_prepare_schema_for_properties(
    schema_dict: Dict[str, Any],
    tool_name_for_log: str,
    current_path_for_log: str
):
    """
    Recursively prepares a schema dictionary and its sub-schemas (properties, items)
    to ensure they are valid for ParameterProperty instantiation, primarily by
    ensuring the 'type' field is present and correct. Modifies schema_dict in place.
    """
    _ensure_dict_schema_has_type(schema_dict, tool_name_for_log, current_path_for_log)

    # Recursively process properties of an object
    if schema_dict.get('type') == 'object' and 'properties' in schema_dict:
        properties_val = schema_dict.get('properties')
        if isinstance(properties_val, dict):
            for prop_name, prop_schema_val in properties_val.items():
                if isinstance(prop_schema_val, dict):
                    _recursively_prepare_schema_for_properties(
                        prop_schema_val, # This is the sub-dictionary to process
                        tool_name_for_log,
                        f"{current_path_for_log}.properties.{prop_name}"
                    )
                else:
                    log.warning(
                        f"Tool '{tool_name_for_log}', path '{current_path_for_log}.properties.{prop_name}': "
                        f"property schema is not a dict, skipping recursive preparation. Schema: {prop_schema_val}"
                    )
        else:
            log.warning(
                f"Tool '{tool_name_for_log}', path '{current_path_for_log}': "
                f"'properties' field is not a dict, skipping recursive preparation of properties. Value: {properties_val}"
            )

    # Recursively process items of an array
    if schema_dict.get('type') == 'array' and 'items' in schema_dict:
        items_val = schema_dict.get('items')
        if isinstance(items_val, dict):
            _recursively_prepare_schema_for_properties(
                items_val, # This is the sub-dictionary to process
                tool_name_for_log,
                f"{current_path_for_log}.items"
            )
        # else: OpenAPI spec allows 'items' to be a boolean or an array of schemas too,
        # but ParameterProperty currently expects a single schema dict or ParameterProperty for items.
        # For simplicity, we only recurse if it's a dict.
        elif not isinstance(items_val, bool): # bool is a valid value for items in some contexts (JSON Schema draft 2020-12)
             log.warning(
                f"Tool '{tool_name_for_log}', path '{current_path_for_log}': "
                f"'items' schema is not a dict, skipping recursive preparation. Schema: {items_val}"
            )

# --- Pydantic Models for Tool Definition ---


class ParameterProperty(BaseModel):
    """
    Represents the schema for a single tool parameter property.
    This is a simplified version, primarily for type and description.
    More complex JSON schema features like 'oneOf', 'allOf', 'format'
    are not explicitly detailed here but could be part of 'additional_details'.
    """
    type: Optional[str] = Field(
        None,
        description=(
            "The JSON schema type of the parameter (e.g., 'string', "
            "'integer', 'boolean', 'array', 'object'). "
            "Optional when anyOf/oneOf/allOf define the type structure."
        )
    )
    description: Optional[str] = Field(
        None,
        description="A human-readable description of the parameter."
    )
    enum: Optional[List[Any]] = Field(
        None,
        description=(
            "A list of allowed values for the parameter, if it's an enum."
        )
    )
    items: Optional[Union['ParameterProperty', Dict[str, Any]]] = Field(
        None,
        description=(
            "If type is 'array', this describes the items in the array. "
            "Can be a simple type or a nested schema."
        )
    )
    properties: Optional[Dict[str, 'ParameterProperty']] = Field(
        None,
        description=(
            "If type is 'object', this describes the properties of the object."
        )
    )
    required: Optional[List[str]] = Field(
        None,
        description=(
            "If type is 'object', lists the required properties of that "
            "object."
        )
    )
    additional_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Allows for any other valid JSON schema properties."
    )

    model_config = {
        "extra": "allow"  # Allow additional fields not explicitly defined
    }


class ParametersSchema(BaseModel):
    """
    Represents the JSON schema for the parameters of a tool.
    Corresponds to the 'parameters' field in an OpenAPI tool definition.
    """
    type: Literal["object"] = Field(
        default="object",
        description="The type of the parameters schema, always 'object'."
    )
    properties: Dict[str, ParameterProperty] = Field(
        default_factory=dict,
        description=(
            "A dictionary mapping parameter names to their schema definitions "
            "(ParameterProperty)."
        )
    )
    required: Optional[List[str]] = Field(
        default=None,
        description="A list of names of parameters that are required."
    )

    @model_validator(mode='before')
    @classmethod
    def ensure_type_object(cls, data: Any) -> Any:
        if isinstance(data, dict) and 'type' not in data:
            data['type'] = 'object'
        elif isinstance(data, dict) and data.get('type') != 'object':
            # This case should ideally be handled by the Literal type,
            # but good to have a check.
            log.warning(
                f"ParametersSchema received type '{data.get('type')}' "
                f"instead of 'object'. Overriding to 'object'."
            )
            data['type'] = 'object'
        return data


class ToolMetadata(BaseModel):
    """
    Encapsulates metadata for a tool, such as categories, tags, examples,
    and importance.
    """
    categories: Optional[List[str]] = Field(
        default=None,
        description=(
            "List of categories this tool belongs to (e.g., 'github', "
            "'search')."
        )
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="List of tags for more specific filtering or grouping."
    )
    examples: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "List of example usages, typically with 'input' and "
            "'expected_output' or 'description'."
        )
    )
    importance: int = Field(
        default=5, ge=1, le=10,
        description=(
            "Importance rating (1-10) affecting ranking or selection of "
            "similar tools."
        )
    )


class ToolDefinition(BaseModel):
    """
    Represents the complete definition of a tool, including its name,
    description, parameters schema, and associated metadata.
    This model provides a structured and type-safe way to handle tool
    definitions.
    """
    name: str = Field(description="The unique name of the tool.")
    description: str = Field(
        description="A human-readable description of what the tool does."
    )
    parameters: ParametersSchema = Field(
        default_factory=ParametersSchema,
        description="The schema defining the parameters accepted by the tool."
    )
    metadata: ToolMetadata = Field(
        default_factory=ToolMetadata,
        description="Additional metadata associated with the tool."
    )


# ForwardRef resolution for ParameterProperty
ParameterProperty.model_rebuild()


# --- Tool Registration ---

# Global registries for tool functions and their definitions
# _TOOL_REGISTRY: Stores the wrapped callable function
# _TOOL_DEFINITIONS: Stores the generated OpenAPI-subset schema dictionary
_TOOL_REGISTRY: Dict[str, Callable] = {}
_TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {}


def tool_function(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters_schema: Optional[Dict[str, Any]] = None,
    categories: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    importance: int = 5,
):
    """
    Decorator to register a function as an executable tool for the LLM.

    Generates an OpenAPI-compatible schema from the function's signature
    and docstring (Google style). Wraps the function to handle execution,
    retries for network errors, and standardized error reporting.

    Args:
        name: Optional custom name for the tool. Defaults to function name.
              Tool names should be unique.
        description: Description of what the tool does. If None, attempts to
                     use the function's docstring summary.
        parameters_schema: Optional explicit schema for the tool's parameters.
                           Should be an object schema compatible with OpenAPI
                           (e.g., {"type": "object",
                                   "properties": {...},
                                   "required": [...]}).
        categories: List of categories this tool belongs to (e.g., 'github',
                    'search').
        tags: List of tags for more specific filtering.
        examples: List of example usages with input and expected output.
        importance: Importance rating (1-10) affecting ranking in similar
                    tools.
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        # Check for name uniqueness *before* defining the wrapper and schema
        if tool_name in _TOOL_REGISTRY:
            raise ValueError(
                f"Tool name '{tool_name}' is already registered. "
                "Tool names must be unique."
            )

        # Validate function signature - must accept 'self' or be
        # static/class method and must accept kwargs (or specific named
        # args matching schema)
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        is_method = param_names and param_names[0] == 'self'
        # If it's a method, the first parameter should be 'self'.
        # If not a method, it must be a standalone function.

        docstring = inspect.getdoc(func)
        # Corrected style name
        parsed_doc = parse(
            docstring or "",
            style=DocstringStyle.GOOGLE  # type: ignore[attr-defined]
        )

        tool_description = (
            description or
            parsed_doc.short_description or
            f"Executes the {tool_name} function."
        )

        # Ensure description is a string, fallback to empty string if None
        # or unexpected type
        if not isinstance(tool_description, str):
            log.warning(
                f"Tool '{tool_name}' description is not a string "
                f"({type(tool_description)}). Using empty string."
            )
            tool_description = ""

        param_descriptions = _extract_param_details_from_docstring(docstring)

        # --- Build Parameter Schema ---
        if parameters_schema is not None:
            # Use explicitly provided schema if available
            log.debug(
                f"Using explicit parameters_schema for tool '{tool_name}'."
            )
            # Basic validation of the explicit schema
            if not isinstance(parameters_schema, dict) or \
               parameters_schema.get("type") != "object" or \
               "properties" not in parameters_schema:
                log.error(
                    f"Error: Explicit parameters_schema for '{tool_name}' "
                    f"is invalid. Must be an object schema with "
                    f"'type: object' and 'properties'."
                )
                # Fallback to empty schema to avoid downstream errors
                final_parameters_schema = {
                    "type": "object", "properties": {}, "required": []
                }
            else:
                final_parameters_schema = parameters_schema
        else:
            # Infer schema if not explicitly provided
            log.debug(
                f"Inferring parameters schema for tool '{tool_name}' "
                "from signature."
            )
            inferred_properties = {}
            required_params = []
            # Iterate through parameters, skipping 'self' if it's a method
            params_to_process = list(sig.parameters.items())
            if is_method:
                params_to_process = params_to_process[1:]  # Skip 'self'

            for p_name, param_obj in params_to_process:
                py_type_hint = param_obj.annotation if param_obj.annotation != inspect.Parameter.empty else Any
                # Exclude 'config: Config' and 'app_state: AppState' from the LLM schema
                param_json_schema_dict = _map_py_type_to_json_schema(py_type_hint, tool_name, p_name)
                if param_json_schema_dict is None: # Type was excluded (e.g., AppState, Config, or List/Tuple thereof)
                    log.debug(f"Tool '{tool_name}', Param '{p_name}': Type '{py_type_hint}' excluded from schema by _map_py_type_to_json_schema.")
                    continue # Do not add this parameter to the tool's schema for the LLM
                param_desc_str = param_descriptions.get(p_name, f"Parameter '{p_name}'")
                if param_obj.default != inspect.Parameter.empty:
                    try: default_repr = repr(param_obj.default)
                    except: default_repr = "<unrepresentable>"
                    param_desc_str += f" (Optional, default: {default_repr[:50]})"
                else:
                    origin_type = get_origin(py_type_hint)
                    args_type = get_args(py_type_hint)
                    if not (origin_type is Union and type(None) in args_type):
                        required_params.append(p_name)
                param_json_schema_dict["description"] = param_desc_str
                inferred_properties[p_name] = param_json_schema_dict

            # Construct the final inferred schema
            final_parameters_schema = {
                "type": "object",
                "properties": inferred_properties,
                "required": required_params,
            }

        # --- Build Full Tool Definition using Pydantic Models ---
        # 1. Create ParameterProperty instances for each parameter
        parameter_properties_for_model: Dict[str, ParameterProperty] = {}
        # final_parameters_schema is dict form (explicit or inferred)
        raw_properties_value = final_parameters_schema.get("properties", {})
        if not isinstance(raw_properties_value, dict):
            log.warning(
                f"Tool '{tool_name}': 'properties' in schema was not a dict, "
                f"defaulting to empty. Value: {raw_properties_value}"
            )
            raw_parameter_props: Dict[str, Any] = {}
        else:
            raw_parameter_props = raw_properties_value

        for p_name, p_dict_schema in raw_parameter_props.items():
            try:
                # args_for_param_prop is the schema for the current top-level parameter (e.g., 'app_state')
                args_for_param_prop = p_dict_schema.copy()
                
                # Recursively prepare this schema and its nested parts to ensure 'type' fields are set
                _recursively_prepare_schema_for_properties(args_for_param_prop, tool_name, p_name)
                
                parameter_properties_for_model[p_name] = ParameterProperty(
                    **args_for_param_prop
                )
            # Catch Pydantic ValidationError or other errors
            except Exception as e:
                # Log the schema that caused the error. If args_for_param_prop was modified, log that.
                schema_at_error = args_for_param_prop if 'args_for_param_prop' in locals() and args_for_param_prop is not p_dict_schema else p_dict_schema
                log_message = (
                    f"Tool '{tool_name}': Failed to parse schema for "
                    f"parameter '{p_name}' into ParameterProperty model: {e}. "
                    f"Schema (after preparation attempt) was: {schema_at_error}"
                )
                log.error(log_message, exc_info=True) # exc_info=True will log the full traceback
                # Fallback: create a generic ParameterProperty
                fallback_description = p_dict_schema.get(
                    'description', f"Error processing schema for {p_name}."
                )
                fallback_type = p_dict_schema.get(
                    'type', "string"
                )  # Default to string
                parameter_properties_for_model[p_name] = ParameterProperty(
                    type=fallback_type,
                    description=fallback_description,
                    enum=None,
                    items=None,
                    properties=None,
                    required=None
                )

        # 2. Create ParametersSchema instance
        parameters_obj = ParametersSchema(
            properties=parameter_properties_for_model,
            required=list(final_parameters_schema.get("required", []))
        )

        # 3. Create ToolMetadata instance
        metadata_obj = ToolMetadata(
            categories=categories or [],  # Ensure list, not None
            tags=tags or [],              # Ensure list, not None
            examples=examples or [],      # Ensure list, not None
            importance=importance
        )

        # 4. Create ToolDefinition instance
        try:
            tool_definition_obj = ToolDefinition(
                name=tool_name,
                description=tool_description,
                parameters=parameters_obj,
                metadata=metadata_obj
            )
            _TOOL_DEFINITIONS[tool_name] = tool_definition_obj
        except Exception as e:  # Catch Pydantic ValidationError
            log.critical(
                f"CRITICAL: Failed to create ToolDefinition Pydantic model "
                f"for tool '{tool_name}': {e}. This tool will not be "
                f"registered correctly.",
                exc_info=True
            )
            # To prevent downstream errors, we might register a minimal valid
            # ToolDefinition or raise the error to halt registration of a
            # malformed tool. For now, logging critical and not adding to
            # _TOOL_DEFINITIONS if invalid. Or, re-raise to make it explicit:
            raise ValueError(
                f"Failed to create ToolDefinition for {tool_name}: {e}"
            ) from e

        log.debug(f"Registered tool '{tool_name}' with definition.")

        # --- Define Wrapper Function ---
        @functools.wraps(func)
        async def wrapper(
            instance: Optional[Any] = None,
            tool_config: Optional[Config] = None,
            **kwargs
        ):
            """
            Wrapper for tool execution handling retries and standardized error
            results. Injects config if the original function accepts it.
            Receives the tool class instance as the first argument
            (or None for standalone).
            Receives config object via tool_config keyword argument.
            """
            # Capture start time for statistics
            start_time = time.time()

            # --- Diagnostic Logging ---
            # Improved logging to show what was received
            instance_type = 'None'
            if instance is not None:
                instance_type = type(instance).__name__
            tool_config_type = 'None'
            if tool_config is not None:
                tool_config_type = type(tool_config).__name__
            log.debug(
                f"Wrapper entry for tool '{tool_name}': "
                f"instance type={instance_type}, "
                f"tool_config type={tool_config_type}, "
                f"kwargs keys={list(kwargs.keys())}"
            )

            # === Config Fallback Chain ===
            # This implements a robust fallback mechanism for obtaining a
            # valid Config object. Order of precedence:
            # 1. Use provided tool_config if valid
            # 2. Try to get config from the tool's instance.config if available
            # 3. Try to get config from the global Config() singleton
            # 4. Report error if all fallbacks fail
            fallback_cfg: Optional[Config] = None
            if not isinstance(tool_config, Config):
                config_type_str = 'None'
                if tool_config is not None:
                    config_type_str = type(tool_config).__name__
                log.warning(
                    f"Tool '{tool_name}': tool_config param "
                    f"was {config_type_str}. Starting fallback chain."
                )
                # 1) Try to pull from the tool class instance if it stored one
                #    and is a Config object
                if instance is not None and \
                   hasattr(instance, "config") and \
                   isinstance(instance.config, Config):
                    fallback_cfg = instance.config
                    log.warning(
                        f"Tool '{tool_name}': Using instance.config fallback."
                    )
                else:
                    try:
                        # 2) Try global singleton access
                        #    (Config() constructor returns the singleton)
                        # Import here to potentially avoid circular import
                        # issues if Config class imports tools
                        from config import Config as ConfigClass
                        test_cfg = ConfigClass()
                        if isinstance(test_cfg, Config):
                            fallback_cfg = test_cfg
                            log.warning(
                                f"Tool '{tool_name}': Using Config() "
                                "singleton fallback."
                            )
                        else:
                            log.warning(
                                f"Tool '{tool_name}': Config() singleton "
                                f"fallback returned non-Config type "
                                f"{type(test_cfg).__name__}."
                            )
                    except ImportError:
                        log.warning(
                            f"Tool '{tool_name}': Could not import "
                            "ConfigClass for singleton fallback."
                        )
                        fallback_cfg = None
                    except Exception as _e:
                        log.error(
                            f"Tool '{tool_name}': Error accessing Config() "
                            f"singleton fallback: {_e}", exc_info=True
                        )
                        fallback_cfg = None

            # Use the fallback config if a valid one was found
            if isinstance(fallback_cfg, Config):
                tool_config = fallback_cfg
                log.debug(
                    f"Tool '{tool_name}': Final tool_config source: "
                    f"Fallback ({type(tool_config).__name__})."
                )
            elif not isinstance(tool_config, Config):
                # If still not a Config object after fallbacks, this is a
                # critical failure
                log.error(
                    f"Tool '{tool_name}' executed without a valid Config "
                    "object! Cannot proceed."
                )
                return {
                    "status": "ERROR",
                    "message": "Configuration object missing or invalid "
                               "during tool execution."
                }
            else:
                log.debug(
                    f"Tool '{tool_name}': Final tool_config source: "
                    f"Executor Argument ({type(tool_config).__name__})."
                )

            # If it's a method, ensure instance was passed
            if is_method and instance is None:
                log.error(
                    f"Tool '{tool_name}' executed without valid instance "
                    "object!"
                )
                return {
                    "status": "ERROR",
                    "message": "Instance object missing during tool execution."
                }

            max_retries = tool_config.DEFAULT_API_MAX_RETRIES
            last_exception = None

            log.info(f"Executing tool '{tool_name}'...")
            # Tool args repr for logging - handle sensitive info?
            # Simplistic approach: just log keys
            tool_args_repr = (
                f"instance={type(instance).__name__ if instance else 'None'}, "
                f"tool_config provided="
                f"{'Yes' if isinstance(tool_config, Config) else 'No'}, "
                f"kwargs keys={list(kwargs.keys())}"
            )
            log.debug(
                f"Tool '{tool_name}' called with: {tool_args_repr} "
                f"(Retries: {max_retries})"
            )

            # Prepare kwargs for the original function, potentially injecting
            # config. Only pass arguments that are in the original
            # function's signature (excluding 'self')
            func_sig = inspect.signature(func)
            # final_kwargs = {} # Old way

            # # Add all kwargs from the caller # Old way
            # for k, v in kwargs.items():
            #     if k in func_sig.parameters:
            #         final_kwargs[k] = v
            #     else:
            #         log.warning(
            #             f"Tool '{tool_name}': Parameter '{k}' is not in "
            #             f"function signature. It will be ignored."
            #         )

            # Start with all keyword arguments passed to the wrapper.
            # Python's argument passing mechanism will correctly distribute these
            # to the original function's named parameters and its **varkw parameter (e.g., **kwargs).
            prepared_kwargs = kwargs.copy()

            # Remove app_state from prepared_kwargs if the function doesn't accept it
            if 'app_state' in prepared_kwargs:
                # Check if the original function accepts app_state parameter
                if 'app_state' not in func_sig.parameters:
                    # Function doesn't accept app_state, remove it from kwargs
                    log.debug(
                        f"Tool '{tool_name}': Removing 'app_state' parameter "
                        f"as function signature does not accept it"
                    )
                    prepared_kwargs.pop('app_state', None)

            # Inject the Config object if function signature expects a 'config'
            # parameter
            if 'config' in func_sig.parameters:
                param_annotation = func_sig.parameters['config'].annotation
                # Simplified check on one logical line:
                is_correct_type = False
                if isinstance(param_annotation, type) and issubclass(param_annotation, Config):
                    is_correct_type = True
                elif param_annotation is Config:
                    is_correct_type = True

                if is_correct_type:
                    prepared_kwargs['config'] = tool_config # Modify/add to prepared_kwargs
                    log.debug(
                        f"Tool '{tool_name}': Injecting config: "
                        f"{type(tool_config).__name__}"
                    )

            # === Inner function to execute the tool with retry logic ===
            async def _execute_tool_calls():
                nonlocal last_exception
                # +1 because we count initial attempt
                for attempt in range(max_retries + 1):
                    try:
                        # --- CORRECTED CALL TO ORIGINAL FUNCTION ---
                        # Call the original function 'func' directly.
                        # If it's a method, pass the instance as the first
                        # argument. Pass the prepared final_kwargs.
                        log.debug(
                            f"Attempt {attempt + 1}/{max_retries + 1}: "
                            f"Calling original func '{func.__name__}' with "
                            f"prepared_kwargs keys: {list(prepared_kwargs.keys())}" # Log new var
                        )

                        if is_method:
                            # Call the method on the instance
                            if inspect.iscoroutinefunction(func):
                                result = await func(instance, **prepared_kwargs)
                            else:
                                result = func(instance, **prepared_kwargs)
                        else:
                            # Call the standalone function
                            if inspect.iscoroutinefunction(func):
                                result = await func(**prepared_kwargs)
                            else:
                                result = func(**prepared_kwargs)

                        # Success! Break the retry loop
                        if attempt > 0:
                            log.info(
                                f"Tool '{tool_name}' succeeded on attempt "
                                f"{attempt + 1}/{max_retries + 1}."
                            )

                        # Ensure result is JSON serializable and wrap in success format
                        try:
                            json.dumps(result, cls=CustomJSONEncoder)
                            return {"status": "SUCCESS", "data": result}
                        except (TypeError, ValueError) as json_e:
                            log.error(
                                f"Tool '{tool_name}' result not JSON "
                                f"serializable: {json_e}. Returning error.",
                                exc_info=True
                            )
                            # Include repr(result) in detail for debugging
                            # non-serializable objects
                            try:
                                result_preview = (
                                    repr(result)[:200] + "..."
                                    if len(repr(result)) > 200
                                    else repr(result)
                                )
                            except RecursionError:
                                result_preview = (
                                    f"<RecursionError during repr() - object "
                                    f"may contain circular references: "
                                    f"{type(result).__name__}>"
                                )
                            except Exception as repr_e:
                                result_preview = (
                                    f"<Error during repr(): "
                                    f"{repr_e.__class__.__name__}: {repr_e}>"
                                )

                            return {
                                "status": "ERROR",
                                "error_type": "SerializationError",
                                "user_facing_message": "I ran into an issue while trying to process your request. Please try again later.",
                                "technical_details": f"Serialization error: {json_e}. Result preview: {result_preview}"
                            }

                    except (RequestsTimeout, RequestsConnectionError) as e:
                        # Network timeout retries with backoff
                        if attempt < max_retries:
                            # Calculate exponential backoff with jitter
                            backoff_time = min(
                                2 ** attempt + (time.time() % 1), 10
                            )  # Max 10 second backoff
                            log.warning(
                                f"Tool '{tool_name}' network error "
                                f"(attempt {attempt + 1}/{max_retries + 1}): "
                                f"{e}. Retrying in {backoff_time:.2f}s...",
                                exc_info=False
                            )
                            last_exception = e
                            await asyncio.sleep(backoff_time)
                            continue
                        else:
                            # Final retry attempt failed - log and return error
                            log.error(
                                f"Tool '{tool_name}' network error after "
                                f"{max_retries + 1} attempts: {e}",
                                exc_info=True
                            )
                            return {
                                "status": "ERROR",
                                "error_type": "NetworkError",
                                "user_facing_message": "I'm having trouble connecting to the required service. Please try again in a few moments.",
                                "technical_details": f"Network error after {max_retries + 1} attempts: {e.__class__.__name__}: {str(e)}"
                            }

                    except RecursionError as e:
                        # Special handling for RecursionError (no retry,
                        # immediate failure)
                        log.error(
                            f"Tool '{tool_name}' recursion error "
                            f"detected: {e}",
                            exc_info=True
                        )
                        return {
                            "status": "ERROR",
                            "error_type": "RecursionError",
                            "user_facing_message": "I encountered an internal problem (recursion error) while processing your request. The development team has been notified.",
                            "technical_details": f"Recursion error: {e.__class__.__name__}: {str(e)}. Function may contain infinite recursion or overly complex recursive structures"
                        }

                    except Exception as e:
                        # Handle all other exceptions (log, but don't retry -
                        # immediately return error)
                        log.exception(
                            f"Tool '{tool_name}' failed with "
                            f"unexpected error: {e}"
                        )
                        # Return a standard error format for unexpected
                        # exceptions
                        return {
                            "status": "ERROR",
                            "error_type": e.__class__.__name__,
                            "user_facing_message": "I ran into an unexpected issue while trying to complete that. Please try again in a moment.",
                            "technical_details": f"Unexpected error: {e.__class__.__name__}: {str(e)}"
                        }

                # (Safeguard return)
                # This part should ideally not be reached if max_retries >= 0
                log.error(
                    f"Tool '{tool_name}' exited retry loop unexpectedly. "
                    f"Last exception: {last_exception}"
                )
                return {
                    "status": "ERROR",
                    "error_type": "UnknownExecutionError",
                    "user_facing_message": "I failed to complete your request after a few tries. Please try again later.",
                    "technical_details": (f"Tool failed unexpectedly after retries. Last error: {last_exception}"
                                if last_exception else "Tool failed unexpectedly after retries. No specific last exception recorded.")
                }

            # Execute the tool with retry logic
            try:
                result = await _execute_tool_calls()
                # Log execution time for performance monitoring
                execution_time = time.time() - start_time
                log.debug(
                    f"Tool '{tool_name}' execution completed in "
                    f"{execution_time:.3f}s with status: "
                    f"{result.get('status', 'UNKNOWN_DICT_NO_STATUS') if isinstance(result, dict) else ('LIST_RESULT' if isinstance(result, list) else 'UNKNOWN_RESULT_TYPE')}"
                )
                # Add execution_time_ms to the result
                if isinstance(result, dict):
                    result["execution_time_ms"] = int(execution_time * 1000)
                return result
            except Exception as e:
                # Last-resort exception handler to ensure wrapper never
                # raises exceptions to caller
                log.critical(
                    f"CRITICAL: Unhandled exception in tool wrapper for "
                    f"'{tool_name}': {e}", exc_info=True
                )
                return {
                    "status": "ERROR",
                    "error_type": "WrapperError",
                    "user_facing_message": "A critical internal error occurred. The development team has been alerted.",
                    "technical_details": f"Critical error in tool wrapper: {e.__class__.__name__}: {str(e)}. This is a bug in the tool wrapper, not the tool itself."
                }

        # --- Store Class Info on Wrapper ---
        # Determine if the function is a method of a class based on its
        # __qualname__. This is needed by ToolExecutor to map function names
        # to class instances.
        if '.' in func.__qualname__ and \
           '<locals>' not in func.__qualname__:
            # Get the class name part before the method name
            class_name = func.__qualname__.rsplit('.', 1)[0]
            # Store the class name as an attribute on the wrapper function
            setattr(wrapper, '_tool_class_name', class_name)
            log.debug(
                f"Storing class context '{class_name}' for tool "
                f"'{func.__name__}'."
            )
        else:
            # It's likely a standalone function not part of a tool class
            # managed by ToolExecutor
            setattr(wrapper, '_tool_class_name', None)
            log.debug(
                f"Marking tool '{func.__name__}' as standalone "
                f"(no class context)."
            )

        # Register the wrapper function last, after everything else is set up
        # Attach the ToolDefinition object to the wrapper function itself
        # so it can be accessed directly from the decorated function.
        # This must be done after 'wrapper' is defined and 'tool_definition_obj' is confirmed.
        if tool_name in _TOOL_DEFINITIONS: # Ensure tool_definition_obj was successfully created and registered
            setattr(wrapper, '_tool_definition', _TOOL_DEFINITIONS[tool_name])
        else:
            # This case should ideally not be hit if the critical log and re-raise above work,
            # but as a safeguard:
            log.error(f"Tool '{tool_name}': _tool_definition could not be set on wrapper as ToolDefinition was not found in _TOOL_DEFINITIONS.")

        _TOOL_REGISTRY[tool_name] = wrapper
        log.debug(f"Tool '{tool_name}' wrapper registered.")

        return wrapper
    return decorator


# --- Registry Access Functions ---

def get_registered_tools() -> Dict[str, Callable]:
    """Returns a copy of the dictionary of registered (wrapped) tool functions.
    """  # noqa: E501
    return _TOOL_REGISTRY.copy()


def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    Returns a list of all tool definitions, with each definition
    as an OpenAPI-compatible dictionary.
    """
    return [
        tool_def.model_dump(exclude_none=True, by_alias=True)
        for tool_def in _TOOL_DEFINITIONS.values()
    ]


def get_tool_definition_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Returns a specific tool definition by name as an OpenAPI-compatible
    dictionary, or None if not found.
    """
    tool_def = _TOOL_DEFINITIONS.get(name)
    if tool_def:
        return tool_def.model_dump(exclude_none=True, by_alias=True)
    return None


def clear_registry():
    """Clears the tool registry - primarily for testing purposes."""
    _TOOL_REGISTRY.clear()
    _TOOL_DEFINITIONS.clear()
    log.info("Tool registry has been cleared.")
