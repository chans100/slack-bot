#!/usr/bin/env python3
"""
Test script for Mistral AI integration.
"""

import os
from importlib import reload
import src.config

def test_mistral_integration():
    """Test the Mistral AI integration."""
    
    # Set the API key for testing
    os.environ["MISTRAL_API_KEY"] = "7McVGm2Nx6Hp3JIoO2cDJIJtk3zhoyj1"
    reload(src.config)
    from src.config import BotConfig
    from mistral_service import MistralService
    
    print("🔍 Testing Mistral AI integration...")
    print(f"🔍 API Key: {os.environ.get('MISTRAL_API_KEY', 'Not set')}")
    
    # Initialize Mistral service
    mistral = MistralService()
    print(f"🔍 Mistral API Key in service: {mistral.api_key}")
    
    # Test connection
    print("\n1️⃣ Testing connection...")
    if mistral.test_connection():
        print("✅ Connection successful!")
    else:
        print("❌ Connection failed!")
        return False
    
    # Test KR explanation
    print("\n2️⃣ Testing KR explanation...")
    kr_name = "Draft Slack Healthcheck Prompt Flow (v1)"
    owner = "Alexander Chan"
    status = "Done"
    
    explanation = mistral.generate_kr_explanation(kr_name, owner, status)
    print(f"✅ KR Explanation: {explanation}")
    
    # Test help suggestion
    print("\n3️⃣ Testing help suggestion...")
    blocker = "Need help with API integration"
    suggestion = mistral.generate_help_suggestion(blocker, kr_name)
    print(f"✅ Help Suggestion: {suggestion}")
    
    # Test standup analysis
    print("\n4️⃣ Testing standup analysis...")
    response = "Today: Worked on the bot integration. On Track: No, blocked by API issues. Blockers: Need help with Mistral API setup."
    analysis = mistral.analyze_standup_response(response)
    print(f"✅ Standup Analysis: {analysis}")
    
    print("\n🎉 All tests completed!")
    return True

if __name__ == "__main__":
    test_mistral_integration() 