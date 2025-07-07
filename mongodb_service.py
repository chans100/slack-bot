"""
MongoDB service for the Slack Health Check Bot.
Handles database operations for storing and retrieving bot data.
"""

import pymongo
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv('.env')

class MongoDBService:
    """Service class for MongoDB operations."""
    
    def __init__(self, uri=None, db_name=None, collection_name=None):
        """
        Initialize MongoDB connection.
        
        Args:
            uri (str): MongoDB connection URI
            db_name (str): Database name
            collection_name (str): Collection name
        """
        # Use MongoDB Atlas URI from environment variable, or default to localhost
        self.uri = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
        self.db_name = db_name or os.environ.get("MONGODB_DB_NAME", "healthcheck_bot")
        self.collection_name = collection_name or "responses"
        self.client = None
        self.db = None
        self.collection = None
        self.connect()

    def connect(self):
        try:
            print(f"🔌 Attempting to connect to MongoDB: {self.db_name}")
            
            # Use the simplest possible connection for MongoDB Atlas
            # MongoDB Atlas handles SSL automatically with mongodb+srv://
            self.client = pymongo.MongoClient(
                self.uri,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=15000,
                socketTimeoutMS=20000,
                maxPoolSize=10,
                retryWrites=True,
                w='majority'
            )
            
            # Test the connection
            self.client.admin.command('ping')
            
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            print("✅ Successfully connected to MongoDB")
            
        except Exception as e:
            print(f"❌ MongoDB connection error: {e}")
            
            # Try with even simpler settings
            try:
                print("🔄 Trying with minimal settings...")
                self.client = pymongo.MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=25000
                )
                
                self.client.admin.command('ping')
                self.db = self.client[self.db_name]
                self.collection = self.db[self.collection_name]
                print("✅ Successfully connected to MongoDB with minimal settings")
                
            except Exception as e2:
                print(f"❌ Minimal settings also failed: {e2}")
                
                # Try with a modified URI (remove any problematic parameters)
                try:
                    print("🔄 Trying with cleaned URI...")
                    # Remove any query parameters that might cause issues
                    clean_uri = self.uri.split('?')[0]
                    if clean_uri.endswith('/'):
                        clean_uri = clean_uri[:-1]
                    
                    self.client = pymongo.MongoClient(clean_uri)
                    self.client.admin.command('ping')
                    self.db = self.client[self.db_name]
                    self.collection = self.db[self.collection_name]
                    print("✅ Successfully connected to MongoDB with cleaned URI")
                    
                except Exception as e3:
                    print(f"❌ All connection attempts failed: {e3}")
                    # Create a fallback in-memory storage or continue without MongoDB
                    self.client = None
                    self.db = None
                    self.collection = None
                    print("⚠️ Running without MongoDB - data will not be persisted")

    def store_response(self, user_id, username, response_type, channel_id, message_ts, thread_ts=None, text=None, timestamp=None, date=None):
        """Store a response in the specified collection."""
        if self.collection is None:
            print("❌ Error storing response: MongoDB not connected")
            return None
        
        doc = {
            "user_id": user_id,
            "username": username,
            "response_type": response_type,
            "channel_id": channel_id,
            "message_ts": message_ts,
            "thread_ts": thread_ts,
            "text": text,
            "timestamp": timestamp or datetime.now(),
            "date": date or datetime.now().strftime("%Y-%m-%d")
        }
        try:
            result = self.collection.insert_one(doc)
            print(f"✅ Response stored with ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Error storing response: {e}")
            return None

    def store_followup_sent(self, user_id, thread_ts, followup_ts):
        """Store that a follow-up message was sent to a user in a specific thread"""
        if self.db is None:
            print("❌ Error storing follow-up tracking: MongoDB not connected")
            return None
        
        doc = {
            "user_id": user_id,
            "thread_ts": thread_ts,
            "followup_ts": followup_ts,
            "timestamp": datetime.now(),
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        try:
            # Use a separate collection for follow-ups
            followup_collection = self.db["followups"]
            result = followup_collection.insert_one(doc)
            print(f"✅ Follow-up tracking stored with ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Error storing follow-up tracking: {e}")
            return None

    def check_followup_sent(self, user_id, thread_ts):
        """Check if a follow-up message was already sent to a user in a specific thread"""
        if self.db is None:
            print("❌ Error checking follow-up status: MongoDB not connected")
            return False
        
        try:
            followup_collection = self.db["followups"]
            existing = followup_collection.find_one({
                "user_id": user_id,
                "thread_ts": thread_ts
            })
            return existing is not None
        except Exception as e:
            print(f"❌ Error checking follow-up status: {e}")
            return False

    def check_message_processed(self, message_ts):
        """Check if a specific message has already been processed"""
        if self.db is None:
            print("❌ Error checking message processing status: MongoDB not connected")
            return False
        
        try:
            processed_collection = self.db["processed_messages"]
            existing = processed_collection.find_one({
                "message_ts": message_ts
            })
            return existing is not None
        except Exception as e:
            print(f"❌ Error checking message processing status: {e}")
            return False

    def mark_message_processed(self, message_ts, user_id, thread_ts):
        """Mark a message as processed to prevent duplicate handling"""
        if self.db is None:
            print("❌ Error marking message as processed: MongoDB not connected")
            return None
        
        try:
            processed_collection = self.db["processed_messages"]
            doc = {
                "message_ts": message_ts,
                "user_id": user_id,
                "thread_ts": thread_ts,
                "timestamp": datetime.now(),
                "date": datetime.now().strftime("%Y-%m-%d")
            }
            result = processed_collection.insert_one(doc)
            print(f"✅ Message marked as processed: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Error marking message as processed: {e}")
            return None

    def insert_document(self, collection_name, document):
        """Insert a document into the specified collection."""
        if not self.db:
            print("⚠️ No database connection available")
            return None
        
        try:
            collection = self.db[collection_name]
            result = collection.insert_one(document)
            return result.inserted_id
        except Exception as e:
            print(f"❌ Error inserting document: {e}")
            return None
    
    def find_documents(self, collection_name, query=None):
        """Find documents in the specified collection."""
        if not self.db:
            print("⚠️ No database connection available")
            return []
        
        try:
            collection = self.db[collection_name]
            query = query or {}
            return list(collection.find(query))
        except Exception as e:
            print(f"❌ Error finding documents: {e}")
            return []
    
    def update_document(self, collection_name, query, update_data):
        """Update a document in the specified collection."""
        if not self.db:
            print("⚠️ No database connection available")
            return False
        
        try:
            collection = self.db[collection_name]
            result = collection.update_one(query, {'$set': update_data})
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error updating document: {e}")
            return False
    
    def delete_document(self, collection_name, query):
        """Delete a document from the specified collection."""
        if not self.db:
            print("⚠️ No database connection available")
            return False
        
        try:
            collection = self.db[collection_name]
            result = collection.delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ Error deleting document: {e}")
            return False
    
    def close(self):
        """Close the MongoDB connection."""
        if self.client:
            self.client.close()
            print("🔌 MongoDB connection closed") 