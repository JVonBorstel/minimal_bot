#!/usr/bin/env python3
"""
🔍 GREPTILE STATUS CHECKER & TESTER
===================================

Check the status of previously submitted repositories and test them if ready.
"""

import asyncio
import sys
import json
import requests
from datetime import datetime

# Add our modules to the path
sys.path.append('.')

try:
    from config import get_config
    from tools.greptile_tools import GreptileTools
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
    sys.exit(1)

def check_and_test_repository(config, repo_url: str, branch: str = "main") -> bool:
    """Check status and test if ready."""
    print(f"\n🔍 Checking: {repo_url}")
    
    api_key = config.get_env_value('GREPTILE_API_KEY')
    api_url = config.get_env_value('GREPTILE_API_URL') or "https://api.greptile.com/v2"
    
    # Extract owner/repo from URL
    parts = repo_url.replace('https://github.com/', '').split('/')
    owner_repo = f"{parts[0]}/{parts[1]}"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    # URL encode the repository identifier
    repo_id = f"github:{branch}:{owner_repo}".replace('/', '%2F')
    
    try:
        # Check status
        response = requests.get(f"{api_url}/repositories/{repo_id}", headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            files_processed = data.get("filesProcessed", 0)
            num_files = data.get("numFiles", 0)
            
            print(f"📊 Status: {status}, Files: {files_processed}/{num_files}")
            
            if status == "COMPLETED":
                print("✅ Repository is COMPLETED! Testing query...")
                
                # Test query
                try:
                    greptile_tools = GreptileTools(config)
                    result = greptile_tools.query_codebase("What is this repository about?", repo_url)
                    
                    if result and result.get("status") == "SUCCESS" and result.get("answer"):
                        print(f"🎉 QUERY SUCCESS! Answer: {result['answer'][:200]}...")
                        return True
                    else:
                        print(f"❌ Query failed: {result}")
                        
                except Exception as e:
                    print(f"❌ Query error: {e}")
                    
            elif status in ["CLONING", "PROCESSING", "INDEXING"]:
                print(f"⏳ Still processing... ({status})")
            else:
                print(f"⚠️ Unexpected status: {status}")
                
        else:
            print(f"❌ Status check failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return False

def main():
    """Check all previously submitted repositories."""
    print("🔍 GREPTILE STATUS CHECKER")
    print("=" * 50)
    print(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        config = get_config()
        
        # Previously submitted repositories
        repositories = [
            "https://github.com/facebook/react",
            "https://github.com/microsoft/vscode"
        ]
        
        success_count = 0
        
        for repo_url in repositories:
            if check_and_test_repository(config, repo_url):
                success_count += 1
        
        print(f"\n📈 Results: {success_count}/{len(repositories)} repositories working")
        
        if success_count > 0:
            print("🎉 GREPTILE TOOLS VALIDATION: SUCCESS!")
            print("✅ At least one repository is working with Greptile!")
            return True
        else:
            print("⏳ No repositories ready yet. Try again in a few minutes.")
            return False
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 