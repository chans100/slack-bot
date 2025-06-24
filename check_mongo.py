from mongodb_service import MongoDBService

mongo = MongoDBService()
responses = list(mongo.collection.find().sort('timestamp', -1).limit(10))

print(f"Total responses in database: {mongo.collection.count_documents({})}")
print("\nRecent responses:")
for r in responses:
    print(f"ID: {r['_id']}")
    print(f"User: {r.get('username', 'Unknown')}")
    print(f"Type: {r.get('response_type', 'Unknown')}")
    print(f"Date: {r.get('date', 'Unknown')}")
    print(f"Message: {r.get('text', 'No text')}")
    print("-" * 50) 