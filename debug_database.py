#!/usr/bin/env python3
"""
Debug script to inspect database structure.
"""

import sqlite3
from config import get_config
from user_auth.db_manager import _get_engine, get_session
from user_auth.orm_models import Base, UserProfile as UserProfileORM

def debug_database():
    """Debug database structure and contents."""
    config = get_config()
    db_path = config.STATE_DB_PATH
    print(f"🔍 Database path: {db_path}")
    
    # Check SQLite directly
    print("\n📋 Direct SQLite inspection:")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"   Tables found: {[t[0] for t in tables]}")
        
        # Check for user_profiles variations
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%user%'")
        user_tables = cursor.fetchall()
        print(f"   User-related tables: {[t[0] for t in user_tables]}")
        
        conn.close()
        
    except Exception as e:
        print(f"   Error: {e}")
    
    # Check SQLAlchemy engine
    print("\n🔧 SQLAlchemy engine inspection:")
    try:
        engine = _get_engine()
        print(f"   Engine URL: {engine.url}")
        
        # Try to create tables
        print("   Creating tables with Base.metadata.create_all...")
        Base.metadata.create_all(engine)
        print("   Table creation completed")
        
        # Check metadata
        print(f"   Tables in metadata: {list(Base.metadata.tables.keys())}")
        
    except Exception as e:
        print(f"   Error: {e}")
    
    # Check again after creation
    print("\n📋 Post-creation SQLite inspection:")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all tables again
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"   Tables found: {[t[0] for t in tables]}")
        
        conn.close()
        
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test session and ORM
    print("\n🔄 Testing ORM session:")
    try:
        with get_session() as session:
            # Try to query (this will fail if table doesn't exist)
            result = session.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = result.fetchall()
            print(f"   Tables via session: {[t[0] for t in tables]}")
            
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    debug_database() 