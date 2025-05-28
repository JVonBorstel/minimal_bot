#!/usr/bin/env python3
"""
Direct test of the Jira tool to demonstrate it works, using mocks.
This bypasses the full bot framework and tests just the Jira tool logic.
"""

import asyncio
import sys
import os
from typing import List, Dict, Any, Optional

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Add the project root to Python path to allow for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from config import get_config, Config
from tools.jira_tools import JiraTools
from state_models import AppState, UserProfile
from jira.exceptions import JIRAError # For simulating Jira errors.
from jira import JIRA # Import JIRA for spec

# Helper to create a mock Jira issue
def create_mock_jira_issue(key: str, summary: str, status_name: str, project_key: str = "TEST", project_name: str = "Test Project", issue_type_name: str = "Story", assignee_name: Optional[str] = None, reporter_name: Optional[str] = None, updated: str = "2023-01-01T12:00:00.000+0000", priority: Optional[str] = None, duedate: Optional[str] = None, labels: Optional[List[str]] = None) -> MagicMock:
    issue = MagicMock()
    issue.key = key
    issue.id = f"{key}-id"
    issue.permalink.return_value = f"https://mocked.jira/browse/{key}"
    
    issue.fields = MagicMock()
    issue.fields.summary = summary
    
    issue.fields.status = MagicMock()
    issue.fields.status.name = status_name
    
    issue.fields.project = MagicMock()
    issue.fields.project.key = project_key
    issue.fields.project.name = project_name
    
    issue.fields.issuetype = MagicMock()
    issue.fields.issuetype.name = issue_type_name
    
    if assignee_name:
        issue.fields.assignee = MagicMock()
        issue.fields.assignee.displayName = assignee_name
    else:
        issue.fields.assignee = None
        
    if reporter_name:
        issue.fields.reporter = MagicMock()
        issue.fields.reporter.displayName = reporter_name
    else:
        issue.fields.reporter = None
        
    issue.fields.updated = updated
    
    if priority:
        issue.fields.priority = MagicMock()
        issue.fields.priority.name = priority
    else:
        issue.fields.priority = None # Ensure it's explicitly None if not provided
        
    issue.fields.duedate = duedate
    issue.fields.labels = labels if labels is not None else []
    
    return issue

@pytest.fixture
def config_fixture() -> Config:
    """Provides a Config instance for tests with mocked Jira credentials for initialization."""
    with patch.object(Config, 'get_env_value', side_effect=lambda key, default=None: {
        'JIRA_API_URL': "https://mocked.jira.com",
        'JIRA_API_EMAIL': "mock_shared_email@example.com",
        'JIRA_API_TOKEN': "mock_shared_token",
        # JIRA_DEFAULT_PROJECT_KEY is no longer mocked here globally in the fixture for all tests.
        # Tests that rely on a specific default will mock it themselves.
        'DEFAULT_API_TIMEOUT_SECONDS': 10,
        'DEFAULT_API_MAX_RETRIES': 3,
    }.get(key, default if default is not None else 'mock_default_config_val')):
        cfg = Config()
        return cfg

@pytest.fixture
def mock_app_state_no_personal_creds() -> AppState:
    """Provides a mocked AppState without personal Jira credentials."""
    user_profile = UserProfile(user_id="test_user_no_creds", display_name="Test User No Creds", email="no_creds@example.com", profile_data={})
    return AppState(current_user=user_profile)

@pytest.fixture
def mock_app_state_with_personal_creds() -> AppState:
    """Provides a mocked AppState with personal Jira credentials."""
    user_profile = UserProfile(user_id="test_user_with_creds", display_name="Test User With Creds", email="personal_creds_user@example.com", profile_data={
        'personal_credentials': {
            'jira_email': 'personal_mock@example.com',
            'jira_token': 'personal_mock_token_is_long_enough_to_be_considered_unscoped_xxxxxxxxxxxxxxxxxxxx'
        }
    })
    return AppState(current_user=user_profile)

