"""
Re-run intent classification on stored calls with transcripts.
If sentiment is available locally, also backfill missing sentiment.
"""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
ENV_PATH = BACKEND_DIR / ".env"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

load_dotenv(ENV_PATH, override=True)
os.environ["ENABLE_SENTIMENT"] = "true"

from backend.services.classification import predict_intent
from backend.services.mongodb import get_db_path, init_db
from backend.services.sentiment import analyze_sentiment

SELECT_CALLS_SQL = """
SELECT
    id,
    created_at,
    duration_seconds,
    full_transcript,
    category_label,
    sentiment_label,
    sentiment_score,
    sentiment_model
FROM calls
ORDER BY created_at DESC
"""

UPDATE_CATEGORY_SQL = """
UPDATE calls
SET category_label = ?,
    category_confidence = ?,
    category_model = ?,
    category_scores_json = ?
WHERE id = ?
"""

UPDATE_CATEGORY_AND_SENTIMENT_SQL = """
UPDATE calls
SET category_label = ?,
    category_confidence = ?,
    category_model = ?,
    category_scores_json = ?,
    sentiment_label = ?,
    sentiment_score = ?,
    sentiment_model = ?
WHERE id = ?
"""


def fetch_calls(db_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(SELECT_CALLS_SQL)
        return cursor.fetchall()
    finally:
        connection.close()


def sentiment_missing(call: sqlite3.Row) -> bool:
    return (
        not str(call["sentiment_label"] or "").strip()
        and call["sentiment_score"] is None
        and not str(call["sentiment_model"] or "").strip()
    )


def update_call(
    db_path: Path,
    call_id: str,
    intent: dict,
    sentiment: dict | None = None,
) -> None:
    category_scores = json.dumps(intent.get("scores") or {}, ensure_ascii=False)
    connection = sqlite3.connect(str(db_path))
    try:
        if sentiment:
            connection.execute(
                UPDATE_CATEGORY_AND_SENTIMENT_SQL,
                (
                    intent.get("label") or "Other",
                    float(intent.get("confidence") or 0.0),
                    intent.get("model"),
                    category_scores,
                    sentiment.get("label"),
                    sentiment.get("score"),
                    sentiment.get("model"),
                    call_id,
                ),
            )
        else:
            connection.execute(
                UPDATE_CATEGORY_SQL,
                (
                    intent.get("label") or "Other",
                    float(intent.get("confidence") or 0.0),
                    intent.get("model"),
                    category_scores,
                    call_id,
                ),
            )
        connection.commit()
    finally:
        connection.close()


async def reclassify() -> None:
    await init_db()
    db_path = get_db_path()
    print(f"SQLite DB: {db_path}")

    if not db_path.exists():
        print("No SQLite DB file found.")
        return

    calls = fetch_calls(db_path)
    eligible_calls = sum(1 for call in calls if str(call["full_transcript"] or "").strip())

    print(f"Found {len(calls)} stored calls.")
    print(f"Eligible for reclassification: {eligible_calls}")

    if not calls:
        return
    if eligible_calls == 0:
        return

    print("Checking whether intent classification is available...")
    intent_probe = await asyncio.to_thread(
        predict_intent,
        "Test billing issue about invoice and payment",
    )
    if not str(intent_probe.get("model") or "").strip() or intent_probe.get("model") == "unavailable":
        print("Intent classification is unavailable in this environment. No category updates were applied.")
        return
    print(f"Intent model ready: {intent_probe.get('model')}")

    print("Checking whether sentiment backfill is available...")
    sentiment_probe = await asyncio.to_thread(
        analyze_sentiment,
        "Test message to load pipeline",
    )
    sentiment_enabled = sentiment_probe is not None
    if sentiment_enabled:
        print("Sentiment model ready. Missing sentiment may also be backfilled.")
    else:
        print("Sentiment unavailable in this environment. Reclassification will continue without sentiment backfill.")

    updated_count = 0
    skipped_count = 0
    failed_count = 0
    sentiment_count = 0

    for index, call in enumerate(calls, start=1):
        call_id = call["id"]
        created_at = call["created_at"] or "?"
        duration = call["duration_seconds"]
        duration_text = f"{duration:.3f}s" if duration is not None else "?"
        transcript = str(call["full_transcript"] or "").strip()

        print(
            f"[{index}/{len(calls)}] Processing {call_id} "
            f"(created={created_at}, duration={duration_text}, transcript={len(transcript)} chars)"
        )

        if not transcript:
            print(f"Skipped {call_id}: transcript is empty.")
            skipped_count += 1
            continue

        try:
            intent = await asyncio.to_thread(predict_intent, transcript)
            if not str(intent.get("model") or "").strip() or intent.get("model") == "unavailable":
                print(f"Failed {call_id}: intent classification returned no usable model.")
                failed_count += 1
                continue

            sentiment_result = None
            if sentiment_enabled and sentiment_missing(call):
                sentiment_result = await asyncio.to_thread(analyze_sentiment, transcript)
                if sentiment_result:
                    sentiment_count += 1

            update_call(db_path, call_id, intent, sentiment_result)
            updated_count += 1

            label = intent.get("label") or "Other"
            confidence = float(intent.get("confidence") or 0.0)
            if sentiment_result:
                print(
                    f"Updated {call_id}: {label} ({confidence:.1%}), "
                    f"sentiment={sentiment_result.get('label')} "
                    f"({float(sentiment_result.get('score', 0.0)):.2f})"
                )
            else:
                print(f"Updated {call_id}: {label} ({confidence:.1%})")
        except Exception as exc:
            print(f"Failed {call_id}: {exc}")
            failed_count += 1

    print(
        f"Done. Updated: {updated_count}, "
        f"Skipped: {skipped_count}, Failed: {failed_count}, Sentiment added: {sentiment_count}"
    )


if __name__ == "__main__":
    asyncio.run(reclassify())
