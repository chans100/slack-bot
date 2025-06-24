#!/usr/bin/env python3
"""
Test MongoDB Atlas connection
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime

# Load environment variables
load_dotenv()

def test_atlas_connection():
    """Test MongoDB Atlas connection"""
    print("🔍 Testing MongoDB Atlas connection...")
    
    # Atlas connection string
    mongo_uri = "mongodb+srv://test123:test123@cluster0.ooqfbmp.mongodb.net/"
    db_name = "SlackBot"
    
    print(f"MongoDB URI: {mongo_uri}")
    print(f"Database Name: {db_name}")
    
    try:
        # Connect to MongoDB Atlas
        client = MongoClient(mongo_uri)
        
        # Test the connection
        client.admin.command('ping')
        print("✅ MongoDB Atlas connection successful!")
        
        # Get database
        db = client[db_name]
        
        # List all collections
        collections = db.list_collection_names()
        print(f"\n📁 Collections in database '{db_name}':")
        for collection in collections:
            print(f"   - {collection}")
        
        # Test inserting a document
        test_doc = {
            "test": True,
            "timestamp": datetime.utcnow(),
            "message": "Test Atlas connection",
            "user": "test123"
        }
        
        # Use Answer collection
        result = db.Answer.insert_one(test_doc)
        print(f"✅ Test document inserted with ID: {result.inserted_id}")
        
        # Test retrieving the document
        retrieved_doc = db.Answer.find_one({"_id": result.inserted_id})
        if retrieved_doc:
            print("✅ Test document retrieved successfully!")
            print(f"   User: {retrieved_doc.get('user', 'Unknown')}")
            print(f"   Message: {retrieved_doc.get('message', 'Unknown')}")
        
        # Clean up test document
        db.Answer.delete_one({"_id": result.inserted_id})
        print("✅ Test document cleaned up")
        
        # Close connection
        client.close()
        print("✅ MongoDB Atlas test completed successfully!")
        return True
        
    except ConnectionFailure as e:
        print(f"❌ MongoDB Atlas connection failed: {e}")
        print("\n💡 Check your credentials and network access")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 MongoDB Atlas Connection Test")
    print("=" * 40)
    
    test_atlas_connection() 