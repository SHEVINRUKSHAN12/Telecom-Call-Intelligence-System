from google.cloud import speech
from google.auth.exceptions import DefaultCredentialsError
import logging
import re
from typing import Dict, List, Optional, Tuple

from services.audio_utils import split_wav_into_chunks

logger = logging.getLogger(__name__)


def _credentials_error_message() -> str:
    return (
        "Google Cloud Speech credentials are invalid or missing. "
        "Set GOOGLE_APPLICATION_CREDENTIALS to a valid service account JSON path."
    )


def _build_speaker_segments(words: List) -> List[Dict]:
    segments: List[Dict] = []
    current = None

    for word in words:
        speaker_tag = int(getattr(word, "speaker_tag", 0) or 0)
        if speaker_tag == 0:
            speaker_tag = 1
        start_time = word.start_time.total_seconds() if word.start_time else 0.0
        end_time = word.end_time.total_seconds() if word.end_time else start_time
        token = word.word or ""

        if current and current["speaker_tag"] == speaker_tag:
            current["text"] = f"{current['text']} {token}".strip()
            current["end_time"] = end_time
        else:
            if current:
                segments.append(current)
            current = {
                "speaker_tag": speaker_tag,
                "speaker_label": f"Speaker {speaker_tag}",
                "text": token,
                "start_time": start_time,
                "end_time": end_time,
            }

    if current:
        segments.append(current)

    return segments


def _build_transcript_from_words(words: List) -> str:
    tokens = []
    for word in words:
        token = (getattr(word, "word", "") or "").strip()
        if token:
            tokens.append(token)
    return " ".join(tokens).strip()


def _build_recognition_config(
    language_code: str,
    alternative_language_codes: Optional[List[str]],
    diarization_speaker_count: int,
    sample_rate_hertz: int,
    enable_diarization: bool,
    model: str = "default",
):
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate_hertz,
        language_code=language_code,
        alternative_language_codes=alternative_language_codes if alternative_language_codes is not None else [],
        audio_channel_count=1,
        enable_automatic_punctuation=True,
        enable_word_time_offsets=enable_diarization,
        model=model,
        use_enhanced=True,
    )
    if enable_diarization:
        config.diarization_config = speech.SpeakerDiarizationConfig(
            enable_speaker_diarization=True,
            min_speaker_count=diarization_speaker_count,
            max_speaker_count=diarization_speaker_count,
        )
    return config


def _parse_stt_response(response, language_code: str, enable_diarization: bool) -> Dict:
    if not response.results:
        return {
            "full_transcript": "",
            "detected_language": "unknown",
            "confidence": 0.0,
            "speaker_segments": [],
            "audio_duration_seconds": 0.0,
        }

    detected_language = language_code
    for result in response.results:
        if getattr(result, "language_code", None):
            detected_language = result.language_code

    if enable_diarization:
        last_result = response.results[-1]
        alternative = last_result.alternatives[0] if last_result.alternatives else None
        full_transcript = (alternative.transcript or "").strip() if alternative else ""
        words: List = list(alternative.words) if alternative else []
        if not full_transcript and words:
            # Some diarization responses return words but empty transcript field.
            full_transcript = _build_transcript_from_words(words)
        avg_confidence = float(getattr(alternative, "confidence", 0.0) or 0.0)
        segments = _build_speaker_segments(words)
    else:
        transcript_parts: List[str] = []
        confidence_sum = 0.0
        confidence_count = 0
        for result in response.results:
            if not result.alternatives:
                continue
            alt = result.alternatives[0]
            if alt.transcript:
                transcript_parts.append(alt.transcript.strip())
            if hasattr(alt, "confidence"):
                confidence_sum += float(alt.confidence or 0.0)
                confidence_count += 1

        full_transcript = " ".join(part for part in transcript_parts if part).strip()
        avg_confidence = confidence_sum / confidence_count if confidence_count > 0 else 0.0
        segments = [
            {
                "speaker_tag": 1,
                "speaker_label": "Speaker 1",
                "text": full_transcript,
                "start_time": 0.0,
                "end_time": 0.0,
            }
        ] if full_transcript else []
        words = []

    audio_duration_seconds = 0.0
    if words:
        audio_duration_seconds = max(
            word.end_time.total_seconds() if word.end_time else 0.0 for word in words
        )

    return {
        "full_transcript": full_transcript.strip(),
        "detected_language": detected_language,
        "confidence": avg_confidence,
        "speaker_segments": segments,
        "audio_duration_seconds": audio_duration_seconds,
    }


_TOKEN_SANITIZE_RE = re.compile(r"[^\w']+", flags=re.UNICODE)


