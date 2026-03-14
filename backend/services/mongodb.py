from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = "./data/calls.db"

CREATE_CALLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    file_filename TEXT NOT NULL,
    file_content_type TEXT,
    file_size_bytes INTEGER NOT NULL,
    file_gcs_uri TEXT NOT NULL,
    file_blob_name TEXT,
    detected_language TEXT,
    duration_seconds REAL,
    full_transcript TEXT NOT NULL,
    search_text TEXT NOT NULL,
    category_label TEXT NOT NULL,
    category_confidence REAL NOT NULL DEFAULT 0,
    category_model TEXT,
    category_scores_json TEXT NOT NULL DEFAULT '{}',
    sentiment_label TEXT,
    sentiment_score REAL,
    sentiment_model TEXT,
    speaker_segments_json TEXT NOT NULL DEFAULT '[]',
    transcription_meta_json TEXT
);
"""

CREATE_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls (created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_calls_category_created_at ON calls (category_label, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_calls_detected_language ON calls (detected_language);",
)


def get_db_path() -> Path:
    raw_path = (os.getenv("SQLITE_PATH") or DEFAULT_SQLITE_PATH).strip()
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = (BACKEND_DIR / db_path).resolve()
    return db_path


def _ensure_parent_directory() -> Path:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@asynccontextmanager
async def _connect():
    db_path = _ensure_parent_directory()
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        await connection.close()


def _clone_default(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value


def _json_dumps(value: Any, default: Any) -> str:
    if value is None:
        value = _clone_default(default)
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return _clone_default(default)
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return _clone_default(default)


def _normalize_iso_utc(value: Any) -> str | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return value.strip()
    else:
        return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat().replace("+00:00", "Z")


def _coerce_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def _coerce_scores(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _build_search_text(full_transcript: str, speaker_segments: list[dict[str, Any]]) -> str:
    segment_text = " ".join(
        str(segment.get("text") or "").strip()
        for segment in speaker_segments
        if str(segment.get("text") or "").strip()
    )
    return " ".join(part for part in (full_transcript.strip(), segment_text) if part).strip()


def _flatten_call_record(record: dict[str, Any]) -> dict[str, Any]:
    file_info = dict(record.get("file") or {})
    category = dict(record.get("category") or {})
    sentiment = dict(record.get("sentiment") or {})
    speaker_segments = _coerce_segments(record.get("speaker_segments"))
    transcription_meta = record.get("transcription_meta")

    full_transcript = str(record.get("full_transcript") or "")
    call_id = str(record.get("id") or record.get("_id") or uuid.uuid4().hex)
    created_at = _normalize_iso_utc(record.get("created_at")) or _normalize_iso_utc(datetime.now(timezone.utc))

    return {
        "id": call_id,
        "created_at": created_at,
        "file_filename": str(file_info.get("filename") or ""),
        "file_content_type": file_info.get("content_type"),
        "file_size_bytes": int(file_info.get("size_bytes") or 0),
        "file_gcs_uri": str(file_info.get("gcs_uri") or ""),
        "file_blob_name": file_info.get("blob_name"),
        "detected_language": record.get("detected_language"),
        "duration_seconds": record.get("duration_seconds"),
        "full_transcript": full_transcript,
        "search_text": _build_search_text(full_transcript, speaker_segments),
        "category_label": str(category.get("label") or "Other"),
        "category_confidence": float(category.get("confidence") or 0.0),
        "category_model": category.get("model"),
        "category_scores_json": _json_dumps(_coerce_scores(category.get("scores")), {}),
        "sentiment_label": sentiment.get("label"),
        "sentiment_score": sentiment.get("score"),
        "sentiment_model": sentiment.get("model"),
        "speaker_segments_json": _json_dumps(speaker_segments, []),
        "transcription_meta_json": (
            None if transcription_meta is None else _json_dumps(dict(transcription_meta), {})
        ),
    }


def _row_to_call_record(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)

    category_scores = _json_loads(payload.get("category_scores_json"), {})
    if not isinstance(category_scores, dict):
        category_scores = {}

    speaker_segments = _json_loads(payload.get("speaker_segments_json"), [])
    if not isinstance(speaker_segments, list):
        speaker_segments = []

    transcription_meta = _json_loads(payload.get("transcription_meta_json"), None)
    if transcription_meta is not None and not isinstance(transcription_meta, dict):
        transcription_meta = None

    sentiment = None
    if any(
        payload.get(key) is not None
        for key in ("sentiment_label", "sentiment_score", "sentiment_model")
    ):
        sentiment = {
            "label": payload.get("sentiment_label"),
            "score": payload.get("sentiment_score"),
            "model": payload.get("sentiment_model"),
        }

    return {
        "id": payload["id"],
        "created_at": payload["created_at"],
        "file": {
            "filename": payload["file_filename"],
            "content_type": payload.get("file_content_type"),
            "size_bytes": payload["file_size_bytes"],
            "gcs_uri": payload["file_gcs_uri"],
            "blob_name": payload.get("file_blob_name"),
        },
        "detected_language": payload.get("detected_language"),
        "duration_seconds": payload.get("duration_seconds"),
        "full_transcript": payload.get("full_transcript") or "",
        "speaker_segments": speaker_segments,
        "category": {
            "label": payload.get("category_label") or "Other",
            "confidence": payload.get("category_confidence") or 0.0,
            "scores": category_scores,
            "model": payload.get("category_model"),
        },
        "sentiment": sentiment,
        "transcription_meta": transcription_meta,
    }


def _build_where_clause(
    *,
    category: str | None = None,
    q: str | None = None,
    start: Any = None,
    end: Any = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if category and str(category).lower() != "all":
        clauses.append("category_label = ?")
        params.append(category)

    if q and str(q).strip():
        clauses.append("search_text LIKE '%' || ? || '%'")
        params.append(str(q).strip())

    start_value = _normalize_iso_utc(start)
    if start_value:
        clauses.append("created_at >= ?")
        params.append(start_value)

    end_value = _normalize_iso_utc(end)
    if end_value:
        clauses.append("created_at <= ?")
        params.append(end_value)

    if not clauses:
        return "", params

    return f"WHERE {' AND '.join(clauses)}", params


async def init_db() -> None:
    async with _connect() as db:
        await db.execute(CREATE_CALLS_TABLE_SQL)
        for statement in CREATE_INDEX_STATEMENTS:
            await db.execute(statement)
        await db.commit()


async def save_call(record: dict) -> str:
    payload = _flatten_call_record(record)

    await init_db()

    async with _connect() as db:
        await db.execute(
            """
            INSERT INTO calls (
                id,
                created_at,
                file_filename,
                file_content_type,
                file_size_bytes,
                file_gcs_uri,
                file_blob_name,
                detected_language,
                duration_seconds,
                full_transcript,
                search_text,
                category_label,
                category_confidence,
                category_model,
                category_scores_json,
                sentiment_label,
                sentiment_score,
                sentiment_model,
                speaker_segments_json,
                transcription_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["created_at"],
                payload["file_filename"],
                payload["file_content_type"],
                payload["file_size_bytes"],
                payload["file_gcs_uri"],
                payload["file_blob_name"],
                payload["detected_language"],
                payload["duration_seconds"],
                payload["full_transcript"],
                payload["search_text"],
                payload["category_label"],
                payload["category_confidence"],
                payload["category_model"],
                payload["category_scores_json"],
                payload["sentiment_label"],
                payload["sentiment_score"],
                payload["sentiment_model"],
                payload["speaker_segments_json"],
                payload["transcription_meta_json"],
            ),
        )
        await db.commit()

    return payload["id"]


