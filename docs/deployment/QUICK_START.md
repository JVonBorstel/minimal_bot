# ⚡ Quick Start - Deploy Your Minimal Bot

Your minimal bot is **production-ready** and fully validated! Here's how to get it deployed and integrated with your team's existing app bot.

## 🚀 **Ultra-Quick Deployment (Windows)**

### **Option 1: PowerShell Script (Easiest)**
```powershell
# Run the automated deployment script
.\deploy.ps1

# It will:
# - Check prerequisites 
# - Run validation tests
# - Deploy the bot
# - Verify health
```

### **Option 2: Docker Compose (Recommended)**
```bash
# Make sure you have .env file with your API keys
docker-compose up -d

# Check health
curl http://localhost:3978/healthz
```

### **Option 3: Direct Python**
```bash
pip install -r requirements.txt
python app.py
```

## 📋 **What You Need Before Deploying**

### **1. Environment Variables (.env file)**
```bash
# Bot Framework (you already have these)
MICROSOFT_APP_ID="ddef1234-..."
MICROSOFT_APP_PASSWORD="your_password"

# API Keys (copy from your current setup)
GEMINI_API_KEY="your_gemini_key"
PERPLEXITY_API_KEY="your_perplexity_key"
GITHUB_TOKEN="ghp_your_github_token"

# Jira (if you use Jira)
JIRA_API_URL="https://yourcompany.atlassian.net"
JIRA_API_EMAIL="your.email@company.com"
JIRA_API_TOKEN="your_jira_token"

# Optional
GREPTILE_API_KEY="your_greptile_key"
GREPTILE_GITHUB_TOKEN="your_greptile_github_token"
```

## 🔗 **Integration with Your Team's App Bot**

### **Quick Integration Options:**

#### **Option A: Complete Replacement**
1. Deploy the minimal bot
2. Update your Bot Framework registration messaging endpoint:
   - From: `https://your-old-bot.azurewebsites.net/api/messages`
   - To: `https://your-minimal-bot.azurewebsites.net/api/messages`

#### **Option B: Gradual Migration**
1. Deploy minimal bot on different port/URL
2. Route specific requests (@augie commands) to new bot
3. Keep existing bot for other functionality
4. Gradually migrate features

#### **Option C: Microservice Style**
1. Keep both bots running
2. Use your existing bot as a proxy
3. Route specific tool requests to minimal bot

## ✅ **Validation Status**

Your bot has been thoroughly tested:

- ✅ **Onboarding System**: 100% test success (7/7 test categories)
- ✅ **Tool Integration**: 12 tools loaded and functional
- ✅ **Database**: SQLite persistence working
- ✅ **Health Checks**: Monitoring endpoints ready
- ✅ **Bot Framework**: Microsoft Bot integration ready

## 🎯 **After Deployment**

### **1. Verify It's Working**
```bash
# Health check
curl http://localhost:3978/healthz

# Should return:
{
  "overall_status": "OK",
  "components": {
    "LLM API": {"status": "OK"},
    "GitHub API": {"status": "OK"},
    "Database": {"status": "OK"}
  }
}
```

### **2. Team Onboarding**
- New team members will automatically get onboarded
- Existing members can restart: `@augie preferences restart_onboarding`
- Admins can manage: `@augie onboarding_admin list_incomplete`

### **3. Monitor Usage**
```bash
# Docker logs
docker-compose logs -f minimal-bot

# Or if using Python directly
tail -f bot.log
```

## 🆘 **If Something Goes Wrong**

### **Check Health**
```bash
curl http://localhost:3978/healthz
```

### **Check Logs**
```bash
# Docker
docker-compose logs minimal-bot

# Python
tail -f bot.log
```

### **Quick Tests**
```bash
python tests\debug\test_basic_startup.py
python tests\scenarios\test_onboarding_system.py
```

## 📚 **More Detailed Info**

- **Full Deployment Guide**: `DEPLOYMENT_GUIDE.md`
- **Test Organization**: `tests/README.md`
- **Test Results Summary**: `TEST_ORGANIZATION_SUMMARY.md`

## 🎉 **You're Ready!**

Your minimal bot is production-ready with:
- **Complete onboarding system** (validated)
- **12 functional tools** (GitHub, Jira, Help, etc.)
- **Robust error handling**
- **Health monitoring**
- **Easy deployment options**

**Just run `.\deploy.ps1` and you're live!** 🚀 