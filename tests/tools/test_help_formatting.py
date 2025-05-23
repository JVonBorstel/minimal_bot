#!/usr/bin/env python3
"""Test help tool formatting and output quality."""

import asyncio
import logging
import sys
import os
import json
import pytest # Add pytest

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.tool_executor import ToolExecutor
from config import get_config
from state_models import AppState
from user_auth.models import UserProfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("test_help_formatting")

@pytest.mark.asyncio
async def test_help_response_structure():
    """Test that help tool returns proper structured response."""
    print("🔍 TESTING HELP RESPONSE STRUCTURE")
    print("=" * 50)
    
    try:
        config = get_config()
        app_state = AppState()
        test_user = UserProfile(
            user_id="format_test_user",
            display_name="Format Test User",
            email="format@test.com",
            assigned_role="ADMIN"
        )
        app_state.current_user = test_user
        
        executor = ToolExecutor(config)
        
        # Execute help tool
        result = await executor.execute_tool("help", {}, app_state)
        
        print(f"📊 Response type: {type(result)}")
        
        # Check top-level structure
        if not isinstance(result, dict):
            print("❌ Response is not a dictionary")
            return False
            
        # Check required top-level keys
        required_keys = ['status', 'data']
        for key in required_keys:
            if key not in result:
                print(f"❌ Missing required key: {key}")
                return False
            print(f"✅ Found required key: {key}")
        
        # Check status
        if result['status'] != 'SUCCESS':
            print(f"❌ Unexpected status: {result['status']}")
            return False
        print("✅ Status is SUCCESS")
        
        # Check data structure
        help_data = result['data']
        if not isinstance(help_data, dict):
            print(f"❌ Help data is not a dictionary: {type(help_data)}")
            return False
        print("✅ Help data is a dictionary")
        
        # Check help data required keys
        help_required_keys = ['title', 'description', 'sections']
        for key in help_required_keys:
            if key not in help_data:
                print(f"❌ Missing help data key: {key}")
                return False
            print(f"✅ Found help data key: {key}")
        
        print("✅ All required structure elements present")
        return True
        
    except Exception as e:
        print(f"❌ Exception during structure testing: {e}")
        log.error(f"Structure test exception: {e}", exc_info=True)
        return False

@pytest.mark.asyncio
async def test_help_content_quality():
    """Test the quality and completeness of help content."""
    print("\n🔍 TESTING HELP CONTENT QUALITY")
    print("=" * 50)
    
    try:
        config = get_config()
        app_state = AppState()
        test_user = UserProfile(
            user_id="content_test_user",
            display_name="Content Test User",
            email="content@test.com",
            assigned_role="ADMIN"
        )
        app_state.current_user = test_user
        
        executor = ToolExecutor(config)
        
        # Execute help tool
        result = await executor.execute_tool("help", {}, app_state)
        
        if not (isinstance(result, dict) and result.get('status') == 'SUCCESS'):
            print("❌ Help tool execution failed")
            return False
            
        help_data = result['data']
        
        # Test title
        title = help_data.get('title', '')
        if not title or len(title.strip()) < 10:
            print(f"❌ Title too short or missing: '{title}'")
            return False
        print(f"✅ Title is present and meaningful: '{title}'")
        
        # Test description
        description = help_data.get('description', '')
        if not description or len(description.strip()) < 20:
            print(f"❌ Description too short or missing: '{description}'")
            return False
        print(f"✅ Description is present and meaningful")
        
        # Test sections
        sections = help_data.get('sections', [])
        if not isinstance(sections, list) or len(sections) < 3:
            print(f"❌ Insufficient sections: {len(sections)}")
            return False
        print(f"✅ Good number of sections: {len(sections)}")
        
        # Test section content
        total_content_items = 0
        for i, section in enumerate(sections):
            if not isinstance(section, dict):
                print(f"❌ Section {i+1} is not a dictionary")
                return False
                
            section_name = section.get('name', '')
            section_content = section.get('content', [])
            
            if not section_name:
                print(f"❌ Section {i+1} missing name")
                return False
                
            if not isinstance(section_content, list) or len(section_content) == 0:
                print(f"❌ Section {i+1} missing or empty content")
                return False
                
            total_content_items += len(section_content)
            print(f"✅ Section '{section_name}': {len(section_content)} items")
        
        # Check total content volume
        if total_content_items < 10:
            print(f"❌ Insufficient total content items: {total_content_items}")
            return False
        print(f"✅ Good content volume: {total_content_items} total items")
        
        # Check for key topics (should mention main tool categories)
        help_text_str = json.dumps(help_data).lower()
        
        expected_mentions = ['github', 'jira', 'greptile', 'perplexity']
        mentions_found = []
        for mention in expected_mentions:
            if mention in help_text_str:
                mentions_found.append(mention)
                print(f"✅ Mentions {mention} tools")
            else:
                print(f"⚠️  Does not explicitly mention {mention}")
        
        if len(mentions_found) >= 3:
            print("✅ Good coverage of main tool categories")
        else:
            print(f"⚠️  Limited tool category coverage: {mentions_found}")
            
        return True
        
    except Exception as e:
        print(f"❌ Exception during content quality testing: {e}")
        log.error(f"Content quality test exception: {e}", exc_info=True)
        return False

