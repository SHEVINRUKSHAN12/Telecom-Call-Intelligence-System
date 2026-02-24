"""
Re-run intent classification and sentiment on ALL calls that have transcripts.
This fixes old records that were classified with the wrong model path.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ["ENABLE_SENTIMENT"] = "true"

from services.mongodb import get_collection
from services.classification import predict_intent
from services.sentiment import analyze_sentiment


async def reclassify():
    col = get_collection()
    all_calls = await col.find({}).to_list(length=None)

    print(f"Total calls: {len(all_calls)}")
    updated = 0

    for call in all_calls:
        call_id = call["_id"]
        transcript = (call.get("full_transcript") or "").strip()

        if not transcript:
            continue

        update = {}

        # Re-run intent classification
        try:
            intent = predict_intent(transcript)
            update["category"] = intent
        except Exception as e:
            print(f"  Intent error for {call_id}: {e}")

        # Re-run sentiment if missing
        if call.get("sentiment") is None:
            try:
                sentiment = analyze_sentiment(transcript)
                if sentiment:
                    update["sentiment"] = sentiment
            except Exception as e:
                print(f"  Sentiment error for {call_id}: {e}")

        if update:
            await col.update_one({"_id": call_id}, {"$set": update})
            cat = update.get("category", {}).get("label", "?")
            conf = update.get("category", {}).get("confidence", 0)
            print(f"Updated {str(call_id)[-8:]}: {cat} ({conf:.1%})")
            updated += 1

    print(f"\nDone! Updated {updated} calls.")


if __name__ == "__main__":
    asyncio.run(reclassify())
