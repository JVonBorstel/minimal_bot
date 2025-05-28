# 🚀 Easy Cloud Hosting - Deploy in 5 Minutes

Your bot is ready to deploy! Here are the **stupidly easy** hosting options where you just upload and connect.

## ⭐ **Railway (EASIEST - Recommended)**

**Why Railway?** 
- Auto-detects everything
- Free tier available
- Deploys on every git push
- Takes 2 minutes

### **Steps:**
1. **Go to [railway.app](https://railway.app)**
2. **"Deploy from GitHub"** → Sign in and select your repo
3. **Add Environment Variables:** Click your service → Variables tab → Add:
   ```
   MICROSOFT_APP_ID=ddef1234-...
   MICROSOFT_APP_PASSWORD=your_password
   GEMINI_API_KEY=your_gemini_key
   PERPLEXITY_API_KEY=your_perplexity_key
   GITHUB_TOKEN=ghp_your_token
   JIRA_API_URL=https://company.atlassian.net
   JIRA_API_EMAIL=you@company.com
   JIRA_API_TOKEN=your_jira_token
   PORT=3978
   ```
4. **Deploy!** It auto-deploys immediately
5. **Get your URL:** `https://minimal-bot-production-1234.up.railway.app`
6. **Update Bot Framework:** Go to Azure Bot Service → Configuration → Messaging endpoint:
   ```
   https://minimal-bot-production-1234.up.railway.app/api/messages
   ```

**Done! Your bot is live and auto-deploys on every commit.**

---

## 🟢 **Render (Also Super Easy)**

**Why Render?**
- Uses your Dockerfile automatically
- Free tier available
- GitHub integration
- Custom domains

### **Steps:**
1. **Go to [render.com](https://render.com)**
2. **"New Web Service"** → Connect your GitHub repo
3. **Configure:**
   - **Name:** `minimal-bot`
   - **Environment:** `Docker`
   - **Branch:** `main`
   - **Port:** `3978`
4. **Add Environment Variables:** In the Environment section, add all your API keys
5. **Deploy!** Render builds with your Dockerfile
6. **Get URL:** `https://minimal-bot.onrender.com`
7. **Update Bot Framework endpoint:**
   ```
   https://minimal-bot.onrender.com/api/messages
   ```

---

## 🔵 **Azure App Service (Microsoft Native)**

**Why Azure?**
- Native Bot Framework support
- Easy GitHub Actions deployment
- Best integration with Bot Framework

### **Quick Azure Deploy:**
1. **Create App Service:**
   ```bash
   # In Azure Portal:
   # 1. Create "Web App" 
   # 2. Runtime: Python 3.10
   # 3. Name: your-minimal-bot
   ```

2. **GitHub Actions Deploy:**
   - Enable **Deployment Center** in Azure portal
   - Connect to GitHub repo
   - Choose GitHub Actions
   - It creates the workflow automatically!

3. **Add Environment Variables:**
   - Go to **Configuration** → **Application settings**
   - Add all your API keys

4. **Your bot URL:** `https://your-minimal-bot.azurewebsites.net`

---

## 🟡 **Google Cloud Run (Container-Based)**

**Why Cloud Run?**
- Serverless container hosting
- Pay only when used
- Auto-scaling

### **Super Easy Deploy:**
```bash
# 1. Install gcloud CLI
# 2. Run these commands:

gcloud auth login
gcloud config set project your-project-id

# Deploy directly from your directory
gcloud run deploy minimal-bot \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 3978

# Add environment variables via Cloud Console
```

**Get URL:** `https://minimal-bot-hash-uc.a.run.app`

---

## 🚀 **One-Click Deploy Buttons**

Add these to your repo README for ultimate ease:

### **Railway:**
```markdown
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template/your-repo)
```

### **Render:**
```markdown
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/yourusername/minimal_bot)
```

### **Heroku:**
```markdown
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/yourusername/minimal_bot)
```

---

## 📋 **Environment Variables Checklist**

**Required for all platforms:**
```bash
MICROSOFT_APP_ID=ddef1234-5678-90ab-cdef-1234567890ab
MICROSOFT_APP_PASSWORD=your_bot_password
GEMINI_API_KEY=your_gemini_key
PERPLEXITY_API_KEY=your_perplexity_key
GITHUB_TOKEN=ghp_your_github_token
PORT=3978
```

**Optional (for full functionality):**
```bash
JIRA_API_URL=https://yourcompany.atlassian.net
JIRA_API_EMAIL=you@company.com
JIRA_API_TOKEN=your_jira_token
GREPTILE_API_KEY=your_greptile_key
GREPTILE_GITHUB_TOKEN=your_greptile_github_token
```

---

## ✅ **After Deployment**

### **1. Test Your Bot:**
```bash
curl https://your-bot-url.com/healthz
```

### **2. Update Bot Framework:**
```bash
# In Azure Bot Service → Configuration → Messaging endpoint:
https://your-bot-url.com/api/messages
```

### **3. Test in Teams:**
- Send a message to your bot
- New users get automatic onboarding
- Existing users can use: `@augie preferences restart_onboarding`

---

## 🎯 **Recommendation: Use Railway**

**For the laziest deployment possible:**
1. Push your code to GitHub
2. Connect GitHub to Railway
3. Add environment variables
4. Update Bot Framework endpoint
5. **Done!**

Railway auto-deploys on every commit, handles everything for you, and has the best developer experience.

**Your bot will be live in under 5 minutes!** 🚀 