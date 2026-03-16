import asyncio
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

from backend.services.mongodb import get_db_path, init_db

MISSING_SENTIMENT_SQL = """
SELECT
    id,
    created_at,
    duration_seconds,
    category_label,
    category_confidence,
    detected_language,
    file_filename,
    LENGTH(full_transcript) AS transcript_length,
    SUBSTR(full_transcript, 1, 160) AS transcript_preview
FROM calls
WHERE NULLIF(TRIM(sentiment_label), '') IS NULL
  AND sentiment_score IS NULL
  AND NULLIF(TRIM(sentiment_model), '') IS NULL
ORDER BY created_at DESC
"""


def fetch_calls_missing_sentiment(db_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(MISSING_SENTIMENT_SQL)
        return cursor.fetchall()
    finally:
        connection.close()


def format_preview(text: str | None, transcript_length: int | None) -> str:
    preview = " ".join((text or "").split())
    if not preview:
        return "<empty transcript>"
    if transcript_length and transcript_length > len(preview):
        return f"{preview}..."
    return preview


async def inspect() -> None:
    await init_db()
    db_path = get_db_path()
    print(f"SQLite DB: {db_path}")

    if not db_path.exists():
        print("No SQLite DB file found.")
        return

    calls = fetch_calls_missing_sentiment(db_path)
    print(f"Calls missing sentiment: {len(calls)}")

    if not calls:
        return

    print("-" * 100)
    for call in calls:
        transcript_length = call["transcript_length"] or 0
        duration = call["duration_seconds"]
        duration_text = f"{duration:.3f}s" if duration is not None else "?"
        confidence = call["category_confidence"] or 0.0
        preview = format_preview(call["transcript_preview"], transcript_length)

        print(f"ID: {call['id']}")
        print(f"Created: {call['created_at'] or '?'}")
        print(
            f"Transcript: {transcript_length} chars  Duration: {duration_text}  "
            f"Category: {call['category_label'] or '?'} ({confidence:.1%})"
        )
        print(
            f"Language: {call['detected_language'] or '?'}  "
            f"File: {call['file_filename'] or '?'}"
        )
        print(f"Preview: {preview}")
        print("-" * 100)


if __name__ == "__main__":
    asyncio.run(inspect())
