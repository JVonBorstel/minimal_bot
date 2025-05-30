"""
Robust utility for safely extracting Gemini function_call arguments as plain dicts.
Handles all known types, including MapComposite, dict, to_dict, and more.
Never calls str() or repr() on unknown objects. Only logs types and attribute names.
"""
from typing import Any, Dict, Optional
import logging

# Get a dedicated logger
log = logging.getLogger(__name__)

try:
    from proto.marshal.collections.maps import MapComposite
except ImportError:
    MapComposite = None

# Try to import the Google generative AI types
try:
    import google.ai.generativelanguage as glm
    GOOGLE_SDK_AVAILABLE = True
except ImportError:
    GOOGLE_SDK_AVAILABLE = False
    glm = None

def safe_extract_function_call(function_call_obj: Any) -> dict:
    """
    Safely extracts a plain dict from any Gemini function_call object, handling all known types.
    Never calls str() or repr() on unknown objects. Only logs types and attribute names.
    Returns a dict, or an empty dict if unprocessable.
    
    Added support for protobuf objects and the latest Google AI SDK format.
    """
    if function_call_obj is None:
        return {}
        
    # If already a dict
    if isinstance(function_call_obj, dict):
        return function_call_obj
        
    # If MapComposite (SDK type)
    if MapComposite and isinstance(function_call_obj, MapComposite):
        try:
            return dict(function_call_obj)
        except Exception as e:
            log.debug(f"MapComposite conversion failed: {type(e).__name__}")
            return {"_error": "MapComposite conversion failed"}
            
    # If has to_dict()
    if hasattr(function_call_obj, 'to_dict') and callable(getattr(function_call_obj, 'to_dict')):
        try:
            return function_call_obj.to_dict()
        except Exception as e:
            log.debug(f"to_dict() method failed: {type(e).__name__}")
            # Fallback to our own attribute extraction below
            pass
            
    # Handle protobuf objects (which have special requirements)
    if GOOGLE_SDK_AVAILABLE and hasattr(function_call_obj, 'DESCRIPTOR'):
        try:
            # Protobuf objects often have structured fields
            result = {}
            
            # Get all field descriptors from the protobuf DESCRIPTOR
            field_names = [field.name for field in function_call_obj.DESCRIPTOR.fields]
            
            # Extract each field safely
            for field in field_names:
                try:
                    if hasattr(function_call_obj, field):
                        value = getattr(function_call_obj, field)
                        
                        # Handle nested protobufs recursively
                        if value is not None and hasattr(value, 'DESCRIPTOR'):
                            result[field] = safe_extract_function_call(value)
                        # Handle basic types
                        elif value is None or isinstance(value, (str, int, float, bool, list, dict)):
                            result[field] = value
                except Exception:
                    pass  # Skip fields that can't be extracted
                    
            if result:
                return result
        except Exception as e:
            log.debug(f"Protobuf extraction failed: {type(e).__name__}")
            # Continue with other methods if protobuf extraction fails
            pass
    
    # Special handling for Google SDK v2.0 and above (for Gemini 2.0/2.5)
    if hasattr(function_call_obj, 'args') and function_call_obj is not None:
        try:
            # Direct args access (most common case in newer SDKs)
            args = getattr(function_call_obj, 'args', None)
            if isinstance(args, dict):
                return args
                
            # Try to convert to dict if it has keys/values/items methods
            elif args is not None and hasattr(args, 'items') and callable(args.items):
                try:
                    return dict(args.items())
                except Exception:
                    pass
                    
            # Try to convert with __iter__ and __getitem__
            elif args is not None and hasattr(args, '__iter__') and hasattr(args, '__getitem__'):
                try:
                    return {key: args[key] for key in args}
                except Exception:
                    pass
                    
            # For other arg types, check for known field/property access patterns
            if args is not None:
                # Try get_value or get_structure standard method
                if hasattr(args, 'get_value') and callable(getattr(args, 'get_value')):
                    try:
                        return args.get_value()
                    except Exception:
                        pass
                        
                # Access internal dict representation for some SDK types
                if hasattr(args, '_values'):
                    try:
                        return dict(args._values)
                    except Exception:
                        pass
        except Exception as e:
            log.debug(f"SDK v2+ args extraction failed: {type(e).__name__}")
            pass
            
    # If JSON string
    if isinstance(function_call_obj, str):
        try:
            import json
            return json.loads(function_call_obj)
        except Exception:
            return {"_original": function_call_obj}
            
    # If has __dict__
    if hasattr(function_call_obj, '__dict__'):
        try:
            # Only include serializable values and non-private attributes
            return {
                k: v for k, v in function_call_obj.__dict__.items()
                if not k.startswith('_') and isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
        except Exception:
            pass
            
    # Fallback: extract all non-callable, non-private attributes
    try:
        props = {}
        
        # First, collect attribute names without trying to access values
        attr_names = [
            attr for attr in dir(function_call_obj) 
            if not attr.startswith('_') and not callable(getattr(function_call_obj, attr, None))
        ]
        
        # Then try to extract each one individually with type checking
        for attr in attr_names:
            try:
                val = getattr(function_call_obj, attr)
                if isinstance(val, (str, int, float, bool, type(None))):
                    # Simple types are safe
                    props[attr] = val
                elif isinstance(val, (list, dict)):
                    # Containers might have non-serializable items, so be careful
                    try:
                        # Test if it can be serialized to JSON
                        import json
                        json.dumps(val)
                        props[attr] = val
                    except (TypeError, json.JSONDecodeError):
                        # If serialization fails, just note the type
                        props[attr] = f"<{type(val).__name__}>"
                else:
                    # For other types, just note the type name
                    props[attr] = f"<{type(val).__name__}>"
            except Exception:
                props[attr] = "<e>"
                
        if props:
            return props
    except Exception:
        pass
        
    # If all else fails, just return the type
    return {"_unextractable_type": type(function_call_obj).__name__} 