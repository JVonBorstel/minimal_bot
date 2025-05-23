import re

# Precompile regex patterns for common sensitive data
# Note: These patterns are examples and may need to be adjusted for specific use cases.
# Order matters: more specific patterns should come before more general ones.
SENSITIVE_PATTERNS = {
    # API Keys (various common prefixes)
    "api_key_generic_prefix": re.compile(r"(sk-|glp_|AIza|ATAT|rk_live_)[a-zA-Z0-9\-_]{20,}"),
    "api_key_exact_length": re.compile(r"\b[a-zA-Z0-9\-_]{32,64}\b"), # General long alphanumeric strings that might be keys
    
    # Authorization Headers
    "auth_bearer_token": re.compile(r"(Bearer\s+)[a-zA-Z0-9\-_\.=]+"),
    "auth_basic_token": re.compile(r"(Basic\s+)[a-zA-Z0-9\+/=]+"),
    "auth_header_full": re.compile(r"(['\"]Authorization['\"]\s*:\s*['\"])(Bearer|Basic)\s+[a-zA-Z0-9\-_\.=]+(['\"])"),

    # Common Secrets / Passwords (Keywords often appear in keys or contexts)
    # These are harder to detect generically without context, focus on values if possible
    "password_like_value": re.compile(r"(['\"]?(?:password|secret|token|key|passwd|pwd)['\"]?\s*[:=]\s*['\"])[^\s'\"]+(['\"]?)", re.IGNORECASE),

    # Email addresses
    "email_address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
    
    # Common PII examples (very basic, real PII detection is complex)
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card_like": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), # Basic, doesn't validate Luhn
}

MASK_REPLACEMENT = "***MASKED***"

def _sanitize_string(text: str) -> str:
    """Applies all predefined regex patterns to a string for sanitization."""
    if not isinstance(text, str):
        return text # Return non-string types as is

    sanitized_text = text
    for key_name, pattern in SENSITIVE_PATTERNS.items():
        if "auth_bearer_token" in key_name or "auth_basic_token" in key_name : # Handle group replacement for bearer/basic
             sanitized_text = pattern.sub(f"\\1{MASK_REPLACEMENT}", sanitized_text)
        elif "auth_header_full" in key_name:
             sanitized_text = pattern.sub(f"\\1\\2 {MASK_REPLACEMENT}\\3", sanitized_text)
        elif "password_like_value" in key_name:
             sanitized_text = pattern.sub(f"\\1{MASK_REPLACEMENT}\\2", sanitized_text)
        else:
            sanitized_text = pattern.sub(MASK_REPLACEMENT, sanitized_text)
    return sanitized_text

def sanitize_data(data):
    """
    Recursively sanitizes a dictionary, list, or string by masking sensitive patterns.
    For dictionaries, it sanitizes values. Keys are not sanitized by this function,
    as key-based sanitization is handled by JSONFormatter's LOG_SENSITIVE_FIELDS.
    """
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return _sanitize_string(data)
    else:
        # Non-dict, non-list, non-string types are returned as is
        return data

if __name__ == '__main__':
    # Test cases
    test_data_dict = {
        "username": "john_doe",
        "api_key": "sk-abc123xyz789qwertyuiopasdfghjklzxcvbnm",
        "credentials": {
            "password": "mysecretpassword123",
            "old_tokens": ["glp_oldTokenDataHere", "anotherTokenValue"],
            "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        },
        "description": "User info with email: test@example.com and secondary key rk_live_thisIsARealKey12345678901234567890",
        "random_id_short": "abc123xyz789",
        "random_id_long": "abc123xyz789qwertyuiopasdfghjklzxcvbnm_long_one_test",
        "config_setting": "{\"Authorization\": \"Basic dXNlcjpwYXNzd29yZA==\"}",
        "notes": "SSN: 123-45-6789, CC: 1234-5678-9012-3456. Call AIzaSyChOtmDRY6sIMq0fD0fBDX_ABCDEFGH",
        "plain_text_api_key": "AIzaSyChOtmDRY6sIMq0fD0fBDX_thisisatestkey"
    }

    test_data_string_direct_key = "This string contains an API key: sk-anotherKeyForDirectTest1234567890 and an email support@domain.com."
    
    test_data_list = [
        "item1",
        {"sensitive_in_list": "sk-listKeyHereValue1234567890", "email_in_list": "contact@example.org"},
        "item3",
        "Authorization: Bearer some_jwt_token_here.payload.signature"
    ]

    print("Original Dictionary:")
    print(json.dumps(test_data_dict, indent=2))
    sanitized_dict = sanitize_data(test_data_dict)
    print("\nSanitized Dictionary:")
    print(json.dumps(sanitized_dict, indent=2))

    print("\nOriginal String:")
    print(test_data_string_direct_key)
    sanitized_string = sanitize_data(test_data_string_direct_key)
    print("\nSanitized String:")
    print(sanitized_string)
    
    print("\nOriginal List:")
    print(json.dumps(test_data_list, indent=2))
    sanitized_list = sanitize_data(test_data_list)
    print("\nSanitized List:")
    print(json.dumps(sanitized_list, indent=2))

    # Test for auth header within a string that looks like a JSON dumped string
    json_string_with_auth = '{"headers": {"Authorization": "Bearer verylongtokenstringgoeshere"}}'
    print("\nOriginal JSON String with Auth:")
    print(json_string_with_auth)
    sanitized_json_string_with_auth = sanitize_data(json_string_with_auth)
    print("\nSanitized JSON String with Auth:")
    print(sanitized_json_string_with_auth)

    # Test specific password pattern
    pass_string = 'The password is: "supersecret"'
    print(f"\nOriginal: {pass_string}")
    print(f"Sanitized: {sanitize_data(pass_string)}")

    pass_string_json = '{"user_password": "password123"}'
    print(f"\nOriginal: {pass_string_json}")
    print(f"Sanitized: {sanitize_data(pass_string_json)}")
    
    # Test case: String that is a key itself but short
    short_key_string = "Authorization" 
    print(f"\nOriginal: {short_key_string}")
    print(f"Sanitized: {sanitize_data(short_key_string)}") # Should not be masked

    # Test case: String that contains a key pattern but is not a value associated with a typical key name
    random_text_with_key_pattern = "A random string sk-abcdef12345678901234567890 found in text."
    print(f"\nOriginal: {random_text_with_key_pattern}")
    print(f"Sanitized: {sanitize_data(random_text_with_key_pattern)}")

    # Test case from real example
    auth_header_example = {"Authorization": "Bearer ghp_X..."}
    print("\nOriginal Auth Header Example:")
    print(json.dumps(auth_header_example, indent=2))
    sanitized_auth_header = sanitize_data(auth_header_example)
    print("\nSanitized Auth Header Example:")
    print(json.dumps(sanitized_auth_header, indent=2))
    
    auth_header_in_string = "some request with header 'Authorization': 'Bearer ghp_Y...' in it"
    print(f"\nOriginal: {auth_header_in_string}")
    print(f"Sanitized: {sanitize_data(auth_header_in_string)}") 