"""
Log Data Sanitizer
==================

This module provides intelligent data sanitization for logging that:
- Protects sensitive user data and credentials
- Preserves debugging utility through selective masking
- Supports configurable sanitization rules
- Maintains data structure for analysis while removing sensitive content
"""

import re
import hashlib
import json
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass
from enum import Enum


class SensitivityLevel(Enum):
    """Different levels of data sensitivity"""
    PUBLIC = "public"           # Can be logged freely
    INTERNAL = "internal"       # Can be logged in internal systems
    CONFIDENTIAL = "confidential"  # Should be hashed or masked
    SECRET = "secret"          # Should never be logged


@dataclass
class SanitizationRule:
    """Configuration for how to sanitize specific data types"""
    pattern: str  # Regex pattern to match
    replacement: str  # How to replace matched content
    sensitivity: SensitivityLevel
    preserve_length: bool = False  # Whether to preserve original length
    preserve_structure: bool = False  # Whether to preserve data structure


class DataSanitizer:
    """Intelligent data sanitizer for log entries"""
    
    def __init__(self):
        self.rules = self._load_default_rules()
        self.hash_salt = "bot_logging_salt_2024"  # In production, use config
        
    def _load_default_rules(self) -> List[SanitizationRule]:
        """Load default sanitization rules"""
        return [
            # API Keys and Tokens
            SanitizationRule(
                pattern=r'\b[A-Za-z0-9]{20,}\b',  # Generic API key pattern
                replacement='[API_KEY:{}]',
                sensitivity=SensitivityLevel.SECRET,
                preserve_length=False
            ),
            
            # Email addresses
            SanitizationRule(
                pattern=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                replacement='[EMAIL:{}]',
                sensitivity=SensitivityLevel.CONFIDENTIAL,
                preserve_length=False
            ),
            
            # IP Addresses
            SanitizationRule(
                pattern=r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
                replacement='[IP:{}]',
                sensitivity=SensitivityLevel.INTERNAL,
                preserve_length=False
            ),
            
            # Phone numbers (US format)
            SanitizationRule(
                pattern=r'\b\d{3}-\d{3}-\d{4}\b',
                replacement='[PHONE:***-***-****]',
                sensitivity=SensitivityLevel.CONFIDENTIAL,
                preserve_length=True
            ),
            
            # Credit card numbers
            SanitizationRule(
                pattern=r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
                replacement='[CARD:****-****-****-****]',
                sensitivity=SensitivityLevel.SECRET,
                preserve_length=True
            ),
            
            # Social Security Numbers
            SanitizationRule(
                pattern=r'\b\d{3}-\d{2}-\d{4}\b',
                replacement='[SSN:***-**-****]',
                sensitivity=SensitivityLevel.SECRET,
                preserve_length=True
            ),
            
            # GitHub tokens
            SanitizationRule(
                pattern=r'ghp_[A-Za-z0-9]{36}',
                replacement='[GITHUB_TOKEN:ghp_***]',
                sensitivity=SensitivityLevel.SECRET,
                preserve_length=False
            ),
            
            # JWT tokens
            SanitizationRule(
                pattern=r'eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*',
                replacement='[JWT_TOKEN:eyJ***]',
                sensitivity=SensitivityLevel.SECRET,
                preserve_length=False
            ),
            
            # Passwords in common formats
            SanitizationRule(
                pattern=r'(?i)(password|passwd|pwd)[\s]*[=:]\s*["\']?([^"\'\s]+)["\']?',
                replacement=r'\1=[PASSWORD:***]',
                sensitivity=SensitivityLevel.SECRET,
                preserve_length=False
            ),
        ]
    
    def sanitize_data(self, data: Any, max_sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL) -> Any:
        """
        Sanitize data based on sensitivity level
        
        Args:
            data: The data to sanitize
            max_sensitivity: Maximum sensitivity level to preserve
            
        Returns:
            Sanitized data
        """
        if isinstance(data, str):
            return self._sanitize_string(data, max_sensitivity)
        elif isinstance(data, dict):
            return self._sanitize_dict(data, max_sensitivity)
        elif isinstance(data, list):
            return self._sanitize_list(data, max_sensitivity)
        else:
            return data
    
    def _sanitize_string(self, text: str, max_sensitivity: SensitivityLevel) -> str:
        """Sanitize a string value"""
        if not text:
            return text
            
        result = text
        
        for rule in self.rules:
            if self._should_apply_rule(rule, max_sensitivity):
                if '{}' in rule.replacement:
                    # Hash-based replacement
                    def replace_with_hash(match):
                        original = match.group(0)
                        hash_value = self._generate_hash(original)[:8]
                        return rule.replacement.format(hash_value)
                    result = re.sub(rule.pattern, replace_with_hash, result)
                else:
                    # Direct replacement
                    result = re.sub(rule.pattern, rule.replacement, result)
                    
        return result
    
    def _sanitize_dict(self, data: Dict[str, Any], max_sensitivity: SensitivityLevel) -> Dict[str, Any]:
        """Sanitize a dictionary"""
        sanitized = {}
        
        for key, value in data.items():
            # Check if key itself is sensitive
            sanitized_key = self._sanitize_key(key, max_sensitivity)
            sanitized_value = self.sanitize_data(value, max_sensitivity)
            sanitized[sanitized_key] = sanitized_value
            
        return sanitized
    
    def _sanitize_list(self, data: List[Any], max_sensitivity: SensitivityLevel) -> List[Any]:
        """Sanitize a list"""
        return [self.sanitize_data(item, max_sensitivity) for item in data]
    
    def _sanitize_key(self, key: str, max_sensitivity: SensitivityLevel) -> str:
        """Sanitize dictionary keys that might be sensitive"""
        sensitive_key_patterns = [
            'password', 'passwd', 'pwd', 'secret', 'key', 'token',
            'credential', 'auth', 'api_key', 'private'
        ]
        
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in sensitive_key_patterns):
            if max_sensitivity.value not in [SensitivityLevel.CONFIDENTIAL.value, SensitivityLevel.SECRET.value]:
                return f"[SENSITIVE_KEY:{self._generate_hash(key)[:6]}]"
                
        return key
    
    def _should_apply_rule(self, rule: SanitizationRule, max_sensitivity: SensitivityLevel) -> bool:
        """Determine if a sanitization rule should be applied"""
        sensitivity_order = {
            SensitivityLevel.PUBLIC: 0,
            SensitivityLevel.INTERNAL: 1,
            SensitivityLevel.CONFIDENTIAL: 2,
            SensitivityLevel.SECRET: 3
        }
        
        return sensitivity_order[rule.sensitivity] > sensitivity_order[max_sensitivity]
    
    def _generate_hash(self, data: str) -> str:
        """Generate a consistent hash for sensitive data"""
        return hashlib.sha256(f"{data}{self.hash_salt}".encode()).hexdigest()
    
    def add_custom_rule(self, rule: SanitizationRule):
        """Add a custom sanitization rule"""
        self.rules.append(rule)
    
    def get_sanitization_summary(self, original_data: Any, sanitized_data: Any) -> Dict[str, Any]:
        """Generate a summary of what was sanitized"""
        return {
            'original_size': len(str(original_data)),
            'sanitized_size': len(str(sanitized_data)),
            'reduction_ratio': 1 - (len(str(sanitized_data)) / len(str(original_data))),
            'types_sanitized': self._detect_sanitized_types(str(sanitized_data))
        }
    
    def _detect_sanitized_types(self, sanitized_text: str) -> List[str]:
        """Detect what types of data were sanitized based on replacement patterns"""
        types = []
        patterns = {
            'API_KEY': r'\[API_KEY:',
            'EMAIL': r'\[EMAIL:',
            'IP': r'\[IP:',
            'PHONE': r'\[PHONE:',
            'CARD': r'\[CARD:',
            'SSN': r'\[SSN:',
            'GITHUB_TOKEN': r'\[GITHUB_TOKEN:',
            'JWT_TOKEN': r'\[JWT_TOKEN:',
            'PASSWORD': r'\[PASSWORD:'
        }
        
        for type_name, pattern in patterns.items():
            if re.search(pattern, sanitized_text):
                types.append(type_name)
                
        return types


