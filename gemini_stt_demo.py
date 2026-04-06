"""
gemini_stt_demo.py
==================
Sinhala STT demo — compares Gemini models AND Chirp 2 side by side.
No frontend, no pipeline — plain Python with console output and real-time costs.

HOW TO RUN:
    python gemini_stt_demo.py your_audio.mp3                      # default: gemini-2.5-flash
    python gemini_stt_demo.py your_audio.mp3 --model gemini-2.5-pro
    python gemini_stt_demo.py your_audio.mp3 --model chirp2       # Chirp 2 only
    python gemini_stt_demo.py your_audio.mp3 --compare            # ALL models side by side
    python gemini_stt_demo.py --pricing                           # show pricing table only

REQUIREMENTS:
    pip install google-cloud-aiplatform google-cloud-speech vertexai --break-system-packages
    ffmpeg must be installed: brew install ffmpeg

SETUP — these come from backend/.env automatically:
    GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json
    GOOGLE_CLOUD_PROJECT=telecom-call-analysis
    STT_GEMINI_LOCATION=us-central1
    STT_V2_REGION=asia-southeast1
"""

import os
import sys
import time
import wave
import json
import math
import tempfile
import argparse
import subprocess
import urllib.request
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK PRICES  (used only if live fetch fails)
# These are hardcoded as a safety net — the script always tries live prices first
# ─────────────────────────────────────────────────────────────────────────────

TOKENS_PER_SECOND = 32        # Google charges 32 audio tokens per second (Gemini 2.5+)
LKR_PER_USD       = 320       # Exchange rate — updated by fetch_live_lkr_rate()

# Active Gemini models — prices from cloud.google.com/vertex-ai/generative-ai/pricing
# Input  = audio tokens charged at audio input rate
# Output = transcript text tokens charged at text output rate
GEMINI_MODELS = {
    "gemini-3-flash":   {"price_per_million": 1.00, "output_price_per_million": 3.00,  "label": "Gemini 3 Flash    (newest)"},
    "gemini-2.5-pro":   {"price_per_million": 1.25, "output_price_per_million": 10.00, "label": "Gemini 2.5 Pro    (high accuracy)"},
    "gemini-2.5-flash": {"price_per_million": 1.00, "output_price_per_million": 2.50,  "label": "Gemini 2.5 Flash  (recommended)"},
}

# Chirp 2: billed per minute of audio
CHIRP2_PRICE_PER_MINUTE = 0.016   # USD per minute (fallback)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 0 — LIVE PRICE FETCHER
# Pulls real prices from Google Cloud Billing Catalog API using your service
# account credentials. Falls back to hardcoded prices if anything goes wrong.
# ─────────────────────────────────────────────────────────────────────────────

# Cache so we only fetch once per run
_live_prices_cache = None


def _get_auth_token() -> str:
    """
    Get a short-lived OAuth2 token from the service account credentials.
    Uses google.auth which is already installed (part of google-cloud-aiplatform).
    """
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-billing.readonly"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token


