import sqlite3
import os

db_path = 'state.sqlite'
if os.path.exists(db_path):
    print(f"Database file exists: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print('Tables found:', [t[0] for t in tables])
    
    # Check if user_auth_profiles table exists (correct table name)
    if any('user_auth_profiles' in t[0] for t in tables):
        print("✅ user_auth_profiles table exists")
        # Check the schema
        cursor = conn.execute("PRAGMA table_info(user_auth_profiles);")
        columns = cursor.fetchall()
        print("Columns in user_auth_profiles:", [(col[1], col[2]) for col in columns])
        
        # Check if any users exist
        cursor = conn.execute("SELECT COUNT(*) FROM user_auth_profiles;")
        count = cursor.fetchone()[0]
        print(f"Number of users in database: {count}")
        
        if count > 0:
            cursor = conn.execute("SELECT user_id, display_name, assigned_role FROM user_auth_profiles LIMIT 5;")
            users = cursor.fetchall()
            print("Sample users:", users)
        
    else:
        print("❌ user_auth_profiles table missing")
    
    conn.close()
else:
    print(f"❌ Database file does not exist: {db_path}") 