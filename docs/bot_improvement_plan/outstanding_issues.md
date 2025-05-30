# Bot Improvement Plan: Outstanding Issues & Enhancements --- FILE IS NOW OUT OF DATE**

This document outlines the key issues and areas for improvement identified for the Augie bot based on recent testing and log analysis.

## High Priority User Experience (UX) / Functional Fixes:

1.  **Jira Tool Integration & Functionality Issues:**
    *   **Symptom:** The bot fails to list Jira tickets for a user, even after clarifying project information. It provides contradictory statements about its ability to use email/usernames or project keys for searching Jira.
    *   **Impact:** A core advertised functionality (Jira integration) appears broken or highly unreliable, leading to user frustration.
    *   **Resolution Progress (Fixes Implemented & Tested):**
        *   Reviewed the `JiraTools` implementation in `tools/jira_tools.py`.
        *   Simplified the JQL query within the `get_issues_by_user` tool to `assignee = "{user_email}"`. This makes the tool's behavior directly align with its description of finding issues assigned to a user by their email. The previous, more complex JQL (`assignee = "{user_email}" OR (assignee = currentUser() AND reporter = "{user_email}")`) was identified as a potential cause for inconsistent results.
        *   Unit tests (`tests/tools/test_jira_tool.py`) for `JiraTools` passed successfully after the change.
        *   Integration tests (`tests/tools/test_jira_real.py`) that interact with a real Jira instance also passed, indicating the modified tool functions correctly in a live environment.
    *   **Original Proposed Resolution (Partially Superseded by above actions):**
        *   Thoroughly review the `JiraTools` implementation (`tools/jira_tools.py` or similar). *(Done)*
        *   Verify the capabilities of functions like searching by assignee (user email/ID) and listing issues by project key. *(Done, and `get_issues_by_user` improved)*
        *   Ensure the tool descriptions provided to the LLM accurately reflect these capabilities and guide the LLM to ask for the correct parameters in the right sequence. *(The simplification should aid this, but ongoing LLM interaction monitoring is advised).*
        *   Test various Jira interaction flows to ensure the LLM can correctly invoke the tools. *(Partially covered by integration tests; further end-to-end LLM testing recommended).*

2.  **Broken `@augie preferences` Command:**
    *   **Symptom:** Bot suggests using `@augie preferences` after onboarding, but the command fails, stating no tool exists.
    *   **Impact:** Contradictory and frustrating for the user.
    *   **Resolution Progress (Partial Fix Implemented):**
        *   A suite of LLM tools for preference management (`list_my_preferences`, `get_my_preference`, `set_my_preference`) has been created in `tools/user_profile_tools.py`.
        *   These tools are registered with the LLM via import in `tools/tool_executor.py`.
        *   This provides the backend capability for the LLM to handle user requests to view or modify their preferences.
        *   The original failure ("no tool exists") when the LLM attempts to handle `@augie preferences` or similar natural language requests should now be resolved.
        *   **Next Step:** User testing is required to confirm the end-to-end functionality and that the LLM correctly utilizes these tools for various preference-related queries (e.g., "show my preferences", "change my nickname", "turn off notifications").
    *   **Original Proposed Resolution:** Implement a reliable handler for this command. This could be a dedicated tool for the LLM to call (e.g., `manage_preferences_tool`) or a hardcoded command in `my_bot.py` that directly interacts with user state. *(The LLM tool approach has been implemented).*

3.  **Bot Amnesia / Onboarding Data Usage:**
    *   **Symptom:** Bot collects user information during onboarding (role, projects, preferences, potentially preferred name) but doesn't seem to "remember" or use this information in subsequent interactions (e.g., when asked "what do you know about me?" or "what do you call me?").
    *   **Log Insight:** Onboarding Q&A might not be consistently added to the main `app_state.messages` history, potentially limiting LLM context.
    *   **Impact:** Reduces the value of the onboarding process; the LLM cannot personalize responses or actions effectively.
    *   **Resolution Progress (Fixes Implemented & Tested):**
        *   Verified that onboarding answers (including "Preferred Name" and "Communication Style") are being correctly saved to `UserProfile.profile_data.preferences` and persisted to the database (investigated `workflows/onboarding.py`, `user_auth/db_manager.py`, and save points in `bot_core/my_bot.py`).
        *   Modified `core_logic/agent_loop.py` (specifically the `start_streaming_response` function) to augment the system prompt provided to the LLM.
        *   The system prompt now includes the user's `preferred_name` (falling back to `display_name`) and `communication_style` if set.
        *   This provides the LLM with direct context to address the user by their preferred name and adapt its communication style, aiming to resolve the "amnesia" regarding these preferences.
    *   **Original Proposed Resolution (Partially Superseded/Refined):**
        *   Verify that onboarding answers (including any "Preferred Name") are being correctly saved to the `UserProfile` model ... and that this `UserProfile` is being correctly persisted ... *(Done)*
        *   Determine if the raw onboarding Q&A messages themselves should be added to `app_state.messages` for conversational context. If so, implement this. *(Not implemented; focus was on structured preference usage. Can be revisited if needed.)*
        *   Crucially, ensure that the relevant persisted user preferences from `UserProfile` are loaded with `AppState` and consistently made available to the LLM ... so it can effectively "remember" and use this information. *(Done for preferred_name and communication_style via system prompt augmentation.)*

4.  **Onboarding Feedback & "Skip" Behavior:**
    *   **Symptom:** Lack of explicit feedback during onboarding makes it unclear if information is being saved. Skipping parts of onboarding can feel like all prior input is discarded.
    *   **Impact:** Reduced user trust and clarity during a critical first-interaction phase.
    *   **Resolution:** Modify the onboarding workflow (`workflows/onboarding.py`) to:
        *   Provide clear confirmation after each piece of information is successfully processed/saved.
        *   When a user skips a step or the rest of onboarding, confirm what information *has* been retained from previous steps.

## Capability Enhancements:

5.  **Inability to "Explain File" Content:**
    *   **Symptom:** Bot states it lacks a specific tool to explain file contents when asked to explain a code file.
    *   **Impact:** Underutilizes existing capabilities. The bot could theoretically use code search (Greptile) to fetch file content and then leverage the LLM to summarize or explain that content.
    *   **Resolution (Future Enhancement):** Enhance `core_logic` to support multi-step reasoning for such requests, allowing the bot to chain tools (e.g., read file content, then pass to LLM for explanation).

## Minor Issues / Maintenance:

6.  **`tool_adapter_metrics` Warning in Logs:**
    *   **Symptom:** Logs show: `WARNING - Key tool_adapter_metrics not found in UserProfile model, skipping for update.`
    *   **Impact:** Minor schema mismatch; data for this specific field isn't being saved. Does not appear to affect core functionality currently.
    *   **Resolution:**
        *   Locate where `tool_adapter_metrics` is being set.
        *   Either add the field to the `UserProfile` model (in `user_auth/models.py`) with the correct type, or remove the attempt to set it if the field is obsolete.

## Confirmed Resolved:

*   **Redis Connectivity & Timeouts:** The primary issue causing 499 errors due to the bot trying to connect to a local Redis instance from Railway has been resolved by configuring the bot to use the Railway-hosted Redis service. 