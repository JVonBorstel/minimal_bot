# user_auth/teams_identity.py
from typing import Dict, Any, Optional
from botbuilder.schema import Activity, ChannelAccount

def extract_user_identity(activity: Activity) -> Optional[Dict[str, Any]]:
    """
    Extracts user identity information from a Bot Framework Activity object.

    Args:
        activity: The Bot Framework Activity object.

    Returns:
        A dictionary containing user identity information if available, otherwise None.
        Keys include: 'user_id', 'name', 'aad_object_id', 'email', 'tenant_id', 
                      'conversation_id', 'channel_id', 'service_url', 'locale'.
    """
    if not activity or not activity.from_property or not activity.from_property.id:
        # Basic check for essential information
        return None

    user_profile: ChannelAccount = activity.from_property
    
    # Standard fields from ChannelAccount
    user_id = user_profile.id
    name = user_profile.name
    aad_object_id = user_profile.aad_object_id # Important for Teams user mapping

    # Teams-specific user information (might be in channel_data or properties)
    # Email is often not directly in from_property for privacy reasons in Teams,
    # it might need to be fetched using BotFrameworkAdapter.get_conversation_members
    # or from channel_data if available.
    email = None 
    tenant_id = None

    if activity.channel_id == "msteams":
        # For Teams, tenant ID is usually in conversation.tenant_id
        if activity.conversation and hasattr(activity.conversation, 'tenant_id'):
            tenant_id = activity.conversation.tenant_id
        
        # Attempt to get email from channelData if present (common in some event types)
        # This check for tenant_id from channel_data should be independent of email extraction
        if activity.channel_data and isinstance(activity.channel_data, dict):
            channel_data_obj = activity.channel_data
            if 'tenant' in channel_data_obj and 'id' in channel_data_obj['tenant']:
                tenant_id = tenant_id or channel_data_obj['tenant']['id'] # Prefer conversation.tenant_id
            
        # Email extraction from user_profile.properties should be outside the channel_data check
        # but still within the msteams channel check.
        # Note: In proactive messages or user-initiated messages, email might not be here.
        # A more robust way to get email is Graph API or get_conversation_members.
        # For simplicity here, we'll check common places.
        if user_profile.properties and 'email' in user_profile.properties: # Sometimes it's in properties
            email = user_profile.properties['email']

    # General activity information
    conversation_id = activity.conversation.id if activity.conversation else None
    channel_id = activity.channel_id
    service_url = activity.service_url
    locale = activity.locale

    identity_info = {
        "user_id": user_id,
        "name": name,
        "aad_object_id": aad_object_id, # Azure Active Directory Object ID
        "email": email, # May be None
        "tenant_id": tenant_id, # May be None outside Teams or specific contexts
        "conversation_id": conversation_id,
        "channel_id": channel_id,
        "service_url": service_url,
        "locale": locale,
    }
    
    # Filter out None values for cleaner output, though None can be significant
    # return {k: v for k, v in identity_info.items() if v is not None}
    return identity_info

# Example Usage (for testing or integration within the bot)
# async def get_user_email_from_teams(turn_context: TurnContext) -> Optional[str]:
#     """
#     More robust way to get user email in Teams by fetching conversation members.
#     Note: This is an async operation and requires the adapter.
#     """
#     if turn_context.activity.channel_id != "msteams":
#         return None
#     try:
#         # This requires BotFrameworkAdapter instance, usually available in TurnContext
#         members = await turn_context.adapter.get_conversation_members(
#             turn_context.activity.conversation.id
#         )
#         for member in members:
#             if member.id == turn_context.activity.from_property.id:
#                 # The email property is often populated here for Teams users
#                 if hasattr(member, 'email') and member.email:
#                     return member.email
#                 # Sometimes it's in properties
#                 if member.properties and 'email' in member.properties:
#                     return member.properties['email']
#         return None
#     except Exception as e:
#         # Log error: f"Failed to get conversation members: {e}"
#         print(f"Error fetching members: {e}") # Replace with actual logging
#         return None 