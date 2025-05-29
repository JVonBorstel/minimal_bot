#!/usr/bin/env python3
"""
Database Setup Script for Minimal Bot
Initializes SQLite tables and checks Redis connectivity.
"""

import sqlite3
import os
import sys
import redis

# Add the parent directory to Python path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
except ImportError as e:
    print(f"⚠️  Could not import config: {e}")
    config = None

def create_sqlite_tables(db_path: str = "state.sqlite"):
    """Create necessary SQLite tables."""
    print(f"📊 Setting up SQLite database: {db_path}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        # Create user_profiles table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT,
                assigned_role TEXT DEFAULT 'user',
                first_seen_timestamp TEXT,
                last_active_timestamp TEXT,
                profile_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create bot_state table (for SQLite storage fallback)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                namespace TEXT NOT NULL,
                id TEXT NOT NULL,
                data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (namespace, id)
            )
        """)
        
        conn.commit()
        
        # Show table info
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"✅ Created/verified {len(tables)} tables:")
        for table in tables:
            table_name = table[0]
            count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = count_cursor.fetchone()[0]
            print(f"   - {table_name}: {count} rows")

def check_redis_connectivity():
    """Check Redis server connectivity."""
    print("\n🔴 Checking Redis connectivity...")
    
    try:
        config = Config()
        redis_config = {
            'host': config.settings.redis_host,
            'port': config.settings.redis_port,
            'db': config.settings.redis_db
        }
    except:
        redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    
    try:
        r = redis.Redis(**redis_config)
        r.ping()
        
        # Get some info
        info = r.info()
        print(f"✅ Redis connected successfully!")
        print(f"   - Version: {info.get('redis_version', 'Unknown')}")
        print(f"   - Host: {redis_config['host']}:{redis_config['port']}")
        print(f"   - Database: {redis_config['db']}")
        print(f"   - Connected clients: {info.get('connected_clients', 'Unknown')}")
        print(f"   - Used memory: {info.get('used_memory_human', 'Unknown')}")
        
        # Check for existing keys
        keys = r.keys("*")
        print(f"   - Existing keys: {len(keys)}")
        
        return True
        
    except redis.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        print(f"   Tried to connect to: {redis_config}")
        print("\n💡 To fix this:")
        print("   1. Install Redis server:")
        print("      - Download from: https://github.com/MSOpenTech/redis/releases")
        print("      - Or use Docker: docker run -d -p 6379:6379 redis:latest")
        print("   2. Or use the bot with SQLite-only mode")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected Redis error: {e}")
        return False

def test_database_inspector():
    """Test the database inspector script."""
    print("\n🔍 Testing database inspector...")
    
    try:
        from scripts.db_inspector import DatabaseInspector
        inspector = DatabaseInspector()
        
        print("✅ Database inspector loaded successfully!")
        print("   You can now use:")
        print("   - python scripts/db_inspector.py")
        print("   - python scripts/db_inspector.py --users 5")
        print("   - python scripts/db_inspector.py --conversations 3")
        return True
        
    except Exception as e:
        print(f"❌ Database inspector test failed: {e}")
        return False

def main():
    print("🤖 Minimal Bot Database Setup")
    print("=" * 40)
    
    try:
        config = Config()
        db_path = config.STATE_DB_PATH
    except:
        db_path = "state.sqlite"
    
    # Setup SQLite
    create_sqlite_tables(db_path)
    
    # Check Redis
    redis_ok = check_redis_connectivity()
    
    # Test inspector
    inspector_ok = test_database_inspector()
    
    print("\n" + "=" * 40)
    print("📋 Setup Summary:")
    print(f"✅ SQLite database: Ready ({db_path})")
    print(f"{'✅' if redis_ok else '❌'} Redis server: {'Ready' if redis_ok else 'Not available'}")
    print(f"{'✅' if inspector_ok else '❌'} Database inspector: {'Ready' if inspector_ok else 'Error'}")
    
    if not redis_ok:
        print("\n⚠️  Bot will use SQLite-only mode for conversations.")
        print("   For full functionality, install Redis server.")
    
    print("\n🎉 Database setup complete!")
    print("\nNext steps:")
    print("1. Run: python scripts/db_inspector.py")
    print("2. Start your bot: python app.py")
    if redis_ok:
        print("3. Open RedisInsight for Redis GUI")
    print("4. Download DB Browser for SQLite GUI")

if __name__ == "__main__":
    main() 