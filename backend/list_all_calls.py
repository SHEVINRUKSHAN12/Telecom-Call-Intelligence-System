import asyncio
import json
from dotenv import load_dotenv

load_dotenv()
from services.mongodb import get_collection

async def inspect():
    col = get_collection()
    # Get all calls, show id, transcript length, sentiment, created_at
    calls = await col.find({}, {"full_transcript": 1, "sentiment": 1, "category": 1, "created_at": 1}).sort("created_at", -1).to_list(length=None)
    print(f"Total calls: {len(calls)}")
    print("-" * 80)
    for c in calls:
        tid = str(c["_id"])
        transcript = c.get("full_transcript") or ""
        has_sent = c.get("sentiment") is not None
        cat_label = c.get("category", {}).get("label", "?") if c.get("category") else "?"
        cat_conf = c.get("category", {}).get("confidence", 0) if c.get("category") else 0
        created = str(c.get("created_at", "?"))[:19]
        print(f"ID: {tid[-8:]}  Created: {created}  Transcript: {len(transcript):>5} chars  Sentiment: {'Yes' if has_sent else 'No '}  Cat: {cat_label} ({cat_conf:.1%})")

if __name__ == "__main__":
    asyncio.run(inspect())
