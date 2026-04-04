"""
pricing.py
==========
API endpoints for real-time STT model pricing.
Visible in Swagger UI at: http://localhost:8007/docs

Endpoints:
    GET /api/stt/pricing          — live prices for all models + LKR rate
    GET /api/stt/pricing/refresh  — force re-fetch from GCP Billing API (clears cache)
"""

import json
import logging
import os
import time
import urllib.request
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — fallback prices used if live fetch fails
# ─────────────────────────────────────────────────────────────────────────────

TOKENS_PER_SECOND = 25          # Gemini charges 25 audio tokens per second

GEMINI_FALLBACK = {
    "gemini-3-flash":   {"price_per_million": 1.00, "label": "Gemini 3 Flash",   "status": "active"},
    "gemini-2.5-pro":   {"price_per_million": 1.00, "label": "Gemini 2.5 Pro",   "status": "active"},
    "gemini-2.5-flash": {"price_per_million": 1.00, "label": "Gemini 2.5 Flash", "status": "active"},
}

CHIRP2_FALLBACK_PER_MINUTE = 0.016   # USD per minute
LKR_FALLBACK               = 320.0   # USD → LKR fallback rate

# In-memory cache — refreshed on demand or after TTL
_price_cache: Optional[dict] = None
_cache_ttl_seconds           = 3600   # 1 hour


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ModelPricing(BaseModel):
    model:             str
    label:             str
    status:            str                     # "active" | "deprecated"
    billing_unit:      str                     # "per_million_tokens" | "per_minute"
    price_usd:         float                   # per 1M tokens OR per minute
    price_source:      str                     # "LIVE" | "FALLBACK"
    cost_per_min_usd:  float
    cost_per_hr_usd:   float
    cost_per_hr_lkr:   float
    sku_description:   Optional[str] = None    # raw SKU description from GCP


class PricingResponse(BaseModel):
    fetched_at:        Optional[str]
    lkr_per_usd:       float
    lkr_source:        str                     # "LIVE" | "FALLBACK"
    models:            list[ModelPricing]
    formula_gemini:    str
    formula_chirp2:    str


# ─────────────────────────────────────────────────────────────────────────────
# LIVE FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_auth_token() -> str:
    """Get OAuth2 token from the existing service account credentials."""
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-billing.readonly"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token


def _fetch_skus(service_name: str, token: str) -> list:
    """Fetch all SKUs for a GCP service, handling pagination."""
    skus       = []
    page_token = ""
    base_url   = f"https://cloudbilling.googleapis.com/v1/{service_name}/skus"

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


def _parse_sku_price(sku: dict) -> float:
    """
    Extract the price per unit from a GCP SKU.
    GCP stores price as: units (integer) + nanos (fractional × 1e-9)
    e.g. units=0, nanos=1000000000 → $1.00 per unit
    """
    try:
        pricing = sku["pricingInfo"][0]["pricingExpression"]
        for tier in pricing.get("tieredRates", []):
            up    = tier.get("unitPrice", {})
            units = int(up.get("units", 0) or 0)
            nanos = int(up.get("nanos",  0) or 0)
            price = units + nanos / 1e9
            if price > 0:
                return price
    except (KeyError, IndexError, TypeError):
        pass
    return 0.0


def _fetch_lkr_rate() -> tuple[float, str]:
    """Fetch live USD→LKR exchange rate. Returns (rate, source)."""
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read())
        rate = float(data["rates"].get("LKR", LKR_FALLBACK))
        return rate, "LIVE"
    except Exception as e:
        logger.warning("LKR rate fetch failed: %s — using fallback %s", e, LKR_FALLBACK)
        return LKR_FALLBACK, "FALLBACK"


