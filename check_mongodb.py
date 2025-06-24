#!/usr/bin/env python3
"""
Script to check MongoDB data for the Slack bot
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime

# Load environment variables
load_dotenv()

def check_mongodb_data():
    """Check what data is in MongoDB"""
    print("🔍 Checking MongoDB data...")
    
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
        
        # List all collections
        collections = db.list_collection_names()
        print(f"\n📁 Collections in database '{db_name}':")
        for collection in collections:
            print(f"   - {collection}")
        
        # Check Answer collection specifically
        if 'Answer' in collections:
            print(f"\n📊 Data in 'Answer' collection:")
            answers = list(db.Answer.find())
            print(f"   Total documents: {len(answers)}")
            
            if answers:
                print("\n   Recent documents:")
                for i, answer in enumerate(answers[-5:], 1):  # Show last 5
                    print(f"   {i}. User: {answer.get('user_name', 'Unknown')}")
                    print(f"      Response: {answer.get('response_data', 'Unknown')}")
                    print(f"      Date: {answer.get('date', 'Unknown')}")
                    print(f"      Time: {answer.get('timestamp', 'Unknown')}")
                    print()
            else:
                print("   No documents found in Answer collection")
        else:
            print("\n❌ 'Answer' collection not found!")
        
        # Check if there are any other collections with data
        for collection in collections:
            if collection != 'Answer':
                count = db[collection].count_documents({})
                if count > 0:
                    print(f"\n📋 Collection '{collection}' has {count} documents")
        
        client.close()
        
    except ConnectionFailure as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def add_test_data():
    """Add some test data to see if it appears"""
    print("\n🔍 Adding test data...")
    
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
    db_name = os.environ.get("MONGODB_DB_NAME", "SlackBot")
    
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        
        # Add test data
        test_data = {
            "user_id": "U123456789",
            "user_name": "test123",
            "response_type": "button_click",
            "response_data": "great",
            "message_ts": "1234567890.123456",
            "channel_id": "C123456789",
            "timestamp": datetime.utcnow(),
            "date": datetime.utcnow().strftime("%Y-%m-%d")
        }
        
        result = db.Answer.insert_one(test_data)
        print(f"✅ Added test data with ID: {result.inserted_id}")
        print(f"   User: test123")
        print(f"   Response: great")
        print(f"   Date: {test_data['date']}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Error adding test data: {e}")
        return False

if __name__ == "__main__":
    print("🚀 MongoDB Data Checker")
    print("=" * 40)
    
    # Check existing data
    check_mongodb_data()
    
    # Ask if user wants to add test data
    print("\n" + "=" * 40)
    response = input("Do you want to add test data for user 'test123'? (y/n): ")
    
    if response.lower() == 'y':
        add_test_data()
        print("\n🔍 Checking data again after adding test data...")
        check_mongodb_data()
    
    print("\n✅ Check complete!") 