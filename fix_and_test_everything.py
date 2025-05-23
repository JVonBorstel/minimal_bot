#!/usr/bin/env python3
"""
Comprehensive fix and test script for the minimal bot.
This script will:
1. Kill any running bot processes
2. Test all tools individually 
3. Run a workflow test
4. Provide a summary of what's working
"""

import asyncio
import logging
import sys
import os
import subprocess
import time

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

def kill_existing_processes():
    """Kill any existing bot processes."""
    log.info("🧹 Cleaning up existing bot processes...")
    
    ports_to_check = [3978, 8501, 3979, 8080]
    killed_any = False
    
    for port in ports_to_check:
        try:
            if sys.platform == "win32":
                # Windows
                result = subprocess.run(
                    f'netstat -ano | findstr :{port}',
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    pids = set()
                    
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            if pid.isdigit():
                                pids.add(pid)
                    
                    for pid in pids:
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', pid], check=True)
                            log.info(f"✅ Killed process {pid} on port {port}")
                            killed_any = True
                        except subprocess.CalledProcessError:
                            pass
            else:
                # Unix/Linux/Mac
                try:
                    result = subprocess.run(
                        ['lsof', '-ti', f':{port}'],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.stdout:
                        pids = result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid and pid.isdigit():
                                try:
                                    subprocess.run(['kill', '-9', pid], check=True)
                                    log.info(f"✅ Killed process {pid} on port {port}")
                                    killed_any = True
                                except subprocess.CalledProcessError:
                                    pass
                except FileNotFoundError:
                    pass
                    
        except Exception:
            pass
    
    if killed_any:
        log.info("⏱️  Waiting 3 seconds for cleanup...")
        time.sleep(3)
    
    return killed_any

async def test_individual_tools():
    """Test each tool individually."""
    log.info("🔧 Testing individual tools...")
    
    try:
        from config import get_config
        from tools.tool_executor import ToolExecutor
        from state_models import AppState, UserProfile
        
        config = get_config()
        tool_executor = ToolExecutor(config)
        
        # Create test app state
        app_state = AppState()
        app_state.current_user = UserProfile(
            user_id="test_user",
            email="jvonborstel@take3tech.com",
            display_name="Test User"
        )
        
        available_tools = tool_executor.get_available_tool_names()
        log.info(f"📋 Available tools: {len(available_tools)} found")
        
        results = {}
        
        # Test Jira (this was the main issue)
        if "jira_get_issues_by_user" in available_tools:
            log.info("🎫 Testing Jira tools...")
            try:
                result = await tool_executor.execute_tool(
                    "jira_get_issues_by_user",
                    {"user_email": "jvonborstel@take3tech.com"},
                    app_state=app_state
                )
                if isinstance(result, list) or (isinstance(result, dict) and result.get("status") != "ERROR"):
                    results["jira"] = "✅ WORKING"
                    log.info("✅ Jira: Working correctly!")
                else:
                    results["jira"] = f"❌ ERROR: {result}"
                    log.error(f"❌ Jira failed: {result}")
            except Exception as e:
                results["jira"] = f"❌ EXCEPTION: {str(e)}"
                log.error(f"❌ Jira exception: {e}")
        
        # Test GitHub
        if "github_list_repositories" in available_tools:
            log.info("📁 Testing GitHub tools...")
            try:
                result = await tool_executor.execute_tool(
                    "github_list_repositories",
                    {},
                    app_state=app_state
                )
                if isinstance(result, list) or (isinstance(result, dict) and result.get("status") != "ERROR"):
                    results["github"] = "✅ WORKING"
                    log.info("✅ GitHub: Working correctly!")
                else:
                    results["github"] = f"❌ ERROR: {result}"
                    log.error(f"❌ GitHub failed: {result}")
            except Exception as e:
                results["github"] = f"❌ EXCEPTION: {str(e)}"
                log.error(f"❌ GitHub exception: {e}")
        
        # Test Greptile
        if "greptile_query_codebase" in available_tools:
            log.info("🔍 Testing Greptile tools...")
            try:
                result = await tool_executor.execute_tool(
                    "greptile_query_codebase",
                    {
                        "query": "What is this repository about?",
                        "github_repo_url": "https://github.com/microsoft/vscode"
                    },
                    app_state=app_state
                )
                if isinstance(result, dict) and result.get("status") == "SUCCESS":
                    results["greptile"] = "✅ WORKING"
                    log.info("✅ Greptile: Working correctly!")
                else:
                    results["greptile"] = f"❌ ERROR: {result}"
                    log.error(f"❌ Greptile failed: {result}")
            except Exception as e:
                results["greptile"] = f"❌ EXCEPTION: {str(e)}"
                log.error(f"❌ Greptile exception: {e}")
        
        # Test Perplexity
        if "perplexity_web_search" in available_tools:
            log.info("🌐 Testing Perplexity tools...")
            try:
                result = await tool_executor.execute_tool(
                    "perplexity_web_search",
                    {"query": "What is Python?"},
                    app_state=app_state
                )
                if isinstance(result, dict) and result.get("answer"):
                    results["perplexity"] = "✅ WORKING"
                    log.info("✅ Perplexity: Working correctly!")
                else:
                    results["perplexity"] = f"❌ ERROR: {result}"
                    log.error(f"❌ Perplexity failed: {result}")
            except Exception as e:
                results["perplexity"] = f"❌ EXCEPTION: {str(e)}"
                log.error(f"❌ Perplexity exception: {e}")
        
        return results
        
    except Exception as e:
        log.error(f"💥 Critical error during tool testing: {e}", exc_info=True)
        return {"critical_error": str(e)}

async def test_workflow():
    """Test the workflow orchestrator."""
    log.info("🔄 Testing workflow orchestrator...")
    
    try:
        from config import get_config
        from tools.tool_executor import ToolExecutor
        from core_logic.workflow_orchestrator import WorkflowOrchestrator, detect_workflow_intent
        from state_models import AppState, UserProfile
        
        config = get_config()
        tool_executor = ToolExecutor(config)
        orchestrator = WorkflowOrchestrator(tool_executor, config)
        
        # Test workflow intent detection
        test_queries = [
            "list my jira tickets",
            "show my github repos", 
            "list both my repos and tickets"
        ]
        
        intent_results = {}
        for query in test_queries:
            intent = detect_workflow_intent(query)
            intent_results[query] = intent
            log.info(f"🎯 '{query}' -> {intent}")
        
        # Test actual workflow execution
        app_state = AppState()
        app_state.current_user = UserProfile(
            user_id="test_user",
            email="jvonborstel@take3tech.com",
            display_name="Test User"
        )
        app_state.messages = [{"role": "user", "content": "list my jira tickets"}]
        
        try:
            workflow_result = await orchestrator.execute_workflow(
                "list_jira_tickets",
                app_state
            )
            if workflow_result.success:
                log.info("✅ Workflow execution: Working correctly!")
                return {"workflow": "✅ WORKING", "intents": intent_results}
            else:
                log.error(f"❌ Workflow execution failed: {workflow_result.final_synthesis}")
                return {"workflow": f"❌ FAILED: {workflow_result.final_synthesis}", "intents": intent_results}
        except Exception as e:
            log.error(f"❌ Workflow execution exception: {e}")
            return {"workflow": f"❌ EXCEPTION: {str(e)}", "intents": intent_results}
            
    except Exception as e:
        log.error(f"💥 Critical error during workflow testing: {e}", exc_info=True)
        return {"workflow_critical_error": str(e)}

async def main():
    """Main function."""
    log.info("🚀 Starting comprehensive bot fix and test...")
    
    # Step 1: Kill existing processes
    killed_processes = kill_existing_processes()
    if killed_processes:
        log.info("✅ Cleaned up existing processes")
    
    # Step 2: Test individual tools
    tool_results = await test_individual_tools()
    
    # Step 3: Test workflows
    workflow_results = await test_workflow()
    
    # Step 4: Summary
    log.info("\n" + "="*60)
    log.info("📊 COMPREHENSIVE TEST RESULTS")
    log.info("="*60)
    
    # Tool results
    log.info("\n🔧 INDIVIDUAL TOOLS:")
    working_tools = 0
    total_tools = 0
    
    for tool_name, result in tool_results.items():
        if tool_name != "critical_error":
            total_tools += 1
            if "✅ WORKING" in result:
                working_tools += 1
            log.info(f"  {tool_name.upper()}: {result}")
    
    # Workflow results
    log.info("\n🔄 WORKFLOWS:")
    if "workflow" in workflow_results:
        log.info(f"  EXECUTION: {workflow_results['workflow']}")
    if "intents" in workflow_results:
        log.info("  INTENT DETECTION:")
        for query, intent in workflow_results["intents"].items():
            log.info(f"    '{query}' -> {intent}")
    
    # Final verdict
    log.info("\n" + "="*60)
    if working_tools == total_tools and "✅ WORKING" in workflow_results.get("workflow", ""):
        log.info("🎉 ALL SYSTEMS WORKING! Your bot is ready to go!")
        log.info("💡 You can now start the bot with: python app.py")
        return True
    else:
        log.warning(f"⚠️  Some issues found: {total_tools - working_tools}/{total_tools} tools need attention")
        if "❌" in workflow_results.get("workflow", ""):
            log.warning("⚠️  Workflow execution has issues")
        log.info("🔧 Check the error messages above for details")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 