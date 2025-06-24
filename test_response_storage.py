#!/usr/bin/env python3
"""
Test response storage by simulating a button click
"""

import requests
import json
from datetime import datetime

def test_button_click():
    """Simulate a button click event"""
    print("🔍 Testing response storage...")
    
    # Simulate the payload that Slack would send
    payload = {
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
        # Send the payload to the bot
        response = requests.post(
            "http://localhost:3000/slack/events",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"✅ Response status: {response.status_code}")
        print(f"✅ Response content: {response.text}")
        
        if response.status_code == 200:
            print("✅ Button click processed successfully!")
        else:
            print("❌ Button click failed!")
            
    except Exception as e:
        print(f"❌ Error testing button click: {e}")

def test_api_endpoints():
    """Test the API endpoints"""
    print("\n🔍 Testing API endpoints...")
    
    try:
        # Test today's report
        response = requests.get("http://localhost:3000/api/report")
        print(f"✅ Today's report status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Report: {data.get('report', 'No report')}")
        else:
            print(f"❌ Report failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing API: {e}")

if __name__ == "__main__":
    print("🚀 Response Storage Test")
    print("=" * 40)
    
    # Test button click
    test_button_click()
    
    # Test API endpoints
    test_api_endpoints()
    
    print("\n✅ Test complete!") 