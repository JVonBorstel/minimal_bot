"""
Test script for demonstrating graceful error handling in the bot
"""
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
from datetime import datetime
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_core.conversation_context_manager import ConversationContextManager, ErrorCategory, ConversationState
from bot_core.my_bot import MyBot
from state_models import AppState
from config import Config

class TestGracefulErrorHandling(unittest.TestCase):
    """Test cases for graceful error handling"""
    
    def setUp(self):
        """Set up test environment"""
        self.context_manager = ConversationContextManager()
    
    def test_frustration_detection(self):
        """Test that frustration patterns are detected correctly"""
        # Test normal message
        context = self.context_manager.track_user_message("Hello, how are you?")
        self.assertEqual(context["frustration_level"], 0.0)
        self.assertFalse(context["should_acknowledge_difficulty"])
        
        # Test frustrated message
        context = self.context_manager.track_user_message("This is not working at all")
        self.assertGreater(context["frustration_level"], 0)
        self.assertTrue(context["should_acknowledge_difficulty"])
        self.assertIn("not working", context["detected_patterns"])
        
        # Test repeated message (strong frustration signal)
        context = self.context_manager.track_user_message("Hello, how are you?")
        self.assertIn("repeated_message", context["detected_patterns"])
        
    def test_error_categorization(self):
        """Test that errors are properly categorized"""
        # Test tool failure
        msg = self.context_manager.handle_error(
            Exception("Tool execution failed"),
            ErrorCategory.TOOL_FAILURE,
            {"user_message": "get my github issues"}
        )
        self.assertIn("alternative approach", msg.lower())
        
        # Test API timeout
        msg = self.context_manager.handle_error(
            Exception("Request timed out"),
            ErrorCategory.API_TIMEOUT,
            {"user_message": "fetch data"}
        )
        self.assertIn("longer than expected", msg.lower())
        
    def test_duplicate_response_prevention(self):
        """Test that duplicate responses are prevented"""
        response = "Here's your information"
        
        # First response should be allowed
        self.assertTrue(self.context_manager.track_bot_response(response))
        
        # Duplicate should be blocked
        self.assertFalse(self.context_manager.track_bot_response(response))
        
        # Different response should be allowed
        self.assertTrue(self.context_manager.track_bot_response("Different information"))
        
    def test_conversation_state_tracking(self):
        """Test conversation state transitions"""
        # Initially healthy
        self.assertEqual(self.context_manager.conversation_state, ConversationState.HEALTHY)
        
        # Add some errors
        for i in range(3):
            self.context_manager.handle_error(
                Exception(f"Error {i}"),
                ErrorCategory.TECHNICAL,
                {}
            )
        
        # Should degrade
        self.assertIn(self.context_manager.conversation_state, 
                     [ConversationState.STRUGGLING, ConversationState.DEGRADED])
        
    def test_high_frustration_responses(self):
        """Test that high frustration generates empathetic responses"""
        # Simulate high frustration
        for msg in ["not working", "broken again", "still failing", "come on!"]:
            self.context_manager.track_user_message(msg)
        
        # Error should generate high empathy response
        error_msg = self.context_manager.handle_error(
            Exception("Another error"),
            ErrorCategory.TECHNICAL,
            {"user_message": "why doesn't this work"}
        )
        
        # Should contain empathetic language
        self.assertTrue(any(word in error_msg.lower() for word in 
                          ["understand", "apologize", "frustration", "hear you"]))
        
    def test_recovery_suggestions(self):
        """Test recovery action suggestions"""
        # No suggestion when healthy
        self.assertIsNone(self.context_manager.suggest_recovery_action())
        
        # Simulate degraded state with frustration
        for msg in ["error", "not working", "broken"]:
            self.context_manager.track_user_message(msg)
            self.context_manager.handle_error(Exception("test"), ErrorCategory.TECHNICAL, {})
        
        # Should suggest recovery
        recovery = self.context_manager.suggest_recovery_action()
        self.assertIsNotNone(recovery)
        self.assertIn("different", recovery.lower())

class TestBotIntegration(unittest.TestCase):
    """Test bot integration with graceful error handling"""
    
    @patch('bot_core.my_bot.get_logger')
    @patch('bot_core.my_bot.setup_logging')
    async def test_bot_with_context_manager(self, mock_setup_logging, mock_get_logger):
        """Test that bot properly uses context manager"""
        # Mock logger
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Create bot with mocked dependencies
        config = MagicMock(spec=Config)
        config.STATE_DB_PATH = ":memory:"
        config.settings.memory_type = "sqlite"
        config.settings.log_detailed_appstate = False
        
        # Create bot (note: this will use the actual ConversationContextManager)
        bot = MyBot(config)
        
        # Verify context manager was initialized
        self.assertIsNotNone(bot.context_manager)
        self.assertIsInstance(bot.context_manager, ConversationContextManager)
        
    def test_error_message_variety(self):
        """Test that error messages vary and don't repeat"""
        context_manager = ConversationContextManager()
        messages = set()
        
        # Generate multiple error messages
        for i in range(10):
            msg = context_manager.handle_error(
                Exception(f"Error {i}"),
                ErrorCategory.TOOL_FAILURE,
                {"user_message": "test"}
            )
            messages.add(msg)
        
        # Should have variety (at least 3 different messages)
        self.assertGreaterEqual(len(messages), 3)

def run_async_test(coro):
    """Helper to run async tests"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)

if __name__ == "__main__":
    print("Testing Graceful Error Handling System")
    print("=" * 50)
    
    # Run basic tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGracefulErrorHandling)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Run integration tests
    print("\n" + "=" * 50)
    print("Testing Bot Integration")
    print("=" * 50)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBotIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Demo the context manager
    print("\n" + "=" * 50)
    print("Demo: Conversation Flow")
    print("=" * 50)
    
    cm = ConversationContextManager()
    
    # Simulate a conversation
    messages = [
        "Hello, can you help me?",
        "Get my github issues",
        "It's not working",
        "This is broken",
        "Why doesn't anything work?",
        "Come on, this is frustrating!"
    ]
    
    for msg in messages:
        print(f"\nUser: {msg}")
        context = cm.track_user_message(msg)
        print(f"Frustration Level: {context['frustration_level']:.2f}")
        print(f"Conversation State: {context['conversation_state'].value}")
        
        # Simulate an error after some messages
        if "github" in msg.lower() or "work" in msg.lower():
            error_msg = cm.handle_error(
                Exception("Simulated error"),
                ErrorCategory.TOOL_FAILURE,
                {"user_message": msg}
            )
            print(f"Bot: {error_msg}")
            
        # Check for recovery suggestions
        recovery = cm.suggest_recovery_action()
        if recovery:
            print(f"Bot (Recovery): {recovery}")
    
    print("\n" + "=" * 50)
    print("Conversation Summary:")
    summary = cm.get_conversation_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}") 