# This will be the mock for the JIRA client instance, not the class
@pytest.fixture
def mock_jira_instance() -> MagicMock:
    # Using spec=JIRA to ensure the mock adheres to the JIRA class interface
    client = MagicMock(spec=JIRA)
    client.server_info.return_value = {'baseUrl': 'https://mocked.jira.com', 'version': '9.0.0', 'serverTitle': 'Mocked Jira Instance'}
    client.search_issues.return_value = [] # Default to no issues
    client.create_issue.return_value = create_mock_jira_issue("NEW-1", "New mock issue", "To Do")
    client.search_assignable_users_for_projects.return_value = []
    client.fields.return_value = []
    return client

@pytest.mark.asyncio
async def test_health_check_ok(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing Jira Health Check (OK - Shared Client)")
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance) as mock_create_client_method:
        jira_tools = JiraTools(config_fixture)
        health_result = jira_tools.health_check(app_state=mock_app_state_no_personal_creds)
        assert health_result['status'] == 'OK'
        assert 'Successfully connected to Jira' in health_result['message']
        # Should be called once for the shared client during health check if no client exists yet or if re-creating
        # or if health_check always creates one for test via _create_jira_client (as it is now)
        mock_create_client_method.assert_called_once_with(config_fixture.get_env_value('JIRA_API_EMAIL'), config_fixture.get_env_value('JIRA_API_TOKEN'))
        mock_jira_instance.server_info.assert_called_once()

@pytest.mark.asyncio
async def test_health_check_personal_creds_ok(config_fixture: Config, mock_app_state_with_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing Jira Health Check (OK - Personal Client)")
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance) as mock_create_client_method:
        jira_tools = JiraTools(config_fixture) # Initializes shared client if creds present
        # Reset mock_create_client_method to check calls only related to personal client in health_check
        mock_create_client_method.reset_mock() 

        health_result = jira_tools.health_check(app_state=mock_app_state_with_personal_creds)
        assert health_result['status'] == 'OK'
        personal_creds = mock_app_state_with_personal_creds.current_user.profile_data['personal_credentials']
        # Called once for personal client
        mock_create_client_method.assert_called_once_with(personal_creds['jira_email'], personal_creds['jira_token'])
        mock_jira_instance.server_info.assert_called_once()
        assert "(using personal credentials)" in health_result['message'] 

