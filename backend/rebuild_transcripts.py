"""
Rebuild full_transcript from speaker_segments for stored calls that are missing it.
If sentiment is available locally, also backfill sentiment for rebuilt transcripts.
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

from backend.services.mongodb import get_db_path, init_db
from backend.services.sentiment import analyze_sentiment

CANDIDATE_CALLS_SQL = """
SELECT
    id,
    created_at,
    duration_seconds,
    category_label,
    speaker_segments_json,
    sentiment_label,
    sentiment_score,
    sentiment_model
FROM calls
WHERE full_transcript IS NULL
   OR NULLIF(TRIM(full_transcript), '') IS NULL
ORDER BY created_at DESC
"""

UPDATE_TRANSCRIPT_SQL = """
UPDATE calls
SET full_transcript = ?, search_text = ?
WHERE id = ?
"""

UPDATE_TRANSCRIPT_AND_SENTIMENT_SQL = """
UPDATE calls
SET full_transcript = ?,
    search_text = ?,
    sentiment_label = ?,
    sentiment_score = ?,
    sentiment_model = ?
WHERE id = ?
"""


def fetch_calls_missing_transcript(db_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(CANDIDATE_CALLS_SQL)
        return cursor.fetchall()
    finally:
        connection.close()


def load_segments(raw_segments: str | None) -> list[dict]:
    if not raw_segments:
        return []

    try:
        segments = json.loads(raw_segments)
    except json.JSONDecodeError:
        return []

    if not isinstance(segments, list):
        return []

    return [segment for segment in segments if isinstance(segment, dict)]


def build_transcript_from_segments(segments: list[dict]) -> str:
    return " ".join(
        str(segment.get("text") or "").strip()
        for segment in segments
        if str(segment.get("text") or "").strip()
    ).strip()


def sentiment_missing(call: sqlite3.Row) -> bool:
    return (
        not str(call["sentiment_label"] or "").strip()
        and call["sentiment_score"] is None
        and not str(call["sentiment_model"] or "").strip()
    )


def update_call(db_path: Path, call_id: str, transcript: str, sentiment: dict | None = None) -> None:
    connection = sqlite3.connect(str(db_path))
    try:
        if sentiment:
            connection.execute(
                UPDATE_TRANSCRIPT_AND_SENTIMENT_SQL,
                (
                    transcript,
                    transcript,
                    sentiment.get("label"),
                    sentiment.get("score"),
                    sentiment.get("model"),
                    call_id,
                ),
            )
        else:
            connection.execute(
                UPDATE_TRANSCRIPT_SQL,
                (
                    transcript,
                    transcript,
                    call_id,
                ),
            )
        connection.commit()
    finally:
        connection.close()


async def rebuild() -> None:
    await init_db()
    db_path = get_db_path()
    print(f"SQLite DB: {db_path}")

    if not db_path.exists():
        print("No SQLite DB file found.")
        return

    calls = fetch_calls_missing_transcript(db_path)
    print(f"Found {len(calls)} calls with missing or empty full_transcript.")

    if not calls:
        return

    print("Checking whether sentiment backfill is available...")
    sentiment_available = await asyncio.to_thread(
        analyze_sentiment,
        "Test message to load pipeline",
    )
    if sentiment_available is None:
        print("Sentiment unavailable in this environment. Rebuild will continue without sentiment backfill.")
    else:
        print("Sentiment model ready. Rebuilt transcripts may also get sentiment.")

    rebuilt_count = 0
    skipped_count = 0
    failed_count = 0
    sentiment_count = 0

    for index, call in enumerate(calls, start=1):
        call_id = call["id"]
        created_at = call["created_at"] or "?"
        category = call["category_label"] or "?"
        duration = call["duration_seconds"]
        duration_text = f"{duration:.3f}s" if duration is not None else "?"

        print(
            f"[{index}/{len(calls)}] Processing {call_id} "
            f"(created={created_at}, category={category}, duration={duration_text})"
        )

        try:
            segments = load_segments(call["speaker_segments_json"])
            transcript = build_transcript_from_segments(segments)

            if not transcript:
                print(f"Skipped {call_id}: speaker_segments has no usable text.")
                skipped_count += 1
                continue

            sentiment_result = None
            if sentiment_available is not None and sentiment_missing(call):
                sentiment_result = await asyncio.to_thread(analyze_sentiment, transcript)
                if sentiment_result:
                    sentiment_count += 1

            update_call(db_path, call_id, transcript, sentiment_result)
            rebuilt_count += 1

            if sentiment_result:
                print(
                    f"Rebuilt {call_id}: {len(transcript)} chars, "
                    f"sentiment={sentiment_result.get('label')} "
                    f"({float(sentiment_result.get('score', 0.0)):.2f})"
                )
            else:
                print(f"Rebuilt {call_id}: {len(transcript)} chars")
        except Exception as exc:
            print(f"Failed {call_id}: {exc}")
            failed_count += 1

    print(
        f"Done. Rebuilt: {rebuilt_count}, "
        f"Skipped: {skipped_count}, Failed: {failed_count}, Sentiment added: {sentiment_count}"
    )


if __name__ == "__main__":
    asyncio.run(rebuild())
