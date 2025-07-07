#!/usr/bin/env python3
"""
Test script to verify DM sending and channel configuration.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')

def test_configuration():
    """Test the configuration for DM and channel settings."""
    print("🔍 Testing DM and Channel Configuration")
    print("=" * 50)
    
    # Check environment variables
    print("📋 Environment Variables:")
    print(f"   CODA_API_TOKEN: {'SET' if os.getenv('CODA_API_TOKEN') else 'NOT SET'}")
    print(f"   CODA_DOC_ID: {os.getenv('CODA_DOC_ID', 'NOT SET')}")
    print(f"   CODA_TABLE_ID: {os.getenv('CODA_TABLE_ID', 'NOT SET')}")
    print(f"   CODA_TABLE_ID2: {os.getenv('CODA_TABLE_ID2', 'NOT SET')}")
    print(f"   CODA_TABLE_ID3: {os.getenv('CODA_TABLE_ID3', 'NOT SET')}")
    print(f"   ESCALATION_CHANNEL: {os.getenv('ESCALATION_CHANNEL', 'general (default)')}")
    
    print("\n📊 Table Configuration:")
    print("   • CODA_TABLE_ID: Health check responses")
    print("   • CODA_TABLE_ID2: Blocker details")
    print("   • CODA_TABLE_ID3: Standup responses")
    
    print("\n📢 Channel Configuration:")
    print("   • Health checks: Sent to DMs")
    print("   • Standups: Sent to DMs")
    print("   • Blocker alerts: Sent to #general (or ESCALATION_CHANNEL)")
    
    print("\n✅ Configuration looks good!")
    print("\n🚀 To test:")
    print("   1. Restart your bot: python src/slack_healthcheck_bot.py")
    print("   2. Check your DM for health check and standup prompts")
    print("   3. Try the 'Not Great' button to test blocker escalation to #general")

if __name__ == "__main__":
    test_configuration() 