"""
Enhanced Bot Handler with comprehensive error handling and safety measures
"""
import logging
import traceback
from typing import Any, Dict, Optional, Tuple
from contextlib import contextmanager

from pydantic import ValidationError
from bot_core.message_handler import MessageProcessor, SafeMessage
from utils.utils import validate_and_repair_state, cleanup_messages
from state_models import AppState

log = logging.getLogger(__name__)

class BotErrorHandler:
    """Enhanced error handler for bot operations"""
    
    def __init__(self):
        self.error_count = 0
        self.validation_error_count = 0
        self.text_integrity_errors = 0
        
    @contextmanager
    def safe_operation(self, operation_name: str):
        """Context manager for safe bot operations with comprehensive error handling"""
        try:
            log.debug(f"Starting safe operation: {operation_name}")
            yield
            log.debug(f"Completed safe operation: {operation_name}")
        except ValidationError as e:
            self.validation_error_count += 1
            log.error(f"Validation error in {operation_name}: {e}")
            self._handle_validation_error(e, operation_name)
        except Exception as e:
            self.error_count += 1
            log.error(f"Unexpected error in {operation_name}: {e}")
            log.error(f"Traceback: {traceback.format_exc()}")
            self._handle_general_error(e, operation_name)
    
    def _handle_validation_error(self, error: ValidationError, operation: str):
        """Handle Pydantic validation errors specifically"""
        log.error(f"Validation error details for {operation}:")
        for err in error.errors():
            log.error(f"  - {err}")
            
            # Check for character splitting indicators
            if 'dictionary or instance' in str(err.get('msg', '')):
                log.warning("Detected potential character splitting or input format issue")
                self.text_integrity_errors += 1
    
    def _handle_general_error(self, error: Exception, operation: str):
        """Handle general errors"""
        error_msg = str(error)
        
        # Look for signs of text processing issues
        if any(indicator in error_msg.lower() for indicator in [
            'character', 'string index', 'iteration', 'encoding'
        ]):
            log.warning(f"Potential text processing issue in {operation}: {error_msg}")
            self.text_integrity_errors += 1
    
    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of errors encountered"""
        return {
            "total_errors": self.error_count,
            "validation_errors": self.validation_error_count,
            "text_integrity_errors": self.text_integrity_errors
        }

class EnhancedBotHandler:
    """Enhanced bot handler with comprehensive safety measures"""
    
    def __init__(self):
        self.error_handler = BotErrorHandler()
        self.message_processor = MessageProcessor()
    
    def safe_process_user_input(self, raw_input: Any, state: AppState) -> Tuple[bool, str]:
        """
        Safely process user input with comprehensive validation and error handling
        
        Returns:
            Tuple[bool, str]: (success, processed_text_or_error_message)
        """
        with self.error_handler.safe_operation("process_user_input"):
            try:
                # Step 1: Validate and repair state first
                is_valid, repairs = validate_and_repair_state(state)
                if repairs:
                    log.info(f"State repairs made: {repairs}")
                
                # Step 2: Safely parse the input message
                safe_message = self.message_processor.safe_parse_message(raw_input)
                
                # Step 3: Validate text integrity
                text_content = safe_message.text
                if not self.message_processor.validate_text_integrity(text_content):
                    log.error(f"Text integrity validation failed for input: '{text_content[:50]}...'")
                    return False, "Error: Message contains invalid text formatting"
                
                # Step 4: Check for suspicious patterns that indicate character splitting
                if self._detect_character_splitting(text_content):
                    log.error(f"Character splitting detected in input: '{text_content[:50]}...'")
                    return False, "Error: Message appears to be corrupted (character splitting detected)"
                
                # Step 5: Add message to state safely
                state.add_message("user", safe_message)
                
                # Step 6: Cleanup if needed
                if len(state.messages) > 100:
                    cleanup_messages(state, keep_last_n=80)
                
                log.info(f"Successfully processed user input: '{text_content[:50]}{'...' if len(text_content) > 50 else ''}'")
                return True, text_content
                
            except Exception as e:
                log.error(f"Failed to process user input: {e}")
                return False, f"Error processing input: {str(e)[:100]}"
    
    def safe_generate_response(self, state: AppState, llm_interface) -> Tuple[bool, str]:
        """
        Safely generate bot response with error handling
        
        Returns:
            Tuple[bool, str]: (success, response_text_or_error_message)
        """
        with self.error_handler.safe_operation("generate_response"):
            try:
                # Validate state before generating response
                is_valid, repairs = validate_and_repair_state(state)
                if not is_valid:
                    log.warning(f"State required repairs before response generation: {repairs}")
                
                # Get conversation history safely
                history = state.get_message_history(limit=20)
                if not history:
                    return False, "Error: No conversation history available"
                
                # Generate response using LLM interface
                response = llm_interface.generate_response(history)
                
                # Validate response integrity
                if not self.message_processor.validate_text_integrity(response):
                    log.error("Generated response failed text integrity check")
                    return False, "I encountered an error generating a proper response. Please try again."
                
                # Add response to state
                state.add_message("assistant", response)
                
                return True, response
                
            except Exception as e:
                log.error(f"Failed to generate response: {e}")
                error_response = "I apologize, but I encountered an error. Please try your request again."
                state.add_message("assistant", error_response)
                return False, error_response
    
    def _detect_character_splitting(self, text: str) -> bool:
        """
        Detect if text shows signs of character splitting
        
        This looks for patterns that indicate individual characters are being
        processed as separate items instead of as a cohesive string.
        """
        if not text or len(text) < 10:
            return False
        
        # Pattern 1: Very long text with no spaces (likely character splitting)
        if len(text) > 50 and ' ' not in text and '\n' not in text:
            log.warning(f"Pattern 1 - Long text without spaces: '{text[:30]}...'")
            return True
        
        # Pattern 2: Text that looks like individual characters separated by delimiters
        if len(text.split(',')) > 20 and all(len(part.strip()) <= 2 for part in text.split(',')[:10]):
            log.warning(f"Pattern 2 - Character-like comma separation: '{text[:30]}...'")
            return True
        
        # Pattern 3: Extremely high ratio of non-alphabetic characters
        alpha_chars = sum(1 for c in text if c.isalpha())
        if len(text) > 20 and alpha_chars / len(text) < 0.3:
            log.warning(f"Pattern 3 - Low alphabetic ratio: '{text[:30]}...'")
            return True
        
        # Pattern 4: Text that looks like encoding artifacts
        if any(indicator in text for indicator in ['\\x', '\\u', 'Ă', 'â€™']):
            log.warning(f"Pattern 4 - Encoding artifacts: '{text[:30]}...'")
            return True
        
        return False
    
    def safe_handle_bot_message(self, activity, state: AppState) -> Tuple[bool, str]:
        """
        Safely handle incoming bot messages with comprehensive error handling
        
        This is the main entry point for processing bot messages.
        """
        with self.error_handler.safe_operation("handle_bot_message"):
            try:
                # Extract message text safely
                raw_message = getattr(activity, 'text', None)
                if raw_message is None:
                    log.warning("Received activity with no text content")
                    return False, "No message content received"
                
                # Process the user input
                success, result = self.safe_process_user_input(raw_message, state)
                if not success:
                    log.error(f"Failed to process user input: {result}")
                    return False, result
                
                # Log successful processing
                log.info(f"Successfully handled bot message: '{result[:50]}{'...' if len(result) > 50 else ''}'")
                return True, result
                
            except Exception as e:
                log.error(f"Critical error in bot message handling: {e}")
                log.error(f"Traceback: {traceback.format_exc()}")
                return False, "A critical error occurred while processing your message."
    
    def get_diagnostic_info(self) -> Dict[str, Any]:
        """Get diagnostic information for debugging"""
        return {
            "error_summary": self.error_handler.get_error_summary(),
            "message_processor_available": self.message_processor is not None,
            "last_operation_status": "ready"
        }

# Example usage and testing
if __name__ == "__main__":
    # Set up logging for testing
    logging.basicConfig(level=logging.DEBUG)
    
    # Create enhanced handler
    handler = EnhancedBotHandler()
    
    # Create test state
    state = AppState()
    
    # Test various problematic inputs
    test_inputs = [
        "Hello world",  # Normal input
        "s u p   b i t c h   d o   y o u   a c t u a l",  # Character split pattern
        {"text": "Hello world"},  # Dict input
        "",  # Empty input
        "A" * 200,  # Very long input without spaces
    ]
    
    print("Testing Enhanced Bot Handler:")
    print("=" * 50)
    
    for i, test_input in enumerate(test_inputs):
        print(f"\nTest {i+1}: {repr(test_input)}")
        success, result = handler.safe_process_user_input(test_input, state)
        print(f"Success: {success}")
        print(f"Result: {result[:100]}{'...' if len(str(result)) > 100 else ''}")
    
    print(f"\nDiagnostic Info:")
    print(handler.get_diagnostic_info()) 