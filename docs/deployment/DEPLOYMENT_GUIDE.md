# 🚀 Minimal Bot Deployment Guide

## 📋 **Pre-Deployment Checklist**

✅ **Validated Components:**
- [x] Onboarding system (100% test success)
- [x] All 12 tools loaded and functional  
- [x] Database persistence working
- [x] Health checks operational
- [x] Bot Framework integration ready

## 🔧 **Deployment Options**

### **Option 1: Quick Docker Deployment** ⚡
```bash
# 1. Ensure your .env file has all required variables
cp .env.example .env  # If you don't have .env yet
# Edit .env with your actual API keys

# 2. Deploy with Docker Compose
docker-compose up -d

# 3. Check health
curl http://localhost:3978/healthz

# Bot is now running on port 3978!
```

### **Option 2: Direct Python Deployment** 🐍
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export MICROSOFT_APP_ID="your_app_id"
export MICROSOFT_APP_PASSWORD="your_app_password"
# ... other env vars from .env

# 3. Run the bot
python app.py

# Bot starts on http://localhost:3978
```

### **Option 3: Cloud Deployment** ☁️

#### **Azure App Service** (Recommended for Bot Framework)
```bash
# 1. Login to Azure
az login

# 2. Create resource group
az group create --name minimal-bot-rg --location eastus

# 3. Create App Service plan
az appservice plan create --name minimal-bot-plan --resource-group minimal-bot-rg --sku B1 --is-linux

# 4. Create web app
az webapp create --resource-group minimal-bot-rg --plan minimal-bot-plan --name your-minimal-bot --deployment-container-image-name your-repo/minimal-bot:latest

# 5. Configure environment variables
az webapp config appsettings set --resource-group minimal-bot-rg --name your-minimal-bot --settings \
  MICROSOFT_APP_ID="your_app_id" \
  MICROSOFT_APP_PASSWORD="your_app_password" \
  GEMINI_API_KEY="your_key" \
  # ... add all your env vars
```

## 🔗 **Integration with Your Team's Existing App Bot**

### **Scenario 1: Replace Existing Bot**
If you want to completely replace your current bot:

1. **Update Bot Framework Registration:**
   ```bash
   # In Azure Bot Service, update the messaging endpoint:
   # Old: https://your-old-bot.azurewebsites.net/api/messages
   # New: https://your-minimal-bot.azurewebsites.net/api/messages
   ```

2. **Migrate User Data:**
   ```python
   # Run migration script (if needed)
   python run_migrations.py
   ```

### **Scenario 2: Gradual Migration**
For a safer transition:

1. **Set Up Parallel Deployment:**
   ```yaml
   # docker-compose.yml
   services:
     minimal-bot:
       # ... existing config
       ports:
         - "3978:3978"  # New bot
     
     legacy-bot:
       # ... your old bot config  
       ports:
         - "3979:3978"  # Keep old bot running
   ```

2. **Route Traffic Gradually:**
   ```javascript
   // In your Teams app, route based on user/feature flags
   const botEndpoint = userProfile.useBetaBot 
     ? "https://your-minimal-bot.azurewebsites.net/api/messages"
     : "https://your-old-bot.azurewebsites.net/api/messages";
   ```

### **Scenario 3: Microservice Integration**
Keep both bots and route specific functions:

1. **Configure Function Routing:**
   ```python
   # In your main bot, proxy specific requests
   if user_query.startswith("@augie"):
       # Route to minimal bot
       response = await forward_to_minimal_bot(user_query)
   else:
       # Handle with existing bot
       response = await handle_locally(user_query)
   ```

## 📊 **Environment Variables Required**

### **Critical Bot Framework Variables:**
```bash
MICROSOFT_APP_ID="ddef1234-5678-90ab-cdef-1234567890ab"
MICROSOFT_APP_PASSWORD="your_bot_password"
```

### **API Integration Variables:**
```bash
# LLM
GEMINI_API_KEY="your_gemini_key"
PERPLEXITY_API_KEY="your_perplexity_key"

