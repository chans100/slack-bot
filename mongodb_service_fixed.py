"""
MongoDB service for the Slack Health Check Bot with improved SSL handling.
Handles database operations for storing and retrieving bot data.
"""

import pymongo
from datetime import datetime
import os
from dotenv import load_dotenv
import ssl
import certifi

# Load environment variables from .env
load_dotenv('.env')

class MongoDBService:
    """Service class for MongoDB operations with improved SSL handling."""
    
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
        """Connect to MongoDB with improved SSL handling."""
        try:
            print(f"🔌 Attempting to connect to MongoDB: {self.db_name}")
            
            # Create SSL context with proper certificate handling
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Try multiple connection approaches
            connection_attempts = [
                # Attempt 1: With SSL context and modern settings
                lambda: pymongo.MongoClient(
                    self.uri,
                    ssl=True,
                    ssl_cert_reqs=ssl.CERT_NONE,
                    ssl_ca_certs=certifi.where(),
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=25000,
                    maxPoolSize=10,
                    retryWrites=True,
                    w='majority'
                ),
                
                # Attempt 2: With minimal SSL settings
                lambda: pymongo.MongoClient(
                    self.uri,
                    ssl=True,
                    ssl_cert_reqs=ssl.CERT_NONE,
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=25000,
                    socketTimeoutMS=30000
                ),
                
                # Attempt 3: Without SSL (for local development)
                lambda: pymongo.MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=15000,
                    socketTimeoutMS=20000
                ),
                
                # Attempt 4: With tlsAllowInvalidCertificates
                lambda: pymongo.MongoClient(
                    self.uri,
                    tlsAllowInvalidCertificates=True,
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=25000
                )
            ]
            
            for i, attempt in enumerate(connection_attempts, 1):
                try:
                    print(f"🔄 Attempt {i}: Trying connection method...")
                    self.client = attempt()
                    
                    # Test the connection
                    self.client.admin.command('ping')
                    
                    self.db = self.client[self.db_name]
                    self.collection = self.db[self.collection_name]
                    print(f"✅ Successfully connected to MongoDB using method {i}")
                    return
                    
                except Exception as e:
                    print(f"❌ Attempt {i} failed: {str(e)[:100]}...")
                    if self.client:
                        self.client.close()
                    continue
            
            # If all attempts failed
            print("❌ All connection attempts failed")
            self.client = None
            self.db = None
            self.collection = None
            print("⚠️ Running without MongoDB - data will not be persisted")
            
        except Exception as e:
            print(f"❌ Unexpected error during connection: {e}")
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

    def get_responses_by_date(self, date):
        """Get all responses for a specific date"""
        if self.collection is None:
            print("❌ Error getting responses: MongoDB not connected")
            return []
        
        try:
            cursor = self.collection.find({"date": date})
            return list(cursor)
        except Exception as e:
            print(f"❌ Error getting responses by date: {e}")
            return []

    def get_user_responses(self, user_id, limit=10):
        """Get recent responses for a specific user"""
        if self.collection is None:
            print("❌ Error getting user responses: MongoDB not connected")
            return []
        
        try:
            cursor = self.collection.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"❌ Error getting user responses: {e}")
            return []

    def insert_document(self, collection_name, document):
        """Insert a document into a specified collection"""
        if self.db is None:
            print("❌ Error inserting document: MongoDB not connected")
            return None
        
        try:
            collection = self.db[collection_name]
            result = collection.insert_one(document)
            print(f"✅ Document inserted with ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Error inserting document: {e}")
            return None

    def find_documents(self, collection_name, query=None):
        """Find documents in a specified collection"""
        if self.db is None:
            print("❌ Error finding documents: MongoDB not connected")
            return []
        
        try:
            collection = self.db[collection_name]
            if query is None:
                query = {}
            cursor = collection.find(query)
            return list(cursor)
        except Exception as e:
            print(f"❌ Error finding documents: {e}")
            return []

    def update_document(self, collection_name, query, update_data):
        """Update a document in a specified collection"""
        if self.db is None:
            print("❌ Error updating document: MongoDB not connected")
            return None
        
        try:
            collection = self.db[collection_name]
            result = collection.update_one(query, {"$set": update_data})
            print(f"✅ Document updated: {result.modified_count} modified")
            return result.modified_count
        except Exception as e:
            print(f"❌ Error updating document: {e}")
            return None

    def delete_document(self, collection_name, query):
        """Delete a document from a specified collection"""
        if self.db is None:
            print("❌ Error deleting document: MongoDB not connected")
            return None
        
        try:
            collection = self.db[collection_name]
            result = collection.delete_one(query)
            print(f"✅ Document deleted: {result.deleted_count} deleted")
            return result.deleted_count
        except Exception as e:
            print(f"❌ Error deleting document: {e}")
            return None

    def close(self):
        """Close the MongoDB connection"""
        if self.client:
            self.client.close()
            print("🔌 MongoDB connection closed") 