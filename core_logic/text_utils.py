"""Utility functions for text processing and analysis."""

import logging
from typing import List, Optional

log = logging.getLogger(__name__)

def is_greeting_or_chitchat(query: Optional[str]) -> bool:
    """
    Determines if a query is a simple greeting or chitchat that doesn't need tools.
    
    IMPORTANT: This function should be very conservative and only flag obvious 
    social pleasantries. When in doubt, return False to let the query proceed
    to tool selection. It's better to provide tools unnecessarily than to 
    block legitimate requests.
    
    Args:
        query: The user query text to analyze
        
    Returns:
        bool: True if the query is clearly just a greeting or chitchat, False otherwise
    """
    if not query:
        return False
    
    # Normalize the query
    normalized_query = query.lower().strip()
    
    # Check for very simple, obvious greetings (exact matches only)
    simple_greetings = [
        "hello", "hi", "hey", "greetings", "good morning", "good afternoon", 
        "good evening", "howdy", "hi there", "hello there", "hiya"
    ]
    
    # Only flag if it's an exact match to avoid blocking complex queries
    if normalized_query in simple_greetings:
        log.info(f"Detected simple greeting: '{query}'. Not requiring tools.")
        return True
    
    # Check for very obvious social pleasantries (exact matches only)
    obvious_chitchat = [
        "thanks", "thank you", "thanks!", "thank you!", 
        "bye", "goodbye", "see you", "good bye",
        "how are you", "how are you?", "how're you", "how're you?"
    ]
    
    if normalized_query in obvious_chitchat:
        log.info(f"Detected obvious chitchat: '{query}'. Not requiring tools.")
        return True
    
    # CONSERVATIVE APPROACH: For anything else, including:
    # - Questions about capabilities ("what can you do?")
    # - Requests for help ("help", "help me")
    # - Any action-oriented language ("list", "show", "create", etc.)
    # - Any complex or compound sentences
    # - Anything with specific nouns or technical terms
    # 
    # Return False to let the intelligent tool selection handle it
    
    return False 