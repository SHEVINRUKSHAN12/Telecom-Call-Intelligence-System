from functools import lru_cache
from typing import Optional
import logging
import os


def _sentiment_enabled() -> bool:
    return os.getenv("ENABLE_SENTIMENT", "false").lower() in {"1", "true", "yes"}


@lru_cache(maxsize=1)
def _get_sentiment_pipeline():
    if not _sentiment_enabled():
        return None, None

    model_name = os.getenv(
        "SENTIMENT_MODEL_NAME",
        "cardiffnlp/twitter-xlm-roberta-base-sentiment",
    )
    try:
        from transformers import pipeline
    except Exception as exc:  # pragma: no cover - optional dependency
        logging.warning("Transformers not available for sentiment: %s", exc)
        return None, None

    return pipeline("sentiment-analysis", model=model_name), model_name


def analyze_sentiment(text: str) -> Optional[dict]:
    if not text:
        return None

    pipeline, model_name = _get_sentiment_pipeline()
    if pipeline is None:
        return None

    try:
        result = pipeline(text, truncation=True)[0]
        return {
            "label": result.get("label"),
            "score": float(result.get("score", 0.0)),
            "model": model_name,
        }
    except Exception:  # pragma: no cover - optional model errors
        return None
