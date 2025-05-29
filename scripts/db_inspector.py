#!/usr/bin/env python3
"""
Database Inspector for Minimal Bot
Provides easy access to view Redis and SQLite databases with bot-specific formatting.
Supports both local development and Railway deployment databases.
"""

import sqlite3
import json
import redis
import argparse
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional
import pprint

# Add the parent directory to Python path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
    from state_models import AppState
    from user_auth.models import UserProfile
except ImportError as e:
    print(f"⚠️  Could not import bot modules: {e}")
    print("Some features may not work properly.")

class DatabaseInspector:
    def __init__(self, config_path: str = None, environment: str = "auto"):
        """Initialize the database inspector.
        
        Args:
            config_path: Path to config file (optional)
            environment: "local", "railway", or "auto" (detect automatically)
        """
        self.environment = self._detect_environment() if environment == "auto" else environment
        print(f"🌍 Environment detected: {self.environment}")
        
        try:
            self.config = Config()
            self._setup_connections()
        except Exception as e:
            print(f"⚠️  Could not load config: {e}")
            self._setup_fallback_connections()

    def _detect_environment(self) -> str:
        """Detect if we're running locally or on Railway."""
        if os.getenv("RAILWAY_ENVIRONMENT"):
            return "railway"
        elif os.getenv("REDIS_URL") or os.getenv("DATABASE_URL"):
            return "railway"
        else:
            return "local"

    def _setup_connections(self):
        """Setup database connections based on environment."""
        if self.environment == "railway":
            self._setup_railway_connections()
        else:
            self._setup_local_connections()

    def _setup_local_connections(self):
        """Setup local database connections."""
        self.sqlite_path = self.config.STATE_DB_PATH
        self.redis_config = {
            'host': self.config.settings.redis_host,
            'port': self.config.settings.redis_port,
            'db': self.config.settings.redis_db
        }
        self.use_postgresql = False

    def _setup_railway_connections(self):
        """Setup Railway database connections."""
        # Redis connection for Railway
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            self.redis_config = {"connection_pool": redis.ConnectionPool.from_url(redis_url)}
        else:
            # Fallback to individual params
            self.redis_config = {
                'host': os.getenv("REDIS_HOST", "localhost"),
                'port': int(os.getenv("REDIS_PORT", "6379")),
                'db': int(os.getenv("REDIS_DB", "0")),
                'password': os.getenv("REDIS_PASSWORD")
            }

        # Database connection for Railway
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            self.database_url = database_url
            self.use_postgresql = True
        else:
            # Fallback to SQLite path
            self.sqlite_path = os.getenv("STATE_DB_PATH", "state.sqlite")
            self.use_postgresql = False

    def _setup_fallback_connections(self):
        """Setup fallback connections when config loading fails."""
        if self.environment == "railway":
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                self.redis_config = {"connection_pool": redis.ConnectionPool.from_url(redis_url)}
            else:
                self.redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
            
            self.database_url = os.getenv("DATABASE_URL")
            self.use_postgresql = bool(self.database_url)
            if not self.use_postgresql:
                self.sqlite_path = "state.sqlite"
        else:
            self.sqlite_path = "state.sqlite"
            self.redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
            self.use_postgresql = False

    def connect_sqlite(self) -> sqlite3.Connection:
        """Connect to SQLite database."""
        if self.use_postgresql:
            raise NotImplementedError("PostgreSQL connections not implemented yet. Use DATABASE_URL for Railway.")
        
        if not os.path.exists(self.sqlite_path):
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_path}")
        return sqlite3.connect(self.sqlite_path)

    def connect_redis(self) -> redis.Redis:
        """Connect to Redis database."""
        try:
            if "connection_pool" in self.redis_config:
                r = redis.Redis(connection_pool=self.redis_config["connection_pool"])
            else:
                # Filter out None values for local connections
                config = {k: v for k, v in self.redis_config.items() if v is not None}
                r = redis.Redis(**config)
            
            r.ping()  # Test connection
            return r
        except redis.ConnectionError as e:
            raise ConnectionError(f"Could not connect to Redis at {self.redis_config}: {e}")

    def view_sqlite_tables(self):
        """View all tables in SQLite database."""
        if self.use_postgresql:
            print("📊 PostgreSQL Tables:")
            print("⚠️  PostgreSQL inspection not implemented yet.")
            print("Use DATABASE_URL and psql or pgAdmin for Railway databases.")
            return

        print("📊 SQLite Tables:")
        print("=" * 50)
        
        with self.connect_sqlite() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            for (table_name,) in tables:
                print(f"\n🗂️  Table: {table_name}")
                
                # Get row count
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = count_cursor.fetchone()[0]
                print(f"   Rows: {count}")
                
                # Get schema
                schema_cursor = conn.execute(f"PRAGMA table_info({table_name})")
                columns = schema_cursor.fetchall()
                print("   Columns:")
                for col in columns:
                    print(f"     - {col[1]} ({col[2]})")

    def view_user_profiles(self, limit: int = 10):
        """View user profiles from SQLite."""
        if self.use_postgresql:
            print("👥 User Profiles:")
            print("⚠️  PostgreSQL user profile viewing not implemented yet.")
            return

        print(f"👥 User Profiles (Last {limit}):")
        print("=" * 50)
        
        with self.connect_sqlite() as conn:
            cursor = conn.execute("""
                SELECT user_id, display_name, email, assigned_role, 
                       first_seen_timestamp, last_active_timestamp, profile_data
                FROM user_profiles 
                ORDER BY last_active_timestamp DESC 
                LIMIT ?
            """, (limit,))
            
            users = cursor.fetchall()
            
            if not users:
                print("No user profiles found.")
                return
                
            for user in users:
                user_id, display_name, email, role, first_seen, last_active, profile_data = user
                print(f"\n👤 {display_name} ({user_id})")
                print(f"   📧 Email: {email or 'Not set'}")
                print(f"   🎭 Role: {role}")
                print(f"   📅 First seen: {first_seen}")
                print(f"   ⏰ Last active: {last_active}")
                
                if profile_data:
                    try:
                        data = json.loads(profile_data)
                        if 'preferences' in data:
                            prefs = data['preferences']
                            print(f"   🎯 Primary role: {prefs.get('primary_role', 'Not set')}")
                            print(f"   📂 Projects: {', '.join(prefs.get('main_projects', []))}")
                            print(f"   🛠️  Tools: {', '.join(prefs.get('tool_preferences', []))}")
                    except json.JSONDecodeError:
                        print("   ⚠️  Invalid profile data JSON")

    def view_bot_conversations(self, limit: int = 5):
        """View bot conversations from Redis."""
        print(f"💬 Bot Conversations (Last {limit}) - {self.environment}:")
        print("=" * 60)
        
        try:
            r = self.connect_redis()
            
            # Get all conversation keys
            keys = r.keys("*conversation*")
            if not keys:
                keys = r.keys("*")  # Fallback to all keys
                
            if not keys:
                print("No conversation data found in Redis.")
                return
                
            # Sort by last access time if possible
            key_info = []
            for key in keys[:limit]:
                try:
                    value = r.get(key)
                    if value:
                        key_info.append((key.decode(), value))
                except:
                    continue
                    
            for i, (key, value) in enumerate(key_info[:limit]):
                print(f"\n💬 Conversation {i+1}: {key}")
                try:
                    data = json.loads(value)
                    if isinstance(data, dict):
                        # Try to parse as AppState
                        session_id = data.get('session_id', 'Unknown')
                        messages = data.get('messages', [])
                        user_info = data.get('current_user', {})
                        
                        print(f"   🆔 Session: {session_id}")
                        print(f"   💬 Messages: {len(messages)}")
                        print(f"   👤 User: {user_info.get('display_name', 'Unknown') if isinstance(user_info, dict) else 'Unknown'}")
                        print(f"   📊 Status: {data.get('last_interaction_status', 'Unknown')}")
                        
                        if messages:
                            last_msg = messages[-1] if isinstance(messages, list) else {}
                            if isinstance(last_msg, dict):
                                role = last_msg.get('role', 'unknown')
                                content = last_msg.get('content', '')[:100]
                                print(f"   💭 Last: [{role}] {content}...")
                except json.JSONDecodeError:
                    print(f"   ⚠️  Invalid JSON data")
                except Exception as e:
                    print(f"   ⚠️  Error parsing: {e}")
                    
        except ConnectionError as e:
            print(f"❌ Could not connect to Redis: {e}")
            if self.environment == "railway":
                print("💡 For Railway Redis access, ensure you have the REDIS_URL environment variable set.")

    def show_connection_info(self):
        """Show current connection configuration."""
        print("🔧 Connection Configuration:")
        print("=" * 40)
        print(f"Environment: {self.environment}")
        
        if self.environment == "railway":
            print("\n🚂 Railway Configuration:")
            print(f"   Redis URL: {'Set' if os.getenv('REDIS_URL') else 'Not set'}")
            print(f"   Database URL: {'Set' if os.getenv('DATABASE_URL') else 'Not set'}")
            print(f"   Use PostgreSQL: {self.use_postgresql}")
        else:
            print("\n🏠 Local Configuration:")
            print(f"   SQLite Path: {getattr(self, 'sqlite_path', 'Not set')}")
            print(f"   Redis: {self.redis_config}")

    def search_conversations(self, search_term: str):
        """Search for conversations containing specific text."""
        print(f"🔍 Searching conversations for: '{search_term}' ({self.environment})")
        print("=" * 60)
        
        try:
            r = self.connect_redis()
            keys = r.keys("*")
            found = 0
            
            for key in keys:
                try:
                    value = r.get(key)
                    if value and search_term.lower() in value.decode().lower():
                        found += 1
                        print(f"\n✅ Found in: {key.decode()}")
                        
                        # Try to show context
                        try:
                            data = json.loads(value)
                            if isinstance(data, dict) and 'messages' in data:
                                for msg in data['messages']:
                                    if isinstance(msg, dict) and search_term.lower() in msg.get('content', '').lower():
                                        role = msg.get('role', 'unknown')
                                        content = msg.get('content', '')
                                        print(f"   💭 [{role}] {content[:200]}...")
                                        break
                        except:
                            pass
                            
                except Exception:
                    continue
                    
            if found == 0:
                print("No conversations found containing that term.")
            else:
                print(f"\n📈 Found {found} conversations")
                
        except ConnectionError as e:
            print(f"❌ Could not connect to Redis: {e}")

    def clear_conversations(self, confirm: bool = False):
        """Clear all conversation data from Redis."""
        if not confirm:
            print(f"⚠️  This will delete ALL conversation data from Redis ({self.environment})!")
            response = input("Type 'DELETE' to confirm: ")
            if response != 'DELETE':
                print("❌ Operation cancelled.")
                return
                
        try:
            r = self.connect_redis()
            keys = r.keys("*")
            
            if keys:
                deleted = r.delete(*keys)
                print(f"🗑️  Deleted {deleted} keys from Redis ({self.environment})")
            else:
                print("No keys found to delete.")
                
        except ConnectionError as e:
            print(f"❌ Could not connect to Redis: {e}")

    def export_conversations(self, output_file: str = None):
        """Export all conversation data to JSON file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"conversations_export_{self.environment}_{timestamp}.json"
            
        try:
            r = self.connect_redis()
            keys = r.keys("*")
            
            export_data = {
                "metadata": {
                    "environment": self.environment,
                    "export_time": datetime.now().isoformat(),
                    "total_keys": len(keys)
                },
                "conversations": {}
            }
            
            for key in keys:
                try:
                    value = r.get(key)
                    if value:
                        export_data["conversations"][key.decode()] = json.loads(value)
                except Exception as e:
                    print(f"⚠️  Could not export key {key}: {e}")
                    
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
                
            print(f"📁 Exported {len(export_data['conversations'])} conversations from {self.environment} to {output_file}")
            
        except ConnectionError as e:
            print(f"❌ Could not connect to Redis: {e}")

def main():
    parser = argparse.ArgumentParser(description="Database Inspector for Minimal Bot")
    parser.add_argument("--env", choices=["local", "railway", "auto"], default="auto", 
                       help="Environment to inspect (default: auto-detect)")
    parser.add_argument("--sqlite-tables", action="store_true", help="View SQLite table information")
    parser.add_argument("--users", type=int, default=10, help="View user profiles (default: 10)")
    parser.add_argument("--conversations", type=int, default=5, help="View recent conversations (default: 5)")
    parser.add_argument("--search", type=str, help="Search conversations for text")
    parser.add_argument("--export", type=str, nargs='?', const=True, help="Export conversations to JSON file")
    parser.add_argument("--clear-redis", action="store_true", help="Clear all Redis data (with confirmation)")
    parser.add_argument("--connection-info", action="store_true", help="Show connection configuration")
    
    args = parser.parse_args()
    
    inspector = DatabaseInspector(environment=args.env)
    
    try:
        if args.connection_info:
            inspector.show_connection_info()
            
        if args.sqlite_tables:
            inspector.view_sqlite_tables()
            
        if args.users:
            inspector.view_user_profiles(args.users)
            
        if args.conversations:
            inspector.view_bot_conversations(args.conversations)
            
        if args.search:
            inspector.search_conversations(args.search)
            
        if args.export:
            if isinstance(args.export, str):
                inspector.export_conversations(args.export)
            else:
                inspector.export_conversations()
                
        if args.clear_redis:
            inspector.clear_conversations()
            
        # If no arguments, show summary
        if not any([args.connection_info, args.sqlite_tables, args.users, args.conversations, 
                   args.search, args.export, args.clear_redis]):
            print("🤖 Minimal Bot Database Inspector")
            print("=" * 40)
            inspector.show_connection_info()
            print("\n")
            inspector.view_sqlite_tables()
            print("\n")
            inspector.view_user_profiles(3)
            print("\n")
            inspector.view_bot_conversations(3)
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 