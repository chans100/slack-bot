#!/usr/bin/env python3
"""
Test script for the fixed MongoDB service with improved SSL handling.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')

# Import the fixed MongoDB service
from mongodb_service_fixed import MongoDBService

def test_mongodb_connection():
    """Test MongoDB connection with improved SSL handling."""
    print("🚀 Fixed MongoDB Integration Test Suite")
    print("=" * 50)
    
    # Get MongoDB configuration from environment
    mongodb_uri = os.environ.get("MONGODB_URI")
    db_name = os.environ.get("MONGODB_DB_NAME", "SlackBot")
    
    print(f"🔍 Testing MongoDB connection...")
    print(f"Database Name: {db_name}")
    
    if not mongodb_uri:
        print("❌ MONGODB_URI not found in environment variables")
        print("💡 Please add MONGODB_URI to your .env file")
        return False
    
    try:
        # Initialize MongoDB service
        mongo_service = MongoDBService()
        
        # Test basic operations
        if mongo_service.collection is None:
            print("❌ MongoDB connection failed")
            return False
        
        print("✅ MongoDB connection successful!")
        
        # Test storing a response
        test_user_id = "test_user_123"
        test_username = "test_user"
        test_response = "5"
        test_channel = "test_channel"
        test_message_ts = "1234567890.123456"
        
        print("\n📝 Testing response storage...")
        result = mongo_service.store_response(
            user_id=test_user_id,
            username=test_username,
            response_type="button_click",
            channel_id=test_channel,
            message_ts=test_message_ts,
            text=test_response
        )
        
        if result:
            print("✅ Response storage successful!")
        else:
            print("❌ Response storage failed")
            return False
        
        # Test retrieving responses
        print("\n📖 Testing response retrieval...")
        responses = mongo_service.get_user_responses(test_user_id, limit=5)
        if responses:
            print(f"✅ Retrieved {len(responses)} responses for user")
            for resp in responses:
                print(f"   - {resp.get('text', 'N/A')} at {resp.get('timestamp', 'N/A')}")
        else:
            print("⚠️ No responses found for test user")
        
        # Test follow-up tracking
        print("\n🔄 Testing follow-up tracking...")
        followup_result = mongo_service.store_followup_sent(
            user_id=test_user_id,
            thread_ts=test_message_ts,
            followup_ts="1234567890.123457"
        )
        
        if followup_result:
            print("✅ Follow-up tracking successful!")
        else:
            print("❌ Follow-up tracking failed")
        
        # Test message processing tracking
        print("\n✅ Testing message processing tracking...")
        processed_result = mongo_service.mark_message_processed(
            message_ts=test_message_ts,
            user_id=test_user_id,
            thread_ts=test_message_ts
        )
        
        if processed_result:
            print("✅ Message processing tracking successful!")
        else:
            print("❌ Message processing tracking failed")
        
        # Test getting responses by date
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"\n📅 Testing responses by date ({today})...")
        today_responses = mongo_service.get_responses_by_date(today)
        print(f"✅ Found {len(today_responses)} responses for today")
        
        # Clean up test data
        print("\n🧹 Cleaning up test data...")
        mongo_service.delete_document("responses", {"user_id": test_user_id})
        mongo_service.delete_document("followups", {"user_id": test_user_id})
        mongo_service.delete_document("processed_messages", {"user_id": test_user_id})
        print("✅ Test data cleaned up")
        
        # Close connection
        mongo_service.close()
        
        print("\n🎉 All tests passed! MongoDB is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def main():
    """Main test function."""
    print("🔧 MongoDB SSL Fix Test")
    print("=" * 30)
    
    # Check if required environment variables are set
    required_vars = ["MONGODB_URI"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\n📋 Setup Instructions:")
        print("1. Create a .env file in your project root")
        print("2. Add your MongoDB Atlas connection string:")
        print("   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/database")
        print("3. Add your database name (optional):")
        print("   MONGODB_DB_NAME=your_database_name")
        return False
    
    # Run the test
    success = test_mongodb_connection()
    
    if success:
        print("\n✅ MongoDB is now working! Both bots can run.")
        print("   - Node.js bot: Uses Coda for storage")
        print("   - Python bot: Uses MongoDB for storage")
    else:
        print("\n❌ MongoDB still has issues. Check your connection string and network access.")
    
    return success

if __name__ == "__main__":
    main() 