"""
gemini_stt.py
=============
Gemini-based Speech-to-Text via Vertex AI.
Uses your existing google-credentials.json service account — no separate API key needed.
Billed from your GCP $300 free credits. No rate limits from free tier.

Controlled via .env:
  STT_GEMINI_ENABLED=true/false
  STT_GEMINI_MODEL=gemini-2.0-flash-001  (or gemini-2.5-flash-preview-04-17 / gemini-2.5-pro-preview-03-25)
  STT_GEMINI_LOCATION=asia-southeast1    (Vertex AI region)

Pipeline:
  Gemini (primary, if enabled) → Chirp 2 (if V2 enabled) → V1 (always fallback)
"""

import base64
import logging
import os
import threading
import time
from typing import Dict, List, Optional

def _interruptible_sleep(seconds: float, interval: float = 0.5):
    """Sleep in small intervals so Ctrl+C can interrupt it."""
    elapsed = 0.0
    while elapsed < seconds:
        time.sleep(min(interval, seconds - elapsed))
        elapsed += interval

logger = logging.getLogger(__name__)

# Lazy Vertex AI init — only runs when Gemini is first used
_vertex_initialized = False


def _init_vertex():
    global _vertex_initialized
    if _vertex_initialized:
        return
    try:
        import vertexai
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        location   = os.getenv("STT_GEMINI_LOCATION", "asia-southeast1").strip()
        if not project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set in .env")
        vertexai.init(project=project_id, location=location)
        _vertex_initialized = True
        logger.info("Vertex AI initialised: project=%s, location=%s", project_id, location)
    except ImportError:
        raise RuntimeError(
            "google-cloud-aiplatform package is not installed. "
            "Run: pip install google-cloud-aiplatform"
        )


def is_gemini_enabled() -> bool:
    return os.getenv("STT_GEMINI_ENABLED", "false").lower() in {"1", "true", "yes"}


def get_gemini_model_name() -> str:
    return (os.getenv("STT_GEMINI_MODEL", "gemini-2.0-flash-001") or "gemini-2.0-flash-001").strip()


def _build_prompt(language_code: str) -> str:
    if language_code == "si-LK":
        return (
            "You are a professional Sinhala transcriptionist. "
            "Transcribe this phone call audio EXACTLY as spoken in Sinhala. "
            "Rules:\n"
            "- Output ONLY the Sinhala text using Sinhala Unicode script\n"
            "- English loanwords spoken with Sinhala pronunciation must be written "
            "phonetically in Sinhala script (e.g. 'connection' → 'කනෙක්ෂන්')\n"
            "- Do NOT translate anything\n"
            "- Do NOT add explanations, headers, or labels\n"
            "- If audio is silent or inaudible, output nothing"
        )
    elif language_code == "en-US":
        return (
            "Transcribe this phone call audio exactly as spoken in English. "
            "Output only the spoken text, no explanations or labels."
        )
    else:
        return (
            f"Transcribe this audio exactly as spoken (language: {language_code}). "
            "Output only the transcribed text, no explanations."
        )


def transcribe_chunk_with_gemini(
    wav_bytes: bytes,
    language_code: str,
    model_name: str,
) -> Optional[str]:
    """Transcribe a single WAV chunk using Vertex AI Gemini."""
    from vertexai.generative_models import GenerativeModel, Part

    _init_vertex()
    model  = GenerativeModel(model_name)
    prompt = _build_prompt(language_code)

    audio_part = Part.from_data(data=wav_bytes, mime_type="audio/wav")
    response   = model.generate_content([audio_part, prompt])

    text = (response.text or "").strip()

    # Filter out refusal / meta responses
    refusal_markers = [
        "i cannot", "i'm unable", "no audio", "inaudible",
        "transcription:", "transcript:", "here is the",
        "i can't", "cannot transcribe",
    ]
    if any(m in text.lower() for m in refusal_markers):
        logger.debug("Gemini returned non-transcript response, treating as empty")
        return None

    return text if text else None


def transcribe_wav_with_gemini(
    wav_bytes: bytes,
    language_code: str = "si-LK",
    model_name: Optional[str] = None,
    chunk_target_seconds: int = 8,
    chunk_max_seconds: int = 10,
    chunk_min_seconds: int = 4,
    chunk_min_silence_ms: int = 300,
    chunk_overlap_seconds: float = 0.5,
) -> Dict:
    """
    Transcribe a full WAV file using Vertex AI Gemini.
    Returns a result dict compatible with the existing STT pipeline.
    """
    from backend.services.audio_utils import split_wav_into_chunks

    if model_name is None:
        model_name = get_gemini_model_name()

    logger.info(
        "Gemini STT (Vertex AI): model=%s, language=%s, audio=%d bytes",
        model_name, language_code, len(wav_bytes),
    )

    chunks = split_wav_into_chunks(
        wav_bytes=wav_bytes,
        target_chunk_seconds=chunk_target_seconds,
        max_chunk_seconds=chunk_max_seconds,
        min_chunk_seconds=chunk_min_seconds,
        min_silence_len_ms=chunk_min_silence_ms,
        overlap_seconds=chunk_overlap_seconds,
    )

    total_chunks  = len(chunks)
    transcripts: List[str] = []
    segments:    List[Dict] = []
    success_count = 0
    total_duration = 0.0

    for i, chunk in enumerate(chunks):
        chunk_bytes = chunk.get("wav_bytes", b"")
        start_time  = float(chunk.get("start_time", 0.0))
        duration    = float(chunk.get("duration_seconds", 0.0))
        total_duration = max(total_duration, start_time + duration)

        logger.info(
            "Transcribing Gemini chunk %d/%d (start=%.1fs, duration=%.1fs, model=%s)",
            i + 1, total_chunks, start_time, duration, model_name,
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                text = transcribe_chunk_with_gemini(chunk_bytes, language_code, model_name)
                if text:
                    transcripts.append(text)
                    segments.append({
                        "speaker_tag":   1,
                        "speaker_label": "Speaker 1",
                        "text":          text,
                        "start_time":    start_time,
                        "end_time":      start_time + duration,
                        "confidence":    None,
                    })
                    success_count += 1
                    logger.info("Gemini chunk %d/%d OK: %d chars", i + 1, total_chunks, len(text))
                else:
                    logger.warning("Gemini chunk %d/%d returned empty response", i + 1, total_chunks)
                break
            except Exception as exc:
                err_str = str(exc).lower()
                if "quota" in err_str or "resource exhausted" in err_str or "429" in err_str:
                    wait = 30 if attempt == 0 else 60
                    logger.warning(
                        "Gemini chunk %d/%d rate limited (attempt %d/%d), waiting %ds...",
                        i + 1, total_chunks, attempt + 1, max_retries, wait,
                    )
                    _interruptible_sleep(wait)
                else:
                    logger.error("Gemini chunk %d/%d failed: %s", i + 1, total_chunks, exc)
                    break

    full_transcript    = " ".join(transcripts).strip()
    empty_chunk_ratio  = (total_chunks - success_count) / total_chunks if total_chunks > 0 else 1.0

    logger.info(
        "Gemini STT complete: chunks=%d/%d, transcript_len=%d, duration=%.1fs",
        success_count, total_chunks, len(full_transcript), total_duration,
    )

    return {
        "full_transcript":   full_transcript,
        "segments":          segments,
        "confidence":        None,
        "duration_seconds":  total_duration,
        "chunk_count":       total_chunks,
        "successful_chunks": success_count,
        "empty_chunk_ratio": empty_chunk_ratio,
        "stt_engine":        f"gemini_vertexai:{model_name}",
    }
