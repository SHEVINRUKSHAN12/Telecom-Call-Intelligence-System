from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional, List, Dict
from bson import ObjectId
import asyncio
import logging
import os

from models.schemas import CallAnalysisResponse, CallListResponse, AnalyticsResponse
from services.storage import upload_audio_to_gcs, generate_signed_audio_url
from services.speech_to_text import transcribe_with_hybrid_fallback
from services.classification import predict_intent
from services.sentiment import analyze_sentiment
from services.audio_utils import convert_to_wav, get_audio_duration_seconds
from services.mongodb import get_collection
from services.translation import detect_language

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_FORMATS = [".wav", ".mp3", ".flac", ".ogg", ".m4a"]


def _serialize_call(record: dict) -> dict:
    record = dict(record)
    record["id"] = str(record.pop("_id"))
    return record


def _parse_iso_date(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _normalize_caller_labels(segments: List[Dict]) -> List[Dict]:
    if not segments:
        return []

    unique_tags = sorted({int(seg.get("speaker_tag", 1) or 1) for seg in segments})
    tag_remap = {tag: idx + 1 for idx, tag in enumerate(unique_tags)}
    normalized: List[Dict] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        original_tag = int(seg.get("speaker_tag", 1) or 1)
        mapped_tag = int(tag_remap.get(original_tag, 1))
        normalized.append(
            {
                "speaker_tag": mapped_tag,
                "speaker_label": f"Caller {mapped_tag}",
                "text": text,
                "start_time": float(seg.get("start_time", 0.0) or 0.0),
                "end_time": float(seg.get("end_time", 0.0) or 0.0),
            }
        )
    return normalized


def _is_diarization_unstable(segments: List[Dict]) -> bool:
    active = [seg for seg in segments if (seg.get("text") or "").strip()]
    if len(active) < 5:
        return False

    tags = [int(seg.get("speaker_tag", 1) or 1) for seg in active]
    if len(set(tags)) < 2:
        return False

    flips = sum(1 for idx in range(1, len(tags)) if tags[idx] != tags[idx - 1])
    flip_ratio = flips / max(1, len(tags) - 1)

    tiny_count = 0
    for seg in active:
        duration = float(seg.get("end_time", 0.0) or 0.0) - float(seg.get("start_time", 0.0) or 0.0)
        if duration < 0.6:
            tiny_count += 1
    tiny_ratio = tiny_count / len(active)

    return flip_ratio > 0.70 and tiny_ratio > 0.35


def _collapse_to_single_speaker(
    segments: List[Dict],
    full_transcript: str,
    duration_seconds: float,
) -> List[Dict]:
    ordered = sorted(segments, key=lambda s: float(s.get("start_time", 0.0) or 0.0))
    collapsed: List[Dict] = []

    for seg in ordered:
        text = (seg.get("text") or "").strip()
        if not text:
            continue

        start_time = float(seg.get("start_time", 0.0) or 0.0)
        end_time = float(seg.get("end_time", start_time) or start_time)
        if end_time < start_time:
            end_time = start_time

        if collapsed and start_time <= float(collapsed[-1]["end_time"]) + 1.0:
            collapsed[-1]["text"] = f"{collapsed[-1]['text']} {text}".strip()
            collapsed[-1]["end_time"] = max(float(collapsed[-1]["end_time"]), end_time)
            continue

        collapsed.append(
            {
                "speaker_tag": 1,
                "speaker_label": "Caller 1",
                "text": text,
                "start_time": start_time,
                "end_time": end_time,
            }
        )

    if not collapsed and full_transcript.strip():
        collapsed = [
            {
                "speaker_tag": 1,
                "speaker_label": "Caller 1",
                "text": full_transcript.strip(),
                "start_time": 0.0,
                "end_time": max(0.0, float(duration_seconds or 0.0)),
            }
        ]

    return collapsed


@router.post("/calls", response_model=CallAnalysisResponse)
async def analyze_call(
    file: UploadFile = File(...),
    agent_speaker_tag: Optional[int] = Query(None, description="Optional speaker tag for the agent"),
):
    del agent_speaker_tag

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported: {', '.join(SUPPORTED_FORMATS)}",
        )

    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        logger.info("Received file: %s (%s, %d bytes)", file.filename, file_ext, len(audio_bytes))

        preprocess_enabled = os.getenv("STT_PREPROCESS_ENABLE", "true").lower() in {"1", "true", "yes"}
        preprocess_high_pass_hz = int(os.getenv("STT_PREPROCESS_HIGHPASS_HZ", "120"))
        preprocess_headroom_db = float(os.getenv("STT_PREPROCESS_HEADROOM_DB", "1.0"))

        try:
            wav_bytes, sample_rate = await asyncio.to_thread(
                convert_to_wav,
                audio_bytes,
                file_ext,
                preprocess_enabled,
                preprocess_high_pass_hz,
                preprocess_headroom_db,
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        wav_filename = os.path.splitext(file.filename)[0] + ".wav"
        storage_result = await asyncio.to_thread(
            upload_audio_to_gcs, wav_bytes, wav_filename, "audio/wav"
        )

        primary_language = (os.getenv("PRIMARY_LANGUAGE_CODE", "si-LK") or "si-LK").strip()
        alt_codes_raw = os.getenv("ALT_LANGUAGE_CODES", "en-US")
        alt_codes = [code.strip() for code in alt_codes_raw.split(",") if code.strip()]
        if primary_language != "si-LK" and "si-LK" not in alt_codes:
            alt_codes.append("si-LK")
        if primary_language != "en-US" and "en-US" not in alt_codes:
            alt_codes.append("en-US")

        enable_diarization = os.getenv("ENABLE_DIARIZATION", "true").lower() in {"1", "true", "yes"}
        use_hybrid_fallback = os.getenv("STT_ENABLE_HYBRID_FALLBACK", "true").lower() in {"1", "true", "yes"}

        stt_package = await asyncio.to_thread(
            transcribe_with_hybrid_fallback,
            wav_bytes=wav_bytes,
            gcs_uri=storage_result["gcs_uri"],
            language_code=primary_language,
            alternative_language_codes=alt_codes,
            diarization_speaker_count=int(os.getenv("DIARIZATION_SPEAKER_COUNT", "2")),
            sample_rate_hertz=sample_rate,
            chunk_target_seconds=int(os.getenv("STT_CHUNK_TARGET_SECONDS", "22")),
            chunk_max_seconds=int(os.getenv("STT_CHUNK_MAX_SECONDS", "25")),
            chunk_min_seconds=int(os.getenv("STT_CHUNK_MIN_SECONDS", "20")),
            chunk_min_silence_ms=int(os.getenv("STT_CHUNK_MIN_SILENCE_MS", "700")),
            chunk_overlap_seconds=float(os.getenv("STT_CHUNK_OVERLAP_SECONDS", "1.0")),
            min_confidence=float(os.getenv("STT_MIN_CONFIDENCE", "0.55")),
            max_empty_chunk_ratio=float(os.getenv("STT_MAX_EMPTY_CHUNK_RATIO", "0.30")),
            min_transcript_chars=int(os.getenv("STT_MIN_TRANSCRIPT_CHARS", "30")),
            enable_diarization=enable_diarization,
            use_hybrid_fallback=use_hybrid_fallback,
        )

        stt_result = stt_package["result"]
        full_transcript = (stt_result.get("full_transcript") or "").strip()
        detected_language = stt_result.get("detected_language") or primary_language
        duration_seconds = stt_result.get("audio_duration_seconds")

        segments = _normalize_caller_labels(stt_result.get("speaker_segments") or [])
        diarization_mode = "two_speaker" if enable_diarization else "single_speaker"
        if enable_diarization and _is_diarization_unstable(segments):
            segments = _collapse_to_single_speaker(segments, full_transcript, float(duration_seconds or 0.0))
            diarization_mode = "single_speaker_fallback"
        elif not segments and full_transcript:
            segments = _collapse_to_single_speaker([], full_transcript, float(duration_seconds or 0.0))
            diarization_mode = "single_speaker_fallback"

        transcription_meta = dict(stt_package.get("transcription_meta") or {})
        transcription_meta["diarization_mode"] = diarization_mode

        quality = dict(stt_package.get("quality") or {})
        quality_passed = bool(stt_package.get("quality_passed", False))
        transcription_meta["quality_passed"] = quality_passed

        if not quality_passed:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Low transcription quality",
                    "quality": quality,
                    "transcription_meta": transcription_meta,
                },
            )

        if os.getenv("ENABLE_LANGUAGE_DETECTION", "false").lower() in {"1", "true", "yes"}:
            try:
                detected_language = (
                    await asyncio.to_thread(detect_language, full_transcript)
                    if full_transcript
                    else detected_language
                )
            except Exception:
                pass

        intent = await asyncio.to_thread(predict_intent, full_transcript)
        sentiment = await asyncio.to_thread(analyze_sentiment, full_transcript)

        if not duration_seconds:
            duration_seconds = await asyncio.to_thread(get_audio_duration_seconds, audio_bytes, file_ext)

        record = {
            "created_at": datetime.utcnow(),
            "file": {
                "filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": len(audio_bytes),
                "gcs_uri": storage_result["gcs_uri"],
                "blob_name": storage_result.get("blob_name"),
            },
            "detected_language": detected_language,
            "duration_seconds": duration_seconds,
            "full_transcript": full_transcript,
            "speaker_segments": segments,
            "category": intent,
            "sentiment": sentiment,
            "transcription_meta": transcription_meta,
        }

        collection = get_collection()
        insert_result = await collection.insert_one(record)
        record["_id"] = insert_result.inserted_id

        return _serialize_call(record)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/calls", response_model=CallListResponse)
