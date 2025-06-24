#!/usr/bin/env python3
"""
Test button click simulation
"""

import requests
import json

def test_button_click():
    """Simulate a button click event"""
    print("🔍 Testing button click event...")
    
    # Simulate the payload that Slack would send for a button click
    payload = {
        "type": "block_actions",
        "user": {
            "id": "U091P8JB77U",
            "name": "test123"
        },
        "actions": [
            {
                "action_id": "great",
                "value": "great",
                "type": "button"
            }
        ],
        "message": {
            "ts": "1750265423.900279"
        },
        "channel": {
            "id": "C091XRDAE4Q"
        },
        "team": {
            "id": "T0919MVQC5A"
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

if __name__ == "__main__":
    test_button_click() 