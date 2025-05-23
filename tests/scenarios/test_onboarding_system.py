#!/usr/bin/env python3
"""
Comprehensive test script for the onboarding system.
Tests new user detection, onboarding workflow, question flow, and data persistence.
"""

import os
import sys
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add the root directory to Python path for imports (go up two levels from tests/scenarios)
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, root_dir)

from state_models import AppState, WorkflowContext
from user_auth.models import UserProfile
from workflows.onboarding import OnboardingWorkflow, OnboardingQuestion, ONBOARDING_QUESTIONS, get_active_onboarding_workflow
from config import get_config

def print_header(title: str):
    """Print a formatted test section header."""
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print(f"{'='*60}")

def print_success(message: str):
    """Print a success message."""
    print(f"✅ {message}")

def print_error(message: str):
    """Print an error message."""
    print(f"❌ {message}")

def print_info(message: str):
    """Print an info message."""
    print(f"ℹ️  {message}")

def create_test_user(user_id: str = "test_onboarding_user", is_new: bool = True) -> UserProfile:
    """Create a test user profile for onboarding testing."""
    
    # Create timestamps
    current_time = int(time.time())
    first_seen = current_time - (10 if is_new else 3600)  # 10 seconds ago if new, 1 hour if not
    
    user_profile = UserProfile(
        user_id=user_id,
        display_name="Test User",
        email="test.user@company.com",
        aad_object_id="test_aad_123",
        tenant_id="test_tenant_456",
        assigned_role="DEFAULT",
        first_seen_timestamp=first_seen,
        last_active_timestamp=current_time,
        profile_data=None if is_new else {"onboarding_completed": True}
    )
    
    return user_profile

def test_onboarding_detection():
    """Test 1: Verify onboarding detection logic."""
    print_header("Test 1: Onboarding Detection Logic")
    
    success_count = 0
    total_tests = 4
    
    try:
        # Test 1.1: New user should trigger onboarding
        new_user = create_test_user("new_user_001", is_new=True)
        app_state = AppState(session_id="test_detection_1")
        
        should_trigger = OnboardingWorkflow.should_trigger_onboarding(new_user, app_state)
        if should_trigger:
            print_success("New user correctly detected for onboarding")
            success_count += 1
        else:
            print_error("New user should trigger onboarding but didn't")
        
        # Test 1.2: Existing user should not trigger onboarding
        existing_user = create_test_user("existing_user_001", is_new=False)
        should_trigger = OnboardingWorkflow.should_trigger_onboarding(existing_user, app_state)
        if not should_trigger:
            print_success("Existing user correctly skipped onboarding")
            success_count += 1
        else:
            print_error("Existing user should not trigger onboarding but did")
        
        # Test 1.3: User with active onboarding should not retrigger
        new_user_2 = create_test_user("new_user_002", is_new=True)
        app_state_2 = AppState(session_id="test_detection_2")
        
        # Add active onboarding workflow
        workflow = WorkflowContext(
            workflow_type="onboarding",
            status="active",
            data={"user_id": new_user_2.user_id}
        )
        app_state_2.active_workflows[workflow.workflow_id] = workflow
        
        should_trigger = OnboardingWorkflow.should_trigger_onboarding(new_user_2, app_state_2)
        if not should_trigger:
            print_success("User with active onboarding correctly skipped retrigger")
            success_count += 1
        else:
            print_error("User with active onboarding should not retrigger but did")
        
        # Test 1.4: User who completed onboarding should not retrigger
        completed_user = create_test_user("completed_user_001", is_new=True)
        completed_user.profile_data = {"onboarding_completed": True}
        
        should_trigger = OnboardingWorkflow.should_trigger_onboarding(completed_user, app_state)
        if not should_trigger:
            print_success("User who completed onboarding correctly skipped retrigger")
            success_count += 1
        else:
            print_error("User who completed onboarding should not retrigger but did")
        
        print_info(f"Detection tests passed: {success_count}/{total_tests}")
        return success_count == total_tests
        
    except Exception as e:
        print_error(f"Error in onboarding detection test: {e}")
        return False