# Development Tools
GITHUB_TOKEN="ghp_your_github_token"
JIRA_API_URL="https://yourcompany.atlassian.net"
JIRA_API_EMAIL="your.email@company.com"
JIRA_API_TOKEN="your_jira_token"

# Code Search
GREPTILE_API_KEY="your_greptile_key"
GREPTILE_GITHUB_TOKEN="your_greptile_github_token"
```

### **Optional Configuration:**
```bash
# Database
DATABASE_TYPE="sqlite"  # or "redis"
REDIS_URL="redis://localhost:6379/0"

# Logging
LOG_LEVEL="INFO"
```

## 🏥 **Health Monitoring**

### **Health Check Endpoints:**
- **Primary**: `GET /healthz`
- **Response Format**:
  ```json
  {
    "overall_status": "OK",
    "components": {
      "LLM API": {"status": "OK", "response_time": "234ms"},
      "GitHub API": {"status": "OK"},
      "Jira API": {"status": "OK"},
      "Database": {"status": "OK"}
    },
    "version": "1.0.0"
  }
  ```

### **Monitoring Setup:**
```bash
# Set up health monitoring
curl -f http://your-bot-url/healthz || alert_team

# Or with docker-compose (health checks built-in)
docker-compose ps  # Shows health status
```

## 🔄 **Migration Steps from Existing Bot**

### **1. Backup Current Bot:**
```bash
# Export current bot configuration
az bot show --name your-existing-bot --resource-group your-rg > bot-backup.json
```

### **2. Test New Bot Functionality:**
```bash
# Run comprehensive tests
python tests/scenarios/test_onboarding_system.py
python tests/integration/test_full_bot_integration.py
```

### **3. Deploy New Bot:**
```bash
# Deploy minimal bot
docker-compose up -d

# Verify health
curl http://your-minimal-bot-url/healthz
```

### **4. Update Bot Registration:**
```bash
# Update messaging endpoint in Azure Bot Service
az bot update --name your-bot --resource-group your-rg \
  --endpoint https://your-minimal-bot.azurewebsites.net/api/messages
```

### **5. Monitor & Rollback Plan:**
```bash
# Monitor logs
docker-compose logs -f minimal-bot

# Quick rollback if needed
az bot update --name your-bot --resource-group your-rg \
  --endpoint https://your-old-bot.azurewebsites.net/api/messages
```

## 🚀 **Post-Deployment Configuration**

### **1. Team Onboarding:**
Once deployed, team members will automatically get onboarded:
- New users get guided setup (validated with 100% test success)
- Existing users can restart onboarding: `@augie preferences restart_onboarding`

### **2. Configure Team-Specific Tools:**
```python
# Update config.py for your team's specific settings
JIRA_PROJECT_KEYS = ["MYTEAM", "PLATFORM"]
GITHUB_ORGS = ["your-org"]
DEFAULT_REPOSITORIES = ["main-app", "api-service"]
```

### **3. Set Up Permissions:**
```python
# Configure user roles in your team
# Admins can manage with: @augie onboarding_admin list_incomplete
```

## 📈 **Success Metrics**

After deployment, monitor:
- ✅ **Onboarding completion rate** 
- ✅ **Tool usage statistics**
- ✅ **API response times**
- ✅ **User satisfaction**

## 🆘 **Troubleshooting**

### **Common Issues:**

1. **Bot not responding:**
   ```bash
   # Check health
   curl http://your-bot-url/healthz
   
   # Check logs
   docker-compose logs minimal-bot
   ```

2. **API keys not working:**
   ```bash
   # Test individual tools
   python tests/debug/quick_tool_validation.py
   ```

3. **Database issues:**
   ```bash
   # Check database
   python tests/database/test_database_examine.py
   ```

## 🎯 **Next Steps**

1. **Deploy** using one of the options above
2. **Test** the deployment with health checks
3. **Update** your Bot Framework registration
4. **Monitor** the migration
5. **Train** your team on the new features

Your minimal bot is **production-ready** and thoroughly tested! 🚀 