class ContextAwareSanitizer(DataSanitizer):
    """Enhanced sanitizer that considers context for smarter sanitization"""
    
    def __init__(self):
        super().__init__()
        self.context_rules = self._load_context_rules()
    
    def _load_context_rules(self) -> Dict[str, List[SanitizationRule]]:
        """Load context-specific sanitization rules"""
        return {
            'llm_prompt': [
                # Be more conservative with LLM prompts
                SanitizationRule(
                    pattern=r'\b\w+@\w+\.\w+\b',  # Any email-like pattern
                    replacement='[EMAIL_REDACTED]',
                    sensitivity=SensitivityLevel.INTERNAL
                )
            ],
            'error_message': [
                # Preserve file paths but sanitize user data
                SanitizationRule(
                    pattern=r'/users/([^/\s]+)',
                    replacement='/users/[USER]',
                    sensitivity=SensitivityLevel.INTERNAL
                )
            ],
            'tool_response': [
                # Be more permissive for debugging tool responses
                SanitizationRule(
                    pattern=r'(user_id|id):\s*(\d+)',
                    replacement=r'\1: [USER_ID:\2]',
                    sensitivity=SensitivityLevel.CONFIDENTIAL
                )
            ]
        }
    
    def sanitize_with_context(self, data: Any, context: str, 
                            max_sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL) -> Any:
        """Sanitize data with context-aware rules"""
        # Apply base sanitization first
        sanitized = self.sanitize_data(data, max_sensitivity)
        
        # Apply context-specific rules
        if context in self.context_rules:
            for rule in self.context_rules[context]:
                if self._should_apply_rule(rule, max_sensitivity):
                    if isinstance(sanitized, str):
                        sanitized = re.sub(rule.pattern, rule.replacement, sanitized)
                    # Add handling for dict/list if needed
        
        return sanitized