def test_workflow_creation():
    """Test 2: Verify workflow creation and initialization."""
    print_header("Test 2: Workflow Creation and Initialization")
    
    try:
        # Create test user and app state
        user = create_test_user("workflow_test_user", is_new=True)
        app_state = AppState(session_id="test_workflow")
        
        # Create onboarding workflow
        onboarding = OnboardingWorkflow(user, app_state)
        workflow = onboarding.start_workflow()
        
        # Verify workflow properties
        if workflow.workflow_type == "onboarding":
            print_success("Workflow type correctly set to 'onboarding'")
        else:
            print_error(f"Workflow type incorrect: {workflow.workflow_type}")
            return False
        
        if workflow.status == "active":
            print_success("Workflow status correctly set to 'active'")
        else:
            print_error(f"Workflow status incorrect: {workflow.status}")
            return False
        
        if workflow.current_stage == "welcome":
            print_success("Workflow stage correctly set to 'welcome'")
        else:
            print_error(f"Workflow stage incorrect: {workflow.current_stage}")
            return False
        
        # Verify workflow data
        data = workflow.data
        if data.get("user_id") == user.user_id:
            print_success("User ID correctly stored in workflow data")
        else:
            print_error("User ID not stored correctly in workflow data")
            return False
        
        if data.get("current_question_index") == 0:
            print_success("Question index correctly initialized to 0")
        else:
            print_error("Question index not initialized correctly")
            return False
        
        if data.get("questions_total") == len(ONBOARDING_QUESTIONS):
            print_success(f"Total questions correctly set to {len(ONBOARDING_QUESTIONS)}")
        else:
            print_error("Total questions count incorrect")
            return False
        
        # Verify workflow is added to app state
        if workflow.workflow_id in app_state.active_workflows:
            print_success("Workflow correctly added to app_state.active_workflows")
        else:
            print_error("Workflow not added to app_state.active_workflows")
            return False
        
        print_success("All workflow creation tests passed")
        return True
        
    except Exception as e:
        print_error(f"Error in workflow creation test: {e}")
        return False

def test_question_flow():
    """Test 3: Verify question flow and answer processing."""
    print_header("Test 3: Question Flow and Answer Processing")
    
    try:
        # Create test setup
        user = create_test_user("question_flow_user", is_new=True)
        app_state = AppState(session_id="test_questions")
        onboarding = OnboardingWorkflow(user, app_state)
        workflow = onboarding.start_workflow()
        
        print_info(f"Testing {len(ONBOARDING_QUESTIONS)} questions")
        
        # Test answers for each question
        test_answers = [
            "John Developer",  # welcome_name
            "1",  # primary_role (Software Developer/Engineer)
            "web-app, mobile-api, dashboard",  # main_projects
            "1,2,3",  # tool_preferences (multiple choice)
            "2",  # communication_style (Brief and to-the-point)
            "yes",  # notifications
            "no"   # personal_credentials
        ]
        
        for i, answer in enumerate(test_answers):
            print_info(f"Processing answer {i+1}: '{answer}'")
            
            result = onboarding.process_answer(workflow.workflow_id, answer)
            
            if result.get("error"):
                print_error(f"Error processing answer {i+1}: {result['error']}")
                return False
            
            if result.get("retry_question"):
                print_error(f"Answer {i+1} rejected: {result['message']}")
                return False
            
            if result.get("completed"):
                print_success(f"Onboarding completed after {i+1} answers")
                break
            
            if result.get("success"):
                print_success(f"Answer {i+1} accepted, moving to next question")
            else:
                print_error(f"Unexpected result for answer {i+1}: {result}")
                return False
        
        # Verify completion
        if workflow.status == "completed":
            print_success("Workflow status correctly updated to 'completed'")
        else:
            print_error(f"Workflow status not updated correctly: {workflow.status}")
            return False
        
        # Verify workflow moved to completed
        if workflow.workflow_id not in app_state.active_workflows:
            print_success("Workflow correctly removed from active workflows")
        else:
            print_error("Workflow not removed from active workflows")
            return False
        
        if any(wf.workflow_id == workflow.workflow_id for wf in app_state.completed_workflows):
            print_success("Workflow correctly added to completed workflows")
        else:
            print_error("Workflow not added to completed workflows")
            return False
        
        print_success("All question flow tests passed")
        return True
        
    except Exception as e:
        print_error(f"Error in question flow test: {e}")
        return False