@pytest.mark.asyncio
async def test_help_with_topic():
    """Test help tool with topic parameter."""
    print("\n🔍 TESTING HELP WITH TOPIC PARAMETER")
    print("=" * 50)
    
    try:
        config = get_config()
        app_state = AppState()
        test_user = UserProfile(
            user_id="topic_test_user",
            display_name="Topic Test User",
            email="topic@test.com",
            assigned_role="ADMIN"
        )
        app_state.current_user = test_user
        
        executor = ToolExecutor(config)
        
        # Test with GitHub topic
        print("Testing help with 'github' topic...")
        github_result = await executor.execute_tool("help", {"topic": "github"}, app_state)
        
        if not (isinstance(github_result, dict) and github_result.get('status') == 'SUCCESS'):
            print("❌ GitHub topic help failed")
            return False
            
        github_data = github_result['data']
        github_text = json.dumps(github_data).lower()
        
        if 'github' not in github_text:
            print("❌ GitHub topic help doesn't mention GitHub")
            return False
        print("✅ GitHub topic help mentions GitHub")
        
        # Test with Jira topic
        print("Testing help with 'jira' topic...")
        jira_result = await executor.execute_tool("help", {"topic": "jira"}, app_state)
        
        if not (isinstance(jira_result, dict) and jira_result.get('status') == 'SUCCESS'):
            print("❌ Jira topic help failed")
            return False
            
        jira_data = jira_result['data']
        jira_text = json.dumps(jira_data).lower()
        
        if 'jira' not in jira_text:
            print("❌ Jira topic help doesn't mention Jira")
            return False
        print("✅ Jira topic help mentions Jira")
        
        # Test with no topic (should still work)
        print("Testing help with no topic...")
        no_topic_result = await executor.execute_tool("help", {}, app_state)
        
        if not (isinstance(no_topic_result, dict) and no_topic_result.get('status') == 'SUCCESS'):
            print("❌ No topic help failed")
            return False
        print("✅ No topic help works correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Exception during topic testing: {e}")
        log.error(f"Topic test exception: {e}", exc_info=True)
        return False

@pytest.mark.asyncio
async def test_help_readability():
    """Test that help output is readable and well-formatted."""
    print("\n🔍 TESTING HELP OUTPUT READABILITY")
    print("=" * 50)
    
    try:
        config = get_config()
        app_state = AppState()
        test_user = UserProfile(
            user_id="readability_test_user",
            display_name="Readability Test User",
            email="readability@test.com",
            assigned_role="ADMIN"
        )
        app_state.current_user = test_user
        
        executor = ToolExecutor(config)
        
        # Execute help tool
        result = await executor.execute_tool("help", {}, app_state)
        
        if not (isinstance(result, dict) and result.get('status') == 'SUCCESS'):
            print("❌ Help tool execution failed")
            return False
            
        help_data = result['data']
        
        # Convert to a readable format for analysis
        def format_help_for_display(data):
            """Format help data for human-readable display."""
            output = []
            output.append(f"Title: {data.get('title', 'N/A')}")
            output.append(f"Description: {data.get('description', 'N/A')}")
            output.append("")
            
            sections = data.get('sections', [])
            for section in sections:
                if isinstance(section, dict):
                    name = section.get('name', 'Unnamed Section')
                    content = section.get('content', [])
                    
                    output.append(f"## {name}")
                    for item in content:
                        if isinstance(item, str):
                            output.append(f"  {item}")
                    output.append("")
            
            return "\n".join(output)
        
        formatted_help = format_help_for_display(help_data)
        
        # Save formatted help for inspection
        with open("help_output_sample.txt", "w", encoding="utf-8") as f:
            f.write(formatted_help)
        print("✅ Saved formatted help output to 'help_output_sample.txt'")
        
        # Basic readability checks
        lines = formatted_help.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        if len(non_empty_lines) < 15:
            print(f"❌ Output too short: {len(non_empty_lines)} lines")
            return False
        print(f"✅ Good output length: {len(non_empty_lines)} lines")
        
        # Check for proper structure indicators
        structure_indicators = ['##', '•', '**', ':', '-']
        indicators_found = 0
        for indicator in structure_indicators:
            if indicator in formatted_help:
                indicators_found += 1
        
        if indicators_found >= 2:
            print(f"✅ Good use of formatting indicators: {indicators_found}")
        else:
            print(f"⚠️  Limited formatting indicators: {indicators_found}")
        
        print("\n📄 SAMPLE OUTPUT (first 10 lines):")
        print("-" * 40)
        for i, line in enumerate(lines[:10]):
            print(line)
        if len(lines) > 10:
            print("...")
        print("-" * 40)
        
        return True
        
    except Exception as e:
        print(f"❌ Exception during readability testing: {e}")
        log.error(f"Readability test exception: {e}", exc_info=True)
        return False

async def main():
    """Run all help formatting tests."""
    print("🤖 STEP 1.15: HELP TOOL FORMATTING VALIDATION")
    print("=" * 70)
    
    # Test 1: Response structure
    success1 = await test_help_response_structure()
    
    # Test 2: Content quality
    success2 = await test_help_content_quality()
    
    # Test 3: Topic parameter
    success3 = await test_help_with_topic()
    
    # Test 4: Readability
    success4 = await test_help_readability()
    
    # Summary
    print("\n📊 FORMATTING TEST SUMMARY")
    print("=" * 40)
    print(f"Response Structure: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"Content Quality: {'✅ PASS' if success2 else '❌ FAIL'}")
    print(f"Topic Parameter: {'✅ PASS' if success3 else '❌ FAIL'}")
    print(f"Output Readability: {'✅ PASS' if success4 else '❌ FAIL'}")
    
    overall_success = success1 and success2 and success3 and success4
    
    if overall_success:
        print(f"\n🎉 ALL FORMATTING TESTS PASSED!")
        print(f"✅ Help tool provides clean, readable output")
        print(f"✅ Help content is well-structured and informative")
        print(f"✅ Topic parameter functionality works correctly")
    else:
        print(f"\n❌ FORMATTING TESTS FAILED!")
        print(f"❌ Help tool output quality needs improvement")
    
    return overall_success

if __name__ == "__main__":
    asyncio.run(main()) 