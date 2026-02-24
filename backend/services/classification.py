from functools import lru_cache
from typing import Dict, List, Optional
import logging
import os


DEFAULT_LABELS = [
    "Fiber Issue",
    "PEO TV Issue",
    "Billing",
    "Complaint",
    "New Connection",
    "Other",
]


def _parse_labels() -> List[str]:
    raw = os.getenv("INTENT_LABELS", "")
    labels = [label.strip() for label in raw.split(",") if label.strip()]
    return labels or DEFAULT_LABELS


def _normalize_label(label: str) -> str:
    normalized = label.replace("_", " ").replace("-", " ").strip()
    if not normalized:
        return normalized
    return " ".join(word.capitalize() for word in normalized.split())


def _canonicalize_label(label: str) -> str:
    return "".join(ch.lower() for ch in label if ch.isalnum())


@lru_cache(maxsize=1)
def _get_classifier():
    model_path = os.getenv("INTENT_MODEL_PATH")
    model_name = os.getenv("INTENT_MODEL_NAME")
    if not model_path and not model_name:
        return None, None

    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    except Exception as exc:  # pragma: no cover - optional dependency
        logging.warning("Transformers not available for intent classification: %s", exc)
        return None, None

    model_source = model_path or model_name
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_source)
        model = AutoModelForSequenceClassification.from_pretrained(model_source)
        clf = pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            top_k=None,
            function_to_apply="softmax",
        )
        return clf, model_source
    except Exception as exc:  # pragma: no cover - model load errors
        logging.warning("Failed to load intent model '%s': %s", model_source, exc)
        return None, None


def predict_intent(text: str) -> Dict:
    labels = _parse_labels()
    if not text:
        return {
            "label": "Other",
            "confidence": 0.0,
            "scores": {label: 0.0 for label in labels},
            "model": "unavailable",
        }

    classifier, model_source = _get_classifier()
    if classifier is None:
        return {
            "label": "Other",
            "confidence": 0.0,
            "scores": {label: 0.0 for label in labels},
            "model": "unavailable",
        }

    results = classifier(text, truncation=True)
    scores_list = results[0] if results and isinstance(results[0], list) else results

    scores: Dict[str, float] = {label: 0.0 for label in labels}
    canonical_to_label = {_canonicalize_label(label): label for label in labels}
    for item in scores_list:
        raw_label = item.get("label", "Other")
        canonical = _canonicalize_label(raw_label)
        mapped_label = canonical_to_label.get(canonical)
        if not mapped_label:
            mapped_label = _normalize_label(raw_label)
            scores.setdefault(mapped_label, 0.0)
        scores[mapped_label] = float(item.get("score", 0.0))

    valid_scores = {label: scores.get(label, 0.0) for label in labels}
    if valid_scores:
        best_label = max(valid_scores, key=valid_scores.get)
        confidence = valid_scores.get(best_label, 0.0)
    else:
        best_label = "Other"
        confidence = scores.get("Other", 0.0)

    return {
        "label": best_label,
        "confidence": confidence,
        "scores": scores,
        "model": model_source,
    }