def _normalize_token(token: str) -> str:
    return _TOKEN_SANITIZE_RE.sub("", (token or "").lower())


def _remove_text_overlap(previous_text: str, current_text: str, max_overlap_words: int = 12) -> str:
    prev_tokens = [tok for tok in (previous_text or "").strip().split() if tok]
    curr_tokens = [tok for tok in (current_text or "").strip().split() if tok]
    if not prev_tokens or not curr_tokens:
        return (current_text or "").strip()

    max_k = min(max_overlap_words, len(prev_tokens), len(curr_tokens))
    overlap_words = 0
    for k in range(max_k, 0, -1):
        prev_norm = [_normalize_token(tok) for tok in prev_tokens[-k:]]
        curr_norm = [_normalize_token(tok) for tok in curr_tokens[:k]]
        if not any(prev_norm) or not any(curr_norm):
            continue
        if prev_norm == curr_norm:
            overlap_words = k
            break

    if overlap_words == 0:
        return " ".join(curr_tokens).strip()
    return " ".join(curr_tokens[overlap_words:]).strip()


def _shift_segments(segments: List[Dict], offset_seconds: float) -> List[Dict]:
    shifted: List[Dict] = []
    for seg in segments:
        shifted.append(
            {
                "speaker_tag": int(seg.get("speaker_tag", 1) or 1),
                "speaker_label": seg.get("speaker_label") or f"Speaker {int(seg.get('speaker_tag', 1) or 1)}",
                "text": (seg.get("text") or "").strip(),
                "start_time": float(seg.get("start_time", 0.0) or 0.0) + offset_seconds,
                "end_time": float(seg.get("end_time", 0.0) or 0.0) + offset_seconds,
            }
        )
    return shifted


def _remap_segments_speaker_tags(segments: List[Dict], speaker_map: Dict[int, int]) -> List[Dict]:
    remapped: List[Dict] = []
    for seg in segments:
        raw_tag = int(seg.get("speaker_tag", 1) or 1)
        mapped_tag = int(speaker_map.get(raw_tag, raw_tag))
        remapped.append(
            {
                "speaker_tag": mapped_tag,
                "speaker_label": f"Speaker {mapped_tag}",
                "text": seg.get("text", ""),
                "start_time": float(seg.get("start_time", 0.0) or 0.0),
                "end_time": float(seg.get("end_time", 0.0) or 0.0),
            }
        )
    return remapped


def _resolve_chunk_speaker_map(previous_segments: List[Dict], incoming_segments: List[Dict]) -> Dict[int, int]:
    """
    Keep speaker tags consistent across chunks for 2-speaker calls.
    Google diarization may flip speaker tags chunk-to-chunk; this chooses
    identity vs swapped mapping using boundary continuity.
    """
    identity = {1: 1, 2: 2}
    swapped = {1: 2, 2: 1}

    if not previous_segments or not incoming_segments:
        return identity

    incoming_tags = {int(seg.get("speaker_tag", 0) or 0) for seg in incoming_segments}
    if not incoming_tags.issubset({1, 2}) or len(incoming_tags) < 2:
        return identity

    last_seg = previous_segments[-1]
    first_seg = incoming_segments[0]
    last_tag = int(last_seg.get("speaker_tag", 1) or 1)
    first_raw_tag = int(first_seg.get("speaker_tag", 1) or 1)
    boundary_gap = float(first_seg.get("start_time", 0.0) or 0.0) - float(last_seg.get("end_time", 0.0) or 0.0)

    # Only force boundary continuity when chunks are adjacent in time.
    if boundary_gap > 2.5:
        return identity

    identity_first = identity.get(first_raw_tag, first_raw_tag)
    swapped_first = swapped.get(first_raw_tag, first_raw_tag)
    if swapped_first == last_tag and identity_first != last_tag:
        return swapped
    return identity


