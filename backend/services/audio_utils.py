from pydub import AudioSegment
from pydub import effects
from pydub.silence import detect_silence
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
import logging
import os
import shutil
import audioop
import wave

logger = logging.getLogger(__name__)

_FFMPEG_PATH: Optional[str] = None
_FFPROBE_PATH: Optional[str] = None


def _resolve_binary(binary_name: str, env_var: str) -> Optional[str]:
    candidates = []
    env_value = os.getenv(env_var)
    if env_value:
        candidates.append(env_value)

    which_path = shutil.which(binary_name)
    if which_path:
        candidates.append(which_path)

    if os.name == "nt":
        user_home = os.path.expanduser("~")
        candidates.extend(
            [
                os.path.join(
                    user_home,
                    "AppData",
                    "Local",
                    "Microsoft",
                    "WinGet",
                    "Links",
                    f"{binary_name}.exe",
                ),
                os.path.join("C:\\", "ffmpeg", "bin", f"{binary_name}.exe"),
                os.path.join("C:\\", "Program Files", "ffmpeg", "bin", f"{binary_name}.exe"),
                os.path.join("C:\\", "Program Files (x86)", "ffmpeg", "bin", f"{binary_name}.exe"),
            ]
        )

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _ffmpeg_install_message() -> str:
    return (
        "FFmpeg is required to process MP3/FLAC/OGG/M4A files. Install ffmpeg and ffprobe "
        "or set FFMPEG_BINARY/FFPROBE_BINARY to their full paths."
    )


def ffmpeg_available() -> bool:
    return bool(_FFMPEG_PATH and _FFPROBE_PATH)


def _find_ffmpeg():
    """Find ffmpeg/ffprobe executables and configure pydub to use them."""
    global _FFMPEG_PATH, _FFPROBE_PATH

    _FFMPEG_PATH = _resolve_binary("ffmpeg", "FFMPEG_BINARY")
    _FFPROBE_PATH = _resolve_binary("ffprobe", "FFPROBE_BINARY")

    if _FFMPEG_PATH:
        AudioSegment.converter = _FFMPEG_PATH
        logger.info("Using ffmpeg at: %s", _FFMPEG_PATH)
    else:
        logger.warning("ffmpeg not found.")

    if _FFPROBE_PATH:
        AudioSegment.ffprobe = _FFPROBE_PATH
        logger.info("Using ffprobe at: %s", _FFPROBE_PATH)
    else:
        logger.warning("ffprobe not found.")

_find_ffmpeg()

# Formats pydub can read (ffmpeg must be installed for mp3/ogg/m4a)
SUPPORTED_INPUT_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}


