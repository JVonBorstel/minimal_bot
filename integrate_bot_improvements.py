#!/usr/bin/env python3
"""
Integration script for bot improvements
Safely integrates the enhanced message handling and error detection
"""
import sys
import logging
from pathlib import Path
import traceback

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def setup_logging():
    """Setup comprehensive logging for debugging"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot_integration.log')
        ]
    )

def test_message_processing():
    """Test the new message processing capabilities"""
    print("Testing Enhanced Message Processing")
    print("=" * 50)
    
    try:
        from bot_core.message_handler import MessageProcessor, SafeMessage
        
        processor = MessageProcessor()
        
        # Test cases that should work
        good_test_cases = [
            "Hello world!",
            {"text": "Hello world!"},
            {"content": "Hello world!"},
            {"role": "user", "text": "Hello world!"}
        ]
        
        print("\n1. Testing valid inputs:")
        for i, test_case in enumerate(good_test_cases):
            try:
                result = processor.safe_parse_message(test_case)
                text = processor.safe_get_text(result)
                integrity = processor.validate_text_integrity(text)
                print(f"   Test {i+1}: ✓ '{text}' (integrity: {integrity})")
            except Exception as e:
                print(f"   Test {i+1}: ✗ Error: {e}")
        
        # Test cases that were problematic before
        problematic_test_cases = [
            "supbitchdoyouactuallyworknow",  # Long string without spaces
            "s u p   b i t c h   d o   y o u   a c t u a l",  # Character-split pattern  
            "2rqy1KLL5D2MMNVDf9WdKXxZLKxOr0SwGvnMV3DAxJTd3DrJkt519I8ps8nIvko",  # Your original problematic input
            "",  # Empty string
            None,  # None input
        ]
        
        print("\n2. Testing previously problematic inputs:")
        for i, test_case in enumerate(problematic_test_cases):
            try:
                result = processor.safe_parse_message(test_case)
                text = processor.safe_get_text(result)
                integrity = processor.validate_text_integrity(text)
                status = "✓" if integrity else "⚠"
                print(f"   Test {i+1}: {status} '{text[:30]}{'...' if len(text) > 30 else ''}' (integrity: {integrity})")
            except Exception as e:
                print(f"   Test {i+1}: ✗ Error: {e}")
        
        return True
        
    except ImportError as e:
        print(f"✗ Failed to import message handler: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        print(traceback.format_exc())
        return False

def test_enhanced_bot_handler():
    """Test the enhanced bot handler"""
    print("\n\nTesting Enhanced Bot Handler")
    print("=" * 50)
    
    try:
        from bot_core.enhanced_bot_handler import EnhancedBotHandler
        from state_models import AppState
        
        handler = EnhancedBotHandler()
        state = AppState()
        
        # Test the specific case that was causing problems
        problematic_inputs = [
            "sup bitch do you actually work now ?",  # Your original message
            "2rqy1KLL5D2MMNVDf9WdKXxZLKxOr0SwGvnMV3DAxJTd3DrJkt519I8ps8nIvko",  # Long problematic string
            {"text": "Hello world"},  # Dict format
        ]
        
        print("\n1. Testing problematic input handling:")
        for i, test_input in enumerate(problematic_inputs):
            try:
                success, result = handler.safe_process_user_input(test_input, state)
                status = "✓" if success else "⚠"
                print(f"   Test {i+1}: {status} Success: {success}")
                print(f"            Result: '{result[:50]}{'...' if len(str(result)) > 50 else ''}'")
                print(f"            Messages in state: {len(state.messages)}")
            except Exception as e:
                print(f"   Test {i+1}: ✗ Error: {e}")
        
        # Test diagnostic info
        print(f"\n2. Diagnostic info:")
        diag = handler.get_diagnostic_info()
        for key, value in diag.items():
            print(f"   {key}: {value}")
        
        return True
        
    except ImportError as e:
        print(f"✗ Failed to import enhanced bot handler: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        print(traceback.format_exc())
        return False

def test_state_validation():
    """Test state validation and repair functions"""
    print("\n\nTesting State Validation and Repair")
    print("=" * 50)
    
    try:
        from state_models import AppState
        from utils.utils import validate_and_repair_state, cleanup_messages
        
        # Create a state with some problematic content
        state = AppState()
        
        # Add some normal messages
        state.add_message("user", "Hello")
        state.add_message("assistant", "Hi there!")
        
        # Add some potentially problematic messages
        state.add_message("user", "2rqy1KLL5D2MMNVDf9WdKXxZLKxOr0SwGvnMV3DAxJTd3DrJkt519I8ps8nIvko")
        
        print(f"1. Initial state: {len(state.messages)} messages")
        
        # Test validation and repair
        is_valid, repairs = validate_and_repair_state(state)
        print(f"2. After validation: Valid: {is_valid}, Repairs: {len(repairs)}")
        if repairs:
            for repair in repairs:
                print(f"   - {repair}")
        
        # Test cleanup
        initial_count = len(state.messages)
        removed = cleanup_messages(state, keep_last_n=10)
        print(f"3. After cleanup: Removed {removed} messages, {len(state.messages)} remaining")
        
        return True
        
    except ImportError as e:
        print(f"✗ Failed to import state validation: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        print(traceback.format_exc())
        return False

def test_original_problematic_case():
    """Test the exact case that was causing problems originally"""
    print("\n\nTesting Original Problematic Case")
    print("=" * 50)
    
    try:
        from bot_core.enhanced_bot_handler import EnhancedBotHandler
        from state_models import AppState
        
        handler = EnhancedBotHandler()
        state = AppState()
        
        # The exact problematic input from your log
        problematic_text = "sup bitch do you actually work now ?"
        
        print(f"Input: '{problematic_text}'")
        print(f"Length: {len(problematic_text)} characters")
        
        # Process it safely
        success, result = handler.safe_process_user_input(problematic_text, state)
        
        print(f"Processing Success: {success}")
        print(f"Result: '{result}'")
        print(f"Messages in state: {len(state.messages)}")
        
        if state.messages:
            last_message = state.messages[-1]
            print(f"Last message text: '{last_message.text}'")
            print(f"Last message role: '{last_message.role}'")
        
        # Verify text integrity
        from bot_core.message_handler import MessageProcessor
        processor = MessageProcessor()
        integrity = processor.validate_text_integrity(result if isinstance(result, str) else "")
        print(f"Text integrity: {integrity}")
        
        return success
        
    except Exception as e:
        print(f"✗ Error testing original case: {e}")
        print(traceback.format_exc())
        return False

def run_comprehensive_test():
    """Run all tests and provide a summary"""
    print("Bot Improvement Integration Test")
    print("=" * 60)
    
    test_results = []
    
    # Run all tests
    test_results.append(("Message Processing", test_message_processing()))
    test_results.append(("Enhanced Bot Handler", test_enhanced_bot_handler()))
    test_results.append(("State Validation", test_state_validation()))
    test_results.append(("Original Problematic Case", test_original_problematic_case()))
    
    # Summary
    print("\n\nTest Summary")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:.<40} {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The bot improvements should resolve your issues.")
        print("\nNext steps:")
        print("1. Update your main bot script to use EnhancedBotHandler")
        print("2. Replace direct message handling with safe_handle_bot_message()")
        print("3. Monitor the bot_integration.log for any issues")
    else:
        print(f"\n⚠️  {total - passed} tests failed. Review the errors above.")
        print("Some integration work may be needed before deployment.")
    
    return passed == total

if __name__ == "__main__":
    setup_logging()
    
    print("Starting Bot Integration Test...")
    print("This will test all the improvements for character splitting and validation issues.")
    print()
    
    try:
        success = run_comprehensive_test()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nCritical error during testing: {e}")
        print(traceback.format_exc())
        sys.exit(1) 