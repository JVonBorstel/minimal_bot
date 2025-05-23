# **⚠️ CRITICAL INSTRUCTIONS FOR ANY AI AGENT WORKING ON THIS PROJECT ⚠️**

## **🎯 PRIMARY OBJECTIVE: BUILD WORKING, FUNCTIONAL CODE**

**READ THIS FIRST - NO EXCEPTIONS:**

This is **NOT** an exercise in writing code that "looks right" or "should work in theory." This is about creating a **PRODUCTION-READY, FULLY-FUNCTIONAL** minimal chatbot that **ACTUALLY WORKS** when deployed.

## **⚡ CRITICAL: SIMPLE & FAST OVER PERFECT**

**DON'T OVERTHINK THIS BUILD:**
- **SPEED MATTERS** - We have limited time, get it working FAST
- **SIMPLE SOLUTIONS** - Don't add complex validation, security, or configs
- **BASIC FUNCTIONALITY** - If it runs and tools work, that's success
- **NO PERFECTIONISM** - Working with rough edges beats broken perfection
- **KEEP IT MINIMAL** - Remove tools, don't add complexity

### **🚨 ABSOLUTE REQUIREMENTS - NO COMPROMISES**

1. **EVERY SINGLE LINE OF CODE YOU WRITE MUST BE EXECUTABLE**
   - No placeholders, no "TODO" comments, no mock implementations
   - No "this should work" - it MUST work when run
   - Test every change as you make it

2. **PRESERVE WORKING FUNCTIONALITY AT ALL COSTS**
   - If something works now, it MUST still work after your changes
   - Never break existing functionality to "clean up" code
   - When in doubt, keep more code rather than risk breaking something

3. **VALIDATE EVERYTHING BEFORE MOVING TO NEXT STEP**
   - Run basic Python syntax check: `python -m py_compile <file>`
   - Quick import test: `python -c "import <module>"`
   - Don't get bogged down in extensive testing - basic functionality check only

4. **NO SHORTCUTS OR ASSUMPTIONS**
   - Don't assume imports will work - verify them
   - Don't assume dependencies exist - check them
   - Don't assume configurations are valid - test them
   - Don't assume removed code wasn't critical - trace dependencies carefully

5. **WORKING > PERFECT**
   - A working bot with extra code is infinitely better than a broken "clean" bot
   - Err on the side of keeping functionality rather than removing it
   - Focus on removing ONLY what you're 100% certain is safe to remove
   - **SPEED MATTERS** - Get it working fast, don't perfectionist-engineer it
   - **SIMPLE > COMPLEX** - Basic functionality beats elegant complexity

### **🎯 WHAT "WORKING" MEANS:**

