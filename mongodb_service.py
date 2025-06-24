import pymongo
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv('.env')

class MongoDBService:
    def __init__(self, uri=None, db_name=None, collection_name=None):
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
            # Configure MongoDB client with basic settings
            client_options = {
                'serverSelectionTimeoutMS': 5000,
                'connectTimeoutMS': 10000,
                'socketTimeoutMS': 20000,
                'maxPoolSize': 10,
                'retryWrites': True,
                'w': 'majority'
            }
            
            # Only add SSL for MongoDB Atlas with proper configuration
            if 'mongodb+srv://' in self.uri:
                # For MongoDB Atlas, use the default SSL settings
                pass
            elif 'mongodb://' in self.uri and 'ssl=true' in self.uri:
                # For local MongoDB with SSL, use basic settings
                pass
            
            self.client = pymongo.MongoClient(self.uri, **client_options)
            
            # Test the connection
            self.client.admin.command('ping')
            
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            print("✅ Successfully connected to MongoDB")
        except Exception as e:
            print(f"❌ MongoDB connection error: {e}")
            # Create a fallback in-memory storage or continue without MongoDB
            self.client = None
            self.db = None
            self.collection = None

    def store_response(self, user_id, username, response_type, channel_id, message_ts, thread_ts=None, text=None, timestamp=None, date=None):
        # Check if MongoDB is connected
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
        # Check if MongoDB is connected
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
        # Check if MongoDB is connected
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
        # Check if MongoDB is connected
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
        # Check if MongoDB is connected
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