#!/usr/bin/env python3
"""
Test Slack event handling
"""

import requests
import json

def test_slack_event():
    """Test if the bot can receive Slack events"""
    print("🔍 Testing Slack event handling...")
    
    # Simulate a button click event from Slack
    event_payload = {
        "type": "block_actions",
        "user": {
            "id": "U123456789",
            "name": "test123"
        },
        "actions": [
            {
                "value": "great",
                "action_id": "great"
            }
        ],
        "message": {
            "ts": "1234567890.123456"
        },
        "channel": {
            "id": "C123456789"
        }
    }
    
    try:
        # Send to local bot
        response = requests.post(
            "http://localhost:3000/slack/events",
            json=event_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"✅ Local response status: {response.status_code}")
        print(f"✅ Local response: {response.text}")
        
        # Send to ngrok URL
        ngrok_response = requests.post(
            "https://b78d-113-32-246-170.ngrok-free.app/slack/events",
            json=event_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"✅ Ngrok response status: {ngrok_response.status_code}")
        print(f"✅ Ngrok response: {ngrok_response.text}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Slack Event Test")
    print("=" * 40)
    test_slack_event() 