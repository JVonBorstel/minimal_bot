import asyncio
import os
import logging
from dotenv import load_dotenv, find_dotenv

# Assuming minimal_bot structure allows importing these
# from config import get_config, Config # Use get_config for singleton
# from state_models import AppState # AppState might be needed for tool calls
# from tools.github_tools import GitHubTools # The tool class itself
# from user_auth.tool_access import requires_permission, Permission # Needed if decorators are active in test

# --- Mock/Simplified Imports for Testing Standalone ---
# If running this script requires the full bot environment setup,
# these mocks might need to be replaced or the script adjusted.
# For now, assuming we can import core components.

# Let's try importing the real components first.
try:
    # Attempt to load dotenv *before* importing config to ensure env vars are available
    print("Attempting to load .env file...")
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, verbose=True)
        print(f"Loaded .env from: {dotenv_path}")
    else:
        print("No .env file found.")

    from config import get_config
    from state_models import AppState # Assuming AppState is simple enough to instantiate
    from tools.github_tools import GitHubTools
    from user_auth.tool_access import requires_permission, Permission # Check if needed

    # Setup basic logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)

    print("Successfully imported core components.")

except ImportError as e:
    print(f"Failed to import core bot components: {e}")
    print("This script might need adjustments depending on how minimal_bot is structured and if components can be imported standalone.")
    # Exit or raise error if imports fail critically
    exit(1) # Exit if essential imports fail

# --- Helper to create a minimal AppState ---
# Tool methods often require AppState, even if parts aren't used in tests.
def create_minimal_app_state() -> AppState:
    print("Creating minimal AppState...")
    # Instantiate AppState with minimal required data.
    # Adjust if AppState requires more complex initialization or data.
    try:
        # AppState might require a user or conversation context.
        # Creating a dummy context and user ID.
        dummy_user_id = "test_user_123"
        dummy_conversation_id = "test_conversation_123"
        dummy_channel_id = "test_channel_123"

        # Assuming AppState can be instantiated with a context object that has user/conversation info
        # If AppState structure is different, this part needs adjustment.
        # Let's assume it can take a simple dict or object resembling the context.
        # This might be the trickiest part without full context of state_models.py
        
        # Based on state_models.py being Pydantic, maybe it needs explicit fields
        # Let's look at state_models.py again briefly... (mental check from attached file)
        # state_models.py has AppState, UserProfile, WorkflowContext.
        # AppState seems to hold general settings and references to user/conversation state.
        # UserProfile has user_id, email, permissions.
        # WorkflowContext holds state for a specific workflow (like story builder).
        # Tool calls often need the *current user's* AppState or a context derived from it.
        # The @requires_permission decorator takes app_state: AppState as the first argument.
        # This suggests the AppState object should contain user info or a link to it.
        # Let's assume AppState requires at least a user ID or a UserProfile.

        # Let's create a dummy UserProfile and link it to AppState.
        # This is an assumption based on typical bot architectures.
        from state_models import UserProfile, WorkflowContext # Assuming these are importable

        dummy_user_profile = UserProfile(
            user_id=dummy_user_id,
            email="testuser@example.com", # Providing a dummy email
            permissions=[Permission.GITHUB_READ_REPO.value, Permission.GITHUB_SEARCH_CODE.value], # Give test user necessary permissions
            workflow_contexts={dummy_conversation_id: WorkflowContext(workflow_type="dummy")} # Minimal context
        )

        # AppState likely holds the currently active user profile or a way to get it.
        # This requires understanding the AppState structure.
        # Let's assume AppState has a method or attribute to set/get the current user.
        # Or perhaps the tool call itself is passed a context object that AppState is derived from.

        # Re-reading github_tools.py: @requires_permission(Permission.GITHUB_READ_REPO, fallback_permission=Permission.READ_ONLY_ACCESS) async def list_repositories(self, app_state: AppState, ...
        # This confirms AppState is passed directly.
        # We need an AppState instance that has a UserProfile linked, so permission checks work.

        # This is complex without knowing how AppState links to users/sessions.
        # A common pattern is that AppState itself is user-specific or contains references.
        # Let's assume AppState needs a user_id or a UserProfile instance during creation or via a method.

        # Looking at state_models again (mentally): AppState has `user_profiles: Dict[str, UserProfile]`.
        # This means AppState holds *all* user profiles.
        # The tool call must somehow identify the *current* user within that AppState.
        # How does the @requires_permission decorator know which user to check in the AppState?
        # The decorator's source (_tool_decorator.py and user_auth/tool_access.py) is needed for this.

        # Let's make a simplified assumption for testing:
        # We create an AppState with one dummy user profile.
        # The tool_access.py logic *might* use the first profile, or need the user_id passed somehow implicitly.
        # The `app_state` parameter itself doesn't seem to carry the user context directly in this signature.

        # Let's check user_auth/tool_access.py... (cannot read arbitrarily)
        # The decorator must be getting the user somehow. Possible ways:
        # 1. It looks for a 'user_id' or 'user_profile' attribute on the `app_state` object.
        # 2. It uses a global/thread-local context set before the tool call.
        # 3. The tool method signature actually receives more hidden args.

        # Option 1 is most likely given `app_state: AppState`. Let's assume AppState has `current_user: UserProfile` or similar.
        # Or maybe the decorator uses the `user_id` from the `app_state.user_profiles` dictionary based on some implicit context?
        # This is tricky. Let's assume for this test script, we can pass a user ID or set a 'current user' on the AppState instance for the test.

        # Let's create a dummy AppState and manually add a user profile to its dictionary.
        # This bypasses the normal state loading/management but allows testing the decorator's check.
        minimal_app_state = AppState()
        minimal_app_state.user_profiles[dummy_user_id] = dummy_user_profile
        minimal_app_state.current_user = dummy_user_profile

        print(f"Created minimal AppState with user ID: {minimal_app_state.current_user.user_id}")
        return minimal_app_state

    except Exception as e:
        print(f"Failed to create minimal AppState: {e}")
        print("AppState structure or initialization is likely different from assumption.")
        raise # Re-raise to stop execution if state setup fails


