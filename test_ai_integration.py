#!/usr/bin/env python3
"""
Test script to verify AI integration in the Slack bot.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from mistral_service import MistralService
from src.slack_healthcheck_bot import generate_kr_explanation

def test_ai_integration():
    """Test that AI responses are being used instead of placeholders."""
    print("🔍 Testing AI Integration in Slack Bot...")
    
    # Test 1: KR Explanation
    print("\n1️⃣ Testing KR Explanation...")
    kr_name = "KR1: Implement user authentication system"
    owner = "John Doe"
    status = "In Progress"
    definition_of_done = "User can log in, register, and reset password"
    
    explanation = generate_kr_explanation(kr_name, owner, status, definition_of_done)
    print(f"✅ KR Explanation: {explanation}")
    
    # Check if it's a placeholder
    if "placeholder" in explanation.lower():
        print("❌ Still using placeholder text!")
        return False
    else:
        print("✅ Using real AI response!")
    
    # Test 2: Help Suggestions
    print("\n2️⃣ Testing Help Suggestions...")
    mistral = MistralService()
    blocker = "I'm having trouble with the database connection in the authentication system"
    kr_name = "KR1: Implement user authentication system"
    
    suggestion = mistral.generate_help_suggestion(blocker, kr_name)
    print(f"✅ Help Suggestion: {suggestion}")
    
    # Check if it's a placeholder
    if "placeholder" in suggestion.lower():
        print("❌ Still using placeholder text!")
        return False
    else:
        print("✅ Using real AI response!")
    
    # Test 3: Standup Analysis
    print("\n3️⃣ Testing Standup Analysis...")
    standup_text = "Today I worked on the authentication system but I'm blocked by database connection issues. I'm not on track and need help."
    
    analysis = mistral.analyze_standup_response(standup_text)
    print(f"✅ Standup Analysis: {analysis}")
    
    # Check if it's a placeholder
    if "placeholder" in str(analysis).lower():
        print("❌ Still using placeholder text!")
        return False
    else:
        print("✅ Using real AI response!")
    
    print("\n🎉 All AI integration tests passed! The bot is using real AI responses.")
    return True

if __name__ == "__main__":
    success = test_ai_integration()
    if success:
        print("\n✅ AI Integration Verification Complete - No placeholders found!")
    else:
        print("\n❌ AI Integration Verification Failed - Placeholders still present!")
        sys.exit(1) 