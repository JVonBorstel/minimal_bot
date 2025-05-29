# Scripts Directory

This directory contains utility scripts for managing and inspecting the Minimal Bot's databases.

## 📁 Available Scripts

### `db_inspector.py` - Database Inspector Tool

**Purpose:** Inspect and manage both Redis and SQLite databases across local and Railway environments.

**Usage:**

```bash
# Quick overview
python scripts/db_inspector.py

# View user profiles
python scripts/db_inspector.py --users 10

# View conversations
python scripts/db_inspector.py --conversations 5

# Search conversations
python scripts/db_inspector.py --search "error"

# Export data
python scripts/db_inspector.py --export backup.json

# Railway environment
python scripts/db_inspector.py --env railway
```

**Features:**

- Auto-detects local vs Railway environment
- Supports both Redis and SQLite/PostgreSQL
- Search functionality across conversations
- Data export capabilities
- Connection troubleshooting

### `setup_databases.py` - Database Setup Tool

**Purpose:** Initialize SQLite tables and verify Redis connectivity.

**Usage:**

```bash
python scripts/setup_databases.py
```

**What it does:**

- Creates missing SQLite tables (`user_profiles`, `bot_state`)
- Tests Redis connectivity and displays connection info
- Verifies database inspector functionality
- Provides setup status summary

## 🚀 Quick Start

### First Time Setup

```bash
# 1. Start Redis (if using WSL)
wsl redis-server --daemonize yes

# 2. Setup databases
python scripts/setup_databases.py

# 3. Inspect databases
python scripts/db_inspector.py
```

### Daily Development

```bash
# Check database health
python scripts/db_inspector.py --connection-info

# View recent activity
python scripts/db_inspector.py --users 5 --conversations 5

# Search for issues
python scripts/db_inspector.py --search "error"
```

### Production Monitoring

```bash
# Export Railway data
$env:REDIS_URL = "your-railway-redis-url"
python scripts/db_inspector.py --env railway --export production_backup.json

# Check Railway connections
python scripts/db_inspector.py --env railway --connection-info
```

## 🛠️ Environment Variables

For Railway access, set these environment variables:

```bash
# PowerShell
$env:REDIS_URL = "redis://user:password@host:port/db"
$env:DATABASE_URL = "postgresql://user:password@host:port/database"

# Bash
export REDIS_URL="redis://user:password@host:port/db"
export DATABASE_URL="postgresql://user:password@host:port/database"
```

## 📋 Common Commands

### Database Health Check

```bash
python scripts/setup_databases.py
```

### View All Data

```bash
python scripts/db_inspector.py
```

### Backup Everything

```bash
# Local backup
python scripts/db_inspector.py --export "backup_local_$(date +%Y%m%d).json"

# Railway backup (with env vars set)
python scripts/db_inspector.py --env railway --export "backup_railway_$(date +%Y%m%d).json"
```

### Troubleshoot Connections

```bash
python scripts/db_inspector.py --connection-info
```

### Search and Debug

```bash
# Find error conversations
python scripts/db_inspector.py --search "error"

# Find specific user conversations
python scripts/db_inspector.py --search "user@example.com"

# Find onboarding issues
python scripts/db_inspector.py --search "onboarding"
```

## 🔧 Dependencies

These scripts require the following Python packages (already in `requirements.txt`):

- `redis` - Redis connectivity
- `sqlite3` - SQLite database (built-in)
- `psycopg2` or `psycopg2-binary` - PostgreSQL connectivity (for Railway)

## 📖 Full Documentation

For comprehensive documentation, see [`docs/DATABASE_MANAGEMENT.md`](../docs/DATABASE_MANAGEMENT.md)

## 🚨 Safety Notes

- **Backup before using `--clear-redis`** - This deletes ALL conversation data
- **Test Railway connections** - Always verify environment variables are set correctly
- **Use `--env local` explicitly** - When you want to avoid auto-detection
- **Export data regularly** - For backup and debugging purposes

## 🆘 Troubleshooting

### Redis Connection Failed

```bash
# Start Redis on WSL
wsl redis-server --daemonize yes

# Verify it's running
wsl redis-cli ping
```

### SQLite Table Missing

```bash
# Recreate tables
python scripts/setup_databases.py
```

### Railway Connection Issues

```bash
# Check environment variables
python scripts/db_inspector.py --env railway --connection-info

# Verify URLs are set
echo $env:REDIS_URL
echo $env:DATABASE_URL
```

These scripts are designed to be safe and non-invasive to your core bot functionality. They only read and inspect data by default, with explicit confirmation required for any destructive operations.
