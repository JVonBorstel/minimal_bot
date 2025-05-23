#!/usr/bin/env python3
"""
🔍 GREPTILE TOOLS VALIDATION SCRIPT
=====================================

This script performs REAL API testing of all Greptile tools to prove they work.
Following the successful pattern from Jira validation.

WHAT WE'RE TESTING:
1. greptile_query_codebase - AI questions about repositories
2. greptile_search_code - Semantic code search
3. greptile_summarize_repo - Repository architecture overview

CRITICAL: This uses REAL Greptile API calls, not mocks!
"""

import asyncio
import sys
import json
import requests
from typing import Dict, Any, Optional
import traceback
from datetime import datetime
import pytest # Add pytest

# Add our modules to the path
sys.path.append('.')

try:
    from tools.tool_executor import ToolExecutor
    from config import get_config
    from state_models import AppState
    from tools.greptile_tools import GreptileTools
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
    print("Make sure you're running this from the minimal_bot directory")
    sys.exit(1)

def print_banner(text: str):
    """Print a formatted banner."""
    print(f"\n{'='*60}")
    print(f"🔍 {text}")
    print(f"{'='*60}")

def print_test_header(test_name: str, test_num: int):
    """Print a test header."""
    print(f"\n📋 TEST {test_num}: {test_name}")
    print(f"{'-'*50}")

def print_result(result: Dict[str, Any], truncate: bool = True):
    """Print formatted result."""
    if truncate and isinstance(result, dict):
        # Truncate long strings for readability
        result_copy = {}
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 200:
                result_copy[key] = value[:200] + "... [TRUNCATED]"
            elif isinstance(value, list) and len(value) > 3:
                result_copy[key] = value[:3] + ["... [TRUNCATED]"]
            else:
                result_copy[key] = value
        result = result_copy
    
    print(f"📊 Result: {json.dumps(result, indent=2, default=str)}")

