import asyncio
import json
from dotenv import load_dotenv

load_dotenv()
from services.mongodb import get_collection

async def inspect():
    col = get_collection()
    call = await col.find_one({}, sort=[("created_at", -1)])  # Most recent call
    if call:
        call["_id"] = str(call["_id"])
        print("=== SENTIMENT ===")
        print(json.dumps(call.get("sentiment"), indent=2))
        print("=== CATEGORY ===")
        print(json.dumps(call.get("category"), indent=2))
        print("=== SPEAKER SEGMENTS (first 3) ===")
        segs = call.get("speaker_segments", [])[:3]
        print(json.dumps(segs, indent=2))
        print("=== TRANSCRIPT (first 200 chars) ===")
        print(call.get("full_transcript","")[:200])
    else:
        print("No calls found.")

if __name__ == "__main__":
    asyncio.run(inspect())
