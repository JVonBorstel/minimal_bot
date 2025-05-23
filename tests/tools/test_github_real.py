#!/usr/bin/env python3
"""Test GitHub tools with real API calls - CORRECTED VERSION."""

import asyncio
import logging
import uuid # Added for unique issue titles
from dotenv import load_dotenv, find_dotenv

import pytest # Add pytest import
import pytest_asyncio # Add this import at the top of the file if not already present

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

@pytest.fixture(scope="module")
def config():
    """Provides the application configuration."""
    print("🔧 (Fixture) Loading configuration...")
    cfg = get_config()
    print("✅ (Fixture) Configuration loaded")
    return cfg

@pytest.fixture(scope="module")
def app_state(config) -> AppState: # Add config dependency
    """Provides a test AppState instance."""
    print("🔧 (Fixture) Creating test AppState...")
    # Create UserProfile with all required fields
    test_user = UserProfile(
        user_id="test_user_github_fixture", # Changed user_id for clarity
        display_name="GitHub Test User (Fixture)",
        email="test_fixture@example.com",
        assigned_role="ADMIN"  # Give admin permissions for testing
    )
    # Create AppState and set current user
    _app_state = AppState(current_user=test_user) # Pass current_user at init
    # _app_state.current_user = test_user # Original way
    
    print(f"✅ (Fixture) Created AppState with user: {test_user.display_name} ({test_user.user_id})")
    return _app_state

@pytest_asyncio.fixture(scope="function") # Changed to pytest_asyncio.fixture
async def github_tools(config, app_state): # Made async, added config and app_state
    """Provides an initialized GitHubTools instance."""
    print("🔧 (Fixture) Initializing GitHub tools...")
    # Initialize GitHub tools
    # Pass app_state directly to GitHubTools constructor if it accepts it,
    # or ensure it's set correctly if GitHubTools relies on a global/contextual app_state.
    # Based on main(), it seems GitHubTools takes app_state in constructor.
    _tools = GitHubTools(config=config, app_state=app_state, testing_mode=False) # Pass app_state
    
    if not _tools.github_clients:
        pytest.skip("GITHUB NOT CONFIGURED. Skipping GitHub real tests.")
        
    print(f"✅ (Fixture) GitHub tools initialized with {len(_tools.github_clients)} account(s)")
    print(f"   (Fixture) Active account: {_tools.active_account_name}")
    print(f"   (Fixture) Authenticated as: {_tools.authenticated_user_login}")
    return _tools

# This local helper function is fine, or its logic can be moved into the app_state fixture
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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
@pytest.mark.real_api
async def test_get_specific_public_repo_details_real(github_tools: GitHubTools, app_state: AppState):
    """Test fetching details for a specific public repository using real API calls."""
    print("\n📋 TESTING: get_specific_public_repo_details_real")
    print("-" * 50)

    # The github_tools fixture (tests/tools/test_github_real.py:67-68) already handles skipping 
    # if GitHub credentials are not configured. No need for an explicit skip here.

    repo_owner = "pytest-dev"  # A well-known public repository owner
    repo_name = "pytest"       # A well-known public repository

    try:
        print(f"🔍 Fetching details for repository: {repo_owner}/{repo_name}")
        # Assuming the method in GitHubTools is get_repo_details and it requires app_state.
        # This is consistent with other tool methods.
        repo_details = await github_tools._get_repo(app_state=app_state, owner=repo_owner, repo=repo_name)
        
        assert repo_details is not None, "API call to get_repo_details returned None"
        print(f"✅ SUCCESS: Retrieved details for {repo_details.full_name}")
        
        assert repo_details.name == repo_name, \
            f"Expected repo name '{repo_name}', got '{repo_details.name}'"
        assert repo_details.owner.login == repo_owner, \
            f"Expected owner login '{repo_owner}', got '{repo_details.owner.login}'"
        assert hasattr(repo_details, "html_url"), "Repository details should include 'html_url'"
        assert hasattr(repo_details, "description"), "Repository details should include 'description'"
        assert repo_details.visibility == "public", "Expected repository to be public"

        print(f"   Name: {repo_details.name}")
        print(f"   Owner: {repo_details.owner.login}")
        print(f"   URL: {repo_details.html_url}")
        print(f"   Description: {str(repo_details.description)[:100]}...")
        print(f"   Visibility: {repo_details.visibility}")

    except Exception as e:
        print(f"❌ ERROR in test_get_specific_public_repo_details_real: {e}")
        # 'log' is defined globally in this file (tests/tools/test_github_real.py:29)
        log.exception("Full error details for test_get_specific_public_repo_details_real:")
        pytest.fail(f"Real API call to get_repo_details for {repo_owner}/{repo_name} failed: {e}")

