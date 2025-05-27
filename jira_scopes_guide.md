# Jira API Scopes & Permissions Guide

## 🎯 **DEFINITIVE ANSWER: Use Classic Scopes!**

**✅ OFFICIAL ATLASSIAN RECOMMENDATION**: *"When choosing your scopes, the recommendation is to use classic scopes."*

**For your ChatOps bot, select these Classic scopes:**
- ✅ `read:jira-user` - View user profiles, usernames, email addresses, and avatars
- ✅ `read:jira-work` - Read Jira project and issue data, search for issues and objects like attachments and worklogs  
- ✅ `write:jira-work` - Create and edit issues, post comments, create worklogs, and delete issues
- ✅ `manage:jira-project` - Create and edit project settings and new project-level objects (versions, components)
- ✅ `manage:jira-configuration` - Take Jira administration actions (create projects, custom fields, view workflows, manage issue link types)
- ✅ `manage:jira-webhook` - Fetch, register, refresh, and delete dynamically declared Jira webhooks

**These 6 classic scopes will cover ALL your current and future bot needs!**

---

## 🔄 **Classic vs Granular Scopes - Official Comparison**

### **Classic Scopes (OFFICIALLY RECOMMENDED)**
- 👍 **Atlassian's official recommendation** - "use classic scopes"
- 👍 **Comprehensive coverage** - Each classic scope covers multiple related operations
- 👍 **Simple management** - Just 6 scopes vs 50+ granular ones  
- 👍 **Future-proof** - New features automatically included
- 👍 **Less breaking** - Won't miss edge case permissions
- 👍 **Scope limit friendly** - Atlassian recommends <50 scopes total

### **Granular Scopes** 
- 👎 **Not recommended** - "Use these scopes only when you can't use classic scopes"
- 👎 **Complex setup** - Need 20-50+ specific scopes
- 👎 **Easy to break** - One missing scope = broken functionality  
- 👎 **Maintenance burden** - Must update when adding features
- 👎 **Hits scope limits** - Atlassian warns against >50 scopes

**🏆 Winner: Classic scopes for internal ChatOps bots!**

---

## 📋 **Step-by-Step Token Creation**

1. **Go to**: https://take3tech.atlassian.net/secure/ViewProfile.jspa
2. **Click**: "Security" tab  
3. **Scroll to**: "API tokens"
4. **Click**: "Create and manage API tokens"
5. **Click**: "Create API token with scopes"
6. **Name**: "ChatOps Bot - Full Access"
7. **Select app**: "Jira"
8. **Select these 6 classic scopes**:
   - ✅ `read:jira-user`
   - ✅ `read:jira-work` 
   - ✅ `write:jira-work`
   - ✅ `manage:jira-project`
   - ✅ `manage:jira-configuration`
   - ✅ `manage:jira-webhook`
9. **Create token**
10. **Copy immediately** - You can only see it once!

---

## 🧪 **Test Your New Token**

After creating the token, update your `.env`:

```bash
JIRA_API_TOKEN="your_new_scoped_token_here"
```

Then run:
```bash
python test_new_jira_token.py
```

**Expected result**: ✅ All tests pass, shows all 6 tickets!

---

## ❓ **Why Classic Scopes Win**

| **Issue** | **Classic Scopes** | **Granular Scopes** |
|-----------|-------------------|---------------------|
| **Missing permission** | Rarely happens (broad coverage) | Common (need exact scope) |
| **New features** | Automatically included | Must manually add scopes |
| **Setup complexity** | 5 minutes | 30+ minutes research |
| **Maintenance** | Zero ongoing work | Constant scope management |
| **Debugging** | Simple (6 scopes to check) | Complex (50+ scopes to verify) |
| **Future Jira updates** | Just works | May break existing functionality |

**🎯 For a reliable ChatOps bot = Classic scopes every time!**

---

## 🚨 **Important Notes**

- **API tokens with scopes** require OAuth 2.0 flow (newer method)
- **Unscoped API tokens** use basic auth (being deprecated)
- **User permissions** still apply - scopes don't override Jira permissions
- **Maximum 50 scopes** recommended per token (classic scopes use only 6!)

Your new scoped token will be **more secure** and **more reliable** than the current unscoped one! 🔒✨

---

## 🎯 **Current Bot Requirements (Essential)**

### **Read Operations**
- ✅ **Browse Projects** - View project list and details
- ✅ **Browse Issues** - Search and view issues across projects  
- ✅ **View Issue Details** - Access issue summaries, descriptions, status, etc.
- ✅ **View User Profiles** - Access user information and assignee details

### **Write Operations** 
- ✅ **Create Issues** - Create new stories, bugs, tasks
- ✅ **Edit Issues** - Update issue fields (for story builder enhancements)

### **Project Access**
- ✅ **LM Project** - Primary project for your tickets
- ✅ **Any Additional Projects** - Where you might create/manage issues

---

## 🚀 **Recommended Extended Scopes (Future-Proof)**

