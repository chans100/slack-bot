#!/usr/bin/env python3
"""
Test script to verify KR status update functionality
"""

from coda_service import CodaService
import os

def test_kr_update():
    """Test KR status update with correct column names"""
    
    # Initialize Coda service
    coda = CodaService()
    
    if not coda.api_token:
        print("❌ No API token configured")
        return False
    
    print("🔍 Testing KR status update...")
    
    # Test finding a KR row
    kr_name = "Draft Slack Healthcheck Prompt Flow (v1)"
    print(f"🔍 Looking for KR: '{kr_name}'")
    
    kr_row = coda.find_kr_row(kr_name)
    if kr_row:
        print(f"✅ Found KR row: {kr_row.get('id')}")
        
        # Test KR information display
        print("🔍 Testing KR information display...")
        kr_info = coda.get_kr_display_info(kr_name)
        
        if kr_info:
            print("✅ KR information retrieved successfully!")
            print(f"   KR Name: {kr_info.get('kr_name', 'Unknown')}")
            print(f"   Owner: {kr_info.get('owner', 'Unknown')}")
            print(f"   Status: {kr_info.get('status', 'Unknown')}")
            print(f"   Progress: {kr_info.get('progress', 'Unknown')}%")
            print(f"   Objective: {kr_info.get('objective', 'Unknown')}")
            print(f"   Sprint: {kr_info.get('sprint', 'Unknown')}")
            print(f"   Predicted Hours: {kr_info.get('predicted_hours', 'Unknown')}")
            print(f"   Urgency: {kr_info.get('urgency', 'Unknown')}")
            return True
        else:
            print("❌ KR information retrieval failed")
            return False
    else:
        print(f"❌ KR '{kr_name}' not found")
        return False

if __name__ == "__main__":
    test_kr_update() 