@pytest.mark.asyncio
@pytest.mark.real_api
async def test_real_github_issue_create_comment_delete(github_tools: GitHubTools, app_state: AppState, config): # Added config fixture
    """
    Tests the full workflow of creating an issue, adding a comment,
    verifying them, and then closing the issue.
    """
    print("\n📋 TESTING: test_real_github_issue_create_comment_delete")
    print("-" * 70)

    # Conditional skipping is handled by the github_tools fixture

    repo_owner = "JVonBorstel"
    repo_name = "Augie-s-fieldtest"
    
    issue_title = f"Test Issue {uuid.uuid4()}"
    issue_body = "This is a test issue created by an automated test."
    comment_body = "This is a test comment."
    
    created_issue_number = None

    try:
        # 1. Create Issue
        print(f"🔧 Creating issue '{issue_title}' in {repo_owner}/{repo_name}...")
        created_issue_details = await github_tools.create_issue(
            app_state=app_state,
            owner=repo_owner,
            repo=repo_name,
            title=issue_title,
            body=issue_body
        )
        assert created_issue_details is not None, "Issue creation failed, returned None."
        assert "number" in created_issue_details, "Issue creation response missing 'number'."
        created_issue_number = created_issue_details["number"]
        print(f"✅ Issue #{created_issue_number} created successfully: {created_issue_details.get('url')}")
        assert created_issue_details["title"] == issue_title
        assert created_issue_details["body"] == issue_body # PyGithub might return None if body is empty string, ensure it matches

        # 2. Verify Issue (Optional but Recommended)
        print(f"🔍 Verifying issue #{created_issue_number}...")
        fetched_issue = await github_tools.get_issue_by_number(
            app_state=app_state,
            owner=repo_owner,
            repo=repo_name,
            issue_number=created_issue_number
        )
        assert fetched_issue is not None, "Failed to fetch the newly created issue."
        assert fetched_issue["title"] == issue_title, f"Fetched issue title mismatch. Expected '{issue_title}', got '{fetched_issue['title']}'"
        assert fetched_issue["body"] == issue_body, f"Fetched issue body mismatch. Expected '{issue_body}', got '{fetched_issue['body']}'"
        assert fetched_issue["state"] == "open", f"Fetched issue state should be 'open', got '{fetched_issue['state']}'"
        print(f"✅ Issue #{created_issue_number} verified successfully.")

        # 3. Create Comment
        print(f"💬 Adding comment to issue #{created_issue_number}...")
        created_comment_details = await github_tools.create_comment_on_issue(
            app_state=app_state,
            owner=repo_owner,
            repo=repo_name,
            issue_number=created_issue_number,
            body=comment_body
        )
        assert created_comment_details is not None, "Comment creation failed, returned None."
        assert "id" in created_comment_details, "Comment creation response missing 'id'."
        comment_id = created_comment_details["id"]
        print(f"✅ Comment ID {comment_id} added successfully: {created_comment_details.get('url')}")
        assert created_comment_details["body"] == comment_body

        # 4. Verify Comment (Optional but Recommended)
        print(f"🔍 Verifying comment on issue #{created_issue_number}...")
        issue_comments = await github_tools.get_issue_comments(
            app_state=app_state,
            owner=repo_owner,
            repo=repo_name,
            issue_number=created_issue_number
        )
        assert any(comment["id"] == comment_id and comment["body"] == comment_body for comment in issue_comments), \
            f"Test comment (ID: {comment_id}) not found or body mismatch in issue comments."
        print(f"✅ Comment ID {comment_id} verified successfully.")

    except Exception as e:
        print(f"❌ ERROR during test_real_github_issue_create_comment_delete: {e}")
        log.exception("Full error details for test_real_github_issue_create_comment_delete:")
        pytest.fail(f"Test failed during main operations: {e}")
    finally:
        # 5. Clean Up (Close Issue)
        if created_issue_number is not None:
            print(f"🧹 Cleaning up: Closing issue #{created_issue_number} in {repo_owner}/{repo_name}...")
            try:
                closed_issue_details = await github_tools.update_issue_state(
                    app_state=app_state,
                    owner=repo_owner,
                    repo=repo_name,
                    issue_number=created_issue_number,
                    state="closed"
                )
                assert closed_issue_details is not None, "Closing issue returned None."
                assert closed_issue_details["state"] == "closed", \
                    f"Issue #{created_issue_number} was not closed. Current state: {closed_issue_details.get('state')}."
                print(f"✅ Issue #{created_issue_number} closed successfully.")
            except Exception as e_cleanup:
                print(f"❌ ERROR during cleanup (closing issue #{created_issue_number}): {e_cleanup}")
                log.exception(f"Full error details for cleanup of issue #{created_issue_number}:")
                # Don't fail the test here if the main part passed, but log it prominently.
                # If the main test already failed, this just adds to the log.
                pytest.warning(f"Cleanup failed for issue #{created_issue_number}: {e_cleanup}")

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