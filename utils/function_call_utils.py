"""
Robust utility for safely extracting Gemini function_call arguments as plain dicts.
Handles all known types, including MapComposite, dict, to_dict, and more.
Never calls str() or repr() on unknown objects. Only logs types and attribute names.
"""
from typing import Any

try:
    from proto.marshal.collections.maps import MapComposite
except ImportError:
    MapComposite = None

def safe_extract_function_call(function_call_obj: Any) -> dict:
    """
    Safely extracts a plain dict from any Gemini function_call object, handling all known types.
    Never calls str() or repr() on unknown objects. Only logs types and attribute names.
    Returns a dict, or an empty dict if unprocessable.
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
        except Exception:
            return {"_error": "MapComposite conversion failed"}
    # If has to_dict()
    if hasattr(function_call_obj, 'to_dict') and callable(getattr(function_call_obj, 'to_dict')):
        try:
            return function_call_obj.to_dict()
        except Exception:
            return {"_error": "to_dict() failed"}
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
            # Only include serializable values
            return {
                k: v for k, v in function_call_obj.__dict__.items()
                if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
        except Exception:
            return {"_error": "__dict__ extraction failed"}
    # Fallback: extract all non-callable, non-private attributes
    try:
        props = {}
        for attr in dir(function_call_obj):
            if not attr.startswith('_') and not callable(getattr(function_call_obj, attr, None)):
                try:
                    val = getattr(function_call_obj, attr)
                    if isinstance(val, (str, int, float, bool, list, dict, type(None))):
                        props[attr] = val
                    else:
                        props[attr] = f"<{type(val).__name__}>"
                except Exception:
                    props[attr] = "<error>"
        if props:
            return props
    except Exception:
        pass
    # If all else fails
    return {"_unextractable_type": type(function_call_obj).__name__} 