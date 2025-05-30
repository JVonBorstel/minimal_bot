# Database Management Guide

This guide covers how to inspect, manage, and troubleshoot the Minimal Bot's databases in both local development and Railway production environments.

## 📊 Database Architecture

Your bot uses a **dual-storage system**:

- **Redis** (Primary): Real-time conversation state, session management, bot memory
- **SQLite** (Secondary): User profiles, authentication data, persistent storage

### Local vs Railway

| Environment | Redis | SQLite |
|-------------|-------|--------|
| **Local** | WSL Redis (localhost:6379) | `state.sqlite` file |
| **Railway** | Railway Redis service | Railway PostgreSQL (via DATABASE_URL) |

## 🚀 Quick Start

### 1. Setup Databases

```bash
# Run the setup script to initialize everything
python scripts/setup_databases.py
```

This will:

- Create missing SQLite tables (`user_profiles`, `bot_state`)
- Test Redis connectivity
- Verify database inspector functionality

### 2. Start Redis (Local Development)

```bash
# Start Redis on WSL
wsl redis-server --daemonize yes

# Verify it's running
wsl redis-cli ping
# Should return: PONG
```

### 3. Inspect Your Databases

```bash
# Quick overview of everything
python scripts/db_inspector.py

# View specific data
python scripts/db_inspector.py --users 10
python scripts/db_inspector.py --conversations 5
python scripts/db_inspector.py --search "hello"
```

## 🔧 Database Inspector Tool

The `scripts/db_inspector.py` script automatically detects your environment and provides access to both local and Railway databases.

### Basic Usage

```bash
# Auto-detect environment and show overview
python scripts/db_inspector.py

# Force specific environment
python scripts/db_inspector.py --env local
python scripts/db_inspector.py --env railway

# Show connection configuration
python scripts/db_inspector.py --connection-info
```

### Data Inspection

```bash
# View user profiles
python scripts/db_inspector.py --users 20

# View recent conversations
python scripts/db_inspector.py --conversations 10

# View SQLite table structure
python scripts/db_inspector.py --sqlite-tables

# Search conversations for specific text
python scripts/db_inspector.py --search "error"
python scripts/db_inspector.py --search "onboarding"
```

### Data Management

```bash
# Export conversations to JSON
python scripts/db_inspector.py --export backup.json
python scripts/db_inspector.py --export conversations_$(date +%Y%m%d).json

# Clear Redis data (with confirmation)
python scripts/db_inspector.py --clear-redis
```

### Railway Access

To inspect Railway databases, set the environment variables:

```bash
# Windows PowerShell
$env:REDIS_URL = "redis://your-railway-redis-url"
$env:DATABASE_URL = "postgresql://your-railway-db-url"

# Then run inspector
python scripts/db_inspector.py --env railway
```

## 🖥️ GUI Tools

### RedisInsight (Redis GUI)

**Installation:**

```bash
winget install RedisInsight.RedisInsight
```

**Setup:**

1. Open RedisInsight
2. Add database connection:
   - Host: `localhost`
   - Port: `6379`
   - Name: `Local Bot Redis`

**Usage:**

- Browse Redis keys visually
- Execute Redis commands
- Monitor real-time performance
- View conversation data in structured format

### DB Browser for SQLite

