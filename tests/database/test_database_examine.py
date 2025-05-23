#!/usr/bin/env python3
"""Examine current SQLite database structure and content."""

import sqlite3
import os
import sys

def examine_sqlite_database():
    """Examine the current SQLite database."""
    db_path = "state.sqlite"
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} does not exist")
        return
    
    print(f"🔍 EXAMINING SQLITE DATABASE: {db_path}")
    print(f"📏 Database file size: {os.path.getsize(db_path) / 1024 / 1024:.2f} MB")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"📋 Tables found: {len(tables)}")
        for table in tables:
            table_name = table[0]
            print(f"  - {table_name}")
            
            # Get row count for each table
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
            print(f"    Rows: {count}")
            
            # Get a few sample rows if any exist
            if count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
                samples = cursor.fetchall()
                print(f"    Sample data (first 3 rows):")
                for i, row in enumerate(samples):
                    print(f"      Row {i+1}: {str(row)[:200]}...")
        
        conn.close()
        print("✅ Database examination complete")
        
    except Exception as e:
        print(f"❌ Error examining database: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    examine_sqlite_database() 