async def get_call_by_id(call_id: str) -> dict[str, Any] | None:
    async with _connect() as db:
        cursor = await db.execute("SELECT * FROM calls WHERE id = ?", (call_id,))
        row = await cursor.fetchone()
        await cursor.close()

    if row is None:
        return None

    return _row_to_call_record(row)


async def get_call_audio_uri(call_id: str) -> str | None:
    async with _connect() as db:
        cursor = await db.execute("SELECT file_gcs_uri FROM calls WHERE id = ?", (call_id,))
        row = await cursor.fetchone()
        await cursor.close()

    if row is None:
        return None

    return row["file_gcs_uri"]


async def list_calls(
    category: str | None = None,
    q: str | None = None,
    start: Any = None,
    end: Any = None,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    where_clause, params = _build_where_clause(category=category, q=q, start=start, end=end)
    safe_limit = max(1, int(limit or 20))

    async with _connect() as db:
        count_cursor = await db.execute(
            f"SELECT COUNT(*) AS total FROM calls {where_clause}",
            params,
        )
        total_row = await count_cursor.fetchone()
        await count_cursor.close()

        list_cursor = await db.execute(
            f"SELECT * FROM calls {where_clause} ORDER BY created_at DESC LIMIT ?",
            (*params, safe_limit),
        )
        rows = await list_cursor.fetchall()
        await list_cursor.close()

    total = int(total_row["total"]) if total_row is not None else 0
    return ([_row_to_call_record(row) for row in rows], total)


async def get_analytics(start: Any = None, end: Any = None) -> dict[str, Any]:
    where_clause, params = _build_where_clause(start=start, end=end)

    async with _connect() as db:
        total_cursor = await db.execute(
            f"SELECT COUNT(*) AS total_calls FROM calls {where_clause}",
            params,
        )
        total_row = await total_cursor.fetchone()
        await total_cursor.close()

        category_cursor = await db.execute(
            f"""
            SELECT category_label AS category, COUNT(*) AS count
            FROM calls
            {where_clause}
            GROUP BY category_label
            ORDER BY count DESC
            """,
            params,
        )
        category_rows = await category_cursor.fetchall()
        await category_cursor.close()

        daily_cursor = await db.execute(
            f"""
            SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count
            FROM calls
            {where_clause}
            GROUP BY substr(created_at, 1, 10)
            ORDER BY date ASC
            """,
            params,
        )
        daily_rows = await daily_cursor.fetchall()
        await daily_cursor.close()

    return {
        "total_calls": int(total_row["total_calls"]) if total_row is not None else 0,
        "category_counts": [
            {"category": row["category"], "count": int(row["count"])}
            for row in category_rows
        ],
        "daily_counts": [
            {"date": row["date"], "count": int(row["count"])}
            for row in daily_rows
        ],
    }
