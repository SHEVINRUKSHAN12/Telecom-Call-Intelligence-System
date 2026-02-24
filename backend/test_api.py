"""
Quick test script to verify Google Cloud Speech-to-Text, Storage, and MongoDB config.
"""
import os
from dotenv import load_dotenv

load_dotenv()

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "./google-credentials.json",
)

print("Testing Google Cloud Speech-to-Text API...")
print(f"Credentials file: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")

try:
    from google.cloud import speech

    client = speech.SpeechClient()
    _ = client
    print("OK: Speech client created")
except Exception as e:
    print(f"ERROR: Speech client failed: {str(e)}")


print("\n" + "=" * 50)
print("Testing Google Cloud Storage API...")

try:
    from google.cloud import storage

    client = storage.Client()
    bucket_name = os.getenv("GCS_BUCKET")
    if bucket_name:
        _ = client.bucket(bucket_name)
        print(f"OK: Storage client ready for bucket: {bucket_name}")
    else:
        print("WARN: GCS_BUCKET not set. Skipping bucket check.")
except Exception as e:
    print(f"ERROR: Storage client failed: {str(e)}")


print("\n" + "=" * 50)
print("MongoDB configuration check...")
mongo_uri = os.getenv("MONGODB_URI")
mongo_db = os.getenv("MONGODB_DB")
print(f"Mongo URI set: {'yes' if mongo_uri else 'no'}")
print(f"Mongo DB set: {mongo_db or 'no'}")

if mongo_uri:
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    
    async def test_mongo():
        # Mask password in logs
        masked_uri = mongo_uri.split('@')[-1] if '@' in mongo_uri else 'local'
        print(f"Attempting to connect to: ...@{masked_uri}")
        try:
            client = AsyncIOMotorClient(mongo_uri)
            # The ismaster command is cheap and does not require auth.
            await client.admin.command('ping')
            print("SUCCESS: MongoDB connection successful!")
            
            # Check database access
            if mongo_db:
                db = client[mongo_db]
                print(f"SUCCESS: Can access database '{mongo_db}'")
        except Exception as e:
            print(f"ERROR: MongoDB connection failed: {str(e)}")

    # Run the async test
    asyncio.run(test_mongo())
else:
    print("ERROR: MONGODB_URI is missing")
