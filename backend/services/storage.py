from google.cloud import storage
from google.auth.exceptions import DefaultCredentialsError
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
import os
import uuid


def _credentials_error_message() -> str:
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds:
        return (
            "Google Cloud credentials are invalid or not readable. "
            f"Check GOOGLE_APPLICATION_CREDENTIALS='{creds}'."
        )
    return (
        "Google Cloud credentials are not configured. "
        "Set GOOGLE_APPLICATION_CREDENTIALS to a valid service account JSON path."
    )


def upload_audio_to_gcs(audio_bytes: bytes, filename: str, content_type: Optional[str]) -> dict:
    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise ValueError("GCS_BUCKET must be set in environment variables")

    try:
        client = storage.Client()
    except (DefaultCredentialsError, FileNotFoundError) as exc:
        raise RuntimeError(_credentials_error_message()) from exc

    bucket = client.bucket(bucket_name)

    safe_name = filename.replace(" ", "_")
    blob_name = f"calls/{datetime.utcnow().strftime('%Y/%m/%d')}/{uuid.uuid4()}_{safe_name}"
    blob = bucket.blob(blob_name)
    blob.metadata = {
        "original_filename": filename,
        "uploaded_at": datetime.utcnow().isoformat(),
    }

    if content_type:
        blob.upload_from_string(audio_bytes, content_type=content_type)
    else:
        blob.upload_from_string(audio_bytes)

    return {
        "gcs_uri": f"gs://{bucket_name}/{blob_name}",
        "blob_name": blob_name,
        "bucket": bucket_name,
    }


def generate_signed_audio_url(gcs_uri: str, expires_minutes: int = 60) -> str:
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        raise ValueError("Invalid GCS URI")

    parsed = urlparse(gcs_uri)
    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")
    if not bucket_name or not blob_name:
        raise ValueError("Invalid GCS URI")

    try:
        client = storage.Client()
    except (DefaultCredentialsError, FileNotFoundError) as exc:
        raise RuntimeError(_credentials_error_message()) from exc

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=datetime.utcnow() + timedelta(minutes=expires_minutes),
            method="GET",
        )
    except Exception as exc:
        raise RuntimeError(f"Could not generate signed audio URL: {exc}") from exc
