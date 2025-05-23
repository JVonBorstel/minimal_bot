"""Core tools that are always available to users."""

import logging
from typing import Dict, Any, List
from ._tool_decorator import tool_function
from config import Config

log = logging.getLogger(__name__)


@tool_function(
    name="help",
    description="Get help and show available commands. Use this when users ask for help, what you can do, or how to use the bot.",
    parameters_schema={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string", 
                "description": "Optional specific topic to get help about"
            }
        },
        "required": []
    },
    categories=["assistance", "documentation"],
    tags=["help", "support", "guide", "commands", "usage", "what can you do", "available", "tools"],
    importance=4  # Reduced importance from 10
)
async def help(topic: str = None, config: Config = None) -> Dict[str, Any]:
    """
    Provides help and shows available commands to the user.
    
    Args:
        topic: Optional specific topic to get help about
        config: Configuration object (injected)
        
    Returns:
        Dict containing help information
    """
    log.info(f"Help tool called with topic: {topic}")
    
    help_response = {
        "title": "🤖 Augie ChatOps Bot - Help & Commands",
        "description": "I'm here to help you with development tasks, project management, and information retrieval!",
        "sections": []
    }
    
    # General help
    general_section = {
        "name": "🌟 Getting Started",
        "content": [
            "Just type naturally! I understand context and can help with:",
            "• Creating and managing GitHub issues and pull requests",
            "• Working with Jira tickets and project planning",
            "• Searching code and repositories",
            "• Finding information online",
            "• And much more!"
        ]
    }
    help_response["sections"].append(general_section)
    
    # Command examples
    examples_section = {
        "name": "💡 Example Commands",
        "content": [
            "**GitHub:**",
            "• 'Create a GitHub issue for the login bug'",
            "• 'Show my open pull requests'",
            "• 'Search for authentication code in the repository'",
            "",
            "**Jira:**",
            "• 'Create a new Jira ticket for the API feature'",
            "• 'Show my assigned Jira issues'",
            "• 'What's in the current sprint?'",
            "",
            "**Code & Search:**",
            "• 'Find all Python files with database queries'",
            "• 'Search the web for React best practices'",
            "• 'Analyze the codebase structure'"
        ]
    }
    help_response["sections"].append(examples_section)
    
    # Tool categories
    categories_section = {
        "name": "🛠️ Available Tool Categories",
        "content": [
            "**GitHub Tools**: Repository management, issues, PRs, code search",
            "**Jira Tools**: Project management, tickets, sprints, workflows",
            "**Greptile Tools**: Semantic code search and analysis",
            "**Perplexity Tools**: Web search and current information",
            "**Core Tools**: Help, status, and basic utilities"
        ]
    }
    help_response["sections"].append(categories_section)
    
    # Tips
    tips_section = {
        "name": "💡 Pro Tips",
        "content": [
            "• Be specific about what you want to do",
            "• I maintain context, so you can have natural conversations",
            "• For complex tasks, I'll guide you through the process",
            "• Just ask if you need clarification on anything!"
        ]
    }
    help_response["sections"].append(tips_section)
    
    # Topic-specific help
    if topic:
        topic_lower = topic.lower()
        if "github" in topic_lower:
            topic_section = {
                "name": f"📚 Help: GitHub",
                "content": [
                    "**GitHub capabilities:**",
                    "• Create, update, and close issues",
                    "• Manage pull requests and reviews",
                    "• Search code across repositories",
                    "• List and analyze repositories",
                    "• Work with commits and branches",
                    "• Manage GitHub Actions workflows"
                ]
            }
            help_response["sections"].append(topic_section)
        elif "jira" in topic_lower:
            topic_section = {
                "name": f"📚 Help: Jira",
                "content": [
                    "**Jira capabilities:**",
                    "• Create and update tickets",
                    "• Manage sprints and boards",
                    "• Search and filter issues",
                    "• Work with projects and epics",
                    "• Track progress and generate reports",
                    "• Handle workflows and transitions"
                ]
            }
            help_response["sections"].append(topic_section)
    
    # Return just the help_response data - the decorator will wrap it
    return help_response


# You can add more core tools here in the future
# For example: status, ping, feedback, etc. 