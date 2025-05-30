from functools import wraps
from typing import Callable, Any, Optional, TYPE_CHECKING
import inspect

from user_auth.permissions import Permission, PermissionManager
from user_auth.models import UserProfile
from config import get_config 
import logging 

if TYPE_CHECKING:
    from state_models import AppState  # Assuming AppState will be in state_models

# Get a logger for this module
logger = logging.getLogger(__name__) # Changed from print to logger



def requires_permission(permission_name: Permission, fallback_permission: Optional[Permission] = None):
    """
    Decorator to check user permission before executing a tool function.

    It expects 'app_state: AppState' to be present in the decorated function's
    keyword arguments or as the first or second positional argument if the
    decorated function is a method.

    Args:
        permission_name: The primary permission required to execute the function.
        fallback_permission: An optional permission to check if the primary one fails.
                             If the fallback is met, 'read_only_mode=True' might be
                             passed to the wrapped function.
    """
    def decorator(func: Callable) -> Callable:
        # Check if the original function is async
        is_async_func = inspect.iscoroutinefunction(func)
        
        if is_async_func:
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                return await _execute_with_permission_check(func, is_async_func, permission_name, fallback_permission, args, kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                # For sync functions, execute permission check and function synchronously
                import asyncio
                
                # Check if we're already in an async context (e.g., during tests)
                try:
                    # Try to get the current event loop
                    current_loop = asyncio.get_running_loop()
                    # If we're in an event loop, we need to run in a thread to avoid "RuntimeError: Cannot run the event loop while another loop is running"
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            lambda: asyncio.run(_execute_with_permission_check(func, is_async_func, permission_name, fallback_permission, args, kwargs))
                        )
                        return future.result()
                except RuntimeError:
                    # No running event loop, we can safely use asyncio.run()
                    return asyncio.run(_execute_with_permission_check(func, is_async_func, permission_name, fallback_permission, args, kwargs))
            return sync_wrapper
    return decorator