class DebugModeSanitizer(DataSanitizer):
    """Sanitizer with debug mode that logs what it's sanitizing"""
    
    def __init__(self, debug_logger=None):
        super().__init__()
        self.debug_logger = debug_logger
        self.sanitization_log = []
    
    def sanitize_data(self, data: Any, max_sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL) -> Any:
        """Sanitize data and log debug information"""
        original_str = str(data)
        sanitized = super().sanitize_data(data, max_sensitivity)
        sanitized_str = str(sanitized)
        
        if original_str != sanitized_str:
            log_entry = {
                'timestamp': time.time(),
                'original_length': len(original_str),
                'sanitized_length': len(sanitized_str),
                'patterns_matched': self._find_matched_patterns(original_str),
                'sensitivity_level': max_sensitivity.value
            }
            
            self.sanitization_log.append(log_entry)
            
            if self.debug_logger:
                self.debug_logger.debug("Data sanitized", **log_entry)
        
        return sanitized
    
    def _find_matched_patterns(self, text: str) -> List[str]:
        """Find which patterns matched in the text"""
        matched = []
        for rule in self.rules:
            if re.search(rule.pattern, text):
                matched.append(rule.pattern)
        return matched
    
    def get_sanitization_stats(self) -> Dict[str, Any]:
        """Get statistics about sanitization activity"""
        if not self.sanitization_log:
            return {'total_sanitizations': 0}
            
        return {
            'total_sanitizations': len(self.sanitization_log),
            'avg_size_reduction': sum(
                1 - (entry['sanitized_length'] / entry['original_length'])
                for entry in self.sanitization_log
            ) / len(self.sanitization_log),
            'common_patterns': self._get_common_patterns(),
            'recent_activity': self.sanitization_log[-10:]  # Last 10 entries
        }
    
    def _get_common_patterns(self) -> Dict[str, int]:
        """Get the most commonly matched sanitization patterns"""
        pattern_counts = {}
        for entry in self.sanitization_log:
            for pattern in entry['patterns_matched']:
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        return dict(sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:5])


# Convenience functions
def sanitize_data(data: Any, max_sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL) -> Any:
    """Quick function to sanitize data"""
    sanitizer = DataSanitizer()
    return sanitizer.sanitize_data(data, max_sensitivity)

def sanitize_for_logging(data: Any, context: str = None) -> Any:
    """Sanitize data specifically for logging purposes"""
    if context:
        sanitizer = ContextAwareSanitizer()
        return sanitizer.sanitize_with_context(data, context, SensitivityLevel.INTERNAL)
    else:
        return sanitize_data(data, SensitivityLevel.INTERNAL)

def sanitize_for_external(data: Any) -> Any:
    """Sanitize data for external consumption (highest security)"""
    return sanitize_data(data, SensitivityLevel.PUBLIC)


# Test utilities
def test_sanitizer():
    """Test the sanitizer with sample data"""
    sanitizer = DataSanitizer()
    
    test_data = {
        'user_email': 'john.doe@example.com',
        'api_key': 'sk-1234567890abcdef1234567890abcdef',
        'phone': '555-123-4567',
        'message': 'Please reset password for user@test.com',
        'config': {
            'database_url': 'postgresql://user:pass@localhost:5432/db',
            'github_token': 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        }
    }
    
    sanitized = sanitizer.sanitize_data(test_data)
    summary = sanitizer.get_sanitization_summary(test_data, sanitized)
    
    print("Original:", json.dumps(test_data, indent=2))
    print("\nSanitized:", json.dumps(sanitized, indent=2))
    print("\nSummary:", json.dumps(summary, indent=2))

if __name__ == "__main__":
    test_sanitizer() 