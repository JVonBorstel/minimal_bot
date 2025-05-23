#!/usr/bin/env python3
"""
Quick real-world test of all tools to verify they're working after fixes.
Run this to test all tools without starting the full bot server.
"""

import asyncio
import logging
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import after path setup
from config import get_config
from tools.tool_executor import ToolExecutor
from state_models import AppState, UserProfile

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

async def test_all_tools():
    """Test all configured tools to ensure they're working."""
    log.info("🚀 Starting comprehensive tool testing...")
    
    try:
        # Load config
        config = get_config()
        log.info("✅ Config loaded successfully")
        
        # Initialize tool executor
        tool_executor = ToolExecutor(config)
        log.info("✅ Tool executor initialized successfully")
        
        # Create mock app state
        app_state = AppState()
        app_state.current_user = UserProfile(
            user_id="test_user",
            email="jvonborstel@take3tech.com",  # Use the configured email
            display_name="Test User"
        )
        
        # Get available tools
        available_tools = tool_executor.get_available_tool_names()
        log.info(f"📋 Available tools: {', '.join(available_tools)}")
        
        # Test results
        results = {}
        
        # Test Jira tools
        if "jira_get_issues_by_user" in available_tools:
            log.info("🎫 Testing Jira tools...")
            try:
                jira_result = await tool_executor.execute_tool(
                    "jira_get_issues_by_user",
                    {"user_email": "jvonborstel@take3tech.com"},
                    app_state=app_state
                )
                results["jira"] = {
                    "status": "SUCCESS" if jira_result and not isinstance(jira_result, dict) or jira_result.get("status") != "ERROR" else "ERROR",
                    "result": jira_result
                }
                log.info(f"✅ Jira: {results['jira']['status']}")
            except Exception as e:
                results["jira"] = {"status": "ERROR", "error": str(e)}
                log.error(f"❌ Jira failed: {e}")
        
        # Test GitHub tools
        if "github_list_repositories" in available_tools:
            log.info("📁 Testing GitHub tools...")
            try:
                github_result = await tool_executor.execute_tool(
                    "github_list_repositories",
                    {},
                    app_state=app_state
                )
                results["github"] = {
                    "status": "SUCCESS" if github_result and not isinstance(github_result, dict) or github_result.get("status") != "ERROR" else "ERROR",
                    "result": github_result
                }
                log.info(f"✅ GitHub: {results['github']['status']}")
            except Exception as e:
                results["github"] = {"status": "ERROR", "error": str(e)}
                log.error(f"❌ GitHub failed: {e}")
        
        # Test Greptile tools
        if "greptile_query_codebase" in available_tools:
            log.info("🔍 Testing Greptile tools...")
            try:
                greptile_result = await tool_executor.execute_tool(
                    "greptile_query_codebase",
                    {
                        "query": "What is the main purpose of this repository?",
                        "github_repo_url": "https://github.com/microsoft/vscode"
                    },
                    app_state=app_state
                )
                results["greptile"] = {
                    "status": "SUCCESS" if greptile_result and greptile_result.get("status") == "SUCCESS" else "ERROR",
                    "result": greptile_result
                }
                log.info(f"✅ Greptile: {results['greptile']['status']}")
            except Exception as e:
                results["greptile"] = {"status": "ERROR", "error": str(e)}
                log.error(f"❌ Greptile failed: {e}")
        
        # Test Perplexity tools
        if "perplexity_web_search" in available_tools:
            log.info("🌐 Testing Perplexity tools...")
            try:
                perplexity_result = await tool_executor.execute_tool(
                    "perplexity_web_search",
                    {"query": "What is Python 3.12?"},
                    app_state=app_state
                )
                results["perplexity"] = {
                    "status": "SUCCESS" if perplexity_result and perplexity_result.get("answer") else "ERROR",
                    "result": perplexity_result
                }
                log.info(f"✅ Perplexity: {results['perplexity']['status']}")
            except Exception as e:
                results["perplexity"] = {"status": "ERROR", "error": str(e)}
                log.error(f"❌ Perplexity failed: {e}")
        
        # Print summary
        log.info("\n" + "="*50)
        log.info("📊 TOOL TEST SUMMARY:")
        log.info("="*50)
        
        success_count = 0
        total_count = 0
        
        for tool_name, result in results.items():
            total_count += 1
            status = result["status"]
            if status == "SUCCESS":
                success_count += 1
                log.info(f"✅ {tool_name.upper()}: WORKING")
            else:
                log.error(f"❌ {tool_name.upper()}: FAILED - {result.get('error', 'Unknown error')}")
        
        log.info(f"\n🎯 FINAL RESULT: {success_count}/{total_count} tools working")
        
        if success_count == total_count:
            log.info("🎉 ALL TOOLS ARE WORKING! You're good to go!")
            return True
        else:
            log.warning(f"⚠️  {total_count - success_count} tools need attention")
            return False
            
    except Exception as e:
        log.error(f"💥 Critical error during testing: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = asyncio.run(test_all_tools())
    sys.exit(0 if success else 1) 