def _fetch_skus(service_id: str, token: str) -> list:
    """
    Fetch all SKUs for a given GCP service from the Cloud Billing Catalog API.
    Handles pagination automatically.
    """
    skus      = []
    page_token = ""
    base_url  = f"https://cloudbilling.googleapis.com/v1/{service_id}/skus"

    while True:
        url = base_url + (f"?pageToken={page_token}" if page_token else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        skus.extend(data.get("skus", []))
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    return skus


def _parse_unit_price(sku: dict) -> float:
    """
    Extract price per unit from a SKU's pricingInfo.
    Google stores prices as: units (integer part) + nanos (fractional × 1e-9)
    Example: units=0, nanos=1000000000 → $1.00 per unit
    """
    try:
        pricing    = sku["pricingInfo"][0]["pricingExpression"]
        tiered     = pricing["tieredRates"]
        # Use the first non-zero tier (base rate)
        for tier in tiered:
            up    = tier.get("unitPrice", {})
            units = int(up.get("units", 0) or 0)
            nanos = int(up.get("nanos", 0) or 0)
            price = units + nanos / 1e9
            if price > 0:
                return price
    except (KeyError, IndexError, TypeError):
        pass
    return 0.0


def fetch_live_prices() -> dict:
    """
    Fetch real-time prices from the Google Cloud Billing Catalog API.

    Returns a dict:
        {
          "gemini-2.5-flash":  { "price_per_million": 1.00, "source": "LIVE" },
          "gemini-2.5-pro":    { "price_per_million": 1.00, "source": "LIVE" },
          "gemini-3-flash":    { "price_per_million": 1.00, "source": "LIVE" },
          "chirp2_per_minute": { "price": 0.016,            "source": "LIVE" },
          "fetched_at":        "2026-03-31 14:22:05",
        }

    Falls back to hardcoded values if the API call fails.
    """
    global _live_prices_cache
    if _live_prices_cache is not None:
        return _live_prices_cache

    print("\n  🌐 Fetching live prices from Google Cloud Billing API...")

    try:
        token = _get_auth_token()

        # ── Vertex AI SKUs (Gemini audio) ─────────────────────────────────────
        # We list all services first to find the Vertex AI service ID reliably
        req  = urllib.request.Request(
            "https://cloudbilling.googleapis.com/v1/services?pageSize=500",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            services = json.loads(resp.read()).get("services", [])

        # Find Vertex AI and Speech-to-Text service IDs
        vertex_service = next(
            (s["name"] for s in services if "Vertex AI" in s.get("displayName", "")), None
        )
        speech_service = next(
            (s["name"] for s in services
             if "Speech" in s.get("displayName", "") and "Text" in s.get("displayName", "")), None
        )

        prices = {"fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        # ── Parse Gemini audio input prices 
        if vertex_service:
            skus = _fetch_skus(vertex_service, token)

            # Map: keyword in SKU description → model name in our GEMINI_MODELS dict
            # Google's SKU descriptions contain the model name and "Audio Input"
            model_keywords = {
                "gemini-3-flash":   ["Gemini 3 Flash", "gemini-3-flash"],
                "gemini-2.5-flash": ["Gemini 2.5 Flash", "gemini-2.5-flash"],
                "gemini-2.5-pro":   ["Gemini 2.5 Pro", "gemini-2.5-pro"],
            }

            for model_key, keywords in model_keywords.items():
                matched = [
                    s for s in skus
                    if any(kw.lower() in s.get("description", "").lower() for kw in keywords)
                    and "audio" in s.get("description", "").lower()
                    and "input" in s.get("description", "").lower()
                ]
                if matched:
                    # Price is per 1 token — multiply by 1,000,000 to get per-million
                    price_per_token   = _parse_unit_price(matched[0])
                    price_per_million = price_per_token * 1_000_000
                    prices[model_key] = {
                        "price_per_million": price_per_million,
                        "sku_description":   matched[0].get("description", ""),
                        "source":            "LIVE",
                    }
                else:
                    # Gemini audio SKUs not in billing catalog — use official pricing page values
                    fallback = GEMINI_MODELS[model_key]["price_per_million"]
                    prices[model_key] = {
                        "price_per_million": fallback,
                        "source":            "OFFICIAL",
                    }

        # ── Parse Chirp 2 / Speech-to-Text price ──────────────────────────────
        if speech_service:
            skus = _fetch_skus(speech_service, token)
            chirp_skus = [
                s for s in skus
                if "chirp" in s.get("description", "").lower()
                or "v2" in s.get("description", "").lower()
            ]
            if chirp_skus:
                # Speech-to-Text bills per 15 seconds — convert to per minute
                price_per_15s  = _parse_unit_price(chirp_skus[0])
                price_per_min  = price_per_15s * 4   # 4 × 15s = 1 minute
                prices["chirp2_per_minute"] = {
                    "price":             price_per_min,
                    "sku_description":   chirp_skus[0].get("description", ""),
                    "source":            "LIVE",
                }
            else:
                prices["chirp2_per_minute"] = {
                    "price":  CHIRP2_PRICE_PER_MINUTE,
                    "source": "OFFICIAL",
                }

        _live_prices_cache = prices

        # Count how many were fetched live
        live_count = sum(
            1 for k, v in prices.items()
            if isinstance(v, dict) and v.get("source") == "LIVE"
        )
        total_count = len([k for k in prices if k != "fetched_at"])
        print(f"  ✅ Live prices fetched: {live_count}/{total_count} models "
              f"[{prices['fetched_at']}]")

        return prices

    except Exception as e:
        print(f"  ⚠️  Could not fetch live prices ({e})")
        print(f"      Using hardcoded fallback prices instead.\n")

        # Return official pricing page values as fallback
        fallback = {
            "fetched_at": None,
            "chirp2_per_minute": {"price": CHIRP2_PRICE_PER_MINUTE, "source": "OFFICIAL"},
        }
        for model_key, info in GEMINI_MODELS.items():
            fallback[model_key] = {
                "price_per_million": info["price_per_million"],
                "source":            "OFFICIAL",
            }
        _live_prices_cache = fallback
        return fallback


def get_gemini_price(model_name: str) -> tuple:
    """
    Return (price_per_million_tokens, source_label) for a Gemini model.
    Tries live prices first, falls back to hardcoded.
    """
    live   = fetch_live_prices()
    entry  = live.get(model_name, {})
    price  = entry.get("price_per_million") or GEMINI_MODELS.get(model_name, {}).get("price_per_million", 1.00)
    source = entry.get("source", "FALLBACK")
    return price, source


def get_chirp2_price() -> tuple:
    """
    Return (price_per_minute, source_label) for Chirp 2.
    Tries live prices first, falls back to hardcoded.
    """
    live   = fetch_live_prices()
    entry  = live.get("chirp2_per_minute", {})
    price  = entry.get("price") or CHIRP2_PRICE_PER_MINUTE
    source = entry.get("source", "FALLBACK")
    return price, source


def fetch_live_lkr_rate() -> float:
    """
    Fetch the current USD→LKR exchange rate from a public currency API.
    Falls back to the hardcoded LKR_PER_USD if unavailable.
    """
    global LKR_PER_USD
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read())
        rate = data["rates"].get("LKR", LKR_PER_USD)
        print(f"  💱 Live exchange rate: 1 USD = {rate:.2f} LKR")
        LKR_PER_USD = rate
        return rate
    except Exception:
        print(f"  💱 Exchange rate unavailable — using {LKR_PER_USD} LKR/USD (hardcoded)")
        return LKR_PER_USD
CHIRP2_REGION           = "asia-southeast1"
CHIRP2_LABEL            = "Chirp 2 (STT V2)  (confidence score)"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — COST CALCULATORS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_gemini_cost(duration_seconds: float, model_name: str,
                          output_tokens: int = 0) -> dict:
    """
    Calculate the real cost of transcribing audio with a Gemini model.
    Includes BOTH input (audio) and output (transcript text) costs.

    Formula:
        input_tokens   = duration_seconds × 25
        input_cost     = (input_tokens  ÷ 1,000,000) × input_price_per_million
        output_cost    = (output_tokens ÷ 1,000,000) × output_price_per_million
        total_cost     = input_cost + output_cost
    """
    info                    = GEMINI_MODELS.get(model_name, {"price_per_million": 1.00,
                                                              "output_price_per_million": 2.50,
                                                              "label": model_name})
    input_price_per_million, price_source = get_gemini_price(model_name)
    output_price_per_million = info.get("output_price_per_million", 2.50)

    input_tokens     = duration_seconds * TOKENS_PER_SECOND
    input_cost_usd   = (input_tokens  / 1_000_000) * input_price_per_million
    output_cost_usd  = (output_tokens / 1_000_000) * output_price_per_million
    total_cost_usd   = input_cost_usd + output_cost_usd
    total_cost_lkr   = total_cost_usd * LKR_PER_USD

    # Per-hour rate based on input only (standard benchmark)
    cost_per_hr_usd  = (3600 * TOKENS_PER_SECOND / 1_000_000) * input_price_per_million
    cost_per_hr_lkr  = cost_per_hr_usd * LKR_PER_USD

    return {
        "engine":                    "gemini",
        "model":                     model_name,
        "label":                     info["label"],
        "duration_seconds":          duration_seconds,
        "input_tokens":              int(input_tokens),
        "output_tokens":             output_tokens,
        "input_price_per_million":   input_price_per_million,
        "output_price_per_million":  output_price_per_million,
        "input_cost_usd":            input_cost_usd,
        "output_cost_usd":           output_cost_usd,
        "price_source":              price_source,
        "cost_usd":                  total_cost_usd,
        "cost_lkr":                  total_cost_lkr,
        "cost_per_hr_usd":           cost_per_hr_usd,
        "cost_per_hr_lkr":           cost_per_hr_lkr,
    }


def calculate_chirp2_cost(duration_seconds: float) -> dict:
    """
    Calculate the real cost of transcribing audio with Chirp 2 (STT V2).
    Uses live prices from Google Cloud Billing API when available.

    Formula:
        minutes       = duration_seconds ÷ 60
        cost_usd      = minutes × price_per_minute
        cost_per_hour = 60 × price_per_minute
    """
    price_per_minute, price_source = get_chirp2_price()

    minutes          = duration_seconds / 60
    cost_usd         = minutes * price_per_minute
    cost_lkr         = cost_usd * LKR_PER_USD
    cost_per_hr_usd  = 60 * price_per_minute
    cost_per_hr_lkr  = cost_per_hr_usd * LKR_PER_USD

    return {
        "engine":           "chirp2",
        "model":            "chirp_2",
        "label":            CHIRP2_LABEL,
        "duration_seconds": duration_seconds,
        "tokens_used":      None,
        "price_per_minute": price_per_minute,
        "price_source":     price_source,
        "cost_usd":         cost_usd,
        "cost_lkr":         cost_lkr,
        "cost_per_hr_usd":  cost_per_hr_usd,
        "cost_per_hr_lkr":  cost_per_hr_lkr,
    }


def print_cost(cost: dict):
    """Print cost breakdown clearly to the console, showing if price is live or fallback."""
    source      = cost.get("price_source", "FALLBACK")
    source_tag  = "🟢 LIVE from GCP"  if source == "LIVE" else "📋 Google pricing page"

    print(f"\n  💰 COST BREAKDOWN")
    print(f"  {'─' * 44}")
    print(f"  Price source    : {source_tag}")
    print(f"  Audio duration  : {cost['duration_seconds']:.1f} seconds")

    if cost["engine"] == "gemini":
        print(f"  Input tokens    : {cost['input_tokens']:,}  ({TOKENS_PER_SECOND} tokens/sec audio)")
        print(f"  Output tokens   : {cost['output_tokens']:,}  (transcript text)")
        print(f"  Input price     : ${cost['input_price_per_million']:.4f} per 1M tokens")
        print(f"  Output price    : ${cost['output_price_per_million']:.4f} per 1M tokens")
    else:
        minutes = cost['duration_seconds'] / 60
        print(f"  Minutes billed  : {minutes:.3f} min")
        print(f"  Price rate      : ${cost['price_per_minute']:.4f} per minute")

    print(f"  LKR rate        : 1 USD = {LKR_PER_USD:.2f} LKR")
    print(f"  {'─' * 44}")
    if cost["engine"] == "gemini":
        print(f"  Input cost      : ${cost['input_cost_usd']:.6f} USD  (audio)")
        print(f"  Output cost     : ${cost['output_cost_usd']:.6f} USD  (transcript)")
    print(f"  This file cost  : ${cost['cost_usd']:.6f} USD")
    print(f"                    LKR {cost['cost_lkr']:.4f}")
    print(f"  ────────────────────────────────────────────")
    print(f"  Rate per hour   : ${cost['cost_per_hr_usd']:.4f} USD  /  LKR {cost['cost_per_hr_lkr']:.2f}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — AUDIO LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_audio_as_wav(file_path: str) -> tuple:
    """
    Load any audio file (mp3, wav, m4a etc.) and convert to 16kHz mono WAV.
    Returns (wav_bytes, duration_seconds).
    Requires ffmpeg installed on the system.
    """
    print(f"\n  📂 Loading audio: {os.path.basename(file_path)}")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-ar", "16000", "-ac", "1", "-f", "wav", tmp_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")

        with open(tmp_path, "rb") as f:
            wav_bytes = f.read()

        with wave.open(tmp_path, "rb") as w:
            duration = w.getnframes() / w.getframerate()

        print(f"  ✅ Loaded: {len(wav_bytes):,} bytes  |  duration={duration:.1f}s  |  16kHz mono WAV")
        return wav_bytes, duration

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def split_wav_into_chunks(wav_bytes: bytes, chunk_seconds: int = 15) -> list:
    """
    Split WAV bytes into fixed-length chunks for APIs with size limits.
    Returns list of (chunk_bytes, start_time, duration) tuples.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        tmp_path = tmp.name

    chunks = []
    try:
        with wave.open(tmp_path, "rb") as w:
            frame_rate   = w.getframerate()
            n_channels   = w.getnchannels()
            sampwidth    = w.getsampwidth()
            total_frames = w.getnframes()
            frames_per_chunk = frame_rate * chunk_seconds

            chunk_index = 0
            while True:
                start_frame = chunk_index * frames_per_chunk
                if start_frame >= total_frames:
                    break
                w.setpos(int(start_frame))
                frames = w.readframes(frames_per_chunk)
                if not frames:
                    break

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as ctmp:
                    ctmp_path = ctmp.name
                with wave.open(ctmp_path, "wb") as cw:
                    cw.setnchannels(n_channels)
                    cw.setsampwidth(sampwidth)
                    cw.setframerate(frame_rate)
                    cw.writeframes(frames)
                with open(ctmp_path, "rb") as f:
                    chunk_bytes = f.read()
                os.unlink(ctmp_path)

                start_time = start_frame / frame_rate
                duration   = len(frames) / (frame_rate * n_channels * sampwidth)
                chunks.append((chunk_bytes, start_time, duration))
                chunk_index += 1
    finally:
        os.unlink(tmp_path)

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — SETUP HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_env():
    """Load backend/.env into environment variables (if not already set)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    # Resolve relative credentials path
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if creds and not os.path.isabs(creds):
        full = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", creds)
        if os.path.exists(full):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = full


def connect_to_vertex_ai():
    """Connect to Google Vertex AI using service account credentials."""
    import vertexai

    project  = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.getenv("STT_GEMINI_LOCATION", "us-central1").strip()

    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT not set. Check backend/.env")

    vertexai.init(project=project, location=location)
    print(f"  🔗 Vertex AI connected  — project={project}  location={location}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — TRANSCRIBE WITH GEMINI
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_with_gemini(wav_bytes: bytes, duration_seconds: float, model_name: str) -> dict:
    """
    Send audio to a Gemini model on Vertex AI and return the Sinhala transcript.

    Steps:
        1. Build Sinhala-specific prompt
        2. Send audio + prompt to Gemini
        3. Return transcript + real-time cost
    """
    from vertexai.generative_models import GenerativeModel, Part

    print(f"\n  🤖 Gemini → {model_name}")

    prompt = (
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

    start_time = time.time()
    model      = GenerativeModel(model_name)
    audio_part = Part.from_data(data=wav_bytes, mime_type="audio/wav")
    response   = model.generate_content([audio_part, prompt])
    elapsed    = time.time() - start_time

    transcript    = (response.text or "").strip()
    # Get actual output token count from Gemini response metadata
    output_tokens = 0
    try:
        output_tokens = response.usage_metadata.candidates_token_count or 0
    except Exception:
        # Fallback: estimate ~1.5 tokens per character for Sinhala Unicode
        output_tokens = int(len(transcript) * 1.5)
    cost          = calculate_gemini_cost(duration_seconds, model_name, output_tokens)

    print(f"     Done in {elapsed:.1f}s  |  {'✅ got transcript' if transcript else '⚠️  empty response'}")

    return {
        "model":            model_name,
        "label":            GEMINI_MODELS.get(model_name, {}).get("label", model_name),
        "engine":           "gemini",
        "transcript":       transcript,
        "confidence":       None,           # Gemini does not return confidence scores
        "elapsed_seconds":  elapsed,
        "duration_seconds": duration_seconds,
        "cost":             cost,
        "success":          bool(transcript),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — TRANSCRIBE WITH CHIRP 2
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_with_chirp2(wav_bytes: bytes, duration_seconds: float) -> dict:
    """
    Transcribe audio using Google Cloud STT V2 (Chirp 2 model).
    Priced at $0.016 per minute. Returns a real confidence score (0.0 – 1.0).

    Chirp 2 inline limit is 60 seconds — longer audio is split into 15s chunks.
    """
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech

    print(f"\n  🎤 Chirp 2 → chirp_2 (STT V2)")

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    region  = os.getenv("STT_V2_REGION", CHIRP2_REGION).strip()

    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT not set. Check backend/.env")

    client     = SpeechClient()
    recognizer = f"projects/{project}/locations/{region}/recognizers/_"

    config = cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=["si-LK"],
        model="chirp_2",
        features=cloud_speech.RecognitionFeatures(
            enable_word_confidence=True,
        ),
    )

    # Chirp 2 inline limit: 60 seconds — split into 15s chunks if longer
    INLINE_LIMIT_SECONDS = 55  # use 55s to be safe
    start_time           = time.time()
    all_transcripts      = []
    all_confidences      = []

    if duration_seconds <= INLINE_LIMIT_SECONDS:
        # Short audio — send in one request
        chunks = [(wav_bytes, 0.0, duration_seconds)]
    else:
        # Long audio — split into 15-second chunks
        print(f"     Audio is {duration_seconds:.1f}s — splitting into 15s chunks...")
        chunks = split_wav_into_chunks(wav_bytes, chunk_seconds=15)

    print(f"     Sending {len(chunks)} chunk(s) to Chirp 2...")

    for i, (chunk_bytes, chunk_start, chunk_dur) in enumerate(chunks):
        request = cloud_speech.RecognizeRequest(
            recognizer=recognizer,
            config=config,
            content=chunk_bytes,
        )
        try:
            response = client.recognize(request=request)
            for result in response.results:
                if result.alternatives:
                    alt = result.alternatives[0]
                    if alt.transcript.strip():
                        all_transcripts.append(alt.transcript.strip())
                    if alt.confidence:
                        all_confidences.append(alt.confidence)
            print(f"     Chunk {i+1}/{len(chunks)} ✅")
        except Exception as e:
            print(f"     Chunk {i+1}/{len(chunks)} ❌  {e}")

    elapsed    = time.time() - start_time
    transcript = " ".join(all_transcripts).strip()
    confidence = sum(all_confidences) / len(all_confidences) if all_confidences else None
    cost       = calculate_chirp2_cost(duration_seconds)

    print(f"     Done in {elapsed:.1f}s  |  confidence={confidence:.2f}" if confidence else
          f"     Done in {elapsed:.1f}s  |  {'✅ got transcript' if transcript else '⚠️  empty response'}")

    return {
        "model":            "chirp_2",
        "label":            CHIRP2_LABEL,
        "engine":           "chirp2",
        "transcript":       transcript,
        "confidence":       confidence,
        "elapsed_seconds":  elapsed,
        "duration_seconds": duration_seconds,
        "cost":             cost,
        "success":          bool(transcript),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — PRINT A SINGLE RESULT
# ─────────────────────────────────────────────────────────────────────────────

def print_result(result: dict):
    """Print transcript + cost for one model result."""
    print(f"\n{'═' * 62}")
    print(f"  MODEL   : {result['label']}")
    print(f"  STATUS  : {'✅ SUCCESS' if result['success'] else '❌ NO TRANSCRIPT'}")
    print(f"  TIME    : {result['elapsed_seconds']:.1f}s to process {result['duration_seconds']:.1f}s of audio")

    if result.get("confidence") is not None:
        pct = result["confidence"] * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  CONF    : {bar}  {pct:.1f}%")
    else:
        print(f"  CONF    : N/A  (Gemini does not return confidence scores)")

    print(f"{'─' * 62}")

    if result["success"]:
        print(f"\n  📝 TRANSCRIPT:\n")
        words = result["transcript"].split()
        line  = "  "
        for word in words:
            if len(line) + len(word) + 1 > 60:
                print(line)
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)
    else:
        print(f"\n  ⚠️  No transcript returned.")

    print_cost(result["cost"])
    print(f"{'═' * 62}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — COMPARE ALL MODELS
# ─────────────────────────────────────────────────────────────────────────────

def compare_all_models(wav_bytes: bytes, duration_seconds: float):
    """
    Run the same audio through ALL Gemini models + Chirp 2 and compare.
    Shows a summary table at the end with transcript, confidence, and cost.
    """
    print(f"\n{'═' * 62}")
    print(f"  🔬 COMPARING ALL MODELS — Gemini + Chirp 2")
    print(f"  Audio: {duration_seconds:.1f}s  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 62}")

    results = []

    # ── Run Gemini models ─────────────────────────────────────────────────────
    for model_name in GEMINI_MODELS:
        try:
            result = transcribe_with_gemini(wav_bytes, duration_seconds, model_name)
        except Exception as e:
            print(f"  ❌ {model_name} failed: {e}")
            result = {
                "model": model_name, "label": GEMINI_MODELS[model_name]["label"],
                "engine": "gemini", "transcript": "", "confidence": None,
                "elapsed_seconds": 0, "duration_seconds": duration_seconds,
                "cost": calculate_gemini_cost(duration_seconds, model_name),
                "success": False, "error": str(e),
            }
        results.append(result)
        print_result(result)

    # ── Run Chirp 2 ───────────────────────────────────────────────────────────
    try:
        result = transcribe_with_chirp2(wav_bytes, duration_seconds)
    except Exception as e:
        print(f"  ❌ Chirp 2 failed: {e}")
        result = {
            "model": "chirp_2", "label": CHIRP2_LABEL,
            "engine": "chirp2", "transcript": "", "confidence": None,
            "elapsed_seconds": 0, "duration_seconds": duration_seconds,
            "cost": calculate_chirp2_cost(duration_seconds),
            "success": False, "error": str(e),
        }
    results.append(result)
    print_result(result)

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n\n{'═' * 72}")
    print(f"  📊 COMPARISON SUMMARY  —  {duration_seconds:.1f}s audio")
    print(f"{'═' * 72}")
    print(f"  {'Model':<32}  {'Status':<8}  {'Conf':>6}  {'Time':>5}  {'USD cost':>10}  {'LKR cost':>10}")
    print(f"  {'─' * 68}")

    for r in results:
        status  = "✅ OK"   if r["success"]          else "❌ FAIL"
        conf    = f"{r['confidence']*100:.1f}%" if r["confidence"] is not None else "N/A"
        elapsed = f"{r['elapsed_seconds']:.1f}s"   if r["elapsed_seconds"]   else "—"
        usd     = f"${r['cost']['cost_usd']:.6f}"
        lkr     = f"LKR {r['cost']['cost_lkr']:.4f}"
        label   = r["label"][:32]
        print(f"  {label:<32}  {status:<8}  {conf:>6}  {elapsed:>5}  {usd:>10}  {lkr:>10}")

    print(f"  {'─' * 68}")
    print(f"\n  HOURLY RATES:")
    seen = set()
    for r in results:
        key = r["model"]
        if key not in seen:
            seen.add(key)
            usd_hr = r['cost']['cost_per_hr_usd']
            lkr_hr = r['cost']['cost_per_hr_lkr']
            label  = r["label"][:32]
            print(f"    {label:<32}  ${usd_hr:.4f}/hr  =  LKR {lkr_hr:.2f}/hr")

    print(f"\n  💡 Chirp 2 is {CHIRP2_PRICE_PER_MINUTE * 60 / (3600 * TOKENS_PER_SECOND / 1_000_000 * 1.00):.1f}× more expensive than Gemini but gives a real confidence score.")
    print(f"{'═' * 72}\n")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — PRICING TABLE (no audio needed)
# ─────────────────────────────────────────────────────────────────────────────

def show_pricing_table():
    """
    Print a full pricing reference table.
    Fetches live prices from Google Cloud Billing API first.
    Shows [LIVE] or [FALLBACK] tag next to each price.
    """
    fetch_live_lkr_rate()   # update LKR rate
    live    = fetch_live_prices()
    per_min = TOKENS_PER_SECOND * 60
    per_hr  = per_min * 60

    fetched_at = live.get("fetched_at")
    timestamp  = f"fetched {fetched_at}" if fetched_at else "hardcoded fallback"

    print(f"\n{'═' * 72}")
    print(f"  💰 SINHALA STT PRICING — {timestamp}")
    print(f"  1 USD = {LKR_PER_USD:.2f} LKR  (live exchange rate)")
    print(f"{'═' * 72}")
    print(f"  {'Model':<32}  {'Source':<10}  {'$/min':>8}  {'$/hr':>8}  {'LKR/hr':>10}")
    print(f"  {'─' * 68}")

    # Gemini models with live prices
    for model_name, info in GEMINI_MODELS.items():
        entry    = live.get(model_name, {})
        ppm      = entry.get("price_per_million") or info["price_per_million"]
        source   = "🟢 LIVE" if entry.get("source") == "LIVE" else "📋 Official"
        min_cost = (per_min / 1_000_000) * ppm
        hr_cost  = (per_hr  / 1_000_000) * ppm
        hr_lkr   = hr_cost * LKR_PER_USD
        label    = info["label"][:32]
        print(f"  {label:<32}  {source:<10}  ${min_cost:>6.4f}  ${hr_cost:>6.4f}  LKR {hr_lkr:>7.2f}")

    print(f"  {'─' * 68}")

    # Chirp 2 with live price
    c2_entry  = live.get("chirp2_per_minute", {})
    c2_min    = c2_entry.get("price") or CHIRP2_PRICE_PER_MINUTE
    c2_source = "🟢 LIVE" if c2_entry.get("source") == "LIVE" else "📋 Official"
    c2_hr     = c2_min * 60
    c2_lkr    = c2_hr * LKR_PER_USD
    print(f"  {CHIRP2_LABEL:<32}  {c2_source:<10}  ${c2_min:>6.4f}  ${c2_hr:>6.4f}  LKR {c2_lkr:>7.2f}")

    print(f"  {'─' * 68}")
    v1t_lkr = 0.006 * 60 * LKR_PER_USD
    v1s_lkr = 0.004 * 60 * LKR_PER_USD
    print(f"  {'V1 Telephony (fallback)':<32}  {'—':<10}  $0.0060  $0.3600  LKR {v1t_lkr:>7.2f}")
    print(f"  {'V1 Standard (fallback)':<32}  {'—':<10}  $0.0040  $0.2400  LKR {v1s_lkr:>7.2f}")
    print(f"{'═' * 72}")
    print(f"  Gemini  : tokens = seconds × {TOKENS_PER_SECOND}  →  cost = tokens ÷ 1,000,000 × price")
    print(f"  Chirp 2 : cost = (seconds ÷ 60) × price_per_minute")
    print(f"{'═' * 72}\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sinhala STT Demo — Gemini models + Chirp 2 with real-time cost"
    )
    parser.add_argument("audio",     nargs="?", help="Path to audio file (mp3, wav, m4a...)")
    parser.add_argument("--model",   default="gemini-2.5-flash",
                        help="Model to use: gemini-2.5-flash | gemini-2.5-pro | gemini-3-flash | chirp2")
    parser.add_argument("--compare", action="store_true",
                        help="Run ALL models (3 Gemini + Chirp 2) on the same audio")
    parser.add_argument("--pricing", action="store_true",
                        help="Show pricing table for all models (no audio needed)")
    args = parser.parse_args()

    print(f"\n{'═' * 62}")
    print(f"  🎙️  SINHALA STT DEMO — Gemini + Chirp 2")
    print(f"  Telecom Call Intelligence System")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 62}")

    # Always load env + live rates first so credentials are available
    load_env()
    fetch_live_lkr_rate()
    fetch_live_prices()

    if args.pricing:
        show_pricing_table()
        return

    if not args.audio:
        print("\n  Usage examples:")
        print("    python gemini_stt_demo.py call.mp3")
        print("    python gemini_stt_demo.py call.mp3 --model gemini-2.5-pro")
        print("    python gemini_stt_demo.py call.mp3 --model chirp2")
        print("    python gemini_stt_demo.py call.mp3 --compare")
        print("    python gemini_stt_demo.py --pricing\n")
        show_pricing_table()
        return

    try:
        # Step 1 — Load audio

        wav_bytes, duration = load_audio_as_wav(args.audio)

        # Step 2 — Connect to Vertex AI (needed for Gemini)
        if args.compare or args.model != "chirp2":
            connect_to_vertex_ai()

        # Step 3 — Transcribe
        if args.compare:
            compare_all_models(wav_bytes, duration)

        elif args.model == "chirp2":
            result = transcribe_with_chirp2(wav_bytes, duration)
            print_result(result)

        else:
            if args.model not in GEMINI_MODELS:
                print(f"\n  ❌ Unknown model: {args.model}")
                print(f"     Available: {', '.join(GEMINI_MODELS.keys())} | chirp2\n")
                sys.exit(1)
            result = transcribe_with_gemini(wav_bytes, duration, args.model)
            print_result(result)

    except FileNotFoundError as e:
        print(f"\n  ❌ {e}\n")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n  ❌ Setup error: {e}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n\n  ⚠️  Stopped by user.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ❌ Error: {e}\n")
        raise


if __name__ == "__main__":
    main()
