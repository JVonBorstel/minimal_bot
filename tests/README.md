# Test Organization for Minimal Chatbot

This directory contains all test files for the minimal chatbot project, organized into logical categories for better maintainability and understanding.

## 📁 Directory Structure

### `/tools/` - Tool-Specific Tests
Tests for individual tools and tool integrations:

**Jira Tools:**
- `test_jira_tool.py` - Basic Jira tool functionality
- `test_jira_real.py` - Real Jira API testing
- `prove_jira_real.py` - Jira API proof of concept
- `debug_jql.py` - JQL query debugging
- `get_cloud_id.py` - Jira cloud ID utility

**GitHub Tools:**
- `test_github_tools.py` - GitHub tool functionality
- `test_github_working.py` - Working GitHub API tests
- `test_github_real.py` - Real GitHub API testing
- `debug_github_structure.py` - GitHub response structure debugging
- `debug_github_returns.py` - GitHub return type analysis

**Greptile Tools:**
- `test_greptile_tools.py` - Greptile integration tests
- `test_greptile_indexing.py` - Repository indexing tests
- `check_greptile_status.py` - Greptile service status checks

**Perplexity Tools:**
- `test_perplexity_tools.py` - Perplexity AI tool tests

**Help Tools:**
- `test_help_basic.py` - Basic help functionality
- `test_help_discovery.py` - Tool discovery via help
- `test_help_formatting.py` - Help output formatting
- `test_help_permissions.py` - Help permission handling

**Utilities:**
- `check_tools.py` - General tool validation

### `/database/` - Database & State Management Tests
Tests for data persistence, memory management, and state handling:

- `test_database_backend_switching.py` - SQLite/Redis backend switching
- `test_database_persistence.py` - Session persistence validation
- `test_database_resilience.py` - Database failure recovery
- `test_database_transactions.py` - Transaction integrity testing
- `test_memory_management.py` - Memory load and cleanup testing
- `test_database_examine.py` - Database structure analysis
- `debug_database.py` - Database debugging utilities

### `/users/` - User Management & Multi-User Tests
Tests for user isolation, permissions, and concurrent usage:

- `test_multiuser_isolation.py` - User state isolation validation
- `test_concurrent_sessions.py` - Concurrent session testing
- `test_permission_enforcement.py` - Permission access control
- `test_group_chat_multiuser.py` - Group chat and multi-user scenarios

### `/integration/` - Full System Integration Tests
End-to-end tests that exercise multiple components:

- `test_full_bot_integration.py` - Complete bot functionality testing
- `test_real_api_connectivity.py` - Real API integration validation
- `test_multi_service_intelligence.py` - Multi-service orchestration
- `test_triage_intelligence.py` - Intelligent request routing

### `/scenarios/` - Real-World Usage Scenarios
Tests that simulate actual user workflows and use cases:

- `demo_user_scenario.py` - Demonstration scenarios
- `test_realistic_scenario.py` - Realistic user interactions
- `test_onboarding_system.py` - User onboarding flow
- `test_with_actual_configured_email.py` - Real email configuration tests
- `test_with_real_user_data.py` - Tests with actual user data
- `test_real_field_usage.py` - Real field validation and usage

### `/debug/` - Debug & Quick Validation Scripts
Lightweight scripts for quick testing and debugging:

- `quick_tool_validation.py` - Fast tool validation
- `test_basic_startup.py` - Basic bot startup testing
- `demonstrate_real_help.py` - Help system demonstration
- `final_proof.py` - Final validation proof
- `test_new_token.py` - New token validation

### `/docs/` - Test Documentation & Logs
Documentation, logs, and analysis from test runs:

**Documentation:**
- `code_stripping_plan.md` - Comprehensive development plan
- `test_database_step_1_13_COMPLETE.md` - Database validation summary
- `STEP_1_14_MULTIUSER_VALIDATION_SUMMARY.md` - Multi-user test summary
- `GROUP_CHAT_VALIDATION_SUMMARY.md` - Group chat test results
- `prompt_for_next_agents.md` - Agent coordination documentation
- `essential_files.md` - Essential file listing

**Log Files:**
- `test_database_transactions.log` - Database transaction logs
- `test_database_persistence.log` - Persistence test logs
- `test_database_resilience.log` - Resilience test logs
- `test_memory_management.log` - Memory management logs
- `test_database_backend_switching.log` - Backend switching logs

**Sample Outputs:**
- `help_output_sample.txt` - Sample help command output

## 🚀 Running Tests

### Individual Tool Tests
```bash
# Test specific tools
python tests/tools/test_jira_tool.py
python tests/tools/test_github_working.py
python tests/tools/test_help_basic.py
```

### Database Tests
```bash
# Test database functionality
python tests/database/test_database_persistence.py
python tests/database/test_memory_management.py
```

### Integration Tests
```bash
# Full system tests
python tests/integration/test_full_bot_integration.py
python tests/integration/test_real_api_connectivity.py
```

### Quick Validation
```bash
# Fast validation scripts
python tests/debug/quick_tool_validation.py
python tests/debug/test_basic_startup.py
```

## 📊 Test Categories by Phase

### Phase 1: Core Functionality (Steps 1.1-1.16)
- **Tool Tests**: Individual tool validation
- **Database Tests**: State management validation
- **Integration Tests**: Multi-component testing

### Phase 2: User Experience
- **User Tests**: Multi-user and permission testing
- **Scenario Tests**: Real-world usage validation

### Phase 3: Production Readiness
- **Debug Tests**: Quick validation and debugging
- **Documentation**: Comprehensive test documentation

## 🎯 Test Success Criteria

- **Tool Tests**: All preserved tools (10 total) must execute successfully
- **Database Tests**: SQLite backend must be production-ready
- **User Tests**: Perfect user isolation and permission enforcement
- **Integration Tests**: End-to-end workflows must complete without errors
- **Scenario Tests**: Real-world usage patterns must work correctly

## 📝 Notes

- All tests are designed to work with real APIs and data (no mocking)
- Tests validate the minimal bot's production readiness
- Each test category builds upon previous validations
- Documentation includes comprehensive logs and analysis
- Test organization follows the project's development phases

For detailed test results and analysis, see the documentation in `/docs/` directory. 