def _merge_segments_in_order(existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
    merged = list(existing)
    for seg in sorted(incoming, key=lambda s: float(s.get("start_time", 0.0) or 0.0)):
        if not seg.get("text"):
            continue

        if merged:
            cleaned = _remove_text_overlap(merged[-1]["text"], seg["text"])
            if not cleaned:
                if merged[-1]["speaker_tag"] == seg["speaker_tag"]:
                    merged[-1]["end_time"] = max(merged[-1]["end_time"], seg["end_time"])
                continue
            seg["text"] = cleaned

            if (
                merged[-1]["speaker_tag"] == seg["speaker_tag"]
                and seg["start_time"] <= merged[-1]["end_time"] + 1.0
            ):
                merged[-1]["text"] = f"{merged[-1]['text']} {seg['text']}".strip()
                merged[-1]["end_time"] = max(merged[-1]["end_time"], seg["end_time"])
                continue

        merged.append(seg)
    return merged


def _collect_quality_metrics(result: Dict) -> Dict:
    transcript = (result.get("full_transcript") or "").strip()
    empty_chunk_ratio = float(result.get("empty_chunk_ratio", 1.0 if not transcript else 0.0) or 0.0)
    if empty_chunk_ratio < 0.0:
        empty_chunk_ratio = 0.0
    if empty_chunk_ratio > 1.0:
        empty_chunk_ratio = 1.0

    speaker_segments = result.get("speaker_segments") or []
    speaker_tags = {
        int(seg.get("speaker_tag", 1) or 1)
        for seg in speaker_segments
        if (seg.get("text") or "").strip()
    }

    return {
        "avg_confidence": float(result.get("confidence", 0.0) or 0.0),
        "empty_chunk_ratio": empty_chunk_ratio,
        "transcript_char_count": len(transcript),
        "detected_speaker_count": len(speaker_tags),
        "chunk_count": int(result.get("chunk_count", 1) or 1),
    }


def _passes_quality_gate(
    metrics: Dict,
    min_confidence: float,
    max_empty_chunk_ratio: float,
    min_transcript_chars: int,
) -> bool:
    return (
        float(metrics.get("avg_confidence", 0.0) or 0.0) >= float(min_confidence)
        and float(metrics.get("empty_chunk_ratio", 1.0) or 1.0) <= float(max_empty_chunk_ratio)
        and int(metrics.get("transcript_char_count", 0) or 0) >= int(min_transcript_chars)
    )


def _quality_rank(metrics: Dict) -> Tuple[float, int, float]:
    return (
        float(metrics.get("avg_confidence", 0.0) or 0.0),
        int(metrics.get("transcript_char_count", 0) or 0),
        1.0 - float(metrics.get("empty_chunk_ratio", 1.0) or 1.0),
    )


def transcribe_gcs_with_diarization(
    gcs_uri: str,
    language_code: str = "si-LK",
    alternative_language_codes: Optional[List[str]] = None,
    diarization_speaker_count: int = 2,
    sample_rate_hertz: int = 16000,
    enable_diarization: bool = True,
) -> Dict:
    """
    Transcribe audio from GCS with multilingual recognition and speaker diarization.

    IMPORTANT: The audio at gcs_uri MUST be mono 16-bit WAV (LINEAR16).
    All format conversion should happen before calling this function.
    """
    try:
        client = speech.SpeechClient()
    except (DefaultCredentialsError, FileNotFoundError) as exc:
        raise RuntimeError(_credentials_error_message()) from exc

    config = _build_recognition_config(
        language_code=language_code,
        alternative_language_codes=alternative_language_codes,
        diarization_speaker_count=diarization_speaker_count,
        sample_rate_hertz=sample_rate_hertz,
        enable_diarization=enable_diarization,
    )

    audio = speech.RecognitionAudio(uri=gcs_uri)

    logger.info(
        "STT request: encoding=LINEAR16, sample_rate=%d, lang=%s, alt_langs=%s, speakers=%d, uri=%s",
        sample_rate_hertz,
        language_code,
        alternative_language_codes,
        diarization_speaker_count,
        gcs_uri,
    )

    try:
        operation = client.long_running_recognize(config=config, audio=audio)
        response = operation.result(timeout=600)

        logger.info("STT response: %d result(s)", len(response.results))

        result = _parse_stt_response(response, language_code, enable_diarization)

        logger.info(
            "STT success: transcript_len=%d, confidence=%.2f, segments=%d, duration=%.1fs",
            len(result["full_transcript"]),
            result["confidence"],
            len(result["speaker_segments"]),
            result["audio_duration_seconds"],
        )
        return result
    except Exception as exc:
        logger.error("Speech-to-Text error: %s", exc)
        raise Exception(f"Speech-to-Text error: {str(exc)}")


def transcribe_wav_with_chunking(
    wav_bytes: bytes,
    language_code: str = "si-LK",
    alternative_language_codes: Optional[List[str]] = None,
    diarization_speaker_count: int = 2,
    sample_rate_hertz: int = 16000,
    chunk_target_seconds: int = 22,
    chunk_max_seconds: int = 25,
    chunk_min_seconds: int = 20,
    chunk_min_silence_ms: int = 700,
    chunk_overlap_seconds: float = 1.0,
    enable_diarization: bool = True,
) -> Dict:
    """
    Chunk-based transcription pipeline for better stability on longer audio.
    Splits mono 16kHz WAV into manageable segments, transcribes each chunk,
    then merges transcript and speaker segments sequentially.
    """
    try:
        client = speech.SpeechClient()
    except (DefaultCredentialsError, FileNotFoundError) as exc:
        raise RuntimeError(_credentials_error_message()) from exc

    chunks = split_wav_into_chunks(
        wav_bytes=wav_bytes,
        target_chunk_seconds=chunk_target_seconds,
        max_chunk_seconds=chunk_max_seconds,
        min_chunk_seconds=chunk_min_seconds,
        min_silence_len_ms=chunk_min_silence_ms,
        overlap_seconds=chunk_overlap_seconds,
    )
    if not chunks:
        return {
            "full_transcript": "",
            "detected_language": "unknown",
            "confidence": 0.0,
            "speaker_segments": [],
            "audio_duration_seconds": 0.0,
            "chunk_count": 0,
            "successful_chunk_count": 0,
            "empty_chunk_ratio": 1.0,
        }

    config = _build_recognition_config(
        language_code=language_code,
        alternative_language_codes=alternative_language_codes,
        diarization_speaker_count=diarization_speaker_count,
        sample_rate_hertz=sample_rate_hertz,
        enable_diarization=enable_diarization,
    )

    merged_transcript = ""
    merged_segments: List[Dict] = []
    detected_language = language_code
    confidence_sum = 0.0
    confidence_count = 0
    successful_chunks = 0
    empty_chunk_count = 0

    for idx, chunk in enumerate(chunks, start=1):
        start_time = float(chunk["start_time"])
        duration = float(chunk["duration_seconds"])
        logger.info(
            "Transcribing chunk %d/%d (start=%.1fs, duration=%.1fs)",
            idx,
            len(chunks),
            start_time,
            duration,
        )

        try:
            response = client.recognize(
                config=config,
                audio=speech.RecognitionAudio(content=chunk["wav_bytes"]),
            )
            chunk_result = _parse_stt_response(response, language_code, enable_diarization=enable_diarization)
        except Exception as exc:
            logger.error("Chunk %d transcription failed: %s", idx, exc)
            empty_chunk_count += 1
            continue

        successful_chunks += 1
        chunk_transcript = (chunk_result["full_transcript"] or "").strip()
        if not chunk_transcript:
            empty_chunk_count += 1
        else:
            cleaned_transcript = _remove_text_overlap(merged_transcript, chunk_transcript)
            if cleaned_transcript:
                merged_transcript = f"{merged_transcript} {cleaned_transcript}".strip()

        if chunk_result.get("detected_language") and chunk_result["detected_language"] != "unknown":
            detected_language = chunk_result["detected_language"]

        if chunk_result.get("confidence", 0.0) > 0:
            confidence_sum += float(chunk_result["confidence"])
            confidence_count += 1

        shifted_segments = _shift_segments(chunk_result["speaker_segments"], start_time)
        speaker_map = _resolve_chunk_speaker_map(merged_segments, shifted_segments)
        aligned_segments = _remap_segments_speaker_tags(shifted_segments, speaker_map)
        merged_segments = _merge_segments_in_order(merged_segments, aligned_segments)

    if successful_chunks == 0:
        raise RuntimeError("Speech-to-Text failed for all audio chunks.")

    audio_duration_seconds = 0.0
    if merged_segments:
        merged_segments = sorted(merged_segments, key=lambda s: float(s.get("start_time", 0.0) or 0.0))
        audio_duration_seconds = max(float(seg.get("end_time", 0.0) or 0.0) for seg in merged_segments)
    else:
        audio_duration_seconds = float(chunks[-1]["end_time"])

    avg_confidence = confidence_sum / confidence_count if confidence_count > 0 else 0.0

    logger.info(
        "Chunked STT success: chunks=%d/%d, transcript_len=%d, segments=%d, duration=%.1fs",
        successful_chunks,
        len(chunks),
        len(merged_transcript),
        len(merged_segments),
        audio_duration_seconds,
    )

    return {
        "full_transcript": merged_transcript,
        "detected_language": detected_language,
        "confidence": avg_confidence,
        "speaker_segments": merged_segments,
        "audio_duration_seconds": audio_duration_seconds,
        "chunk_count": len(chunks),
        "successful_chunk_count": successful_chunks,
        "empty_chunk_ratio": (empty_chunk_count / len(chunks)) if chunks else 1.0,
    }


def transcribe_with_hybrid_fallback(
    wav_bytes: bytes,
    gcs_uri: str,
    language_code: str = "si-LK",
    alternative_language_codes: Optional[List[str]] = None,
    diarization_speaker_count: int = 2,
    sample_rate_hertz: int = 16000,
    chunk_target_seconds: int = 22,
    chunk_max_seconds: int = 25,
    chunk_min_seconds: int = 20,
    chunk_min_silence_ms: int = 700,
    chunk_overlap_seconds: float = 1.0,
    min_confidence: float = 0.55,
    max_empty_chunk_ratio: float = 0.30,
    min_transcript_chars: int = 30,
    enable_diarization: bool = True,
    use_hybrid_fallback: bool = True,
) -> Dict:
    chunked_result = transcribe_wav_with_chunking(
        wav_bytes=wav_bytes,
        language_code=language_code,
        alternative_language_codes=alternative_language_codes,
        diarization_speaker_count=diarization_speaker_count,
        sample_rate_hertz=sample_rate_hertz,
        chunk_target_seconds=chunk_target_seconds,
        chunk_max_seconds=chunk_max_seconds,
        chunk_min_seconds=chunk_min_seconds,
        chunk_min_silence_ms=chunk_min_silence_ms,
        chunk_overlap_seconds=chunk_overlap_seconds,
        enable_diarization=enable_diarization,
    )

    chunked_metrics = _collect_quality_metrics(chunked_result)
    chunked_pass = _passes_quality_gate(
        chunked_metrics,
        min_confidence=min_confidence,
        max_empty_chunk_ratio=max_empty_chunk_ratio,
        min_transcript_chars=min_transcript_chars,
    )

    selected_result = chunked_result
    selected_metrics = chunked_metrics
    pipeline_used = "chunked_primary"
    fallback_attempted = False
    fallback_used = False
    fallback_metrics = None

    if use_hybrid_fallback and not chunked_pass:
        fallback_attempted = True
        try:
            fallback_result = transcribe_gcs_with_diarization(
                gcs_uri=gcs_uri,
                language_code=language_code,
                alternative_language_codes=alternative_language_codes,
                diarization_speaker_count=diarization_speaker_count,
                sample_rate_hertz=sample_rate_hertz,
                enable_diarization=enable_diarization,
            )
            fallback_result = dict(fallback_result)
            fallback_result["chunk_count"] = 1
            fallback_result["successful_chunk_count"] = 1
            fallback_result["empty_chunk_ratio"] = 0.0 if (fallback_result.get("full_transcript") or "").strip() else 1.0
            fallback_metrics = _collect_quality_metrics(fallback_result)

            fallback_pass = _passes_quality_gate(
                fallback_metrics,
                min_confidence=min_confidence,
                max_empty_chunk_ratio=max_empty_chunk_ratio,
                min_transcript_chars=min_transcript_chars,
            )

            if fallback_pass and not chunked_pass:
                selected_result = fallback_result
                selected_metrics = fallback_metrics
                pipeline_used = "fallback_long_running"
                fallback_used = True
            elif fallback_pass == chunked_pass and _quality_rank(fallback_metrics) > _quality_rank(chunked_metrics):
                selected_result = fallback_result
                selected_metrics = fallback_metrics
                pipeline_used = "fallback_long_running"
                fallback_used = True
        except Exception as exc:
            logger.warning("Fallback long-running STT failed: %s", exc)

    quality_passed = _passes_quality_gate(
        selected_metrics,
        min_confidence=min_confidence,
        max_empty_chunk_ratio=max_empty_chunk_ratio,
        min_transcript_chars=min_transcript_chars,
    )

    transcription_meta = {
        "pipeline_used": pipeline_used,
        "chunk_count": int(selected_result.get("chunk_count", 1) or 1),
        "successful_chunk_count": int(selected_result.get("successful_chunk_count", 1) or 1),
        "avg_confidence": float(selected_metrics.get("avg_confidence", 0.0) or 0.0),
        "empty_chunk_ratio": float(selected_metrics.get("empty_chunk_ratio", 1.0) or 1.0),
        "transcript_char_count": int(selected_metrics.get("transcript_char_count", 0) or 0),
        "detected_speaker_count": int(selected_metrics.get("detected_speaker_count", 0) or 0),
        "quality_passed": bool(quality_passed),
        "fallback_used": bool(fallback_used),
        "fallback_attempted": bool(fallback_attempted),
    }

    return {
        "result": selected_result,
        "quality": selected_metrics,
        "quality_passed": quality_passed,
        "transcription_meta": transcription_meta,
        "chunked_quality": chunked_metrics,
        "fallback_quality": fallback_metrics,
    }
