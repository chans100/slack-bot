#!/usr/bin/env python3
"""
Test script for the Python Coda service.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from coda_service import CodaService

# Load environment variables
load_dotenv('.env')

def test_coda_service():
    """Test the Coda service functionality."""
    print("🚀 Python Coda Service Test")
    print("=" * 40)
    
    # Check environment variables
    required_vars = ["CODA_API_TOKEN", "CODA_DOC_ID", "CODA_TABLE_ID"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\n📋 Setup Instructions:")
        print("1. Add CODA_API_TOKEN to your .env file")
        print("2. Add CODA_DOC_ID to your .env file")
        print("3. Add CODA_TABLE_ID to your .env file")
        print("4. Add CODA_TABLE_ID2 to your .env file (optional)")
        return False
    
    try:
        # Initialize Coda service
        coda = CodaService()
        
        # Test connection
        print("\n🔍 Testing Coda connection...")
        if not coda.test_connection():
            print("❌ Coda connection test failed")
            return False
        
        # Test adding a response
        print("\n📝 Testing response storage...")
        test_user_id = "test_python_user_123"
        test_response = "5"
        
        success = coda.add_response(
            user_id=test_user_id,
            response=test_response,
            username="test_python_user"
        )
        
        if success:
            print("✅ Response storage successful!")
        else:
            print("❌ Response storage failed")
            return False
        
        # Test retrieving responses
        print("\n📖 Testing response retrieval...")
        responses = coda.get_user_responses(test_user_id, limit=5)
        if responses:
            print(f"✅ Retrieved {len(responses)} responses for user")
            for resp in responses:
                print(f"   - {resp.get('response', 'N/A')} at {resp.get('timestamp', 'N/A')}")
        else:
            print("⚠️ No responses found for test user")
        
        # Test getting responses by date
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"\n📅 Testing responses by date ({today})...")
        today_responses = coda.get_responses_by_date(today)
        print(f"✅ Found {len(today_responses)} responses for today")
        
        # Test blocker functionality if blocker table is configured
        if coda.blocker_table_id:
            print("\n🚨 Testing blocker storage...")
            blocker_success = coda.add_blocker(
                user_id=test_user_id,
                blocker_description="Test blocker from Python",
                kr_name="KR1: Test KR",
                urgency="High",
                notes="This is a test blocker",
                username="test_python_user"
            )
            
            if blocker_success:
                print("✅ Blocker storage successful!")
            else:
                print("❌ Blocker storage failed")
            
            # Test getting blockers by date
            print(f"\n📅 Testing blockers by date ({today})...")
            today_blockers = coda.get_blockers_by_date(today)
            print(f"✅ Found {len(today_blockers)} blockers for today")
        
        print("\n🎉 All Coda tests passed! Python bot can use Coda for storage.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def main():
    """Main test function."""
    success = test_coda_service()
    
    if success:
        print("\n✅ Python Coda service is working!")
        print("   - Both Node.js and Python bots can now use Coda")
        print("   - No more MongoDB dependency for Python bot")
        print("   - Unified data storage across both bots")
    else:
        print("\n❌ Python Coda service has issues.")
        print("   - Check your Coda API token and table IDs")
        print("   - Ensure your .env file has the correct values")
    
    return success

if __name__ == "__main__":
    main() 