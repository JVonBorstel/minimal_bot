# Database Quick Reference Card

## 🚀 Essential Commands

### Start Redis (WSL)

```bash
wsl redis-server --daemonize yes
wsl redis-cli ping  # Should return PONG
```

### Setup & Health Check

```bash
python scripts/setup_databases.py
```

### Database Inspector

```bash
# Overview of everything
python scripts/db_inspector.py

# Specific data views
python scripts/db_inspector.py --users 10
python scripts/db_inspector.py --conversations 5
python scripts/db_inspector.py --sqlite-tables
```

### Search & Export

```bash
python scripts/db_inspector.py --search "error"
python scripts/db_inspector.py --export backup.json
```

### Railway Access

```bash
$env:REDIS_URL = "redis://your-url"
python scripts/db_inspector.py --env railway
```

## 🔧 Direct Database Access

### Redis (WSL)

```bash
wsl redis-cli
KEYS "*"                    # List all keys
KEYS "*conversation*"       # List conversation keys  
GET "session-id"           # Get specific conversation
INFO                       # Redis server info
FLUSHALL                   # Clear all data (careful!)
```

### SQLite

```bash
sqlite3 state.sqlite
.tables                                    # List tables
SELECT * FROM user_profiles LIMIT 10;     # View users
SELECT * FROM bot_state LIMIT 10;         # View bot state
.quit                                      # Exit
```

## 🚨 Emergency Commands

### Redis Issues

```bash
wsl redis-server --daemonize yes          # Start Redis
wsl redis-cli shutdown                    # Stop Redis
wsl redis-cli ping                        # Test connection
```

### SQLite Issues

```bash
python scripts/setup_databases.py        # Recreate tables
cp state.sqlite state_backup.sqlite      # Backup database
```

## 📊 Monitoring Commands

### Daily Health Check

```bash
python scripts/db_inspector.py --connection-info
python scripts/db_inspector.py --users 5 --conversations 5
```

### Backup

```bash
# Local
python scripts/db_inspector.py --export "backup_$(date +%Y%m%d).json"

# Railway (with env vars set)
python scripts/db_inspector.py --env railway --export "railway_backup.json"
```

## 🔍 Debugging Commands

### Find Problems

```bash
python scripts/db_inspector.py --search "error"
python scripts/db_inspector.py --search "exception"
python scripts/db_inspector.py --search "failed"
```

### User-Specific Issues

```bash
python scripts/db_inspector.py --search "user@example.com"
python scripts/db_inspector.py --search "user-id-123"
```

## 📱 GUI Tools

### RedisInsight

- Install: `winget install RedisInsight.RedisInsight`
- Connect to: `localhost:6379`

### DB Browser for SQLite  

- Download: [sqlitebrowser.org](https://sqlitebrowser.org)
- Open: `state.sqlite`

## ⚡ Environment Variables

```bash
# PowerShell (Railway)
$env:REDIS_URL = "redis://user:pass@host:port/db"
$env:DATABASE_URL = "postgresql://user:pass@host:port/db"

# Verify
python scripts/db_inspector.py --env railway --connection-info
```

## 🎯 Common Workflows

### Development Startup

```bash
wsl redis-server --daemonize yes
python scripts/setup_databases.py
python app.py
```

### Debugging Issues

```bash
python scripts/db_inspector.py --search "error"
python scripts/db_inspector.py --export debug.json
# Analyze debug.json for patterns
```

### Production Monitoring

```bash
# Set Railway env vars
python scripts/db_inspector.py --env railway --export production_backup.json
python scripts/db_inspector.py --env railway --search "error"
```

### Data Migration

```bash
# Export from old environment
python scripts/db_inspector.py --export migration_data.json

# Import to new environment (manual process)
# Analyze migration_data.json structure
```

---
**💡 Tip:** Bookmark this page for quick reference during development!
