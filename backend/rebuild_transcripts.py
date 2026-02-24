"""
Rebuild full_transcript from speaker_segments for calls that have segments but no transcript.
Also re-runs sentiment analysis on the rebuilt transcripts.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ["ENABLE_SENTIMENT"] = "true"

from services.mongodb import get_collection
from services.sentiment import analyze_sentiment


async def rebuild():
    col = get_collection()

    # Find calls that have speaker_segments with text but empty/null full_transcript
    all_calls = await col.find({}).to_list(length=None)

    rebuilt_count = 0
    sentiment_count = 0

    for call in all_calls:
        call_id = call["_id"]
        transcript = (call.get("full_transcript") or "").strip()
        segments = call.get("speaker_segments") or []

        # Get combined text from segments
        segment_text = " ".join(
            (seg.get("text") or "").strip()
            for seg in segments
            if (seg.get("text") or "").strip()
        ).strip()

        # If full_transcript is empty but segments have text, rebuild it
        if not transcript and segment_text:
            update = {"$set": {"full_transcript": segment_text}}

            # Also run sentiment on the rebuilt text
            try:
                sentiment_result = analyze_sentiment(segment_text)
                if sentiment_result:
                    update["$set"]["sentiment"] = sentiment_result
                    sentiment_count += 1
            except Exception as e:
                print(f"  Sentiment error for {call_id}: {e}")

            await col.update_one({"_id": call_id}, update)
            rebuilt_count += 1
            print(f"Rebuilt: {call_id} ({len(segment_text)} chars)")

        # Also fix calls that have transcript but no sentiment
        elif transcript and call.get("sentiment") is None:
            try:
                sentiment_result = analyze_sentiment(transcript)
                if sentiment_result:
                    await col.update_one(
                        {"_id": call_id},
                        {"$set": {"sentiment": sentiment_result}},
                    )
                    sentiment_count += 1
                    print(f"Sentiment added: {call_id}")
            except Exception as e:
                print(f"  Sentiment error for {call_id}: {e}")

    print(f"\nDone! Rebuilt {rebuilt_count} transcripts, added {sentiment_count} sentiments.")


if __name__ == "__main__":
    asyncio.run(rebuild())
