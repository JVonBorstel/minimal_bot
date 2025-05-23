#!/usr/bin/env python3
"""Debug script to check what GitHub tools actually return."""

import asyncio
import logging
from dotenv import load_dotenv, find_dotenv

# Load .env file first
print("🔧 Loading environment configuration...")
dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, verbose=True)

# Import after loading env
from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from tools.github_tools import GitHubTools

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def create_test_app_state() -> AppState:
    """Create a minimal AppState with proper UserProfile for testing."""
    test_user = UserProfile(
        user_id="test_user_github_123",
        display_name="GitHub Test User",
        email="test@example.com",
        assigned_role="ADMIN"
    )
    
    app_state = AppState()
    app_state.current_user = test_user
    return app_state

async def debug_github_tools():
    """Debug what GitHub tools actually return."""
    print("🔍 DEBUGGING GITHUB TOOL RETURNS")
    print("=" * 50)
    
    # Setup
    config = get_config()
    app_state = create_test_app_state()
    github_tools = GitHubTools(config=config, app_state=app_state, testing_mode=False)
    
    print(f"GitHub configured: {bool(github_tools.github_clients)}")
    
    if not github_tools.github_clients:
        print("❌ GitHub not configured")
        return
    
    # Test repositories
    print("\n🔍 Testing list_repositories return type...")
    repos = await github_tools.list_repositories(app_state=app_state)
    print(f"Type: {type(repos)}")
    print(f"Dir: {[attr for attr in dir(repos) if not attr.startswith('_')]}")
    
    if hasattr(repos, '__iter__'):
        print("Is iterable: Yes")
        try:
            repo_list = list(repos)
            print(f"Converted to list length: {len(repo_list)}")
            if repo_list:
                print(f"First item type: {type(repo_list[0])}")
                print(f"First item keys: {repo_list[0].keys() if hasattr(repo_list[0], 'keys') else 'No keys'}")
                print(f"First item sample: {str(repo_list[0])[:200]}...")
        except Exception as e:
            print(f"Error converting to list: {e}")
    else:
        print("Is iterable: No")
    
    # Test code search
    print("\n🔍 Testing search_code return type...")
    results = await github_tools.search_code(app_state=app_state, query="README")
    print(f"Type: {type(results)}")
    print(f"Dir: {[attr for attr in dir(results) if not attr.startswith('_')]}")
    
    if hasattr(results, '__iter__'):
        print("Is iterable: Yes")
        try:
            result_list = list(results)
            print(f"Converted to list length: {len(result_list)}")
            if result_list:
                print(f"First item type: {type(result_list[0])}")
                print(f"First item keys: {result_list[0].keys() if hasattr(result_list[0], 'keys') else 'No keys'}")
                print(f"First item sample: {str(result_list[0])[:200]}...")
        except Exception as e:
            print(f"Error converting to list: {e}")
    else:
        print("Is iterable: No")

if __name__ == "__main__":
    asyncio.run(debug_github_tools()) 