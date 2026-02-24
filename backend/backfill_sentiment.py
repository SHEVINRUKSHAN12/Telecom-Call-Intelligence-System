import asyncio
import os
import sys

from dotenv import load_dotenv

# Ensure environment is loaded and sentiment is enabled
load_dotenv()
os.environ["ENABLE_SENTIMENT"] = "true"

from services.mongodb import get_collection
from services.sentiment import analyze_sentiment


async def backfill_sentiment():
    print("Connecting to MongoDB...")
    collection = get_collection()

    # Find calls that have a transcript but no sentiment
    query = {"sentiment": None, "full_transcript": {"$ne": None, "$ne": ""}}
    calls = await collection.find(query).to_list(length=None)

    if not calls:
        print("No calls found that need sentiment backfilling.")
        return

    print(f"Found {len(calls)} calls to process. Initializing sentiment model...")
    print("(This step might take some time if the model is still downloading)")

    # Test loading the model first so we fail early if it hangs
    try:
        analyze_sentiment("Test message to load pipeline")
    except Exception as e:
        print(f"Failed to load sentiment model: {e}")
        return

    print("Model loaded. Processing calls...")

    updated_count = 0
    for call in calls:
        call_id = call["_id"]
        transcript = call.get("full_transcript", "")
        
        if not transcript.strip():
            continue

        try:
            sentiment_result = analyze_sentiment(transcript)
            if sentiment_result:
                await collection.update_one(
                    {"_id": call_id},
                    {"$set": {"sentiment": sentiment_result}}
                )
                print(f"Updated call {call_id} with sentiment: {sentiment_result['label']} ({sentiment_result['score']:.2f})")
                updated_count += 1
            else:
                print(f"Could not determine sentiment for call {call_id}.")
        except Exception as e:
            print(f"Error processing call {call_id}: {e}")

    print(f"\nBackfill complete! Successfully updated {updated_count} calls.")

if __name__ == "__main__":
    try:
        asyncio.run(backfill_sentiment())
    except KeyboardInterrupt:
        print("\nBackfill cancelled by user.")
        sys.exit(0)
