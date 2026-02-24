import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from services.mongodb import get_collection

async def test_mongo():
    col = get_collection()
    calls = await col.find({}).sort("created_at", -1).limit(5).to_list(length=5)
    print(f"Found {len(calls)} calls")
    for c in calls:
        s = c.get("sentiment")
        print(f"Call ID: {c['_id']}, Sentiment: {s}")

if __name__ == "__main__":
    asyncio.run(test_mongo())
