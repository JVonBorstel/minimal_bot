#!/usr/bin/env python3
"""
Admin User Setup Script
Run this script to configure your permanent admin user
"""

import os
import sys

def setup_admin_user():
    """Interactive setup for admin user configuration"""
    
    print("🔧 ADMIN USER SETUP")
    print("=" * 50)
    print("This will help you configure a permanent admin user for the bot.")
    print("The admin user will be automatically created/updated on bot startup.")
    print()
    
    # Get user information
    admin_user_id = input("Enter your admin user ID (e.g., 'jordan.admin'): ").strip()
    if not admin_user_id:
        print("❌ User ID is required!")
        return False
        
    admin_user_name = input("Enter your display name (e.g., 'Jordan - System Administrator'): ").strip()
    if not admin_user_name:
        admin_user_name = "System Administrator"
        
    admin_user_email = input("Enter your email address: ").strip()
    
    # Check if .env file exists
    env_file_path = ".env"
    env_exists = os.path.exists(env_file_path)
    
    if env_exists:
        print(f"\n📄 Found existing .env file")
        update_env = input("Do you want to update the existing .env file? (y/n): ").strip().lower()
        if update_env != 'y':
            print("❌ Skipping .env file update")
            return False
    
    # Prepare environment variables
    admin_vars = {
        'ADMIN_USER_ID': admin_user_id,
        'ADMIN_USER_NAME': admin_user_name,
        'ADMIN_USER_EMAIL': admin_user_email
    }
    
    if env_exists:
        # Read existing .env file
        with open(env_file_path, 'r') as f:
            lines = f.readlines()
        
        # Update admin variables
        updated_lines = []
        admin_vars_found = set()
        
        for line in lines:
            line = line.strip()
            if line.startswith('#') or not line or '=' not in line:
                updated_lines.append(line + '\n')
                continue
                
            key = line.split('=')[0].strip()
            if key in admin_vars:
                updated_lines.append(f"{key}={admin_vars[key]}\n")
                admin_vars_found.add(key)
            else:
                updated_lines.append(line + '\n')
        
        # Add any missing admin variables
        for key, value in admin_vars.items():
            if key not in admin_vars_found:
                updated_lines.append(f"{key}={value}\n")
        
        # Write updated .env file
        with open(env_file_path, 'w') as f:
            f.writelines(updated_lines)
            
    else:
        # Create new .env file with minimal configuration
        env_content = f"""# === ADMIN USER CONFIGURATION ===
ADMIN_USER_ID={admin_user_id}
ADMIN_USER_NAME={admin_user_name}
ADMIN_USER_EMAIL={admin_user_email}

# === CORE APP SETTINGS ===
APP_ENV=development
PORT=8501
LOG_LEVEL=INFO

# === LLM CONFIGURATION ===
GEMINI_API_KEY=your_gemini_api_key_here

# === BOT FRAMEWORK ===
MICROSOFT_APP_ID=
MICROSOFT_APP_PASSWORD=

# === TOOL CONFIGURATIONS ===
# Add your tool configurations here...
"""
        
        with open(env_file_path, 'w') as f:
            f.write(env_content)
    
    print(f"\n✅ Admin user configuration saved to {env_file_path}")
    print(f"   User ID: {admin_user_id}")
    print(f"   Name: {admin_user_name}")
    print(f"   Email: {admin_user_email}")
    print()
    print("🚀 Next steps:")
    print("   1. Make sure your other environment variables are configured (API keys, etc.)")
    print("   2. Start the bot: python app.py")
    print("   3. The admin user will be automatically created on startup")
    
    return True

def manual_admin_creation():
    """Manually create admin user in database"""
    print("\n🔧 MANUAL ADMIN USER CREATION")
    print("=" * 50)
    
    try:
        from config import get_config
        from user_auth.utils import ensure_admin_user_exists
        
        config = get_config()
        
        if not config.ADMIN_USER_ID:
            print("❌ ADMIN_USER_ID not configured in environment variables.")
            print("   Please run the setup first or set the environment variables manually.")
            return False
        
        print(f"Creating admin user: {config.ADMIN_USER_ID}")
        
        if ensure_admin_user_exists():
            print("✅ Admin user created/updated successfully!")
            return True
        else:
            print("❌ Failed to create admin user")
            return False
            
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        return False

if __name__ == "__main__":
    print("MINIMAL BOT - ADMIN SETUP")
    print("=" * 50)
    
    action = input("Choose an action:\n1. Configure admin user in .env file\n2. Manually create admin user in database\nEnter choice (1 or 2): ").strip()
    
    if action == "1":
        setup_admin_user()
    elif action == "2":
        manual_admin_creation()
    else:
        print("❌ Invalid choice. Please run the script again.")
        sys.exit(1) 