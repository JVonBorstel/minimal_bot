#!/usr/bin/env python3
"""Test GitHub tools with real API calls - CORRECTED VERSION."""

import asyncio
import logging
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
        repos = await github_tools.list_repositories(app_state=app_state)
        
        print(f"✅ SUCCESS: Retrieved {len(repos)} repositories")
        
        if repos:
            print("\n📊 Repository Details:")
            for i, repo in enumerate(repos[:5]):  # Show first 5
                print(f"  {i+1}. {repo.get('full_name', 'N/A')}")
                print(f"     Description: {repo.get('description', 'No description')[:80]}...")
                print(f"     Private: {repo.get('private', 'N/A')}")
                print(f"     Language: {repo.get('language', 'N/A')}")
                print(f"     Stars: {repo.get('stars', 0)}")
                print(f"     URL: {repo.get('url', 'N/A')}")
                print()
            
            if len(repos) > 5:
                print(f"     ... and {len(repos) - 5} more repositories")
        else:
            print("⚠️ No repositories found")
            
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
        results = await github_tools.search_code(
            app_state=app_state,
            query=test_query
        )
        
        print(f"✅ SUCCESS: Found {len(results)} code search results")
        
        if results:
            print("\n📊 Search Results:")
            for i, result in enumerate(results[:3]):  # Show first 3
                print(f"  {i+1}. {result.get('path', 'N/A')} in {result.get('repository', 'N/A')}")
                print(f"     URL: {result.get('url', 'N/A')}")
                print()
            
            if len(results) > 3:
                print(f"     ... and {len(results) - 3} more results")
        else:
            print("⚠️ No code search results found")
            
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        log.exception("Full error details:")
        return False

async def main():
    """Main test function."""
    print("🚀 GITHUB TOOLS VALIDATION TEST")
    print("=" * 60)
    
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
        print("=" * 60)
        
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