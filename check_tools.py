#!/usr/bin/env python3
"""Quick script to check what tools are currently configured."""

from tools.tool_executor import ToolExecutor
from config import get_config

def main():
    config = get_config()
    executor = ToolExecutor(config)
    
    all_tools = list(executor.configured_tools.keys())
    print(f"Total configured tools: {len(all_tools)}")
    print("\nAll configured tools:")
    for i, tool in enumerate(all_tools, 1):
        print(f"{i:2d}. {tool}")
    
    # Group by service
    jira_tools = [t for t in all_tools if 'jira' in t.lower()]
    github_tools = [t for t in all_tools if 'github' in t.lower()]
    greptile_tools = [t for t in all_tools if 'greptile' in t.lower()]
    perplexity_tools = [t for t in all_tools if 'perplexity' in t.lower()]
    other_tools = [t for t in all_tools if not any(service in t.lower() for service in ['jira', 'github', 'greptile', 'perplexity'])]
    
    print(f"\nBy service:")
    print(f"- Jira: {len(jira_tools)} tools")
    print(f"- GitHub: {len(github_tools)} tools") 
    print(f"- Greptile: {len(greptile_tools)} tools")
    print(f"- Perplexity: {len(perplexity_tools)} tools")
    print(f"- Other: {len(other_tools)} tools")
    
    if other_tools:
        print(f"  Other tools: {other_tools}")

if __name__ == "__main__":
    main() 