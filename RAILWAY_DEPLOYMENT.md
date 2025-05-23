# Railway Deployment Guide

This guide will help you deploy your minimal bot to Railway successfully.

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **Bot Framework Registration**: You need a Microsoft Bot Framework registration
3. **Environment Variables**: Prepare all required API keys and configuration

## Quick Deploy

### Option 1: Deploy from GitHub (Recommended)

1. **Connect GitHub Repository**:
   - Go to [railway.app](https://railway.app)
   - Click "Start a New Project"
   - Select "Deploy from GitHub repo"
   - Connect your GitHub account and select this repository

2. **Configure Environment Variables**:
   ```bash
   # Required Bot Framework Variables
   MICROSOFT_APP_ID=your_bot_app_id_here
   MICROSOFT_APP_PASSWORD=your_bot_password_here
   
   # Required AI/LLM API Keys
   GEMINI_API_KEY=your_gemini_api_key_here
   PERPLEXITY_API_KEY=your_perplexity_api_key_here
   
   # Optional Tool Integrations
   JIRA_API_URL=https://your-org.atlassian.net
   JIRA_API_EMAIL=your_email@company.com
   JIRA_API_TOKEN=your_jira_api_token
   
   GREPTILE_API_KEY=your_greptile_api_key
   GREPTILE_GITHUB_TOKEN=your_github_token
   
   # Database (Railway will auto-configure if you add PostgreSQL)
   DATABASE_URL=railway_will_set_this_automatically
   ```

3. **Add Environment Variables in Railway**:
   - Go to your project dashboard
   - Click on your service
   - Go to "Variables" tab
   - Add each environment variable listed above

### Option 2: Railway CLI Deploy

1. **Install Railway CLI**:
   ```bash
   npm install -g @railway/cli
   ```

2. **Login and Deploy**:
   ```bash
   railway login
   railway link
   railway up
   ```

## Environment Variables Reference

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `MICROSOFT_APP_ID` | Bot Framework App ID | `ddef1234-5678-90ab-cdef-1234567890ab` |
| `MICROSOFT_APP_PASSWORD` | Bot Framework Password | `your_secret_password` |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIza...` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PERPLEXITY_API_KEY` | Perplexity AI API Key | - |
| `JIRA_API_URL` | Your Jira instance URL | - |
| `JIRA_API_EMAIL` | Jira account email | - |
| `JIRA_API_TOKEN` | Jira API token | - |
| `GREPTILE_API_KEY` | Greptile API key | - |
| `GREPTILE_GITHUB_TOKEN` | GitHub token for Greptile | - |
| `LOG_LEVEL` | Logging level | `INFO` |

## Database Setup

### Option 1: Add PostgreSQL (Recommended)
1. In Railway dashboard, click "Add Service"
2. Select "PostgreSQL"
3. Railway will automatically set `DATABASE_URL`

### Option 2: Use SQLite (Default)
- No additional setup needed
- Uses local SQLite file (data may not persist across deployments)

## Verification Steps

1. **Check Deployment Status**:
   - Go to Railway dashboard
   - Ensure deployment shows "Success"

2. **Test Health Endpoint**:
   ```bash
   curl https://your-app-url.railway.app/healthz
   ```
   Should return status "OK"

3. **Test Bot Endpoint**:
   ```bash
   curl https://your-app-url.railway.app/api/messages
   ```

4. **Configure Bot Framework**:
   - Go to [Azure Bot Services](https://portal.azure.com)
   - Update messaging endpoint to: `https://your-app-url.railway.app/api/messages`

## Common Issues & Solutions

### Deployment Fails

**Issue**: Build fails during deployment
**Solution**: 
- Check Railway logs for specific errors
- Ensure all dependencies in `requirements.txt` are valid
- Verify Dockerfile syntax

### Bot Not Responding

**Issue**: Bot receives messages but doesn't respond
**Solution**:
- Verify `MICROSOFT_APP_ID` and `MICROSOFT_APP_PASSWORD` are correct
- Check messaging endpoint URL in Azure Bot Service
- Review Railway logs for errors

### Health Check Failing

**Issue**: Railway shows service as unhealthy
**Solution**:
- Ensure `/healthz` endpoint is accessible
- Check that app is binding to `0.0.0.0` not `localhost`
- Verify port configuration uses Railway's `PORT` environment variable

### Database Issues

**Issue**: State not persisting between deployments
**Solution**:
- Add PostgreSQL service in Railway
- Configure `DATABASE_URL` environment variable
- Run database migrations

## Railway Configuration Files

The following files are configured for Railway:

- **`railway.toml`**: Railway service configuration
- **`Dockerfile`**: Container build instructions  
- **`.dockerignore`**: Files excluded from Docker build
- **`requirements.txt`**: Python dependencies

## Support

If you encounter issues:

1. Check Railway deployment logs
2. Review the health check endpoint: `/healthz`
3. Verify all environment variables are set correctly
4. Ensure Bot Framework messaging endpoint is updated

## Security Notes

- Never commit API keys or passwords to Git
- Use Railway's environment variables feature for secrets
- Regularly rotate API keys and tokens
- Enable Railway's security features if available 