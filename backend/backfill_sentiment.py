import asyncio
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

from backend.services.mongodb import get_db_path, init_db
from backend.services.sentiment import analyze_sentiment

MISSING_SENTIMENT_SQL = """
SELECT
    id,
    created_at,
    duration_seconds,
    category_label,
    full_transcript
FROM calls
WHERE full_transcript IS NOT NULL
  AND NULLIF(TRIM(full_transcript), '') IS NOT NULL
  AND NULLIF(TRIM(sentiment_label), '') IS NULL
  AND sentiment_score IS NULL
  AND NULLIF(TRIM(sentiment_model), '') IS NULL
ORDER BY created_at DESC
"""

UPDATE_SENTIMENT_SQL = """
UPDATE calls
SET sentiment_label = ?, sentiment_score = ?, sentiment_model = ?
WHERE id = ?
"""


def fetch_calls_missing_sentiment(db_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(MISSING_SENTIMENT_SQL)
        return cursor.fetchall()
    finally:
        connection.close()


def update_call_sentiment(db_path: Path, call_id: str, sentiment: dict) -> None:
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            UPDATE_SENTIMENT_SQL,
            (
                sentiment.get("label"),
                sentiment.get("score"),
                sentiment.get("model"),
                call_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


async def backfill_sentiment() -> None:
    await init_db()
    db_path = get_db_path()
    print(f"SQLite DB: {db_path}")

    if not db_path.exists():
        print("No SQLite DB file found.")
        return

    calls = fetch_calls_missing_sentiment(db_path)
    print(f"Found {len(calls)} calls with missing sentiment.")

    if not calls:
        return

    print("Initializing sentiment model...")
    warmup = await asyncio.to_thread(analyze_sentiment, "Test message to load pipeline")
    if warmup is None:
        print("Failed to initialize sentiment analysis. Ensure sentiment dependencies are installed.")
        return

    updated_count = 0
    skipped_count = 0
    failed_count = 0

    for index, call in enumerate(calls, start=1):
        call_id = call["id"]
        created_at = call["created_at"] or "?"
        transcript = (call["full_transcript"] or "").strip()
        category = call["category_label"] or "?"
        duration = call["duration_seconds"]
        duration_text = f"{duration:.3f}s" if duration is not None else "?"

        print(
            f"[{index}/{len(calls)}] Processing {call_id} "
            f"(created={created_at}, category={category}, duration={duration_text}, "
            f"transcript={len(transcript)} chars)"
        )

        if not transcript:
            print(f"Skipped {call_id}: transcript is empty.")
            skipped_count += 1
            continue

        try:
            sentiment_result = await asyncio.to_thread(analyze_sentiment, transcript)
            if not sentiment_result:
                print(f"Skipped {call_id}: sentiment analysis returned no result.")
                skipped_count += 1
                continue

            update_call_sentiment(db_path, call_id, sentiment_result)
            print(
                f"Updated {call_id}: {sentiment_result.get('label')} "
                f"({float(sentiment_result.get('score', 0.0)):.2f})"
            )
            updated_count += 1
        except Exception as exc:
            print(f"Failed {call_id}: {exc}")
            failed_count += 1

    print(
        f"Backfill complete. Updated: {updated_count}, "
        f"Skipped: {skipped_count}, Failed: {failed_count}"
    )


if __name__ == "__main__":
    try:
        asyncio.run(backfill_sentiment())
    except KeyboardInterrupt:
        print("\nBackfill cancelled by user.")
        sys.exit(0)