async def list_calls(
    q: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Category filter"),
    start: Optional[str] = Query(None, description="ISO start date"),
    end: Optional[str] = Query(None, description="ISO end date"),
    limit: int = Query(50, ge=1, le=200, description="Max number of calls to return"),
):
    query: dict = {}
    if q:
        query["$text"] = {"$search": q}
    if category and category.lower() != "all":
        query["category.label"] = category

    date_filter = {}
    try:
        if start:
            date_filter["$gte"] = _parse_iso_date(start)
        if end:
            date_filter["$lte"] = _parse_iso_date(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start/end date format")
    if date_filter:
        query["created_at"] = date_filter

    collection = get_collection()
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("created_at", -1).limit(limit)
    items = []
    async for doc in cursor:
        doc = _serialize_call(doc)
        preview = doc.get("full_transcript", "")[:160]
        items.append(
            {
                "id": doc["id"],
                "created_at": doc["created_at"],
                "file_name": doc.get("file", {}).get("filename", ""),
                "detected_language": doc.get("detected_language"),
                "duration_seconds": doc.get("duration_seconds"),
                "category": doc.get("category"),
                "sentiment": doc.get("sentiment"),
                "preview": preview,
            }
        )

    return {"total": total, "items": items}


@router.get("/calls/{call_id}", response_model=CallAnalysisResponse)
async def get_call(call_id: str):
    collection = get_collection()
    try:
        doc = await collection.find_one({"_id": ObjectId(call_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid call ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Call not found")

    return _serialize_call(doc)


@router.get("/calls/{call_id}/audio-url")
async def get_call_audio_url(call_id: str):
    collection = get_collection()
    try:
        doc = await collection.find_one({"_id": ObjectId(call_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid call ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Call not found")

    gcs_uri = doc.get("file", {}).get("gcs_uri")
    if not gcs_uri:
        raise HTTPException(status_code=404, detail="Audio URI not found for this call")

    try:
        url = await asyncio.to_thread(generate_signed_audio_url, gcs_uri, 60)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"url": url, "expires_in_minutes": 60}


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    start: Optional[str] = Query(None, description="ISO start date"),
    end: Optional[str] = Query(None, description="ISO end date"),
):
    match: dict = {}
    if start or end:
        date_filter = {}
        try:
            if start:
                date_filter["$gte"] = _parse_iso_date(start)
            if end:
                date_filter["$lte"] = _parse_iso_date(end)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start/end date format")
        match["created_at"] = date_filter

    collection = get_collection()

    category_pipeline = [
        {"$match": match},
        {"$group": {"_id": "$category.label", "count": {"$sum": 1}}},
        {"$project": {"_id": 0, "category": "$_id", "count": 1}},
        {"$sort": {"count": -1}},
    ]

    daily_pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                },
                "count": {"$sum": 1},
            }
        },
        {"$project": {"_id": 0, "date": "$_id", "count": 1}},
        {"$sort": {"date": 1}},
    ]

    category_counts = await collection.aggregate(category_pipeline).to_list(length=None)
    daily_counts = await collection.aggregate(daily_pipeline).to_list(length=None)
    total_calls = await collection.count_documents(match)

    return {
        "total_calls": total_calls,
        "category_counts": category_counts,
        "daily_counts": daily_counts,
    }