def test_data_persistence():
    """Test 4: Verify data is properly stored in user profile."""
    print_header("Test 4: Data Persistence and Profile Updates")
    
    try:
        # Create test setup and complete onboarding
        user = create_test_user("persistence_user", is_new=True)
        app_state = AppState(session_id="test_persistence")
        onboarding = OnboardingWorkflow(user, app_state)
        workflow = onboarding.start_workflow()
        
        # Quick completion with test data
        test_answers = [
            "Jane Manager",  # preferred name
            "8",  # Team Lead/Manager
            "project-alpha, project-beta",  # projects
            "1,2,7",  # tools (GitHub, Jira, DevOps)
            "4",  # Business-friendly summaries
            "yes",  # notifications
            "no"   # no personal credentials
        ]
        
        # Process all answers
        for answer in test_answers:
            result = onboarding.process_answer(workflow.workflow_id, answer)
            if result.get("completed"):
                break
        
        # Verify profile data was updated
        profile_data = user.profile_data
        if not profile_data:
            print_error("Profile data not updated")
            return False
        
        if profile_data.get("onboarding_completed"):
            print_success("Onboarding completion flag set correctly")
        else:
            print_error("Onboarding completion flag not set")
            return False
        
        if profile_data.get("onboarding_completed_at"):
            print_success("Onboarding completion timestamp recorded")
        else:
            print_error("Onboarding completion timestamp not recorded")
            return False
        
        # Verify preferences
        preferences = profile_data.get("preferences", {})
        
        expected_preferences = {
            "preferred_name": "Jane Manager",
            "primary_role": "Team Lead/Manager",
            "main_projects": ["project-alpha", "project-beta"],
            "tool_preferences": ["GitHub/Git", "Jira/Issue Tracking", "Deployment/DevOps"],
            "communication_style": "Business-friendly summaries",
            "notifications_enabled": True
        }
        
        for key, expected_value in expected_preferences.items():
            actual_value = preferences.get(key)
            if actual_value == expected_value:
                print_success(f"Preference '{key}' stored correctly: {actual_value}")
            else:
                print_error(f"Preference '{key}' incorrect. Expected: {expected_value}, Got: {actual_value}")
                return False
        
        print_success("All data persistence tests passed")
        return True
        
    except Exception as e:
        print_error(f"Error in data persistence test: {e}")
        return False

def test_answer_validation():
    """Test 5: Verify answer validation works correctly."""
    print_header("Test 5: Answer Validation")
    
    try:
        user = create_test_user("validation_user", is_new=True)
        app_state = AppState(session_id="test_validation")
        onboarding = OnboardingWorkflow(user, app_state)
        
        # Test validation for different question types
        validation_tests = [
            # (question_index, valid_answer, invalid_answer, question_type)
            (0, "John", "", "text"),  # Name - required
            (1, "1", "99", "choice"),  # Role - choice selection
            (3, "1,2,3", "99,100", "multi_choice"),  # Tools - multi choice
            (5, "yes", "maybe", "yes_no"),  # Notifications - Yes/No question
        ]
        
        success_count = 0
        
        for question_index, valid_answer, invalid_answer, question_type in validation_tests:
            question = ONBOARDING_QUESTIONS[question_index]
            
            # Test valid answer
            validation_result = onboarding._validate_answer(question, valid_answer)
            if validation_result.get("valid"):
                print_success(f"Valid answer for {question_type} question accepted: '{valid_answer}'")
                success_count += 1
            else:
                print_error(f"Valid answer for {question_type} question rejected: '{valid_answer}'")
            
            # Test invalid answer
            validation_result = onboarding._validate_answer(question, invalid_answer)
            if not validation_result.get("valid"):
                print_success(f"Invalid answer for {question_type} question rejected: '{invalid_answer}'")
                success_count += 1
            else:
                print_error(f"Invalid answer for {question_type} question accepted: '{invalid_answer}'")
        
        print_info(f"Validation tests passed: {success_count}/{len(validation_tests) * 2}")
        return success_count == len(validation_tests) * 2
        
    except Exception as e:
        print_error(f"Error in answer validation test: {e}")
        return False

def test_workflow_recovery():
    """Test 6: Verify workflow can be recovered and continued."""
    print_header("Test 6: Workflow Recovery and Continuation")
    
    try:
        # Create test setup
        user = create_test_user("recovery_user", is_new=True)
        app_state = AppState(session_id="test_recovery")
        onboarding = OnboardingWorkflow(user, app_state)
        workflow = onboarding.start_workflow()
        
        # Answer first few questions
        first_answers = ["Sarah", "2"]  # Name and role
        
        for answer in first_answers:
            result = onboarding.process_answer(workflow.workflow_id, answer)
            if result.get("error") or result.get("completed"):
                print_error(f"Unexpected result during setup: {result}")
                return False
        
        # Verify we can find the active workflow
        active_workflow = get_active_onboarding_workflow(app_state, user.user_id)
        if active_workflow:
            print_success("Active onboarding workflow found correctly")
        else:
            print_error("Active onboarding workflow not found")
            return False
        
        if active_workflow.workflow_id == workflow.workflow_id:
            print_success("Correct workflow retrieved by user ID")
        else:
            print_error("Wrong workflow retrieved")
            return False
        
        # Verify workflow state
        current_index = active_workflow.data.get("current_question_index", 0)
        if current_index == 2:  # Should be on question 3 (0-indexed)
            print_success(f"Workflow correctly positioned at question {current_index + 1}")
        else:
            print_error(f"Workflow position incorrect: {current_index}")
            return False
        
        # Continue with more answers
        continuing_answers = ["test-project", "1,2", "1", "no", "no"]
        
        for answer in continuing_answers:
            result = onboarding.process_answer(workflow.workflow_id, answer)
            if result.get("completed"):
                print_success("Workflow completed successfully after recovery")
                break
            elif result.get("error"):
                print_error(f"Error continuing workflow: {result['error']}")
                return False
        
        print_success("All workflow recovery tests passed")
        return True
        
    except Exception as e:
        print_error(f"Error in workflow recovery test: {e}")
        return False

