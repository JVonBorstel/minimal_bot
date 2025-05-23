#!/usr/bin/env python3
"""Debug script to examine the dict structure returned by GitHub tools."""

import asyncio
import json
from dotenv import load_dotenv, find_dotenv

# Load .env file first
dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, verbose=True)

# Import after loading env
from config import get_config
from state_models import AppState
from user_auth.models import UserProfile
from tools.github_tools import GitHubTools

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

async def examine_dict_structure():
    """Examine the actual dict structure returned by GitHub tools."""
    print("🔍 EXAMINING GITHUB TOOL DICT STRUCTURE")
    print("=" * 50)
    
    # Setup
    config = get_config()
    app_state = create_test_app_state()
    github_tools = GitHubTools(config=config, app_state=app_state, testing_mode=False)
    
    if not github_tools.github_clients:
        print("❌ GitHub not configured")
        return
    
    # Test repositories
    print("\n📋 Examining list_repositories result...")
    repos_result = await github_tools.list_repositories(app_state=app_state)
    
    print(f"Result type: {type(repos_result)}")
    print(f"Result keys: {list(repos_result.keys())}")
    
    for key, value in repos_result.items():
        print(f"\nKey: '{key}'")
        print(f"Value type: {type(value)}")
        
        if isinstance(value, (list, tuple)):
            print(f"Value length: {len(value)}")
            if value:
                print(f"First item type: {type(value[0])}")
                if hasattr(value[0], 'keys'):
                    print(f"First item keys: {list(value[0].keys())}")
                print(f"First item sample: {str(value[0])[:200]}...")
        elif isinstance(value, str):
            print(f"String value: {value[:100]}...")
        else:
            print(f"Value: {str(value)[:200]}...")
    
    # Test code search
    print("\n\n🔍 Examining search_code result...")
    search_result = await github_tools.search_code(app_state=app_state, query="README")
    
    print(f"Result type: {type(search_result)}")
    print(f"Result keys: {list(search_result.keys())}")
    
    for key, value in search_result.items():
        print(f"\nKey: '{key}'")
        print(f"Value type: {type(value)}")
        
        if isinstance(value, (list, tuple)):
            print(f"Value length: {len(value)}")
            if value:
                print(f"First item type: {type(value[0])}")
                if hasattr(value[0], 'keys'):
                    print(f"First item keys: {list(value[0].keys())}")
                print(f"First item sample: {str(value[0])[:200]}...")
        elif isinstance(value, str):
            print(f"String value: {value[:100]}...")
        else:
            print(f"Value: {str(value)[:200]}...")

if __name__ == "__main__":
    asyncio.run(examine_dict_structure()) 