def split_wav_into_chunks(
    wav_bytes: bytes,
    target_chunk_seconds: int = 6,
    max_chunk_seconds: int = 6,
    min_chunk_seconds: int = 6,
    min_silence_len_ms: int = 300,
    overlap_seconds: float = 0.0,
    silence_thresh_db: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Split normalized WAV audio into chunk-sized WAV byte payloads.
    Prefers cutting at silence boundaries to reduce word truncation.
    """
    try:
        audio = AudioSegment.from_file(BytesIO(wav_bytes), format="wav")
    except Exception as exc:
        raise RuntimeError(f"Could not read WAV bytes for chunking: {exc}") from exc

    total_ms = len(audio)
    if total_ms <= 0:
        return []

    target_ms = max(1, int(target_chunk_seconds * 1000))
    max_ms = max(target_ms, int(max_chunk_seconds * 1000))
    min_ms = min(target_ms, int(min_chunk_seconds * 1000))
    if min_ms > max_ms:
        min_ms = max_ms
    overlap_ms = max(0, int(overlap_seconds * 1000))

    if silence_thresh_db is None:
        silence_thresh = int(audio.dBFS - 16) if audio.dBFS != float("-inf") else -45
    else:
        silence_thresh = silence_thresh_db

    silence_ranges = detect_silence(
        audio,
        min_silence_len=min_silence_len_ms,
        silence_thresh=silence_thresh,
    )
    cut_points = sorted({int((start + end) / 2) for start, end in silence_ranges})

    chunks: List[Dict[str, Any]] = []
    cursor_ms = 0
    while cursor_ms < total_ms:
        remaining_ms = total_ms - cursor_ms
        if remaining_ms <= max_ms:
            end_ms = total_ms
        else:
            search_start = cursor_ms + min_ms
            search_end = min(cursor_ms + max_ms, total_ms)
            candidates = [cp for cp in cut_points if search_start <= cp <= search_end]
            if candidates:
                ideal_cut = cursor_ms + target_ms
                end_ms = min(candidates, key=lambda cp: abs(cp - ideal_cut))
            else:
                end_ms = search_end

        if end_ms <= cursor_ms:
            end_ms = min(cursor_ms + max_ms, total_ms)

        chunk_start_ms = max(0, cursor_ms - overlap_ms) if chunks else cursor_ms

        chunk_audio = audio[chunk_start_ms:end_ms]
        buf = BytesIO()
        chunk_audio.export(buf, format="wav")
        chunk_bytes = buf.getvalue()

        chunks.append(
            {
                "index": len(chunks),
                "start_time": chunk_start_ms / 1000.0,
                "content_start_time": cursor_ms / 1000.0,
                "end_time": end_ms / 1000.0,
                "duration_seconds": (end_ms - chunk_start_ms) / 1000.0,
                "wav_bytes": chunk_bytes,
            }
        )
        cursor_ms = end_ms

    # Merge tiny tail chunk back into previous chunk for better context.
    if len(chunks) > 1 and chunks[-1]["duration_seconds"] < 2.0:
        prev_start_ms = int(chunks[-2]["start_time"] * 1000)
        merged_audio = audio[prev_start_ms:total_ms]
        merged_buf = BytesIO()
        merged_audio.export(merged_buf, format="wav")
        chunks[-2] = {
            "index": chunks[-2]["index"],
            "start_time": prev_start_ms / 1000.0,
            "end_time": total_ms / 1000.0,
            "duration_seconds": (total_ms - prev_start_ms) / 1000.0,
            "wav_bytes": merged_buf.getvalue(),
        }
        chunks.pop()

    logger.info(
        "Audio chunking complete: total_duration=%.1fs, chunks=%d, target=%ss, max=%ss, overlap=%.1fs",
        total_ms / 1000.0,
        len(chunks),
        target_chunk_seconds,
        max_chunk_seconds,
        overlap_ms / 1000.0,
    )
    return chunks


def get_audio_duration_seconds(audio_bytes: bytes, file_extension: str) -> Optional[float]:
    try:
        fmt = file_extension.strip(".").lower()
        if fmt == "wav":
            with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
                frame_rate = wav_file.getframerate()
                if frame_rate <= 0:
                    return None
                return float(wav_file.getnframes() / frame_rate)

        if not ffmpeg_available():
            logger.warning("Skipping duration extraction for %s: %s", fmt, _ffmpeg_install_message())
            return None

        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=fmt)
        return float(audio.duration_seconds)
    except FileNotFoundError:
        logger.warning("Audio tooling missing while reading duration: %s", _ffmpeg_install_message())
        return None
    except Exception as exc:
        logger.warning("Could not get audio duration: %s", exc)
        return None


def get_audio_sample_rate(audio_bytes: bytes, file_extension: str) -> Optional[int]:
    try:
        fmt = file_extension.strip(".").lower()
        if fmt == "wav":
            with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
                return int(wav_file.getframerate())

        if not ffmpeg_available():
            logger.warning("Skipping sample-rate extraction for %s: %s", fmt, _ffmpeg_install_message())
            return None

        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=fmt)
        return int(audio.frame_rate)
    except FileNotFoundError:
        logger.warning("Audio tooling missing while reading sample rate: %s", _ffmpeg_install_message())
        return None
    except Exception as exc:
        logger.warning("Could not get sample rate: %s", exc)
        return None


def _normalize_wav_without_ffmpeg(audio_bytes: bytes) -> Tuple[bytes, int]:
    with wave.open(BytesIO(audio_bytes), "rb") as source_wav:
        channels = source_wav.getnchannels()
        sample_width = source_wav.getsampwidth()
        sample_rate = source_wav.getframerate()
        raw_frames = source_wav.readframes(source_wav.getnframes())

    if channels > 1:
        raw_frames = audioop.tomono(raw_frames, sample_width, 0.5, 0.5)

    if sample_width != 2:
        raw_frames = audioop.lin2lin(raw_frames, sample_width, 2)

    out_buf = BytesIO()
    with wave.open(out_buf, "wb") as out_wav:
        out_wav.setnchannels(1)
        out_wav.setsampwidth(2)
        out_wav.setframerate(sample_rate)
        out_wav.writeframes(raw_frames)

    return out_buf.getvalue(), sample_rate


def convert_to_wav(
    audio_bytes: bytes,
    file_extension: str,
    apply_preprocessing: bool = True,
    high_pass_hz: int = 120,
    normalize_headroom_db: float = 1.0,
) -> Tuple[bytes, int]:
    """
    Convert any supported audio format to mono 16-bit 16kHz WAV (LINEAR16).
    Returns (wav_bytes, sample_rate_hertz).

    ALL formats (including WAV) go through ffmpeg/pydub to ensure proper
    codec handling (mu-law, a-law, ADPCM, etc.) and consistent 16kHz output.
    """
    fmt = file_extension.strip(".").lower()
    logger.info("Converting %s audio (%d bytes) to WAV...", fmt, len(audio_bytes))

    if not ffmpeg_available():
        # Fallback for WAV-only when ffmpeg is missing
        if fmt == "wav":
            try:
                wav_bytes, sample_rate = _normalize_wav_without_ffmpeg(audio_bytes)
                logger.info("Processed WAV without ffmpeg: %d bytes, %dHz", len(wav_bytes), sample_rate)
                return wav_bytes, sample_rate
            except Exception as exc:
                raise RuntimeError(f"Could not process WAV file (ffmpeg not available): {exc}") from exc
        raise RuntimeError(_ffmpeg_install_message())

    # Use ffmpeg/pydub for ALL formats — this correctly handles:
    #  - Non-PCM WAV codecs (mu-law, a-law, ADPCM) common in telephony
    #  - Proper sample rate detection and resampling
    #  - Any container/codec combination
    try:
        if fmt == "wav":
            # Let pydub auto-detect the actual codec inside the WAV container
            audio = AudioSegment.from_file(BytesIO(audio_bytes), format="wav")
        else:
            audio = AudioSegment.from_file(BytesIO(audio_bytes), format=fmt)
    except Exception as exc:
        # If format-specific load fails, try auto-detection
        try:
            audio = AudioSegment.from_file(BytesIO(audio_bytes))
        except Exception as decode_exc:
            raise RuntimeError(f"Could not decode audio: {decode_exc}") from exc

    original_rate = audio.frame_rate
    original_channels = audio.channels
    logger.info("Original audio: duration=%.1fs, rate=%dHz, channels=%d",
                audio.duration_seconds, original_rate, original_channels)

    # Force mono + 16-bit + 16kHz for LINEAR16 encoding
    audio = audio.set_channels(1)
    audio = audio.set_sample_width(2)  # 16-bit
    audio = audio.set_frame_rate(16000)

    if apply_preprocessing:
        # Light denoise and level stabilization before STT.
        audio = audio.high_pass_filter(max(20, int(high_pass_hz)))
        audio = effects.normalize(audio, headroom=max(0.1, float(normalize_headroom_db)))

    sample_rate = audio.frame_rate
    logger.info("Audio properties: duration=%.1fs, sample_rate=%dHz, channels=%d",
                audio.duration_seconds, sample_rate, audio.channels)

    buf = BytesIO()
    try:
        audio.export(buf, format="wav")
    except FileNotFoundError as exc:
        raise RuntimeError(_ffmpeg_install_message()) from exc
    wav_bytes = buf.getvalue()

    logger.info("Converted to WAV: %d bytes, %dHz (original: %dHz)", len(wav_bytes), sample_rate, original_rate)
    return wav_bytes, sample_rate

