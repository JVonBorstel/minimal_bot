#!/usr/bin/env python3
"""
🔍 GREPTILE REPOSITORY INDEXING AND TESTING SCRIPT
====================================================

This script first submits a repository for indexing, then tests the Greptile tools.
Following the Greptile API documentation pattern.
"""

import asyncio
import sys
import json
import requests
import time
from typing import Dict, Any
from datetime import datetime

# Add our modules to the path
sys.path.append('.')

try:
    from config import get_config
    from tools.greptile_tools import GreptileTools
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
    sys.exit(1)

def print_banner(text: str):
    """Print a formatted banner."""
    print(f"\n{'='*60}")
    print(f"🔍 {text}")
    print(f"{'='*60}")

def print_step(step: str, num: int):
    """Print a step header."""
    print(f"\n📋 STEP {num}: {step}")
    print(f"{'-'*50}")

def submit_repository_for_indexing(config, repo_url: str, branch: str = "main") -> bool:
    """Submit a repository for indexing using the Greptile API."""
    print_step("Submit Repository for Indexing", 1)
    
    api_key = config.get_env_value('GREPTILE_API_KEY')
    api_url = config.get_env_value('GREPTILE_API_URL') or "https://api.greptile.com/v2"
    github_token = config.get_env_value('GREPTILE_GITHUB_TOKEN')
    
    # Extract owner/repo from URL
    parts = repo_url.replace('https://github.com/', '').split('/')
    if len(parts) < 2:
        print(f"❌ Invalid repository URL: {repo_url}")
        return False
    
    owner_repo = f"{parts[0]}/{parts[1]}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    if github_token:
        headers["X-GitHub-Token"] = github_token
    
    payload = {
        "remote": "github",
        "repository": owner_repo,
        "branch": branch,
        "reload": False,
        "notify": False
    }
    
    print(f"🏗️ Repository: {repo_url}")
    print(f"🌿 Branch: {branch}")
    print(f"📦 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(f"{api_url}/repositories", headers=headers, json=payload, timeout=30)
        print(f"📡 Response Status: {response.status_code}")
        print(f"📡 Response Text: {response.text}")
        
        if response.status_code == 200:
            print("✅ Repository submitted for indexing!")
            return True
        elif response.status_code == 400 and "already exists" in response.text.lower():
            print("✅ Repository already exists/indexed!")
            return True
        else:
            print(f"❌ Failed to submit repository: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error submitting repository: {e}")
        return False

def check_repository_status(config, repo_url: str, branch: str = "main") -> Dict[str, Any]:
    """Check the indexing status of a repository."""
    print_step("Check Repository Status", 2)
    
    api_key = config.get_env_value('GREPTILE_API_KEY')
    api_url = config.get_env_value('GREPTILE_API_URL') or "https://api.greptile.com/v2"
    
    # Extract owner/repo from URL
    parts = repo_url.replace('https://github.com/', '').split('/')
    owner_repo = f"{parts[0]}/{parts[1]}"
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    # URL encode the repository identifier
    repo_id = f"github:{branch}:{owner_repo}".replace('/', '%2F')
    
    try:
        response = requests.get(f"{api_url}/repositories/{repo_id}", headers=headers, timeout=30)
        print(f"📡 Status Check Response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"📊 Repository Info: {json.dumps(data, indent=2)}")
            return data
        else:
            print(f"❌ Failed to check status: {response.status_code} - {response.text}")
            return {"status": "UNKNOWN", "error": response.text}
            
    except Exception as e:
        print(f"❌ Error checking status: {e}")
        return {"status": "ERROR", "error": str(e)}

def test_simple_query(config, repo_url: str) -> bool:
    """Test a simple query against the indexed repository."""
    print_step("Test Simple Query", 3)
    
    try:
        greptile_tools = GreptileTools(config)
        
        # Simple test query
        query = "What is this repository about?"
        print(f"🔍 Query: '{query}'")
        print(f"🏗️ Repository: {repo_url}")
        
        result = greptile_tools.query_codebase(query, repo_url)
        
        print(f"📊 Result: {json.dumps(result, indent=2, default=str)}")
        
        if result and result.get("status") == "SUCCESS" and result.get("answer"):
            print("✅ Query test PASSED!")
            return True
        else:
            print(f"❌ Query test FAILED: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Query test FAILED with exception: {e}")
        return False

async def main():
    """Main test workflow."""
    print_banner("GREPTILE REPOSITORY INDEXING & TESTING")
    print(f"🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        config = get_config()
        print("✅ Configuration loaded")
        
        # Test with a simple, well-known repository
        test_repos = [
            "https://github.com/solana-labs/solana-program-library",  # Well-known Solana repo
            "https://github.com/facebook/react",                      # Popular React repo
            "https://github.com/microsoft/vscode"                     # Popular VSCode repo
        ]
        
        for repo_url in test_repos:
            print(f"\n🧪 Testing with repository: {repo_url}")
            
            # Step 1: Submit for indexing
            if submit_repository_for_indexing(config, repo_url):
                
                # Step 2: Check status (with brief wait)
                print("⏳ Waiting 5 seconds before checking status...")
                time.sleep(5)
                
                status_info = check_repository_status(config, repo_url)
                
                if status_info.get("status") in ["COMPLETED", "PROCESSING"]:
                    # Step 3: Test query (regardless of status - might work)
                    if test_simple_query(config, repo_url):
                        print(f"🎉 SUCCESS! Repository {repo_url} works with Greptile!")
                        
                        print_banner("GREPTILE TOOLS VALIDATION: SUCCESS!")
                        print("✅ At least one repository is working with Greptile!")
                        print(f"✅ Working repository: {repo_url}")
                        return True
                else:
                    print(f"⚠️ Repository status: {status_info.get('status', 'UNKNOWN')}")
                    if status_info.get("status") == "PROCESSING":
                        print("ℹ️ Repository is still being processed. Try again later.")
            
            print("➡️ Trying next repository...")
        
        print_banner("GREPTILE TOOLS VALIDATION: PARTIAL SUCCESS")
        print("⚠️ Repositories submitted for indexing but may need more time to process")
        print("ℹ️ Try running the test again in a few minutes")
        return False
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    if success:
        print(f"\n🎯 RESULT: GREPTILE INDEXING & TESTING SUCCESSFUL!")
        sys.exit(0)
    else:
        print(f"\n⚠️ RESULT: GREPTILE INDEXING INITIATED - MAY NEED TIME TO PROCESS")
        sys.exit(1) 