**Installation:**
Download from [sqlitebrowser.org](https://sqlitebrowser.org)

**Setup:**

1. Open DB Browser for SQLite  
2. File → Open Database → Select `state.sqlite`

**Usage:**

- Browse tables (`user_profiles`, `bot_state`)
- Execute SQL queries
- Edit data directly
- Export/import data

## 🛠️ Advanced Management

### Direct Redis Commands (WSL)

```bash
# Connect to Redis CLI
wsl redis-cli

# View all keys
KEYS "*"

# View conversation keys only
KEYS "*conversation*"

# Get specific conversation
GET "session-id-here"

# View Redis information
INFO

# Clear all data (careful!)
FLUSHALL

# Exit
exit
```

### SQLite Commands

```bash
# Open SQLite CLI
sqlite3 state.sqlite

# View tables
.tables

# View user profiles
SELECT user_id, display_name, assigned_role FROM user_profiles;

# View table schema
.schema user_profiles

# Count records
SELECT COUNT(*) FROM user_profiles;
SELECT COUNT(*) FROM bot_state;

# Exit
.quit
```

### Environment Variables

For Railway access, you need these environment variables:

```bash
# Required for Railway Redis access
REDIS_URL=redis://user:password@host:port/db

# Required for Railway PostgreSQL access  
DATABASE_URL=postgresql://user:password@host:port/database

# Optional: Force environment detection
RAILWAY_ENVIRONMENT=production
```

## 🔍 Troubleshooting

### Redis Connection Issues

**Problem:** `ConnectionError: Could not connect to Redis`

**Solutions:**

1. **Start Redis on WSL:**

   ```bash
   wsl redis-server --daemonize yes
   ```

2. **Check if Redis is running:**

   ```bash
   wsl redis-cli ping
   ```

3. **Check Redis logs:**

   ```bash
   wsl tail -f /var/log/redis/redis-server.log
   ```

### SQLite Issues

**Problem:** `no such table: user_profiles`

**Solution:**

```bash
python scripts/setup_databases.py
```

**Problem:** `database is locked`

**Solutions:**

1. Stop the bot: `Ctrl+C` in bot terminal
2. Close any open SQLite connections
3. Restart the bot

### Railway Access Issues

**Problem:** Can't connect to Railway databases

**Solutions:**

1. **Get connection URLs from Railway dashboard:**
   - Go to your Railway project
   - Variables tab
   - Copy `REDIS_URL` and `DATABASE_URL`

2. **Set environment variables:**

   ```bash
   $env:REDIS_URL = "your-redis-url"
   $env:DATABASE_URL = "your-database-url"
   ```

3. **Test connection:**

   ```bash
   python scripts/db_inspector.py --env railway --connection-info
   ```

## 📈 Monitoring & Maintenance

### Regular Health Checks

```bash
# Daily health check script
python scripts/setup_databases.py

# Check database sizes
python scripts/db_inspector.py --connection-info
```

### Data Backup

```bash
# Export conversations (local)
python scripts/db_inspector.py --export "backup_local_$(date +%Y%m%d).json"

# Export conversations (Railway)
python scripts/db_inspector.py --env railway --export "backup_railway_$(date +%Y%m%d).json"

# Backup SQLite database
cp state.sqlite "backups/state_$(date +%Y%m%d).sqlite"
```

### Performance Monitoring

**Redis:**

```bash
# Monitor Redis performance
wsl redis-cli --latency
wsl redis-cli --stat

# Check memory usage
wsl redis-cli INFO memory
```

**SQLite:**

```bash
# Check database size and integrity
sqlite3 state.sqlite "PRAGMA integrity_check;"
sqlite3 state.sqlite "PRAGMA table_info(user_profiles);"
```

## 🚨 Emergency Recovery

### Redis Data Loss

If Redis loses data:

1. **Check if Redis is running:** `wsl redis-cli ping`
2. **Restart Redis:** `wsl redis-server --daemonize yes`  
3. **Bot will recreate conversation state automatically**
4. **User profiles in SQLite are unaffected**

### SQLite Corruption

If SQLite becomes corrupted:

1. **Stop the bot immediately**
2. **Backup corrupted database:** `cp state.sqlite state_corrupted.sqlite`
3. **Try repair:** `sqlite3 state.sqlite ".recover" | sqlite3 state_recovered.sqlite`
4. **Or restore from backup:** `cp backups/state_YYYYMMDD.sqlite state.sqlite`
5. **Run setup:** `python scripts/setup_databases.py`

## 📝 Development Tips

### Testing Database Changes

```bash
# Test on copy of production data
cp state.sqlite state_test.sqlite
# Modify state_test.sqlite safely
# Test changes with modified database
```

### Debugging Conversations

```bash
# Find conversations with errors
python scripts/db_inspector.py --search "error"
python scripts/db_inspector.py --search "exception"

# Export problematic conversation for analysis
python scripts/db_inspector.py --export debug_conversation.json
```

### Development Workflow

1. **Start Redis:** `wsl redis-server --daemonize yes`
2. **Run database setup:** `python scripts/setup_databases.py`
3. **Start bot:** `python app.py`
4. **Monitor databases:** Use RedisInsight and DB Browser
5. **Inspect data:** `python scripts/db_inspector.py`

This guide provides comprehensive database management without modifying core bot functionality. All tools are in the `scripts/` directory and documentation is in `docs/`.
