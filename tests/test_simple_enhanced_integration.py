"""
Simple test to validate enhanced agent components work correctly.
"""

import sys
import os

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

def test_imports():
    """Test that we can import the enhanced components."""
    try:
        from core_logic.enhanced_agent_controller import EnhancedAgentController
        from core_logic.intelligent_response_composer import IntelligentResponseComposer
        from config import Config
        from tools.tool_executor import ToolExecutor
        print("✅ All imports successful")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        assert False, f"Import failed: {e}"

def test_basic_instantiation():
    """Test basic instantiation of enhanced components."""
    try:
        from core_logic.enhanced_agent_controller import EnhancedAgentController
        from core_logic.intelligent_response_composer import IntelligentResponseComposer
        from unittest.mock import Mock
        
        # Create mock dependencies
        mock_config = Mock()
        mock_config.get_system_prompt.return_value = "Test prompt"
        
        mock_tool_executor = Mock()
        mock_tool_executor.get_available_tool_definitions.return_value = []
        
        # Test instantiation
        controller = EnhancedAgentController(mock_tool_executor, mock_config)
        composer = IntelligentResponseComposer(mock_config)
        
        print("✅ Basic instantiation successful")
        print(f"Controller: {controller}")
        print(f"Composer: {composer}")
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        assert False, f"Instantiation failed: {e}"

if __name__ == "__main__":
    print("🧪 Testing Enhanced Agent Integration...")
    
    success = True
    success &= test_imports()
    success &= test_basic_instantiation()
    
    if success:
        print("\n🎉 All basic tests passed!")
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1) 