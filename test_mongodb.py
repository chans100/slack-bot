#!/usr/bin/env python3
"""
Test script for MongoDB integration
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime

# Load environment variables
load_dotenv()

def test_mongodb_connection():
    """Test MongoDB connection"""
    print("🔍 Testing MongoDB connection...")
    
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
    db_name = os.environ.get("MONGODB_DB_NAME", "SlackBot")
    
    print(f"MongoDB URI: {mongo_uri}")
    print(f"Database Name: {db_name}")
    
    try:
        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        
        # Test the connection
        client.admin.command('ping')
        print("✅ MongoDB connection successful!")
        
        # Get database
        db = client[db_name]
        
        # Test inserting a document
        test_doc = {
            "test": True,
            "timestamp": datetime.utcnow(),
            "message": "Test connection"
        }
        
        result = db.test_collection.insert_one(test_doc)
        print(f"✅ Test document inserted with ID: {result.inserted_id}")
        
        # Test retrieving the document
        retrieved_doc = db.test_collection.find_one({"_id": result.inserted_id})
        if retrieved_doc:
            print("✅ Test document retrieved successfully!")
        
        # Clean up test document
        db.test_collection.delete_one({"_id": result.inserted_id})
        print("✅ Test document cleaned up")
        
        # Close connection
        client.close()
        print("✅ MongoDB test completed successfully!")
        return True
        
    except ConnectionFailure as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("\n💡 Make sure MongoDB is running:")
        print("   - Local: Start MongoDB service")
        print("   - Atlas: Check connection string and network access")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_response_storage():
    """Test storing a mock response"""
    print("\n🔍 Testing response storage...")
    
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
    db_name = os.environ.get("MONGODB_DB_NAME", "SlackBot")
    
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Mock response data
        mock_response = {
            "user_id": "U123456789",
            "user_name": "Test User",
            "response_type": "button_click",
            "response_data": "great",
            "message_ts": "1234567890.123456",
            "channel_id": "C123456789",
            "timestamp": datetime.utcnow(),
            "date": datetime.utcnow().strftime("%Y-%m-%d")
        }
        
        # Store the response
        result = db.Answer.insert_one(mock_response)
        print(f"✅ Mock response stored with ID: {result.inserted_id}")
        
        # Retrieve the response
        retrieved = db.Answer.find_one({"_id": result.inserted_id})
        if retrieved:
            print(f"✅ Mock response retrieved: {retrieved['user_name']} - {retrieved['response_data']}")
        
        # Clean up
        db.Answer.delete_one({"_id": result.inserted_id})
        print("✅ Mock response cleaned up")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Response storage test failed: {e}")
        return False

def test_daily_summary():
    """Test daily summary aggregation"""
    print("\n🔍 Testing daily summary...")
    
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
    db_name = os.environ.get("MONGODB_DB_NAME", "SlackBot")
    
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Insert some test data
        test_responses = [
            {
                "user_id": "U1",
                "user_name": "Alice",
                "response_type": "button_click",
                "response_data": "great",
                "message_ts": "1234567890.123456",
                "channel_id": "C123456789",
                "timestamp": datetime.utcnow(),
                "date": today
            },
            {
                "user_id": "U2", 
                "user_name": "Bob",
                "response_type": "button_click",
                "response_data": "okay",
                "message_ts": "1234567890.123457",
                "channel_id": "C123456789",
                "timestamp": datetime.utcnow(),
                "date": today
            },
            {
                "user_id": "U3",
                "user_name": "Charlie", 
                "response_type": "button_click",
                "response_data": "great",
                "message_ts": "1234567890.123458",
                "channel_id": "C123456789",
                "timestamp": datetime.utcnow(),
                "date": today
            }
        ]
        
        # Insert test data
        result = db.Answer.insert_many(test_responses)
        print(f"✅ Inserted {len(result.inserted_ids)} test responses")
        
        # Test aggregation pipeline
        pipeline = [
            {"$match": {"date": today}},
            {"$group": {
                "_id": "$response_data",
                "count": {"$sum": 1},
                "users": {"$addToSet": "$user_name"}
            }},
            {"$sort": {"count": -1}}
        ]
        
        summary = list(db.Answer.aggregate(pipeline))
        print(f"✅ Daily summary generated: {len(summary)} response types")
        
        for item in summary:
            print(f"   {item['_id']}: {item['count']} responses from {item['users']}")
        
        # Clean up test data
        db.Answer.delete_many({"date": today})
        print("✅ Test data cleaned up")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Daily summary test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 MongoDB Integration Test Suite")
    print("=" * 40)
    
    # Run tests
    connection_ok = test_mongodb_connection()
    
    if connection_ok:
        storage_ok = test_response_storage()
        summary_ok = test_daily_summary()
        
        if storage_ok and summary_ok:
            print("\n🎉 All tests passed! MongoDB integration is working correctly.")
        else:
            print("\n⚠️  Some tests failed. Check the output above for details.")
    else:
        print("\n❌ MongoDB connection failed. Please check your configuration.")
        print("\n📋 Setup Instructions:")
        print("1. Install MongoDB locally or use MongoDB Atlas")
        print("2. Update your .env file with correct MONGODB_URI and MONGODB_DB_NAME")
        print("3. Ensure MongoDB is running and accessible") 