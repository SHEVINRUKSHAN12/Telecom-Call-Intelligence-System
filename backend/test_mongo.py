import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def test_mongo():
    mongo_uri = os.getenv("MONGODB_URI")
    mongo_db_name = os.getenv("MONGODB_DB")
    
    print("-" * 50)
    print("MongoDB Connection Test")
    print("-" * 50)
    
    if not mongo_uri:
        print("ERROR: MONGODB_URI not found in environment variables.")
        return

    # Mask password for display
    masked_uri = mongo_uri
    if "@" in mongo_uri:
        part1 = mongo_uri.split("@")[0]
        part2 = mongo_uri.split("@")[1]
        masked_uri = f"{part1.split(':')[0]}:****@{part2}"
    
    print(f"URI: {masked_uri}")
    print(f"DB:  {mongo_db_name}")
    print("-" * 50)

    try:
        print("Connecting...")
        client = AsyncIOMotorClient(mongo_uri)
        
        # 'ping' is a lightweight command to check connectivity
        await client.admin.command('ping')
        print("✅ SUCCESS: Connected to MongoDB Atlas!")
        
        if mongo_db_name:
            db = client[mongo_db_name]
            # List collections to verify database access
            collections = await db.list_collection_names()
            print(f"✅ SUCCESS: Access to database '{mongo_db_name}' verified.")
            print(f"   Collections found: {collections}")
            
    except Exception as e:
        print("❌ ERROR: Connection failed.")
        print(f"Details: {str(e)}")
        print("\nTroubleshooting tips:")
        print("1. Check if your IP is whitelisted in MongoDB Atlas (Network Access -> Allow All properly set?)")
        print("2. Check if username/password are correct.")
        print("3. Ensure 'pymongo[srv]' is installed.")

if __name__ == "__main__":
    asyncio.run(test_mongo())
