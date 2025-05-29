#!/usr/bin/env python3
"""
Enhanced Agent Demo Script

This script demonstrates how to enable and test the enhanced agent functionality.
The enhanced mode provides intelligent planning and detailed progress feedback for complex requests.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def show_current_status():
    """Show the current enhanced agent configuration."""
    from core_logic.agent_loop import _is_enhanced_mode_enabled, _should_use_enhanced_planning
    
    print("🔧 Enhanced Agent Configuration")
    print("=" * 50)
    print(f"Enhanced Mode Enabled: {_is_enhanced_mode_enabled()}")
    print(f"Environment Variable ENABLE_ENHANCED_AGENT: {os.getenv('ENABLE_ENHANCED_AGENT', 'Not Set')}")
    print()
    
    # Test planning logic with sample queries
    test_queries = [
        ("Show me my Jira tickets", "Simple query"),
        ("Please analyze my Jira tickets step by step and create a comprehensive report", "Complex query"),
        ("Help me plan my sprint strategy with detailed analysis", "Complex query"),
        ("What's the weather?", "Simple query")
    ]
    
    print("📋 Query Planning Analysis")
    print("=" * 50)
    for query, expected in test_queries:
        would_use_enhanced = _should_use_enhanced_planning(query)
        status = "✅" if would_use_enhanced else "⚪"
        print(f"{status} {expected}: '{query[:50]}{'...' if len(query) > 50 else ''}'")
        print(f"   → Would use enhanced planning: {would_use_enhanced}")
        print()

def test_component_loading():
    """Test loading the enhanced components."""
    print("🧪 Component Loading Test")
    print("=" * 50)
    
    try:
        from core_logic.agent_loop import _load_enhanced_components
        enhanced_controller_class, response_composer_class = _load_enhanced_components()
        
        if enhanced_controller_class and response_composer_class:
            print("✅ Enhanced components loaded successfully")
            print(f"   Controller: {enhanced_controller_class.__name__}")
            print(f"   Composer: {response_composer_class.__name__}")
            
            # Test instantiation with mock dependencies
            from unittest.mock import Mock
            
            mock_config = Mock()
            mock_config.get_system_prompt.return_value = "Test system prompt"
            
            mock_tool_executor = Mock()
            mock_tool_executor.get_available_tool_definitions.return_value = []
            
            try:
                controller = enhanced_controller_class(mock_tool_executor, mock_config)
                composer = response_composer_class(mock_config)
                print("✅ Component instantiation successful")
                print(f"   Controller instance: {type(controller).__name__}")
                print(f"   Composer instance: {type(composer).__name__}")
            except Exception as e:
                print(f"❌ Component instantiation failed: {e}")
        else:
            print("❌ Enhanced components not available")
            
    except Exception as e:
        print(f"❌ Component loading failed: {e}")
    
    print()

def demonstrate_usage():
    """Show how to enable enhanced mode."""
    print("🚀 How to Enable Enhanced Mode")
    print("=" * 50)
    print("1. Set environment variable:")
    print("   export ENABLE_ENHANCED_AGENT=true")
    print()
    print("2. Or in Windows PowerShell:")
    print("   $env:ENABLE_ENHANCED_AGENT='true'")
    print()
    print("3. Or programmatically:")
    print("   import os")
    print("   os.environ['ENABLE_ENHANCED_AGENT'] = 'true'")
    print()
    print("📝 Enhanced Mode Features:")
    print("• Intelligent analysis of complex requests")
    print("• Step-by-step execution planning")
    print("• Real-time progress tracking with progress bars")
    print("• Smart error recovery and fallback")
    print("• Context-aware response composition")
    print()
    print("🔍 Enhanced Mode Triggers:")
    print("• Queries containing: 'step by step', 'detailed analysis', 'comprehensive'")
    print("• Requests for: 'analyze my', 'create report', 'plan my'")
    print("• Complex workflow patterns")
    print()

def enable_enhanced_mode_demo():
    """Temporarily enable enhanced mode and show the difference."""
    print("🧠 Enhanced Mode Demo")
    print("=" * 50)
    
    # Save current state
    original_value = os.getenv('ENABLE_ENHANCED_AGENT')
    
    try:
        # Enable enhanced mode
        os.environ['ENABLE_ENHANCED_AGENT'] = 'true'
        print("✅ Enhanced mode temporarily enabled")
        
        from core_logic.agent_loop import _is_enhanced_mode_enabled, _should_use_enhanced_planning
        
        print(f"   Enhanced mode active: {_is_enhanced_mode_enabled()}")
        
        # Test with a complex query
        complex_query = "Please analyze my Jira tickets step by step and create a comprehensive report"
        print(f"   Complex query would use enhanced planning: {_should_use_enhanced_planning(complex_query)}")
        
        # Test component loading
        print("   Enhanced components available:", end=" ")
        try:
            from core_logic.agent_loop import _load_enhanced_components
            controller_class, composer_class = _load_enhanced_components()
            print("✅ Yes" if controller_class and composer_class else "❌ No")
        except Exception:
            print("❌ No")
        
    finally:
        # Restore original state
        if original_value is None:
            os.environ.pop('ENABLE_ENHANCED_AGENT', None)
        else:
            os.environ['ENABLE_ENHANCED_AGENT'] = original_value

def main():
    """Run the enhanced agent demonstration."""
    print("🤖 Enhanced Agent Demonstration")
    print("=" * 60)
    print()
    
    show_current_status()
    test_component_loading()
    demonstrate_usage()
    enable_enhanced_mode_demo()
    
    print("\n" + "=" * 60)
    print("✨ Enhanced agent integration is ready!")
    print("   • Fully backward compatible")
    print("   • Optional enhancement via environment variable")
    print("   • No parallel systems or code bloat")
    print("   • Clean fallback to original functionality")
    print("=" * 60)

if __name__ == "__main__":
    main() 