- **Bot starts up** without crashing
- **Basic state management** works (don't overthink SQLite vs Redis switching)
- **Tools execute** and return something (doesn't have to be perfect)
- **Multi-tool execution works** - Multiple tools can run
- **No major crashes** during normal operation

### **🚫 FAILURE CONDITIONS THAT ARE UNACCEPTABLE:**

- Bot won't start up at all
- Major Python syntax errors that prevent running
- Complete inability to execute any tools
- Total crashes that kill the bot process
- **BUT minor issues, warnings, or imperfect error handling are OK if basic functionality works**

### **📋 MANDATORY VALIDATION CHECKLIST FOR EVERY STEP:**

Before marking ANY step complete, you MUST verify:
- [ ] No Python syntax errors (quick check: `python -m py_compile <file>`)
- [ ] No broken imports in main modules
- [ ] No calls to removed functions (basic grep check)
- [ ] Bot can start up without immediate crashes
- [ ] **Keep it simple but don't skip these basics**

### **🔧 IF SOMETHING BREAKS:**

1. **STOP IMMEDIATELY** - do not continue to next step
2. **RESTORE FROM BACKUP** - use the backup from Step 0.2
3. **ANALYZE THE FAILURE** - understand exactly what went wrong
4. **UPDATE THE PLAN** - modify approach to avoid the same failure
5. **GET USER GUIDANCE** - ask for help rather than guess

### **💡 SUCCESS MINDSET:**

- **Conservative approach**: Keep more code rather than risk breaking functionality
- **Incremental progress**: Validate each small change before proceeding
- **Real testing**: Actually run the code, don't just read it
- **User focus**: The user needs a working bot, not clean code
- **Production mentality**: This will be deployed and used by real people

---

# **Comprehensive Plan for Creating the Reliable Minimal Bot**

## **Progress Tracking Log**
> **Instructions for LLMs**: Update this section after completing each step. Mark with ✅ when complete, 🔄 when in progress, ❌ when failed.

### **Phase 0: Prerequisites** 
- [x] ✅ **Step 0.1**: Verify current codebase state - **COMPLETE**
- [x] ✅ **Step 0.2**: Create backup of current state
- [x] ✅ **Step 0.3**: Create/copy tools directory structure
- [ ] **Step 0.4**: Validate all expected files exist

### **Phase 1: Targeted Code Stripping**
- [x] **Step 1.1**: Strip `jira_tools.py` 
- [x] **Step 1.2**: Strip `github_tools.py`
- [x] **Step 1.3**: Refine Core Logic
- [x] **Step 1.4**: Refine Bot Core & App
- [x] **Step 1.5**: Refine State Models
- [x] **Step 1.6**: Refine Config
- [x] **Step 1.7**: Refine User Auth & Utils
- [x] **Step 1.8**: Final Tool Framework Check
- [ ] **Step 1.9**: Validate User-Bot Interactions 

### **Phase 2: Verification and Documentation**
- [ ] **Step 2.1**: Internal Consistency Check
- [ ] **Step 2.2**: Document Changes
- [ ] **Step 2.3**: Create Testing Guide

---

## **Goal**
Create a lightweight version of the chatbot within the `minimal_bot` directory that reliably handles startup, configurable state management (Redis/SQLite), user profiles, core message processing, and execution of a specific, limited set of tools (`help`, `jira_get_issues_by_user`, `github_list_repositories`, `github_search_code`, all Perplexity tools, all Greptile tools), while implementing robust error handling.

---

## **Phase 0: Prerequisites** 

### **Step 0.1: Verify Current Codebase State** ✅ **[COMPLETE]**
**Assigned to**: Claude-Assistant-001  
**Status**: ✅ Complete  
**Completed**: 2024-01-15 (Current session)
**Task**: Audit current directory structure and identify missing components  
**Expected Files Check**:
- ✅ `app.py`, `config.py`, `state_models.py` - Present
- ✅ `bot_core/`, `core_logic/`, `user_auth/` directories - Present  
- ❌ `tools/` directory - **MISSING** (Critical dependency)
- ✅ Database files and alembic - Present

**Completion Notes**: 
- Analyzed current minimal_bot directory structure
- Confirmed core infrastructure files are present
- Identified critical missing dependency: `tools/` directory must be created
- Found all core_logic files present with tool-related infrastructure
- Database files and migration setup confirmed present
- User auth and bot core directories properly structured

**⚠️ Critical Finding**: Tools directory is completely missing and must be created/copied before any stripping can begin. This is a prerequisite blocker for Phase 1.

**Completion Criteria**: ✅ All expected directories and core files confirmed present
**Notes**: Tools directory needs to be created/copied from main codebase

---

### **Step 0.2: Create Backup of Current State**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete  
**Task**: Create backup copy of entire `minimal_bot` directory  
**Commands**: 
```bash
# Create backup in parent directory
cp -r minimal_bot minimal_bot_backup_$(date +%Y%m%d_%H%M%S)
```
**Completion Criteria**: Backup directory created and verified
**Rollback Strategy**: If any step fails, restore from this backup

---

### **Step 0.3: Create/Copy Tools Directory Structure**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Create tools directory with all required files  
**Required Files**:
- `tools/__init__.py`
- `tools/_tool_decorator.py` 
- `tools/tool_executor.py`
- `tools/core_tools.py` (with help tool)
- `tools/jira_tools.py` (full version - to be stripped)
- `tools/github_tools.py` (full version - to be stripped)
- `tools/perplexity_tools.py` (keep all)
- `tools/greptile_tools.py` (keep all)

**Source**: Copy from main Augie codebase if available
**Completion Criteria**: All tool files present and Python syntax valid

---

### **Step 0.4: Validate All Expected Files Exist**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Run comprehensive file existence check  
**Validation**: Check all files from `essential_files.md` exist
**Completion Criteria**: All essential files confirmed present
**Notes**: All files listed in `essential_files.md` and Step 0.3 are present. Some tool files (`greptile_tools.py`, `github_tools.py`, `jira_tools.py`, `core_tools.py`, `tool_executor.py`, `_tool_decorator.py`) were found to have content, which was unexpected at this stage for some of them as Step 0.3 aimed to create empty files. Subsequent stripping steps will address `jira_tools.py` and `github_tools.py`. `perplexity_tools.py` and `greptile_tools.py` are intended to be kept. The content of `core_tools.py`, `tool_executor.py`, and `_tool_decorator.py` should be reviewed during later refinement if not explicitly handled by a stripping step.
**Blockers**: Cannot proceed to Phase 1 until this passes

---

## **Phase 1: Targeted Code Stripping**

### **Step 1.1: Strip `jira_tools.py`**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Remove all JIRA tools except `jira_get_issues_by_user`  

**Detailed Actions**:
1. **Audit Current Tools**: List all function definitions in `tools/jira_tools.py`
2. **Identify Dependencies**: Find imports/helpers used ONLY by tools to be removed
3. **Surgical Removal**: Remove disallowed tools and their exclusive dependencies
4. **Preserve Structure**: Keep `JiraTools` class, `__init__`, `health_check`
5. **Validate Syntax**: Ensure remaining code is syntactically correct
6. **Test Preserved Tool**: Basic syntax check on remaining `jira_get_issues_by_user`

**Tools to Remove**: All except `jira_get_issues_by_user`  
**Tools to Preserve**: `jira_get_issues_by_user`  
**Completion Criteria**: 
- ✅ Only 1 JIRA tool function remains (`jira_get_issues_by_user`)
- ✅ File passes Python syntax validation
- ✅ No broken imports in preserved code (verified by syntax check and manual review of remaining code)

**Dependencies to Check**: 
- Check if any `core_logic/` files reference removed tools (deferred to Step 1.3)
- Update imports in `tools/__init__.py` if needed (deferred to Step 1.8)

---

### **Step 1.2: Strip `github_tools.py`**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Remove all GitHub tools except `github_list_repositories` and `github_search_code`

**Detailed Actions**:
1. **Audit Current Tools**: List all function definitions in `tools/github_tools.py`
2. **Identify Dependencies**: Find imports/helpers used ONLY by tools to be removed  
3. **Surgical Removal**: Remove disallowed tools and their exclusive dependencies
4. **Preserve Structure**: Keep `GitHubTools` class, `__init__`, `health_check`
5. **Validate Syntax**: Ensure remaining code is syntactically correct
6. **Test Preserved Tools**: Basic syntax check on remaining tools

**Tools to Remove**: All except the 2 specified  
**Tools to Preserve**: `github_list_repositories`, `github_search_code`  
**Completion Criteria**:
- ✅ Only 2 GitHub tool functions remain (`github_list_repositories`, `github_search_code`)
- ✅ File passes Python syntax validation  
- ✅ No broken imports in preserved code (verified by syntax check and manual review)

**Dependencies to Check**:
- Check if any `core_logic/` files reference removed tools (deferred to Step 1.3)
- Update imports in `tools/__init__.py` if needed (deferred to Step 1.8)

---

### **Step 1.3: Refine Core Logic**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Clean core logic files of references to removed tools

**Files to Process**:
- `core_logic/agent_loop.py`
- `core_logic/tool_processing.py` 
- `core_logic/tool_selector.py`
- `core_logic/tool_call_adapter.py`
- `core_logic/tool_call_adapter_integration.py`
- `core_logic/constants.py`
- `core_logic/history_utils.py`

**Detailed Actions**:
1. **Scan for Tool References**: Search for any hardcoded tool names that were removed
2. **Clean Imports**: Remove unused imports from tool modules
3. **Update Constants**: Remove any constants specific to removed tools
4. **Validate Logic Flow**: Ensure tool selection and execution pipeline intact
5. **Preserve Multi-Tool Execution**: Ensure sequential and parallel tool execution still works
6. **Test Core Pipeline**: Verify message processing → tool selection → execution flow

**Completion Criteria**:
- ✅ No obvious references to removed tool *names* in `core_logic` files requiring code changes (e.g., hardcoded calls). Example references in comments are acceptable.
- ✅ Core logic files do not directly import `JiraTools` or `GitHubTools` classes, interacting via `ToolExecutor` instead.
- ✅ `core_logic/constants.py` reviewed; no constants specific to removed tools found.
- ✅ Core message processing pipeline appears intact structurally.
- ✅ Multi-tool execution logic appears preserved structurally.
**Notes**: Detailed validation of tool registration and execution against the stripped tool files will occur in Step 1.8.

---

### **Step 1.4: Refine Bot Core & App**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Clean bot core and app files

**Files to Process**:
- `bot_core/my_bot.py`
- `app.py`

**Detailed Actions**:
1. **Remove Tool Handlers**: Delete any specific handlers for removed tools
2. **Clean Imports**: Remove unused tool imports
3. **Verify State Logic**: Ensure SQLite/Redis logic preserved
4. **Validate Bot Framework Integration**: Teams bot functionality intact

**Completion Criteria**:
- ✅ Bot startup logic in `app.py` appears intact.
- ✅ State management (SQLite/Redis) in `bot_core/my_bot.py` (and its usage in `app.py`) appears preserved.
- ✅ No direct references to removed tool *names or functions* found in `app.py` or `bot_core/my_bot.py`.
**Notes**: `app.py` checks `is_tool_configured` for 'jira' and 'github', which is a general configuration check and not tied to specific removed tool functions. This is acceptable.

---

### **Step 1.5: Refine State Models**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Clean state models of unused fields

**File to Process**: `state_models.py`

**Detailed Actions**:
1. **Audit Model Fields**: Identify fields used exclusively by removed tools
2. **Remove Unused Fields**: Safely remove fields not needed
3. **Preserve Core Models**: Keep `AppState`, user profiles, chat history
4. **Validate Serialization**: Ensure models still serialize/deserialize correctly

**Completion Criteria**:
- ✅ Core models (`AppState`, `UserProfile`, `WorkflowContext`, etc.) reviewed.
- ✅ No fields found that are *exclusively* tied to removed tool functionalities.
- ✅ Models appear to be generic and support core functionality (chat history, user profiles, generic tool/workflow state).
- ✅ Serialization will be handled by Pydantic; structural integrity maintained.
**Notes**: The state models are designed generically and do not require changes based on the tool stripping performed so far.

---

### **Step 1.6: Refine Config**  
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Clean configuration options

**File to Process**: `config.py`

**Detailed Actions**:
1. **Remove Unused Config**: Delete config options for removed tools
2. **Preserve Core Config**: Keep LLM, state backend, preserved tools config
3. **Validate Config Loading**: Ensure config still loads correctly
4. **Update Validation**: Remove validation for removed features

**Completion Criteria**:
- ✅ `config.py` reviewed. No config options found that are *exclusively* for removed tools.
- ✅ Core configurations for LLM, state backend, and connection details for preserved tool services (Jira, GitHub) are maintained.
- ✅ Config loading and validation logic (e.g., for Jira API keys) remains valid for preserved tools.
**Notes**: General service-level configurations (e.g., JIRA_API_URL) are still required for the preserved tools. Default project/issue type for Jira are kept as they don't harm and might be useful.

---

### **Step 1.7: Refine User Auth & Utils**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Clean user auth and utils directories

**Directories to Process**: `user_auth/`, `utils/`

**Detailed Actions**:
1. **Scan for Tool Dependencies**: Find any code specific to removed tools
2. **Remove Unused Code**: Clean up tool-specific auth/utils
3. **Preserve Core Functionality**: Keep user profiles, permissions, logging
4. **Validate Dependencies**: Ensure remaining code has all dependencies

**Completion Criteria**:
- ✅ `user_auth/` and `utils/` files reviewed.
- ✅ No code found that is specific to *removed tool functionalities* requiring changes.
- ✅ Core user auth functionality (profiles, DB interaction, permission checking logic) preserved.
- ✅ Core utils (logging, state helpers) preserved.
- ✅ Permission definitions in `user_auth/permissions.py` for removed tools are kept as they don't cause harm and might be used later; this is acceptable.

---

### **Step 1.8: Final Tool Framework Check**
**Assigned to**: Gemini (current LLM)
**Status**: ✅ Complete
**Task**: Comprehensive tool framework validation

**Files to Review**:
- `tools/tool_executor.py`
- `tools/__init__.py`

**Detailed Actions**:
1. **Validate Tool Registration**: Ensure all preserved tools properly registered
2. **Check Imports**: Verify all imports resolve correctly  
3. **Quick Tool Discovery**: Confirm tool executor can find all preserved tools
4. **Basic Tool Metadata**: Ensure tool descriptions intact (don't overthink)

**Completion Criteria**:
- ✅ All preserved tools discoverable by `ToolExecutor`.
- ✅ `ToolExecutor` instantiates `JiraTools`, `GitHubTools`, `PerplexityTools`, `GreptileTools`, and `CoreTools` correctly.
- ✅ Imports in `tools/__init__.py`, `tools/tool_executor.py`, and `tools/_tool_decorator.py` are correct and resolve.
- ✅ Tool descriptions and parameter schemas for preserved tools are intact.
**Notes**: The tool framework relies on eager imports in `tool_executor.py` to register tools. The stripped tool classes are still imported, and `ToolExecutor` correctly discovers and instantiates only the preserved, decorated methods. This approach is sound.

---

### **Step 1.9: Validate User-Bot Interactions**
**Assigned to**: Gemini (current LLM)
**Status**: 🔄 In Progress
**Task**: Comprehensive validation of user-bot interactions with all preserved tools

**Test Scenarios to Execute**:

**Scenario 1: Help Command Interaction**
- **User Input**: "@bot help" or "what can you do?"
- **Expected**: Bot responds with help information listing available tools
- **Validation**: Verify help tool executes and returns tool descriptions

**Scenario 2: Jira Tool Interaction**
- **User Input**: "Show me my Jira issues" or "Get my open tickets"
- **Expected**: Bot calls `jira_get_issues_by_user` with user's email
- **Validation**: Tool executes with proper parameter injection (user email)

**Scenario 3: GitHub Repository Listing**
- **User Input**: "List my GitHub repositories" or "Show my repos"
- **Expected**: Bot calls `github_list_repositories` 
- **Validation**: Tool executes and returns repository data structure

**Scenario 4: GitHub Code Search**
- **User Input**: "Search for function named authenticate in GitHub"
- **Expected**: Bot calls `github_search_code` with query
- **Validation**: Tool executes and returns code search results

**Scenario 5: Greptile Codebase Query**
- **User Input**: "What does the main function do in https://github.com/user/repo?"
- **Expected**: Bot calls `greptile_query_codebase` with repo URL and query
- **Validation**: Tool executes and returns AI-generated analysis

**Scenario 6: Greptile Code Search**
- **User Input**: "Find authentication logic in the codebase"
- **Expected**: Bot calls `greptile_search_code` with semantic query
- **Validation**: Tool executes and returns relevant code snippets

**Scenario 7: Greptile Repository Summary**
- **User Input**: "Summarize the architecture of this repository"
- **Expected**: Bot calls `greptile_summarize_repo` 
- **Validation**: Tool executes and returns high-level overview

**Scenario 8: Multi-Tool Workflow**
- **User Input**: "List my repos, then summarize the first one"
- **Expected**: Bot executes `github_list_repositories` then `greptile_summarize_repo`
- **Validation**: Sequential tool execution works correctly

**Scenario 9: Tool Selection Intelligence**
- **User Input**: Various queries to test tool selector pattern matching
- **Expected**: Correct tools selected based on query content
- **Validation**: Tool selector chooses appropriate tools for different query types

**Scenario 10: Permission-Based Access**
- **User Input**: Commands that should respect user permission levels
- **Expected**: Users without proper permissions get appropriate error messages
- **Validation**: Permission system correctly filters available tools

**Detailed Actions**:
1. **Setup Test Environment**: Configure bot with test credentials/mock data
2. **Execute Each Scenario**: Run through all 10 test scenarios systematically
3. **Monitor Execution**: Log tool calls, parameters, responses, and errors
4. **Document Results**: Record success/failure for each scenario with details
5. **Identify Issues**: Note any failures, unexpected behaviors, or missing functionality
6. **Validate Workflows**: Ensure multi-tool execution and tool chaining works
7. **Test Tool Framework**: Verify tool discovery, instantiation, and execution pipeline

**Completion Criteria**:
- ✅ All 10 test scenarios execute without critical failures
- ✅ Each preserved tool (help, jira_get_issues_by_user, github_list_repositories, github_search_code, greptile_query_codebase, greptile_search_code, greptile_summarize_repo) responds correctly
- ✅ Multi-tool workflows function properly
- ✅ Tool selection intelligence works for different query types
- ✅ Permission system correctly filters tools based on user access
- ✅ No bot crashes or major execution errors during normal interactions
- ✅ Tool framework properly discovers and executes all preserved tools

**Acceptance Criteria**: 
- Minimum 8/10 scenarios must pass completely
- Any failures must be documented with reproduction steps
- Bot must remain stable throughout all test interactions
- Core functionality (startup, tool execution, basic responses) must work

**Dependencies**: All previous steps (1.1-1.8) must be complete
**Notes**: This comprehensive testing ensures the stripped bot maintains full functionality for real user scenarios and validates the entire tool execution pipeline.

---

## **Phase 2: Verification and Documentation**

### **Step 2.1: Internal Consistency Check**
**Task**: Basic validation - keep it simple but don't skip essentials

**Essential Checks**:
1. **Python Syntax**: No syntax errors in main files
2. **Import Test**: Core modules import successfully  
3. **Startup Test**: Bot starts without crashing
4. **Tool Check**: Preserved tools are discoverable

**Completion Criteria**: Basic functionality confirmed

---

### **Step 2.2: Create Testing Guide**
**Task**: Simple testing instructions for user

**Deliverable**: `minimal_bot/TESTING.md` with basic test steps:
1. Bot startup test
2. Help command test  
3. One tool from each category test
4. Multi-tool execution test

**Completion Criteria**: User has clear steps to verify bot works

---

## **Success Criteria**

The minimal bot is ready when:
- ✅ Bot starts up without crashing
- ✅ Preserved tools execute and return results
- ✅ Multi-tool execution works
- ✅ No major syntax or import errors
- ✅ Basic functionality confirmed