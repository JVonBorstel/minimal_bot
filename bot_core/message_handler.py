"""
Enhanced message handling with Pydantic V2 best practices
"""
import logging
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

log = logging.getLogger(__name__)

class SafeTextPart(BaseModel):
    """Safe text part that handles various input formats"""
    content: str = Field(default="", description="Text content")
    
    @model_validator(mode='before')
    @classmethod
    def validate_input(cls, value: Any) -> Dict[str, Any]:
        """Handle various input formats safely"""
        if isinstance(value, str):
            return {"content": value}
        elif isinstance(value, dict):
            # Handle both 'text' and 'content' keys
            content = value.get('content') or value.get('text') or ""
            return {"content": str(content)}
        elif hasattr(value, 'text'):
            return {"content": str(value.text)}
        elif hasattr(value, 'content'):
            return {"content": str(value.content)}
        else:
            # Convert any other type to string
            return {"content": str(value) if value is not None else ""}
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: Any) -> str:
        """Ensure content is always a string"""
        if v is None:
            return ""
        return str(v)

class SafeMessage(BaseModel):
    """Safe message handling that prevents character splitting"""
    role: str = Field(default="user")
    parts: List[SafeTextPart] = Field(default_factory=list)
    raw_text: Optional[str] = Field(default=None)
    
    @model_validator(mode='before')
    @classmethod
    def handle_various_inputs(cls, value: Any) -> Dict[str, Any]:
        """Handle various message input formats"""
        if isinstance(value, str):
            # Single string input
            return {
                "role": "user",
                "parts": [{"content": value}],
                "raw_text": value
            }
        elif isinstance(value, dict):
            # Dictionary input
            result = {
                "role": value.get('role', 'user'),
                "parts": [],
                "raw_text": None
            }
            
            # Handle different text fields
            text_content = None
            if 'text' in value:
                text_content = value['text']
            elif 'content' in value:
                text_content = value['content']
            elif 'parts' in value:
                # Handle parts array
                parts = value['parts']
                if isinstance(parts, list):
                    result['parts'] = [SafeTextPart.model_validate(part) for part in parts]
                else:
                    text_content = str(parts)
            
            if text_content is not None:
                result['raw_text'] = str(text_content)
                result['parts'] = [{"content": str(text_content)}]
            
            return result
        else:
            # Handle object with attributes
            if hasattr(value, 'text'):
                text = str(value.text)
                return {
                    "role": getattr(value, 'role', 'user'),
                    "parts": [{"content": text}],
                    "raw_text": text
                }
            else:
                # Fallback
                return {
                    "role": "user", 
                    "parts": [{"content": str(value)}],
                    "raw_text": str(value)
                }
    
    @property
    def text(self) -> str:
        """Get the full text content"""
        if self.raw_text:
            return self.raw_text
        return "".join(part.content for part in self.parts)
    
    def get_content(self) -> str:
        """Safe method to get message content"""
        return self.text

class MessageProcessor:
    """Enhanced message processor with better error handling"""
    
    @staticmethod
    def safe_parse_message(raw_message: Any) -> SafeMessage:
        """Safely parse any message format"""
        try:
            return SafeMessage.model_validate(raw_message)
        except ValidationError as e:
            log.warning(f"Message validation failed: {e}")
            # Fallback to basic string conversion
            return SafeMessage(
                role="user",
                parts=[SafeTextPart(content=str(raw_message))],
                raw_text=str(raw_message)
            )
    
    @staticmethod
    def safe_get_text(message: Any) -> str:
        """Safely extract text from any message format"""
        if isinstance(message, SafeMessage):
            return message.text
        elif isinstance(message, str):
            return message
        elif isinstance(message, dict):
            return message.get('text', message.get('content', str(message)))
        elif hasattr(message, 'text'):
            return str(message.text)
        elif hasattr(message, 'content'):
            return str(message.content)
        else:
            return str(message)
    
    @staticmethod
    def validate_text_integrity(text: str) -> bool:
        """Check if text is being processed correctly (not character-split)"""
        if not text:
            return True
        
        # Check for signs of character splitting
        words = text.split()
        if len(words) == 0:
            return True
        
        # If we have a reasonable number of actual words, it's probably OK
        avg_word_length = sum(len(word) for word in words) / len(words)
        
        # If average word length is 1, we might have character splitting
        if avg_word_length <= 1.5 and len(words) > 5:
            log.warning(f"Possible character splitting detected in text: '{text[:50]}...'")
            return False
        
        return True

# Usage examples and testing
if __name__ == "__main__":
    processor = MessageProcessor()
    
    # Test various input formats
    test_inputs = [
        "Hello world",
        {"text": "Hello world"},
        {"content": "Hello world"},
        {"role": "user", "text": "Hello world"},
        {"parts": [{"text": "Hello"}, {"text": " world"}]}
    ]
    
    for test_input in test_inputs:
        try:
            message = processor.safe_parse_message(test_input)
            print(f"Input: {test_input}")
            print(f"Output: {message.text}")
            print(f"Valid: {processor.validate_text_integrity(message.text)}")
            print("---")
        except Exception as e:
            print(f"Error with {test_input}: {e}") 