#!/usr/bin/env python3
"""
Script to run Alembic migrations programmatically.
"""

from alembic.config import Config
from alembic import command
import os

def run_migrations():
    """Run all pending Alembic migrations."""
    try:
        # Create Alembic config
        alembic_cfg = Config("alembic.ini")
        
        # Run upgrade to head
        print("🔄 Running Alembic migrations...")
        command.upgrade(alembic_cfg, "head")
        print("✅ Migrations completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migrations()
    if success:
        print("🎉 Database is ready!")
    else:
        print("💥 Migration failed!")
        exit(1) 