def _build_pricing_response(force_refresh: bool = False) -> dict:
    """
    Core function — fetches live prices from GCP Billing API and LKR rate.
    Returns a dict that maps directly to PricingResponse.
    Results are cached for 1 hour unless force_refresh=True.
    """
    global _price_cache

    # Return cached data if still fresh
    if not force_refresh and _price_cache is not None:
        cached_at = _price_cache.get("_cached_epoch", 0)
        if time.time() - cached_at < _cache_ttl_seconds:
            logger.info("Returning cached pricing (age=%.0fs)", time.time() - cached_at)
            return _price_cache

    lkr_rate, lkr_source = _fetch_lkr_rate()

    # Start with fallback prices for all models
    model_data = {}
    for model_key, info in GEMINI_FALLBACK.items():
        model_data[model_key] = {
            "price_per_million": info["price_per_million"],
            "label":             info["label"],
            "status":            info["status"],
            "source":            "FALLBACK",
            "sku_description":   None,
        }
    model_data["chirp2"] = {
        "price_per_minute": CHIRP2_FALLBACK_PER_MINUTE,
        "label":            "Chirp 2 (STT V2)",
        "status":           "active",
        "source":           "FALLBACK",
        "sku_description":  None,
    }

    # Try to fetch live prices from GCP Billing API
    try:
        token = _get_auth_token()

        # List GCP services to find Vertex AI and Speech-to-Text
        req = urllib.request.Request(
            "https://cloudbilling.googleapis.com/v1/services?pageSize=500",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            services = json.loads(resp.read()).get("services", [])

        vertex_service = next(
            (s["name"] for s in services if "Vertex AI" in s.get("displayName", "")), None
        )
        speech_service = next(
            (s["name"] for s in services
             if "Speech" in s.get("displayName", "") and "Text" in s.get("displayName", "")), None
        )

        # ── Gemini audio input prices ─────────────────────────────────────────
        if vertex_service:
            skus = _fetch_skus(vertex_service, token)

            model_keywords = {
                "gemini-3-flash":   ["Gemini 3 Flash",   "gemini-3-flash"],
                "gemini-2.5-flash": ["Gemini 2.5 Flash", "gemini-2.5-flash"],
                "gemini-2.5-pro":   ["Gemini 2.5 Pro",   "gemini-2.5-pro"],
            }

            for model_key, keywords in model_keywords.items():
                matched = [
                    s for s in skus
                    if any(kw.lower() in s.get("description", "").lower() for kw in keywords)
                    and "audio" in s.get("description", "").lower()
                    and "input" in s.get("description", "").lower()
                ]
                if matched:
                    price_per_token   = _parse_sku_price(matched[0])
                    price_per_million = price_per_token * 1_000_000
                    if price_per_million > 0:
                        model_data[model_key]["price_per_million"] = price_per_million
                        model_data[model_key]["source"]            = "LIVE"
                        model_data[model_key]["sku_description"]   = matched[0].get("description")

        # ── Chirp 2 / Speech-to-Text price ───────────────────────────────────
        if speech_service:
            skus = _fetch_skus(speech_service, token)
            chirp_skus = [
                s for s in skus
                if "chirp" in s.get("description", "").lower()
                or ("v2" in s.get("description", "").lower()
                    and "speech" in s.get("description", "").lower())
            ]
            if chirp_skus:
                price_per_15s = _parse_sku_price(chirp_skus[0])
                price_per_min = price_per_15s * 4   # 4 × 15s = 1 minute
                if price_per_min > 0:
                    model_data["chirp2"]["price_per_minute"] = price_per_min
                    model_data["chirp2"]["source"]           = "LIVE"
                    model_data["chirp2"]["sku_description"]  = chirp_skus[0].get("description")

        logger.info("Live prices fetched from GCP Billing API")

    except Exception as e:
        logger.warning("GCP Billing API fetch failed: %s — using fallback prices", e)

    # ── Build final response structure ────────────────────────────────────────
    per_min_tokens = TOKENS_PER_SECOND * 60
    per_hr_tokens  = per_min_tokens * 60

    models = []

    for model_key, info in GEMINI_FALLBACK.items():
        md  = model_data[model_key]
        ppm = md["price_per_million"]
        models.append({
            "model":            model_key,
            "label":            md["label"],
            "status":           md["status"],
            "billing_unit":     "per_million_tokens",
            "price_usd":        ppm,
            "price_source":     md["source"],
            "cost_per_min_usd": round((per_min_tokens / 1_000_000) * ppm, 6),
            "cost_per_hr_usd":  round((per_hr_tokens  / 1_000_000) * ppm, 6),
            "cost_per_hr_lkr":  round((per_hr_tokens  / 1_000_000) * ppm * lkr_rate, 4),
            "sku_description":  md.get("sku_description"),
        })

    # Chirp 2
    c2  = model_data["chirp2"]
    c2p = c2["price_per_minute"]
    models.append({
        "model":            "chirp_2",
        "label":            c2["label"],
        "status":           c2["status"],
        "billing_unit":     "per_minute",
        "price_usd":        c2p,
        "price_source":     c2["source"],
        "cost_per_min_usd": round(c2p, 6),
        "cost_per_hr_usd":  round(c2p * 60, 6),
        "cost_per_hr_lkr":  round(c2p * 60 * lkr_rate, 4),
        "sku_description":  c2.get("sku_description"),
    })

    result = {
        "fetched_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lkr_per_usd":    round(lkr_rate, 4),
        "lkr_source":     lkr_source,
        "models":         models,
        "formula_gemini": f"cost = (duration_sec × {TOKENS_PER_SECOND} tokens) ÷ 1,000,000 × price_per_million",
        "formula_chirp2": "cost = (duration_sec ÷ 60) × price_per_minute",
        "_cached_epoch":  time.time(),
    }

    _price_cache = result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/stt/pricing",
    response_model=PricingResponse,
    summary="Get real-time STT model pricing",
    description="""
Returns live pricing for all active STT models — Gemini (3 Flash, 2.5 Pro, 2.5 Flash)
and Chirp 2 — with costs in USD and LKR.

**Price source tags:**
- `LIVE` — price fetched from Google Cloud Billing Catalog API right now
- `FALLBACK` — GCP API was unreachable, using last known hardcoded price

**Exchange rate:** fetched live from exchangerate-api.com. Falls back to 320 LKR/USD.

Results are **cached for 1 hour**. Use `/api/stt/pricing/refresh` to force a fresh fetch.
    """,
    tags=["STT Pricing"],
)
async def get_stt_pricing():
    try:
        data = _build_pricing_response(force_refresh=False)
        # Remove internal cache key before returning
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        logger.error("Pricing endpoint error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stt/pricing/refresh",
    response_model=PricingResponse,
    summary="Force refresh live pricing from GCP",
    description="""
Clears the pricing cache and fetches fresh prices directly from the
**Google Cloud Billing Catalog API** and live exchange rate API.

Use this when you want to confirm the very latest prices without waiting
for the 1-hour cache to expire.
    """,
    tags=["STT Pricing"],
)
async def refresh_stt_pricing():
    try:
        data = _build_pricing_response(force_refresh=True)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        logger.error("Pricing refresh error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
