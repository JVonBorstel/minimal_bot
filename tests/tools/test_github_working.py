#!/usr/bin/env python3
"""Working GitHub tools test script - handles structured responses correctly."""

import asyncio
import logging
import json
from dotenv import load_dotenv, find_dotenv

# Load .env file first
print("🔧 Loading environment configuration...")
dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, verbose=True)
    print(f"✅ Loaded .env from: {dotenv_path}")
else:
    print("⚠️ No .env file found")

# Import after loading env
from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from user_auth.permissions import Permission
from tools.github_tools import GitHubTools

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def create_test_app_state() -> AppState:
    """Create a minimal AppState with proper UserProfile for testing."""
    print("🔧 Creating test AppState...")
    
    # Create UserProfile with all required fields
    test_user = UserProfile(
        user_id="test_user_github_123",
        display_name="GitHub Test User",
        email="test@example.com",
        assigned_role="ADMIN"  # Give admin permissions for testing
    )
    
    # Create AppState and set current user
    app_state = AppState()
    app_state.current_user = test_user
    
    print(f"✅ Created AppState with user: {test_user.display_name} ({test_user.user_id})")
    return app_state

async def test_github_list_repositories(github_tools: GitHubTools, app_state: AppState):
    """Test the github_list_repositories tool."""
    print("\n📋 TESTING: github_list_repositories")
    print("-" * 50)
    
    try:
        print("🔍 Calling github_list_repositories...")
        response = await github_tools.list_repositories(app_state=app_state)
        
        # Handle structured response
        if isinstance(response, dict) and 'data' in response:
            status = response.get('status', 'UNKNOWN')
            execution_time = response.get('execution_time_ms', 0)
            repos = response['data']
            
            print(f"✅ SUCCESS: Status={status}, Time={execution_time}ms")
            print(f"📊 Retrieved {len(repos)} repositories")
            
            if repos:
                print("\n📄 Repository Details:")
                for i, repo in enumerate(repos[:5]):  # Show first 5
                    print(f"  {i+1}. {repo.get('full_name', 'N/A')}")
                    print(f"     Description: {repo.get('description', 'No description') or 'No description'}")
                    print(f"     Private: {repo.get('private', 'N/A')}")
                    print(f"     Language: {repo.get('language', 'N/A') or 'Not specified'}")
                    print(f"     Stars: {repo.get('stars', 0)}")
                    print(f"     URL: {repo.get('url', 'N/A')}")
                    print(f"     Last Updated: {repo.get('updated_at', 'N/A')}")
                    print()
                
                if len(repos) > 5:
                    print(f"     ... and {len(repos) - 5} more repositories")
                    
                print("🎯 REAL DATA EXAMPLES:")
                print(f"  - Total repos found: {len(repos)}")
                print(f"  - First repo: {repos[0].get('full_name', 'N/A')}")
                print(f"  - Languages used: {set(r.get('language') for r in repos if r.get('language'))}")
                
            else:
                print("⚠️ No repositories found")
        else:
            print(f"❌ Unexpected response format: {type(response)}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        log.exception("Full error details:")
        return False

async def test_github_search_code(github_tools: GitHubTools, app_state: AppState):
    """Test the github_search_code tool."""
    print("\n🔍 TESTING: github_search_code")
    print("-" * 50)
    
    # Test with a simple, common query
    test_query = "README"
    
    try:
        print(f"🔍 Searching for code containing: '{test_query}'")
        response = await github_tools.search_code(
            app_state=app_state,
            query=test_query
        )
        
        # Handle structured response
        if isinstance(response, dict) and 'data' in response:
            status = response.get('status', 'UNKNOWN')
            execution_time = response.get('execution_time_ms', 0)
            results = response['data']
            
            print(f"✅ SUCCESS: Status={status}, Time={execution_time}ms")
            print(f"📊 Found {len(results)} code search results")
            
            if results:
                print("\n📄 Search Results:")
                for i, result in enumerate(results[:3]):  # Show first 3
                    print(f"  {i+1}. {result.get('path', 'N/A')} in {result.get('repository', 'N/A')}")
                    print(f"     File: {result.get('name', 'N/A')}")
                    print(f"     URL: {result.get('url', 'N/A')}")
                    print(f"     Git URL: {result.get('git_url', 'N/A')}")
                    print()
                
                if len(results) > 3:
                    print(f"     ... and {len(results) - 3} more results")
                    
                print("🎯 REAL DATA EXAMPLES:")
                print(f"  - Total results found: {len(results)}")
                print(f"  - First result: {results[0].get('path', 'N/A')} in {results[0].get('repository', 'N/A')}")
                print(f"  - Repositories found: {set(r.get('repository') for r in results if r.get('repository'))}")
                
            else:
                print("⚠️ No code search results found")
        else:
            print(f"❌ Unexpected response format: {type(response)}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        log.exception("Full error details:")
        return False

async def main():
    """Main test function."""
    print("🚀 GITHUB TOOLS VALIDATION TEST - WORKING VERSION")
    print("=" * 70)
    
    try:
        # Load config
        print("🔧 Loading configuration...")
        config = get_config()
        print("✅ Configuration loaded")
        
        # Create test app state
        app_state = create_test_app_state()
        
        # Initialize GitHub tools
        print("🔧 Initializing GitHub tools...")
        github_tools = GitHubTools(config=config, app_state=app_state, testing_mode=False)
        
        # Check if GitHub is configured
        if not github_tools.github_clients:
            print("\n❌ GITHUB NOT CONFIGURED")
            print("Please ensure the following are set:")
            print("  - GitHub account configured in settings")
            print("  - Valid GitHub token with 'repo' scope")
            return False
        
        print(f"✅ GitHub tools initialized with {len(github_tools.github_clients)} account(s)")
        print(f"   Active account: {github_tools.active_account_name}")
        print(f"   Authenticated as: {github_tools.authenticated_user_login}")
        
        # Run tests
        test_results = []
        
        # Test 1: List repositories
        result1 = await test_github_list_repositories(github_tools, app_state)
        test_results.append(("github_list_repositories", result1))
        
        # Test 2: Search code
        result2 = await test_github_search_code(github_tools, app_state)
        test_results.append(("github_search_code", result2))
        
        # Summary
        print("\n📊 TEST SUMMARY")
        print("=" * 70)
        
        passed = 0
        total = len(test_results)
        
        for tool_name, success in test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"  {tool_name}: {status}")
            if success:
                passed += 1
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL GITHUB TOOLS WORKING!")
            print("\n✅ VALIDATION COMPLETE - GITHUB TOOLS PROVEN TO WORK WITH REAL DATA")
            return True
        else:
            print(f"⚠️ {total - passed} tests failed")
            return False
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        log.exception("Full error details:")
        return False

if __name__ == "__main__":
    asyncio.run(main()) 