def _run_direct_api_access_check(config) -> bool:
    """Checks direct API access to Greptile before testing tools."""
    print_test_header("Direct Greptile API Access Check", 0)
    
    api_key = config.get_env_value('GREPTILE_API_KEY')
    api_url = config.get_env_value('GREPTILE_API_URL') or "https://api.greptile.com/v2"
    
    if not api_key:
        print("❌ No API key found!")
        return False
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Test health endpoint
    try:
        print(f"🌐 Testing API endpoint: {api_url}/health")
        response = requests.get(f"{api_url}/health", headers=headers, timeout=10)
        print(f"📡 Response Status: {response.status_code}")
        print(f"📡 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("✅ Direct API access successful!")
            try:
                data = response.json()
                print(f"📊 Health data: {json.dumps(data, indent=2)}")
            except:
                print(f"📊 Health response text: {response.text}")
            return True
        else:
            print(f"❌ API returned status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Direct API test failed: {e}")
        traceback.print_exc()
        return False

@pytest.mark.asyncio
async def test_greptile_tools():
    """Test all Greptile tools with real API calls."""
    
    print_banner("GREPTILE TOOLS REAL API VALIDATION")
    print(f"🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize configuration and executor
    try:
        config = get_config()
        executor = ToolExecutor(config)
        app_state = AppState()
        
        print(f"✅ Configuration loaded")
        print(f"✅ ToolExecutor initialized")
        print(f"✅ AppState created")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        traceback.print_exc()
        return False
    
    # Test direct API access first
    if not _run_direct_api_access_check(config):
        print("❌ Direct API access failed. Cannot proceed with tool tests.")
        return False
    
    # Test repositories to use
    test_repos = [
        "https://github.com/takethree/loanmaps",  # Default repo from config
        "https://github.com/microsoft/vscode",   # Popular public repo
        "https://github.com/facebook/react"      # Another popular repo
    ]
    
    # Track test results
    results = {
        "query_codebase": False,
        "search_code": False, 
        "summarize_repo": False
    }
    
    try:
        # TEST 1: Query Codebase
        print_test_header("greptile_query_codebase", 1)
        
        query = "What is the main purpose of this repository and how is the code organized?"
        repo_url = test_repos[0]  # Use default repo
        
        print(f"🔍 Query: '{query}'")
        print(f"🏗️ Repository: {repo_url}")
        
        try:
            result = await executor.execute_tool(
                "greptile_query_codebase",
                {
                    "query": query,
                    "github_repo_url": repo_url
                },
                app_state
            )
            
            print_result(result)
            
            if result and isinstance(result, dict):
                status = result.get("status") or result.get("data", {}).get("status")
                if status == "SUCCESS" and result.get("answer"):
                    print("✅ Query codebase test PASSED!")
                    results["query_codebase"] = True
                else:
                    print(f"❌ Query codebase test FAILED: {result}")
            else:
                print(f"❌ Query codebase test FAILED: Invalid result format")
                
        except Exception as e:
            print(f"❌ Query codebase test FAILED with exception: {e}")
            traceback.print_exc()
        
        # TEST 2: Search Code
        print_test_header("greptile_search_code", 2)
        
        search_query = "authentication"
        repo_url = test_repos[1]  # Use vscode repo
        
        print(f"🔍 Search Query: '{search_query}'")
        print(f"🏗️ Repository: {repo_url}")
        
        try:
            result = await executor.execute_tool(
                "greptile_search_code",
                {
                    "query": search_query,
                    "github_repo_url": repo_url,
                    "limit": 5
                },
                app_state
            )
            
            print_result(result)
            
            if result and isinstance(result, dict):
                status = result.get("status")
                results_list = result.get("results", [])
                if status == "SUCCESS" and isinstance(results_list, list):
                    print(f"✅ Search code test PASSED! Found {len(results_list)} results")
                    results["search_code"] = True
                else:
                    print(f"❌ Search code test FAILED: {result}")
            else:
                print(f"❌ Search code test FAILED: Invalid result format")
                
        except Exception as e:
            print(f"❌ Search code test FAILED with exception: {e}")
            traceback.print_exc()
        
        # TEST 3: Summarize Repository
        print_test_header("greptile_summarize_repo", 3)
        
        repo_url = test_repos[2]  # Use React repo
        
        print(f"🏗️ Repository: {repo_url}")
        
        try:
            result = await executor.execute_tool(
                "greptile_summarize_repo",
                {
                    "repo_url": repo_url
                },
                app_state
            )
            
            print_result(result)
            
            if result and isinstance(result, dict):
                status = result.get("status")
                summary = result.get("summary") or result.get("answer")
                if status == "SUCCESS" and summary:
                    print("✅ Summarize repo test PASSED!")
                    results["summarize_repo"] = True
                else:
                    print(f"❌ Summarize repo test FAILED: {result}")
            else:
                print(f"❌ Summarize repo test FAILED: Invalid result format")
                
        except Exception as e:
            print(f"❌ Summarize repo test FAILED with exception: {e}")
            traceback.print_exc()
        
        # TEST 4: Health Check
        print_test_header("Greptile Health Check", 4)
        
        try:
            greptile_tools = GreptileTools(config)
            health_result = greptile_tools.health_check()
            
            print_result(health_result, truncate=False)
            
            if health_result.get("status") == "OK":
                print("✅ Health check PASSED!")
            else:
                print(f"❌ Health check FAILED: {health_result}")
                
        except Exception as e:
            print(f"❌ Health check FAILED with exception: {e}")
            traceback.print_exc()
        
        # FINAL RESULTS
        print_banner("GREPTILE VALIDATION RESULTS")
        
        passed_tests = sum(results.values())
        total_tests = len(results)
        
        print(f"📊 Test Results Summary:")
        for tool_name, passed in results.items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"   {tool_name}: {status}")
        
        print(f"\n📈 Overall Score: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests >= 2:  # At least 2/3 tools must work
            print("🎉 GREPTILE TOOLS VALIDATION: SUCCESS!")
            print("✅ Greptile tools are working with real API data!")
            return True
        else:
            print("💥 GREPTILE TOOLS VALIDATION: FAILED!")
            print("❌ Too many tools failed. Check API configuration and Greptile service status.")
            return False
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR during testing: {e}")
        traceback.print_exc()
        return False

def main():
    """Main test runner."""
    try:
        success = asyncio.run(test_greptile_tools())
        
        if success:
            print(f"\n🎯 RESULT: GREPTILE TOOLS ARE WORKING!")
            print(f"📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            sys.exit(0)
        else:
            print(f"\n💥 RESULT: GREPTILE TOOLS FAILED VALIDATION!")
            print(f"📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 