### **Issue Management**
- 📝 **Add Comments** - Comment on issues for bot interactions
- 🔄 **Transition Issues** - Move tickets between workflow states
- 🏷️ **Manage Labels** - Add/remove labels for categorization
- 🔗 **Link Issues** - Create relationships between tickets
- 📎 **Manage Attachments** - Upload files, screenshots, logs
- ⏰ **Set Due Dates** - Manage deadlines and scheduling
- 📊 **Update Story Points** - Agile estimation management

### **Advanced Features**
- 👥 **Assign Issues** - Change assignees programmatically  
- 🔍 **Advanced Search** - Complex JQL queries for reporting
- 📋 **Manage Boards** - Access Agile/Kanban boards (if using Jira Software)
- 🏃 **Sprint Management** - Add/remove issues from sprints
- 📈 **View Reports** - Access project metrics and reports
- ⚙️ **Manage Workflows** - View available transitions and statuses

### **Notification & Integration**
- 🔔 **Webhooks** - Set up automated notifications
- 👁️ **Watch Issues** - Subscribe to issue updates
- 📧 **Email Notifications** - Manage notification preferences

---

## 🛠️ **How to Set Up Proper API Token**

### **Step 1: Generate New API Token**
```
1. Go to: https://take3tech.atlassian.net/secure/ViewProfile.jspa
2. Click "Security" tab
3. Scroll to "API tokens" 
4. Click "Create and manage API tokens"
5. Click "Create API token"
6. Name: "ChatOps Bot - Full Access"
7. Copy the generated token immediately
```

### **Step 2: Verify User Permissions**
Make sure your Jira user (jvonborstel@take3tech.com) has these **Jira Permissions**:

#### **Global Permissions**
- ✅ **Jira System Administrators** (if you're admin)
- ✅ **Jira Users** (minimum required)

#### **Project Permissions** (for each project like LM)
- ✅ **Browse Projects** 
- ✅ **Create Issues**
- ✅ **Edit Issues** 
- ✅ **Delete Issues** (optional)
- ✅ **Assign Issues**
- ✅ **Assignable User** (to be assigned issues)
- ✅ **Resolve Issues**
- ✅ **Close Issues** 
- ✅ **Add Comments**
- ✅ **Edit All Comments**
- ✅ **Transition Issues**
- ✅ **Link Issues**
- ✅ **Manage Attachments**
- ✅ **Work on Issues** (for time tracking)

#### **Agile/Software Permissions** (if using Jira Software)
- ✅ **Manage Sprints**
- ✅ **View Development Tools**
- ✅ **Edit Sprint**

### **Step 3: Update Configuration**
```bash
# Update .env file
JIRA_API_TOKEN="your_new_token_here"
JIRA_DEFAULT_PROJECT_KEY="LM"  # Fix the project key too
```

---

## 🔧 **Troubleshooting Permission Issues**

### **Common Problems & Solutions**

#### **"No projects found"**
- **Cause**: User lacks "Browse Projects" permission
- **Fix**: Admin needs to add you to project roles

#### **"Issue does not exist"** 
- **Cause**: No "Browse Issues" permission for that project
- **Fix**: Add user to appropriate project role (Developer, etc.)

#### **"Cannot create issues"**
- **Cause**: Missing "Create Issues" permission  
- **Fix**: Project admin adds "Create Issues" to your role

#### **"Cannot transition"**
- **Cause**: Workflow restrictions or missing "Transition Issues" permission
- **Fix**: Check workflow configuration and user permissions

### **Permission Verification Commands**
```bash
# Test basic access
python show_my_jira_tickets.py

# Test project access  
python explore_jira_tickets.py

# Test story creation (after fixing project key)
python -c "
import asyncio
from test_tool_reliability_fixed import FixedToolReliabilityTester
tester = FixedToolReliabilityTester()
asyncio.run(tester.test_jira_tools())
"
```

---

## 📋 **Recommended Jira User Setup**

### **Ideal Role Assignment**
For maximum bot functionality, ensure your user has:

1. **Project Role**: `Developer` or `Administrator` 
2. **Permission Scheme**: `Default Permission Scheme` (or custom with full access)
3. **Notification Scheme**: Appropriate for receiving updates
4. **Issue Security**: Access to all relevant security levels

### **API Token Best Practices**
- 🔒 **Regenerate Quarterly** - For security
- 📝 **Document Usage** - Keep track of what uses each token  
- 🏷️ **Descriptive Names** - "ChatOps Bot - Full Access" not "Token1"
- 🔄 **Test After Creation** - Verify permissions immediately
- 🗂️ **Separate Tokens** - Different tokens for different applications

---

## 🎯 **Testing Your Setup**

Once configured, your bot should be able to:

✅ List all your 6 tickets (LM-13048, LM-13282, etc.)  
✅ Create new stories in LM project  
✅ Update ticket fields and status  
✅ Add comments and labels  
✅ Search across all accessible projects  
✅ Manage assignments and priorities  

**Test command**: `python show_my_jira_tickets.py` should show all 6 tickets! 