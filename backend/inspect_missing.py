import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
from services.mongodb import get_collection

async def inspect():
    col = get_collection()
    calls = await col.find({"sentiment": None}).to_list(length=None)
    for c in calls:
        print(f"Call ID: {c['_id']}, Transcript Length: {len(c.get('full_transcript', '') or '')}, Duration: {c.get('duration_seconds')}")

if __name__ == "__main__":
    asyncio.run(inspect())
