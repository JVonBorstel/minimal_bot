## Essential Files for Minimal Bot

This document lists the files and directories identified as necessary to run a minimal version of the bot with core functionality, Microsoft Teams integration, Redis and SQLite state management, User Profile handling, and simplified Jira/GitHub tool access.

**Core Components:**

*   `app.py`: Main application entry point.
*   `config.py`: Handles configuration.
*   `requirements.txt`: Project dependencies.
*   `llm_interface.py`: LLM interaction logic.
*   `health_checks.py`: Health check endpoint.
*   `state_models.py`: Defines `AppState` and other state models.
*   `alembic.ini` and `alembic/`: Needed for SQLite schema setup.
*   `state.sqlite`, `state.sqlite-shm`, `state.sqlite-wal`: The SQLite database files.

**Microsoft Teams Integration (Bot Framework):**

*   `bot_core/adapter_with_error_handler.py`: Custom Bot Framework adapter.
*   `bot_core/my_bot.py`: Main bot logic, including `SQLiteStorage` and `on_message_activity`.

**State Management & User Profile (Redis & SQLite):**

*   `bot_core/my_bot.py` (Contains `SQLiteStorage`)
*   `bot_core/redis_storage.py`: Redis storage implementation.
*   `user_auth/` (Entire directory: `models.py`, `orm_models.py`, `db_manager.py`, `utils.py`, `permissions.py`, `tool_access.py`, `teams_identity.py`).

**Core Logic:**

*   `core_logic/agent_loop.py`: Core agent processing loop.
*   `core_logic/tool_processing.py`: Logic for processing tool calls.
*   `core_logic/tool_selector.py`: Logic for selecting tools.
*   `core_logic/tool_call_adapter.py`: Adapts tool calls for the LLM.
*   `core_logic/tool_call_adapter_integration.py`: Integration for the tool call adapter.
*   `core_logic/constants.py`: Application-wide constants.
*   `core_logic/history_utils.py`: Utilities for managing conversation history.

**Utilities:**

*   `utils/` (Entire directory: including `logging_config.py`, `utils.py`, and any other necessary helpers).

**Simplified Tool Handling:**

*   `tools/tool_executor.py`: Executes tools.
*   `tools/__init__.py`: Likely registers tools and the `@tool` decorator.
*   `tools/_tool_decorator.py`: Defines the `@tool` decorator.
*   `tools/core_tools.py`: Contains the `help` tool.
*   `tools/jira_tools.py`: Include this file, potentially simplifying it to only include `jira_get_issues_by_user`.
*   `tools/github_tools.py`: Include this file, potentially simplifying it to only include `github_list_repositories`.
*   `tools/perplexity_tools.py`: Included for potential LLM/search integration dependencies.

**(Note: The `.env` file is also required, but the user will copy this manually.)** 