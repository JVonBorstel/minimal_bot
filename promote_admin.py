#!/usr/bin/env python3
"""
Admin Promotion Script
Use this to promote a user to admin after they've chatted with the bot once
"""

import sys
from user_auth.utils import promote_user_to_admin_by_email
from user_auth import db_manager

def show_recent_users():
    """Show recent users to help identify who to promote"""
    print("\n📋 Recent Users (last 10):")
    print("-" * 80)
    
    try:
        all_users = db_manager.get_all_user_profiles()
        
        # Sort by last_active_timestamp descending
        sorted_users = sorted(
            all_users, 
            key=lambda x: x.get('last_active_timestamp', 0), 
            reverse=True
        )
        
        for i, user in enumerate(sorted_users[:10], 1):
            user_id = user.get('user_id', 'N/A')
            display_name = user.get('display_name', 'N/A')
            email = user.get('email', 'N/A')
            role = user.get('assigned_role', 'N/A')
            
            # Truncate long user IDs for display
            if len(user_id) > 30:
                display_user_id = user_id[:27] + "..."
            else:
                display_user_id = user_id
                
            print(f"{i:2}. {display_name:<25} | {role:<10} | {email:<30} | {display_user_id}")
        
    except Exception as e:
        print(f"❌ Error retrieving users: {e}")

def promote_by_email():
    """Promote a user to admin by email address"""
    print("\n🔧 PROMOTE USER TO ADMIN")
    print("-" * 50)
    
    email = input("Enter the email address of the user to promote: ").strip()
    
    if not email:
        print("❌ Email address is required!")
        return False
    
    print(f"\n🔄 Promoting user with email: {email}")
    
    if promote_user_to_admin_by_email(email):
        print(f"✅ Successfully promoted {email} to ADMIN!")
        print("   They will have full admin access on their next interaction.")
        return True
    else:
        print(f"❌ Failed to promote {email}")
        print("   Make sure they have chatted with the bot at least once.")
        return False

def show_admin_users():
    """Show all current admin users"""
    print("\n👑 Current Admin Users:")
    print("-" * 60)
    
    try:
        all_users = db_manager.get_all_user_profiles()
        admin_users = [u for u in all_users if u.get('assigned_role') == 'ADMIN']
        
        if not admin_users:
            print("   No admin users found.")
            return
            
        for admin in admin_users:
            user_id = admin.get('user_id', 'N/A')
            display_name = admin.get('display_name', 'N/A')
            email = admin.get('email', 'N/A')
            
            # Truncate long user IDs
            if len(user_id) > 40:
                display_user_id = user_id[:37] + "..."
            else:
                display_user_id = user_id
                
            print(f"   • {display_name} ({email})")
            print(f"     ID: {display_user_id}")
            print()
            
    except Exception as e:
        print(f"❌ Error retrieving admin users: {e}")

if __name__ == "__main__":
    print("🤖 MINIMAL BOT - ADMIN PROMOTION TOOL")
    print("=" * 60)
    
    while True:
        print("\nChoose an action:")
        print("1. Show recent users")
        print("2. Show current admin users") 
        print("3. Promote user to admin by email")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            show_recent_users()
        elif choice == "2":
            show_admin_users()
        elif choice == "3":
            promote_by_email()
        elif choice == "4":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.") 