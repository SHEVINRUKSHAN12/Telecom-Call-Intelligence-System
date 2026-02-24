import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
from services.mongodb import get_collection

async def check_sentiment():
    col = get_collection()
    call = await col.find_one({"sentiment": {"$ne": None}})
    if call:
        print(call.get("sentiment"))
    else:
        print("No calls with sentiment found.")

if __name__ == "__main__":
    asyncio.run(check_sentiment())
