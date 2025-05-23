#!/usr/bin/env python3
"""Get the Cloud ID for the Jira instance."""

import requests
from config import get_config

def get_cloud_id():
    config = get_config()
    jira_url = config.get_env_value('JIRA_API_URL')
    
    # Extract the base URL (remove /rest/api/... part)
    if '/rest/api' in jira_url:
        base_url = jira_url.split('/rest/api')[0]
    else:
        base_url = jira_url.rstrip('/')
    
    tenant_info_url = f"{base_url}/_edge/tenant_info"
    
    print(f"🔍 Getting Cloud ID from: {tenant_info_url}")
    
    try:
        response = requests.get(tenant_info_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        cloud_id = data.get('cloudId')
        
        if cloud_id:
            print(f"✅ Found Cloud ID: {cloud_id}")
            print(f"\n📋 Your new Jira URL should be:")
            print(f"   https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/latest/")
            print(f"\n🔧 Current URL in config: {jira_url}")
            print(f"🆕 Update JIRA_API_URL to: https://api.atlassian.com/ex/jira/{cloud_id}")
            return cloud_id
        else:
            print(f"❌ No cloudId found in response: {data}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting cloud ID: {e}")
        return None

if __name__ == "__main__":
    get_cloud_id() 