async def _execute_with_permission_check(func: Callable, is_async_func: bool, permission_name: Permission, fallback_permission: Optional[Permission], args, kwargs) -> Any:
    app_config = get_config()
    app_state: Optional['AppState'] = None

    # Attempt to find AppState instance
    # Priority 1: Keyword argument named 'app_state'
    if 'app_state' in kwargs and hasattr(kwargs['app_state'], 'current_user'):
        app_state = kwargs['app_state']

    # Priority 2: Positional arguments
    if not app_state and args:
        # Scenario 2a: args[0] is 'self' and has 'self.app_state'
        if hasattr(args[0], 'app_state') and \
           hasattr(args[0].app_state, 'current_user') and \
           hasattr(args[0].app_state, 'has_permission'): # Check if self.app_state is AppState-like
            app_state = args[0].app_state
        # Scenario 2b: args[0] *is* an AppState instance
        elif hasattr(args[0], 'current_user') and hasattr(args[0], 'has_permission'):
            app_state = args[0]
        # Scenario 2c: args[1] *is* an AppState instance (if args[0] was 'self' but didn't have valid .app_state)
        elif len(args) > 1 and hasattr(args[1], 'current_user') and hasattr(args[1], 'has_permission'):
            app_state = args[1]

    # Fallback: If not found by specific name/position, iterate through all kwargs values then all args
    if not app_state:
        for kw_val in kwargs.values():
            if hasattr(kw_val, 'current_user') and hasattr(kw_val, 'has_permission'):
                app_state = kw_val
                break
    if not app_state and args:
        for arg_val in args:
            if hasattr(arg_val, 'current_user') and hasattr(arg_val, 'has_permission'):
                app_state = arg_val
                break
    
    # Prepare a clean version of kwargs for the wrapped function,
    # removing decorator-specific or potentially problematic args.
    kwargs_for_actual_call = kwargs.copy()
    kwargs_for_actual_call.pop('tool_config', None) # ToolExecutor might pass this
    # Do NOT pop 'app_state' here if it was originally passed as a kwarg,
    # func(*args, **kwargs_for_actual_call) will pass it correctly.

    # If RBAC is disabled, bypass permission checks
    if not app_config.settings.security_rbac_enabled:
        user_id_for_log = "N/A"
        if app_state and hasattr(app_state, 'current_user') and app_state.current_user:
            user_id_for_log = app_state.current_user.user_id
        logger.debug(
            f"RBAC is disabled. Allowing action '{func.__name__}' for user '{user_id_for_log}' without permission check."
        )
        # Ensure app_state is passed correctly. args[0] is self.
        # Explicitly pass app_state as the second positional arg.
        # Filter out 'app_state' from kwargs if it exists to prevent multiple values error.
        cleaned_kwargs = {k: v for k, v in kwargs_for_actual_call.items() if k != 'app_state'}
        if args and app_state:
            # Check if args[0] is None (standalone function) - don't pass it
            if args[0] is None:
                if is_async_func:
                    return await func(app_state, **cleaned_kwargs)
                else:
                    return func(app_state, **cleaned_kwargs)
            else: # args[0] is self (the instance)
                if is_async_func:
                    return await func(args[0], app_state, **cleaned_kwargs)
                else:
                    return func(args[0], app_state, **cleaned_kwargs)
        else: # Should not typically happen for instance methods if app_state is always expected
            if is_async_func:
                return await func(*args, **kwargs_for_actual_call) # Fallback, might still error if app_state missing
            else:
                return func(*args, **kwargs_for_actual_call)

    # --- RBAC is ENFORCED from here --- 
    if not app_state or not hasattr(app_state, 'current_user'):
        logger.warning(f"RBAC Enabled: No AppState or user context for permission check on {func.__name__}. Denying access.")
        return {
            "status": "PERMISSION_DENIED",
            "message": f"Action '{func.__name__}' cannot be performed due to missing user context for permission check."
        }

    current_user: Optional[UserProfile] = app_state.current_user

    if not current_user:
        logger.warning(f"RBAC Enabled: UserProfile not available in AppState for permission check on {func.__name__}. Denying access.")
        return {
            "status": "PERMISSION_DENIED",
            "message": f"Action '{func.__name__}' cannot be performed because the user profile could not be loaded."
        }

    # At this point, app_state and current_user are valid.
    # Now, use AppState's own has_permission method, which already incorporates the RBAC check
    # and PermissionManager logic.
    if app_state.has_permission(permission_name):
        cleaned_kwargs = {k: v for k, v in kwargs_for_actual_call.items() if k != 'app_state'}
        if args and app_state:
            # Check if args[0] is None (standalone function) - don't pass it
            if args[0] is None:
                # For standalone functions, just pass app_state and cleaned_kwargs
                if is_async_func:
                    return await func(app_state, **cleaned_kwargs)
                else:
                    return func(app_state, **cleaned_kwargs)
            # Check if app_state comes from args[0].app_state
            elif hasattr(args[0], 'app_state') and args[0].app_state is app_state:
                # If app_state is from args[0].app_state, don't add it as a second argument
                if is_async_func:
                    return await func(args[0], **cleaned_kwargs)
                else:
                    return func(args[0], **cleaned_kwargs)
            else:
                # Check if app_state is already being passed in kwargs with a different parameter name
                app_state_in_kwargs = False
                for k, v in cleaned_kwargs.items():
                    if v is app_state:
                        app_state_in_kwargs = True
                        break
                
                if app_state_in_kwargs:
                    # If app_state is already in kwargs with a different name, don't add it again
                    if is_async_func:
                        return await func(args[0], **cleaned_kwargs)
                    else:
                        return func(args[0], **cleaned_kwargs)
                else:
                    # Otherwise pass it as the second parameter
                    if is_async_func:
                        return await func(args[0], app_state, **cleaned_kwargs)
                    else:
                        return func(args[0], app_state, **cleaned_kwargs)
        else:
            if is_async_func:
                return await func(*args, **kwargs_for_actual_call)
            else:
                return func(*args, **kwargs_for_actual_call)
    
    if fallback_permission and app_state.has_permission(fallback_permission):
        # Create a new kwargs dict for fallback to avoid modifying the original one
        kwargs_for_fallback_call_copy = kwargs_for_actual_call.copy()
        kwargs_for_fallback_call_copy['read_only_mode'] = True
        
        cleaned_kwargs_fallback = {k: v for k, v in kwargs_for_fallback_call_copy.items() if k != 'app_state'}

        logger.debug(f"User '{current_user.user_id}' using fallback permission '{fallback_permission.value}' for {func.__name__}, read_only_mode=True")
        if args and app_state:
            # Check if args[0] is None (standalone function) - don't pass it
            if args[0] is None:
                # For standalone functions, just pass app_state and cleaned_kwargs
                if is_async_func:
                    return await func(app_state, **cleaned_kwargs_fallback)
                else:
                    return func(app_state, **cleaned_kwargs_fallback)
            # Check if app_state comes from args[0].app_state for fallback permission as well
            elif hasattr(args[0], 'app_state') and args[0].app_state is app_state:
                # If app_state is from args[0].app_state, don't add it as a second argument
                if is_async_func:
                    return await func(args[0], **cleaned_kwargs_fallback)
                else:
                    return func(args[0], **cleaned_kwargs_fallback)
            else:
                # Check if app_state is already being passed in kwargs with a different parameter name
                app_state_in_kwargs = False
                for k, v in cleaned_kwargs_fallback.items():
                    if v is app_state:
                        app_state_in_kwargs = True
                        break
                
                if app_state_in_kwargs:
                    # If app_state is already in kwargs with a different name, don't add it again
                    if is_async_func:
                        return await func(args[0], **cleaned_kwargs_fallback)
                    else:
                        return func(args[0], **cleaned_kwargs_fallback)
                else:
                    # Otherwise pass it as the second parameter
                    if is_async_func:
                        return await func(args[0], app_state, **cleaned_kwargs_fallback)
                    else:
                        return func(args[0], app_state, **cleaned_kwargs_fallback)
        else:
            if is_async_func:
                return await func(*args, **kwargs_for_fallback_call_copy) # Original fallback kwargs if no args/app_state adjustments
            else:
                return func(*args, **kwargs_for_fallback_call_copy)

    # If neither primary nor fallback permission (if applicable) is met
    denial_message = f"Action '{func.__name__}' requires permission '{permission_name.value}' which you do not have."
    if fallback_permission:
        denial_message += f" Fallback permission '{fallback_permission.value}' was also not met."
    
    logger.info(f"RBAC Enabled: User '{current_user.user_id}' lacks permission '{permission_name.value}' (and fallback, if any) for {func.__name__}.")
    
    return {
        "status": "PERMISSION_DENIED",
        "message": denial_message
    } 