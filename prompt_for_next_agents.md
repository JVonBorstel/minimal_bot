# **CRITICAL INSTRUCTIONS FOR TOOL VALIDATION AGENTS**

## **🎯 YOUR MISSION: PROVE THESE TOOLS ACTUALLY WORK**

You are taking over **Steps 1.10, 1.11, and 1.12** of the minimal bot validation process. The previous agent just successfully validated the **Jira tool** by actually testing it and fixing real authentication issues.

**YOU MUST FOLLOW THE EXACT SAME RIGOROUS PROCESS.**

---

## **🚨 ABSOLUTE REQUIREMENTS - NO EXCEPTIONS**

### **1. REAL TESTING ONLY**
- **NO claiming tools work without actually running them**
- **NO assuming API calls will work**
- **NO mock/fake data - test with REAL APIs**
- **NO "looks good" - make it ACTUALLY work**

### **2. CREATE ACTUAL TEST SCRIPTS**
- Write Python scripts that call the tools directly
- Run the scripts and show the output
- If tools fail, debug and fix them
- Document every step with real command outputs

### **3. HANDLE AUTHENTICATION ISSUES**
- API keys might be missing/invalid
- Tokens might need specific scopes
- Endpoints might need configuration
- **FIX THESE ISSUES, don't just report them**

### **4. PROVE WITH REAL DATA**
- GitHub tools must list REAL repositories
- Greptile tools must analyze REAL codebases  
- Perplexity tools must return REAL search results
- Show actual API responses, not theoretical examples

### **5. COMMIT WORKING STATES**
- After each tool works, commit to git
- Use descriptive commit messages
- Create checkpoint saves like the previous agent

---

## **📋 WHAT THE PREVIOUS AGENT ACCOMPLISHED (YOUR STANDARD)**

The previous agent validated the Jira tool by:

1. **Created comprehensive test script** (`test_new_token.py`)
2. **Found real authentication problems** (wrong scopes, wrong URL format)
3. **Researched and fixed the issues** (found Cloud ID requirement, correct scopes)
4. **Actually tested with real Jira instance** (returned real issue data: LM-13282, LM-13048, etc.)
5. **Proved the tool works** (authentication, project access, issue retrieval)
6. **Committed working state** (git commit "jira works bitches")

**YOU MUST ACHIEVE THE SAME LEVEL OF VALIDATION FOR YOUR TOOLS.**

---

## **🔧 STEP 1.10: VALIDATE GITHUB TOOLS (HIGH PRIORITY)**

### **Your Tasks:**
1. **Create `test_github_tools.py` script**
2. **Test `github_list_repositories` with real GitHub account**
3. **Test `github_search_code` with real code search**
4. **Fix any authentication/permission issues**
5. **Show actual repository data and search results**
6. **Commit working state to git**

### **Expected Issues You MUST Solve:**
- GitHub token might need specific scopes
- API rate limits might need handling
- Repository access permissions
- Search API might have different requirements

### **Success Criteria:**
- ✅ GitHub tools return REAL user repositories
- ✅ Code search returns REAL code snippets
- ✅ No authentication errors
- ✅ Actual GitHub API responses documented
- ✅ Git commit with working state

### **Test Script Template:**
```python
#!/usr/bin/env python3
"""Test GitHub tools with real API calls."""

import asyncio
from tools.tool_executor import ToolExecutor
from config import get_config
from state_models import AppState

async def test_github_tools():
    print("🔍 TESTING GITHUB TOOLS")
    print("=" * 50)
    
    config = get_config()
    executor = ToolExecutor(config)
    app_state = AppState()
    
    # Test 1: List repositories
    print("\n📋 TEST 1: List Repositories")
    result = await executor.execute_tool("github_list_repositories", {}, app_state)
    print(f"Result: {result}")
    
    # Test 2: Search code
    print("\n🔍 TEST 2: Search Code")
    result = await executor.execute_tool("github_search_code", {"query": "authentication"}, app_state)
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_github_tools())
```

---

## **🔧 STEP 1.11: VALIDATE GREPTILE TOOLS (HIGH PRIORITY)**

### **Your Tasks:**
1. **Create `test_greptile_tools.py` script**
2. **Test all Greptile tools with real repositories**
3. **Fix any API key/endpoint issues**
4. **Show actual AI analysis results**
5. **Commit working state to git**

### **Expected Issues You MUST Solve:**
- Greptile API key configuration
- Repository URL format requirements
- API rate limits or usage quotas
- Response format validation

### **Success Criteria:**
- ✅ Greptile tools return REAL AI analysis
- ✅ Codebase queries work with actual repos
- ✅ No API authentication errors
- ✅ Actual Greptile API responses documented
- ✅ Git commit with working state

### **What to Test:**
- `greptile_query_codebase` - Query real repository code
- `greptile_search_code` - Semantic code search
- `greptile_summarize_repo` - Repository summarization

---

## **🔧 STEP 1.12: VALIDATE PERPLEXITY TOOLS (HIGH PRIORITY)**