async def main():
    print("Starting GitHub tool test script...")
    try:
        # 1. Load Config
        config = get_config()
        print("Config loaded.")

        # 2. Create minimal AppState
        app_state = create_minimal_app_state()
        print("Minimal AppState created.")

        # 3. Initialize GitHub Tools
        # GitHubTools requires config, optional app_state, optional testing_mode
        github_tools = GitHubTools(config=config, app_state=app_state, testing_mode=False)
        print("GitHubTools initialized.")

        # Check if GitHub is configured based on the tool's internal check
        if not hasattr(github_tools, 'github_clients') or not github_tools.github_clients:
             print("\n--- GitHub Tools NOT Configured ---\n")
             print("No GitHub clients were initialized. Please ensure the following are set in your .env file:")
             print("  - GITHUB_ACCOUNT_0_NAME")
             print("  - GITHUB_ACCOUNT_0_TOKEN (with 'repo' scope)")
             print("  - Optionally, GITHUB_ACCOUNT_0_BASE_URL for Enterprise")
             print("Exiting test.")
             return # Exit if tools aren't configured

        print("\n--- Testing list_repositories ---\n")
        try:
            # Call the list_repositories tool
            # It requires app_state as the first argument due to the decorator
            print("Calling github_list_repositories...")
            # The tool signature is: async def list_repositories(self, app_state: AppState, user_or_org: Optional[str] = None, ...
            # We need to pass app_state and any other required/optional args.
            # Let's list repos for the authenticated user (user_or_org=None).
            repos = await github_tools.list_repositories(app_state=app_state, user_or_org=None)
            print(f"Received {len(repos)} repositories (max {github_tools.MAX_LIST_RESULTS}).")
            for i, repo in enumerate(repos):
                print(f"  {i+1}. {repo.get('full_name', 'N/A')}: {repo.get('description', '')[:80]}...") # Print first 80 chars of description
                print(f"     URL: {repo.get('url', 'N/A')}")
                if i >= 4: # Print details for first few, then just names
                     if len(repos) > 5:
                          print("...")
                          print(f"Showing first 5 repos out of {len(repos)}. Total retrieved: {len(repos)} (max {github_tools.MAX_LIST_RESULTS})")
                     break # Don't print all details if list is long

        except Exception as e:
            print(f"Error during list_repositories test: {e}")
            logging.exception("Details of list_repositories error:") # Log full traceback

        print("\n--- Testing search_code ---\n")
        try:
            # Call the search_code tool
            # It requires app_state as the first argument due to the decorator
            # Signature: async def search_code(self, app_state: AppState, query: str, owner: Optional[str] = None, repo: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
            # You'll need to provide a valid owner, repo, and query that exists in your code.
            # Replace these with actual values from your GitHub account for testing.
            test_owner = os.environ.get("GITHUB_TEST_OWNER", "octocat") # Default to octocat if env var not set
            test_repo = os.environ.get("GITHUB_TEST_REPO", "Spoon-Knife") # Default to Spoon-Knife
            test_query = os.environ.get("GITHUB_TEST_QUERY", "test") # Default query "test"

            print(f"Calling github_search_code with query='{test_query}', owner='{test_owner}', repo='{test_repo}'")
            # Ensure you replace test_owner, test_repo, test_query with values relevant to your configured account and repos.
            # Or, ideally, set GITHUB_TEST_OWNER, GITHUB_TEST_REPO, GITHUB_TEST_QUERY environment variables.
            # For a user's own private repo, omit owner and repo, and the tool might search across accessible repos (if implemented that way).
            # The tool signature implies owner/repo are optional, but testing with them is good.
            # Let's test searching within a specific repo using the test env vars.

            code_results = await github_tools.search_code(
                 app_state=app_state,
                 query=test_query, # e.g., "def authenticate"
                 owner=test_owner, # e.g., "myusername"
                 repo=test_repo    # e.g., "my-private-repo"
            )
            print(f"Received {len(code_results)} code search results (max {github_tools.MAX_SEARCH_RESULTS}).")
            for i, result in enumerate(code_results):
                print(f"  {i+1}. {result.get('path', 'N/A')} in {result.get('repository', 'N/A')}")
                print(f"     URL: {result.get('url', 'N/A')}")
                if i >= 2: # Print details for first few
                    if len(code_results) > 3:
                         print("...")
                         print(f"Showing first 3 results out of {len(code_results)}. Total retrieved: {len(code_results)} (max {github_tools.MAX_SEARCH_RESULTS})")
                    break # Don't print all details if list is long

        except Exception as e:
            print(f"Error during search_code test: {e}")
            logging.exception("Details of search_code error:") # Log full traceback


    except Exception as e:
        print(f"An unexpected error occurred during test execution: {e}")
        logging.exception("Details of unexpected error:") # Log full traceback

    print("\n--- GitHub Tool Test Script Finished ---\n")


if __name__ == "__main__":
    # GitHub API calls are async when using asyncio.to_thread in the tool
    asyncio.run(main()) 