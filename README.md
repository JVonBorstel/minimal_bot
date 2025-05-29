# Minimal Bot

A sophisticated AI-powered chatbot with dual-storage architecture, user authentication, onboarding workflows, and comprehensive tool integration.

## 🎯 Features

- **Dual Database Architecture**: Redis for real-time conversation state, SQLite for persistent user data
- **User Authentication & Profiles**: Role-based access control with user onboarding
- **AI Integration**: Google Gemini AI with tool selection and streaming responses
- **Multi-Environment Support**: Local development and Railway production deployment
- **Tool Integration**: Jira, GitHub, Greptile, Perplexity, and more
- **Comprehensive Database Management**: Built-in tools for inspection and debugging

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Redis server (WSL or local installation)
- Bot Framework Emulator (for testing)

### Installation

1. **Clone and setup:**

   ```bash
   git clone <your-repo>
   cd minimal_bot
   pip install -r requirements.txt
   ```

2. **Configure environment:**

   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

3. **Setup databases:**

   ```bash
   # Start Redis (if using WSL)
   wsl redis-server --daemonize yes
   
   # Initialize database tables
   python scripts/setup_databases.py
   ```

4. **Start the bot:**

   ```bash
   python app.py
   ```

## 📊 Database Management

The bot includes comprehensive database management tools for both development and production environments.

### Quick Commands

```bash
# Database health check and setup
python scripts/setup_databases.py

# Inspect databases (auto-detects environment)
python scripts/db_inspector.py

# View user profiles and recent conversations
python scripts/db_inspector.py --users 10 --conversations 5

# Search conversations for debugging
python scripts/db_inspector.py --search "error"

# Export data for backup
python scripts/db_inspector.py --export backup.json
```

### Documentation

- **📖 [Complete Database Management Guide](docs/DATABASE_MANAGEMENT.md)** - Comprehensive documentation
- **⚡ [Quick Reference Card](docs/DATABASE_QUICK_REFERENCE.md)** - Essential commands at a glance  
- **🛠️ [Scripts Documentation](scripts/README.md)** - Available utility scripts

### GUI Tools

- **RedisInsight**: Visual Redis browser (`winget install RedisInsight.RedisInsight`)
- **DB Browser for SQLite**: SQLite database viewer ([sqlitebrowser.org](https://sqlitebrowser.org))

## 🏗️ Architecture

### Database Systems

| Component | Local Development | Railway Production |
|-----------|-------------------|-------------------|
| **Conversation State** | WSL Redis (localhost:6379) | Railway Redis Service |
| **User Profiles** | SQLite (`state.sqlite`) | Railway PostgreSQL |
| **Bot State Storage** | SQLite fallback | Redis primary |

### Key Components

- **`bot_core/`**: Core bot logic and message handling
- **`user_auth/`**: User authentication and profile management
- **`workflows/`**: Onboarding and workflow management
- **`tools/`**: External service integrations
- **`scripts/`**: Database management and utility scripts
- **`docs/`**: Comprehensive documentation

## 🛠️ Development

### Daily Workflow

```bash
# 1. Start Redis
wsl redis-server --daemonize yes

# 2. Check database health
python scripts/setup_databases.py

# 3. Start bot
python app.py

# 4. Monitor databases (optional)
python scripts/db_inspector.py --connection-info
```

### Debugging

```bash
# Find conversation errors
python scripts/db_inspector.py --search "error"

# Export problematic conversations
python scripts/db_inspector.py --search "user@example.com" --export debug.json

# Check specific user's onboarding
python scripts/db_inspector.py --search "onboarding"
```

### Testing

```bash
# Run tests
pytest

# Test database setup
python scripts/setup_databases.py

# Test database connections
python scripts/db_inspector.py --connection-info
```

## 🚂 Railway Deployment

### Setup Environment Variables

In your Railway project, set:

```bash
# Required for Redis
REDIS_URL=redis://user:password@host:port/db

# Required for PostgreSQL  
DATABASE_URL=postgresql://user:password@host:port/database

# Optional bot configuration
GEMINI_API_KEY=your-gemini-key
JIRA_API_URL=your-jira-url
# ... other API keys
```

### Monitor Production

```bash
# Set environment variables locally
$env:REDIS_URL = "your-railway-redis-url"
$env:DATABASE_URL = "your-railway-db-url"

# Inspect production databases
python scripts/db_inspector.py --env railway

# Export production data
python scripts/db_inspector.py --env railway --export production_backup.json

# Search production issues
python scripts/db_inspector.py --env railway --search "error"
```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Core Bot Settings
PORT=3978
LOG_LEVEL=INFO
MEMORY_TYPE=redis  # or sqlite

# Database Paths
STATE_DB_PATH=state.sqlite
REDIS_HOST=localhost
REDIS_PORT=6379

# AI Models
GEMINI_MODEL=models/gemini-1.5-pro-latest
GEMINI_API_KEY=your-api-key

# External Services
JIRA_API_URL=your-jira-url
GITHUB_TOKEN=your-github-token
```

### Bot Framework

Connect with Bot Framework Emulator:

- **Endpoint**: `http://127.0.0.1:3978/api/messages`
- **App ID**: (leave blank for local testing)
- **App Password**: (leave blank for local testing)

## 🆘 Troubleshooting

### Redis Connection Issues

```bash
# Start Redis
wsl redis-server --daemonize yes

# Test connection
wsl redis-cli ping  # Should return PONG

# Check bot connection
python scripts/db_inspector.py --connection-info
```

### SQLite Database Issues

```bash
# Recreate missing tables
python scripts/setup_databases.py

# Check database integrity
sqlite3 state.sqlite "PRAGMA integrity_check;"
```

### Bot Framework Connection

1. Ensure bot is running: `python app.py`
2. Check endpoint in emulator: `http://127.0.0.1:3978/api/messages`
3. Verify no firewall blocking port 3978

### Railway Deployment Issues

```bash
# Test Railway connections locally
python scripts/db_inspector.py --env railway --connection-info

# Check environment variables are set
echo $env:REDIS_URL
echo $env:DATABASE_URL
```

## 📚 Documentation

- **[Database Management Guide](docs/DATABASE_MANAGEMENT.md)** - Complete database documentation
- **[Quick Reference](docs/DATABASE_QUICK_REFERENCE.md)** - Essential commands
- **[Scripts Documentation](scripts/README.md)** - Utility scripts reference

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes without modifying core bot functionality
4. Test with database management tools:

   ```bash
   python scripts/setup_databases.py
   python scripts/db_inspector.py --connection-info
   ```

5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

---

## 🎉 Getting Help

- **Database Issues**: See [Database Management Guide](docs/DATABASE_MANAGEMENT.md)
- **Quick Commands**: See [Quick Reference](docs/DATABASE_QUICK_REFERENCE.md)
- **Bot Framework**: Refer to [Microsoft Bot Framework Documentation](https://docs.microsoft.com/en-us/azure/bot-service/)

**Happy coding!** 🤖