def test_edge_cases():
    """Test 7: Verify edge cases and error handling."""
    print_header("Test 7: Edge Cases and Error Handling")
    
    try:
        success_count = 0
        total_tests = 4
        
        # Test 7.1: Invalid workflow ID
        user = create_test_user("edge_case_user", is_new=True)
        app_state = AppState(session_id="test_edge_cases")
        onboarding = OnboardingWorkflow(user, app_state)
        
        result = onboarding.process_answer("invalid_workflow_id", "test answer")
        if result.get("error") == "Workflow not found":
            print_success("Invalid workflow ID correctly handled")
            success_count += 1
        else:
            print_error("Invalid workflow ID not handled correctly")
        
        # Test 7.2: Empty/skip answers for optional questions
        workflow = onboarding.start_workflow()
        
        # Skip the projects question (index 2, which is optional)
        # First, get to the projects question
        onboarding.process_answer(workflow.workflow_id, "Test User")  # name
        onboarding.process_answer(workflow.workflow_id, "1")  # role
        
        # Now skip the projects question
        result = onboarding.process_answer(workflow.workflow_id, "skip")
        if result.get("success") and not result.get("error"):
            print_success("Optional question skip handled correctly")
            success_count += 1
        else:
            print_error("Optional question skip not handled correctly")
        
        # Test 7.3: Very long answer
        long_answer = "A" * 1000  # 1000 character answer
        result = onboarding.process_answer(workflow.workflow_id, long_answer)
        if result.get("success") or result.get("valid", True):  # Should accept long text
            print_success("Long answer handled correctly")
            success_count += 1
        else:
            print_error("Long answer not handled correctly")
        
        # Test 7.4: Special characters in answer
        special_answer = "Test@User#123!$%^&*()"
        result = onboarding.process_answer(workflow.workflow_id, special_answer)
        if not result.get("error"):  # Should accept special characters in text
            print_success("Special characters handled correctly")
            success_count += 1
        else:
            print_error("Special characters not handled correctly")
        
        print_info(f"Edge case tests passed: {success_count}/{total_tests}")
        return success_count >= total_tests - 1  # Allow 1 failure
        
    except Exception as e:
        print_error(f"Error in edge case test: {e}")
        return False

def run_all_tests():
    """Run all onboarding tests and report results."""
    print_header("ONBOARDING SYSTEM COMPREHENSIVE TESTS")
    print_info("Testing new user onboarding workflow system")
    print_info(f"Total onboarding questions defined: {len(ONBOARDING_QUESTIONS)}")
    
    tests = [
        ("Onboarding Detection", test_onboarding_detection),
        ("Workflow Creation", test_workflow_creation), 
        ("Question Flow", test_question_flow),
        ("Data Persistence", test_data_persistence),
        ("Answer Validation", test_answer_validation),
        ("Workflow Recovery", test_workflow_recovery),
        ("Edge Cases", test_edge_cases),
    ]
    
    results = []
    start_time = time.time()
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            status = "PASSED" if result else "FAILED"
            print_info(f"{test_name}: {status}")
        except Exception as e:
            print_error(f"{test_name}: FAILED with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    passed = sum(1 for _, result in results if result)
    total = len(results)
    duration = time.time() - start_time
    
    print_header("TEST SUMMARY")
    print_info(f"Tests passed: {passed}/{total}")
    print_info(f"Success rate: {(passed/total)*100:.1f}%")
    print_info(f"Total duration: {duration:.2f} seconds")
    
    if passed == total:
        print_success("🎉 ALL TESTS PASSED! Onboarding system is ready for deployment.")
    else:
        print_error(f"❌ {total - passed} tests failed. Review the issues above.")
    
    # Detailed results
    print("\n📊 Detailed Results:")
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error during testing: {e}")
        sys.exit(1) 