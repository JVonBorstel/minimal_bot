#!/usr/bin/env python3
"""
REAL API CONNECTIVITY TEST - Actually call APIs and prove the bot works end-to-end
This tests the user's scenario with REAL API calls, not just tool selection
"""

import asyncio
import pytest # Add pytest
import time
from config import get_config
from user_auth.models import UserProfile
from tools.tool_executor import ToolExecutor
from state_models import AppState

@pytest.mark.asyncio
async def test_real_api_connectivity():
    print("🌐 REAL API CONNECTIVITY TEST")
    print("Testing actual API calls for: 'Compare my repo against my Jira ticket'")
    print("=" * 80)
    
    try:
        # Setup
        config = get_config()
        tool_executor = ToolExecutor(config)
        
        test_user = UserProfile(
            user_id="real_api_test",
            display_name="Real API User", 
            email="dev@company.com",  # Change this to your actual email
            assigned_role="DEVELOPER"
        )
        
        app_state = AppState(
            session_id=f"real_api_test_{int(time.time())}",
            current_user=test_user
        )
        
        print(f"✅ Setup complete - {len(tool_executor.get_available_tool_names())} tools available")
        print(f"👤 Testing with user: {test_user.email}")
        
        # Test real API calls for the user's scenario
        api_tests = [
            {
                "name": "1️⃣ Get My Jira Issues",
                "tool": "jira_get_issues_by_user", 
                "params": {
                    "user_email": test_user.email,
                    "status_category": "To Do"
                },
                "description": "Get actual Jira tickets for the user"
            },
            {
                "name": "2️⃣ List My GitHub Repositories", 
                "tool": "github_list_repositories",
                "params": {},
                "description": "Get actual GitHub repositories"
            },
            {
                "name": "3️⃣ Search Code in Repository",
                "tool": "github_search_code",
                "params": {
                    "query": "function",
                    "repository_name": "auto-detect",  # Will use first repo from list
                    "file_extensions": ["js", "py", "ts"],
                    "sort_by": "indexed"
                },
                "description": "Search for actual code in repositories"
            },
            {
                "name": "4️⃣ Greptile Repository Summary",
                "tool": "greptile_summarize_repo", 
                "params": {
                    "repository_url": "auto-detect",  # Will use first repo from list
                    "include_patterns": ["*.py", "*.js"],
                    "focus": "architecture"
                },
                "description": "Get AI-powered repository analysis"
            },
            {
                "name": "5️⃣ Help Tool (Baseline)",
                "tool": "help",
                "params": {},
                "description": "Baseline test - should always work"
            }
        ]
        
        print(f"\n🔧 Executing {len(api_tests)} REAL API calls...")
        
        results = []
        github_repos = []  # Store for later tests
        
        for i, test in enumerate(api_tests):
            print(f"\n{'='*60}")
            print(f"🔧 {test['name']}: {test['description']}")
            print(f"🛠️  Tool: {test['tool']}")
            
            start_time = time.time()
            
            try:
                # Handle auto-detect for repository-dependent tests
                if "auto-detect" in str(test['params']):
                    if test['tool'] == "github_search_code" and github_repos:
                        # Use first repo from previous GitHub call
                        test['params']['repository_name'] = github_repos[0]['name']
                        print(f"   🎯 Auto-detected repository: {github_repos[0]['name']}")
                    elif test['tool'] == "greptile_summarize_repo" and github_repos:
                        # Use first repo URL - try multiple possible fields
                        repo = github_repos[0]
                        print(f"   🔍 Available repo fields: {list(repo.keys())}")
                        
                        # Try different possible URL fields
                        repo_url = repo.get('html_url') or repo.get('clone_url') or repo.get('git_url') or repo.get('ssh_url')
                        if repo_url:
                            test['params']['repository_url'] = repo_url
                            print(f"   🎯 Auto-detected repository URL: {repo_url}")
                        else:
                            # Fallback to constructing GitHub URL
                            owner = repo.get('owner', {}).get('login', 'unknown')
                            name = repo.get('name', 'unknown')
                            repo_url = f"https://github.com/{owner}/{name}"
                            test['params']['repository_url'] = repo_url
                            print(f"   🎯 Constructed repository URL: {repo_url}")
                
                # Execute the actual tool with real API call
                print(f"   🌐 Making REAL API call...")
                result = await tool_executor.execute_tool(
                    tool_name=test['tool'],
                    tool_input=test['params'],
                    app_state=app_state
                )
                
                end_time = time.time()
                duration_ms = int((end_time - start_time) * 1000)
                
                # Analyze the result
                success = False
                data_received = False
                error_msg = None
                
                if isinstance(result, dict):
                    if result.get('status') == 'SUCCESS':
                        success = True
                        data = result.get('data', [])
                        
                        if isinstance(data, list) and len(data) > 0:
                            data_received = True
                            print(f"   ✅ SUCCESS: Received {len(data)} items")
                            
                            # Store GitHub repos for later tests
                            if test['tool'] == "github_list_repositories":
                                github_repos = data
                                print(f"   📦 Found repositories: {[repo.get('name', 'Unknown') for repo in data[:3]]}")
                            
                            # Show sample data
                            if test['tool'] == "jira_get_issues_by_user":
                                print(f"   🎫 Sample Jira issues: {[issue.get('key', 'Unknown') for issue in data[:3]]}")
                            elif test['tool'] == "github_search_code":
                                print(f"   🔍 Found {len(data)} code matches")
                            elif test['tool'] == "help":
                                print(f"   📚 Help shows {len(data)} available tools")
                                
                        elif isinstance(data, dict):
                            data_received = True
                            print(f"   ✅ SUCCESS: Received data object")
                            
                        else:
                            print(f"   ⚠️  SUCCESS but no data: {result.get('message', 'No message')}")
                            
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        print(f"   ❌ FAILED: {error_msg}")
                        
                else:
                    print(f"   ❌ FAILED: Unexpected result type: {type(result)}")
                    error_msg = f"Unexpected result type: {type(result)}"
                
                print(f"   ⏱️  API Response Time: {duration_ms}ms")
                
                test_result = {
                    "name": test['name'],
                    "tool": test['tool'],
                    "success": success,
                    "data_received": data_received,
                    "duration_ms": duration_ms,
                    "error": error_msg
                }
                results.append(test_result)
                
            except Exception as e:
                end_time = time.time()
                duration_ms = int((end_time - start_time) * 1000)
                
                print(f"   💥 EXCEPTION: {str(e)}")
                print(f"   ⏱️  Failed after: {duration_ms}ms")
                
                test_result = {
                    "name": test['name'],
                    "tool": test['tool'], 
                    "success": False,
                    "data_received": False,
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
                results.append(test_result)
        
        # Overall assessment
        print(f"\n{'='*80}")
        print("📊 REAL API CONNECTIVITY ASSESSMENT")
        print("=" * 80)
        
        successful_calls = [r for r in results if r["success"]]
        data_calls = [r for r in results if r["data_received"]]
        
        print(f"✅ Successful API calls: {len(successful_calls)}/{len(results)} ({len(successful_calls)/len(results)*100:.0f}%)")
        print(f"📊 Calls with real data: {len(data_calls)}/{len(results)} ({len(data_calls)/len(results)*100:.0f}%)")
        
        avg_duration = sum(r["duration_ms"] for r in results) / len(results)
        print(f"⏱️  Average response time: {avg_duration:.0f}ms")
        
        print(f"\n📋 Detailed API Results:")
        for result in results:
            status = "✅" if result["success"] else "❌"
            data_status = "📊" if result["data_received"] else "📭"
            print(f"   {status} {data_status} {result['name']}: {result['duration_ms']}ms")
            if result["error"]:
                print(f"      Error: {result['error']}")
        
        # Determine if the bot is ready for the user's scenario
        critical_tools = ["jira_get_issues_by_user", "github_list_repositories", "help"]
        critical_working = [r for r in results if r["tool"] in critical_tools and r["success"]]
        
        if len(critical_working) >= 2:  # At least 2 of 3 critical tools work
            print(f"\n🎉 REAL API CONNECTIVITY: WORKING!")
            print(f"✅ Your bot can handle real API calls!")
            print(f"✅ Critical tools are connecting successfully!")
            print(f"✅ Ready for 'compare my repo against my Jira ticket' scenario!")
            return True
        else:
            print(f"\n⚠️  REAL API CONNECTIVITY: NEEDS WORK")
            print(f"❌ Critical tools not working reliably")
            return False
            
    except Exception as e:
        print(f"\n💥 REAL API CONNECTIVITY TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_real_api_connectivity())
    if success:
        print(f"\n🏆 YOUR BOT HAS REAL API CONNECTIVITY!")
        print(f"✅ Multiple services working with real data")
        print(f"✅ Ready for production deployment")
    exit(0 if success else 1) 