@pytest.mark.asyncio
async def test_health_check_error(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing Jira Health Check (ERROR)")
    mock_jira_instance.server_info.side_effect = JIRAError(status_code=500, text="Server Error")
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
        jira_tools = JiraTools(config_fixture)
        health_result = jira_tools.health_check(app_state=mock_app_state_no_personal_creds)
        assert health_result['status'] == 'ERROR'
        assert 'Jira API error during health check' in health_result['message']

@pytest.mark.asyncio
async def test_get_issues_by_user_success(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing get_issues_by_user (Success)")
    mock_issues_response = [
        create_mock_jira_issue("TEST-1", "First test issue", "To Do", assignee_name="test_user@example.com"),
        create_mock_jira_issue("TEST-2", "Second test issue", "In Progress", assignee_name="test_user@example.com")
    ]
    mock_jira_instance.search_issues.return_value = mock_issues_response
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
        jira_tools = JiraTools(config_fixture)
        user_email_to_test = "test_user@example.com"
        result = await jira_tools.get_issues_by_user(app_state=mock_app_state_no_personal_creds, user_email=user_email_to_test, status_category="all", max_results=5)
        
        assert isinstance(result, dict)
        assert result.get('status') == 'SUCCESS' # Assuming decorator adds this
        assert 'data' in result
        issues_data = result['data']
        assert len(issues_data) == 2
        assert issues_data[0]['key'] == "TEST-1"
        mock_jira_instance.search_issues.assert_called_once()
        jql_query = mock_jira_instance.search_issues.call_args[0][0]
        assert f'assignee = "{user_email_to_test}"' in jql_query

@pytest.mark.asyncio
async def test_get_issues_by_user_uses_profile_email(config_fixture: Config, mock_app_state_with_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing get_issues_by_user (Uses Profile Email)")
    profile_email = mock_app_state_with_personal_creds.current_user.email
    mock_issues_response = [create_mock_jira_issue("PROF-1", "Profile user issue", "To Do", assignee_name=profile_email)]
    mock_jira_instance.search_issues.return_value = mock_issues_response
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
        jira_tools = JiraTools(config_fixture)
        result = await jira_tools.get_issues_by_user(app_state=mock_app_state_with_personal_creds, user_email=None, status_category="all")
        
        assert isinstance(result, dict)
        assert result.get('status') == 'SUCCESS'
        assert 'data' in result
        issues_data = result['data']
        assert len(issues_data) == 1
        assert issues_data[0]['key'] == "PROF-1"
        jql_query = mock_jira_instance.search_issues.call_args[0][0]
        assert f'assignee = "{profile_email}"' in jql_query

@pytest.mark.asyncio
async def test_get_issues_by_user_no_email_error(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing get_issues_by_user (No Email Error)")
    # Ensure the mock_app_state's user has no email for this specific test
    mock_app_state_no_personal_creds.current_user.email = None 
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
        jira_tools = JiraTools(config_fixture)
        result = await jira_tools.get_issues_by_user(app_state=mock_app_state_no_personal_creds, user_email=None)
        assert isinstance(result, dict)
        assert result.get('status') == 'ERROR' # Assuming decorator indicates error status
        # Check the actual error structure from the decorator
        assert result.get('error_type') == 'ValueError' 
        assert 'technical_details' in result
        assert "User email not provided and could not be determined" in result['technical_details']

    # Restore email for other tests if AppState is reused (though fixtures usually recreate)
    mock_app_state_no_personal_creds.current_user.email = "no_creds@example.com" 

@pytest.mark.asyncio
async def test_get_issues_by_project_success(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing get_issues_by_project (Success)")
    test_project_key = "PROJKEY"
    mock_issues_response = [
        create_mock_jira_issue("PROJKEY-100", "Project issue one", "Done", project_key=test_project_key),
        create_mock_jira_issue("PROJKEY-101", "Project issue two", "To Do", project_key=test_project_key)
    ]
    mock_jira_instance.search_issues.return_value = mock_issues_response
    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
        jira_tools = JiraTools(config_fixture)
        result = await jira_tools.get_issues_by_project(app_state=mock_app_state_no_personal_creds, project_key=test_project_key, status_category="all", max_results=10)
        
        assert isinstance(result, dict)
        assert result.get('status') == 'SUCCESS'
        assert 'data' in result
        issues_data = result['data']
        assert len(issues_data) == 2
        assert issues_data[0]['project_key'] == test_project_key
        jql_query = mock_jira_instance.search_issues.call_args[0][0]
        assert f'project = "{test_project_key.upper()}"' in jql_query

@pytest.mark.asyncio
async def test_create_story_success(config_fixture: Config, mock_app_state_with_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing create_story (Success)")
    assignee_email_to_test = "assignee@example.com"
    mock_assignable_user = MagicMock()
    mock_assignable_user.accountId = "user-account-id-123"
    mock_jira_instance.search_assignable_users_for_projects.return_value = [mock_assignable_user]
    mock_jira_instance.fields.return_value = [{'id': 'customfield_10016', 'name': 'Story Points'}] # Simulate story points field exists
    
    created_issue_summary = "A new story by test"
    project_key_to_use = "MOCKPROJ"
    mock_created_issue_instance = create_mock_jira_issue("NEW-123", created_issue_summary, "To Do", project_key=project_key_to_use)
    mock_jira_instance.create_issue.return_value = mock_created_issue_instance

    with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
        jira_tools = JiraTools(config_fixture)
        result = await jira_tools.create_story(
            app_state=mock_app_state_with_personal_creds,
            summary=created_issue_summary,
            description="Detailed story description.",
            project_key=project_key_to_use,
            assignee_email=assignee_email_to_test,
            story_points=5
        )
        
        assert isinstance(result, dict)
        assert result.get('status') == 'SUCCESS'
        assert 'data' in result
        created_issue_data = result['data']
        
        assert created_issue_data['key'] == "NEW-123"
        assert created_issue_data['summary'] == created_issue_summary
        assert created_issue_data['project_key'] == project_key_to_use 
        assert created_issue_data['assignee_email'] == assignee_email_to_test
        assert created_issue_data['story_points'] == 5
        
        mock_jira_instance.create_issue.assert_called_once()
        call_kwargs = mock_jira_instance.create_issue.call_args[1]
        assert call_kwargs['fields']['project']['key'] == project_key_to_use
        assert call_kwargs['fields']['summary'] == created_issue_summary
        assert call_kwargs['fields']['assignee']['accountId'] == "user-account-id-123"
        assert call_kwargs['fields']['customfield_10016'] == 5

@pytest.mark.asyncio
async def test_create_story_no_project_key_uses_default(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing create_story (No Project Key - Uses Default)")
    
    expected_default_project_key = "MOCKPROJ_test_default"

    def custom_config_get_env_value_for_default_test(key, default=None):
        # This side_effect provides the specific default project key for this test,
        # and other necessary values for Config/JiraTools initialization.
        values = {
            'JIRA_API_URL': "https://mocked.jira.com", 
            'JIRA_API_EMAIL': "mock_shared_email@example.com", 
            'JIRA_API_TOKEN': "mock_shared_token",
            'DEFAULT_API_TIMEOUT_SECONDS': 10,
            'DEFAULT_API_MAX_RETRIES': 3,
            'JIRA_DEFAULT_PROJECT_KEY': expected_default_project_key 
        }
        if key in values:
            return values[key]
        # Fallback for any other keys that might be requested by Config class itself during init, not covered above
        # This helps ensure Config() doesn't complain if it needs other env vars we haven't thought of.
        return default # or a generic mock value like 'generic_mock_env_val'

    # Patch Config.get_env_value so it returns the default project key when JiraTools checks for it.
    # Also patch JiraTools._create_jira_client to prevent real client creation during JiraTools.__init__.
    with patch.object(Config, 'get_env_value', side_effect=custom_config_get_env_value_for_default_test):
        with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance) as mock_create_client_for_init:
            # The config_fixture is passed, but its get_env_value calls will be overridden by the patch above.
            # JiraTools.__init__ calls self._create_jira_client, which is now patched.
            jira_tools = JiraTools(config_fixture) 
            # mock_create_client_for_init should have been called by JiraTools.__init__ for the shared client.
            mock_create_client_for_init.assert_called() 

            # Configure the mock_jira_instance for the create_issue call specifically for this test logic
            mock_jira_instance.create_issue.return_value = create_mock_jira_issue(
                "DEF-1", "Default project story", "To Do", project_key=expected_default_project_key
            )
            # Reset mocks that might have been called during JiraTools.__init__ via the _create_jira_client patch
            # if those calls aren't relevant to the specific assertions of create_story itself.
            mock_jira_instance.create_issue.reset_mock() # Reset before the actual call we are testing
            mock_jira_instance.search_assignable_users_for_projects.reset_mock() # Also reset this if create_story uses it
            mock_jira_instance.fields.reset_mock() # And this one too
            
            result = await jira_tools.create_story(
                app_state=mock_app_state_no_personal_creds, 
                summary="Default project story"
                # project_key is deliberately None to test default logic
            )
            
            assert isinstance(result, dict)
            assert result.get('status') == 'SUCCESS', f"Expected SUCCESS, got {result.get('status')}. Error: {result.get('technical_details') or result.get('error_message')}"
            assert 'data' in result
            created_issue_data = result['data']
            assert created_issue_data['project_key'] == expected_default_project_key

            mock_jira_instance.create_issue.assert_called_once()
            created_fields = mock_jira_instance.create_issue.call_args[1]['fields']
            assert created_fields['project']['key'] == expected_default_project_key

@pytest.mark.asyncio
async def test_create_story_no_project_key_and_no_default_error(config_fixture: Config, mock_app_state_no_personal_creds: AppState, mock_jira_instance: MagicMock):
    print("🚀 Testing create_story (No Project Key & No Default Error)")
    
    def custom_side_effect_no_default_proj(key, default=None):
        # This side_effect is specific to this test
        values = {
            'JIRA_API_URL': "https://mocked.jira.com", 
            'JIRA_API_EMAIL': "mock_shared@example.com", 
            'JIRA_API_TOKEN': "mock_shared_token",
            'DEFAULT_API_TIMEOUT_SECONDS': 10,
            'DEFAULT_API_MAX_RETRIES': 3,
            # JIRA_DEFAULT_PROJECT_KEY is deliberately omitted from this map
        }
        if key == 'JIRA_DEFAULT_PROJECT_KEY':
            return None # Explicitly return None for the default project key
        return values.get(key, default if default is not None else 'specific_mock_val_for_other_keys')

    # Patch Config.get_env_value just for the scope of this test
    with patch.object(Config, 'get_env_value', side_effect=custom_side_effect_no_default_proj):
        # We need a new Config instance that will use the above patch during its own __init__ if needed,
        # and critically, the JiraTools instance will use this patched version via its stored config.
        # The original config_fixture may not be suitable if its patch doesn't cover this specific scenario correctly.
        # However, JiraTools takes a config instance. So, the config it uses IS the one from config_fixture.
        # The patch here must apply to calls made FROM that config_fixture instance OR the Config class generally.
        # Let's ensure the JiraTools instance is created *within* this more specific patch context if necessary,
        # or ensure this patch correctly affects self.config.get_env_value() within JiraTools.

        # The key is that JiraTools calls self.config.get_env_value(). We need to ensure this call 
        # uses our custom_side_effect_no_default_proj.
        # The config_fixture has its own patch. This test-specific patch must take precedence for calls to Config.get_env_value.

        # Re-initialize JiraTools with the base config_fixture, the patch will apply to Config.get_env_value calls
        jira_tools = JiraTools(config_fixture) 

        with patch.object(JiraTools, '_create_jira_client', return_value=mock_jira_instance):
            result = await jira_tools.create_story(app_state=mock_app_state_no_personal_creds, summary="Story that needs a project")
            assert isinstance(result, dict)
            assert result.get('status') == 'ERROR'
            # Check the actual error structure from the decorator
            assert result.get('error_type') == 'ValueError'
            assert 'technical_details' in result
            assert "No project key provided and no default project configured" in result['technical_details']

# If run directly, for quick check, though pytest is preferred.
if __name__ == "__main__":
    print("Running Jira tool tests with mocks. Use 'pytest tests/tools/test_jira_tool.py' for full features.")
    
    async def main():
        # Minimal setup to run tests directly (not all features of pytest like fixtures will work easily here)
        # This is mostly for very basic execution check, pytest is the way to go.
        print("WARNING: Running without pytest, some features might be limited.")
        cfg = Config() # Basic config, might not reflect fixture's mocks
        
        # Mock app_state for direct runs
        user_profile_no_creds = UserProfile(user_id="direct_run_user1", email="direct1@example.com", profile_data={})
        app_state_no_creds = AppState(current_user=user_profile_no_creds)
        
        user_profile_with_creds = UserProfile(user_id="direct_run_user2", email="direct2@example.com", profile_data={
            'personal_credentials': {'jira_email': 'p_direct@example.com', 'jira_token': 'p_direct_token_longenoughxxx'}
        })
        app_state_with_creds = AppState(current_user=user_profile_with_creds)

        # This direct run won't use the mock_jira_instance fixture or patch.object easily.
        # It will try to make real connections unless JIRA itself is globally patched before JiraTools init.
        # For true mocked testing, `pytest` is essential.
        print("--- Direct run is highly limited for mocked tests. Please use pytest. ---")

        # Example: Manually trying one test (highly simplified, mocks won't be applied as in pytest)
        try:
            print("Attempting a simplified health check (likely to fail or be real if not globally mocked):")
            # This won't use the sophisticated patching from pytest fixtures here.
            # To truly test with mocks without pytest, you'd need to structure patches manually around calls.
            # jira_tools_direct = JiraTools(cfg)
            # health = jira_tools_direct.health_check(app_state_no_creds)
            # print(f"Simplified health: {health}")
        except Exception as e:
            print(f"Error in simplified direct run: {e}")

    asyncio.run(main()) 