### **Your Tasks:**
1. **Create `test_perplexity_tools.py` script**
2. **Test all Perplexity tools with real queries**
3. **Fix any API configuration issues**
4. **Show actual search/analysis results**
5. **Commit working state to git**

### **Expected Issues You MUST Solve:**
- Perplexity API key setup
- Request format requirements
- Usage limits or quotas
- Response parsing issues

### **Success Criteria:**
- ✅ Perplexity tools return REAL search results
- ✅ Web search includes actual sources
- ✅ No API authentication errors
- ✅ Actual Perplexity API responses documented
- ✅ Git commit with working state

### **What to Test:**
- `perplexity_web_search` - Real web search queries
- `perplexity_summarize_topic` - Topic summarization
- `perplexity_structured_search` - Structured information search

---

## **🔥 DEBUGGING METHODOLOGY (COPY FROM JIRA SUCCESS)**

### **When Tools Fail (THEY WILL):**

1. **Check Configuration First**
   ```bash
   python -c "from config import get_config; config = get_config(); print('GitHub token:', bool(config.get_env_value('GITHUB_TOKEN'))); print('Greptile key:', bool(config.get_env_value('GREPTILE_API_KEY'))); print('Perplexity key:', bool(config.get_env_value('PERPLEXITY_API_KEY')))"
   ```

2. **Test Direct API Calls**
   - Use `requests` to test API endpoints directly
   - Verify authentication works outside the tool framework
   - Check response formats and error messages

3. **Fix Authentication Issues**
   - Research correct API token scopes (like we did for Jira)
   - Update `.env` file with correct credentials
   - Test API access before testing tools

4. **Document Every Fix**
   - Show before/after API responses
   - Explain what was broken and how you fixed it
   - Create test scripts that prove the fix works

### **Script Templates for Direct API Testing:**

**GitHub Direct Test:**
```python
import requests
from config import get_config

config = get_config()
token = config.get_env_value('GITHUB_TOKEN')
headers = {'Authorization': f'token {token}'}

# Test repository access
response = requests.get('https://api.github.com/user/repos', headers=headers)
print(f"GitHub API Status: {response.status_code}")
print(f"Response: {response.json()[:3] if response.status_code == 200 else response.text}")
```

**Greptile Direct Test:**
```python
import requests
from config import get_config

config = get_config()
api_key = config.get_env_value('GREPTILE_API_KEY')
headers = {'Authorization': f'Bearer {api_key}'}

# Test API access
response = requests.get('https://api.greptile.com/v2/health', headers=headers)  # Adjust endpoint
print(f"Greptile API Status: {response.status_code}")
print(f"Response: {response.text}")
```

---

## **📝 DOCUMENTATION REQUIREMENTS**

### **For Each Tool, Document:**
1. **Initial State**: What errors/issues you found
2. **Debugging Process**: Steps taken to identify problems
3. **Solutions Applied**: Configuration changes, token updates, etc.
4. **Final Test Results**: Actual API responses and data
5. **Working Examples**: Prove tools work with real data

### **Git Commits Required:**
- After fixing each tool: `git commit -m "github tools working"`
- After fixing each tool: `git commit -m "greptile tools working"`  
- After fixing each tool: `git commit -m "perplexity tools working"`

---

## **🚫 UNACCEPTABLE BEHAVIORS**

### **DO NOT:**
- ❌ Claim tools work without running test scripts
- ❌ Use mock/fake data instead of real API calls
- ❌ Skip authentication debugging
- ❌ Report "looks good" without actual validation
- ❌ Leave broken tools and move to next step
- ❌ Ask user to fix issues - YOU fix them

### **DO:**
- ✅ Create and run comprehensive test scripts
- ✅ Debug and fix authentication issues
- ✅ Show actual API responses and data
- ✅ Document every problem and solution
- ✅ Commit working states to git
- ✅ Follow the successful Jira validation pattern

---

## **📊 SUCCESS METRICS**

### **Each Tool Validation is Complete When:**
1. ✅ Test script runs without errors
2. ✅ Tool returns real data from live API
3. ✅ Authentication issues resolved
4. ✅ Git commit created with working state
5. ✅ Documentation shows actual results

### **Overall Success:**
- ✅ All 3 tool categories (GitHub, Greptile, Perplexity) validated
- ✅ 3 git commits showing incremental progress
- ✅ Real data demonstrated for each tool type
- ✅ Ready for next agent to continue with Steps 1.13+

---

## **🎯 FINAL REMINDER**

The user has been burned by agents who fake results and claim things work when they don't. **DO NOT BE THAT AGENT.**

Follow the successful pattern established by the Jira validation:
1. **Test rigorously**
2. **Fix real problems** 
3. **Show actual results**
4. **Commit working code**

Your validation will be judged by whether the tools actually return real data when tested. Anything less is unacceptable.

**GO MAKE THESE TOOLS ACTUALLY WORK.** 