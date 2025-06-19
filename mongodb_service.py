import pymongo
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from token.env
load_dotenv('token.env')

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
            self.client = pymongo.MongoClient(self.uri)
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            print("✅ Successfully connected to MongoDB")
        except Exception as e:
            print(f"❌ MongoDB connection error: {e}")

    def store_response(self, user_id, username, response_type, channel_id, message_ts, thread_ts=None, text=None, timestamp=None, date=None):
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
        except Exception as e:
            print(f"❌ Error storing response: {e}") 