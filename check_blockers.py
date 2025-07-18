#!/usr/bin/env python3
"""
Check the current status of tracked blockers.
"""

import requests
import json

def check_blockers():
    """Check the current status of tracked blockers."""
    
    # Your ngrok URL
    url = "https://5175473613b3.ngrok-free.app/slack/events"
    
    # Send a simple ping to trigger blocker check
    ping_data = {
        'type': 'ping',
        'test': 'check_blockers'
    }
    
    print("🔍 Checking tracked blockers status...")
    
    try:
        response = requests.post(url, json=ping_data, timeout=10)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📄 Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Blocker check completed")
        else:
            print("❌ Failed to check blockers")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_blockers() 