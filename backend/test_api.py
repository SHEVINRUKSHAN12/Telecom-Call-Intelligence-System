"""
Quick diagnostic script for Google Cloud Speech-to-Text, Storage, and the SQLite backend.
"""
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
ENV_PATH = BACKEND_DIR / ".env"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(ENV_PATH, override=True)

credentials_path = Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./google-credentials.json"))
if not credentials_path.is_absolute():
    credentials_path = (BACKEND_DIR / credentials_path).resolve()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)

from backend.services.mongodb import get_db_path, init_db


def print_section(title: str) -> None:
    print("\n" + "=" * 50)
    print(title)


def calls_table_exists(db_path: Path) -> bool:
    if not db_path.exists():
        return False

    connection = sqlite3.connect(str(db_path))
    try:
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("calls",),
        )
        return cursor.fetchone() is not None
    finally:
        connection.close()


def run_speech_check() -> None:
    print("Testing Google Cloud Speech-to-Text API...")
    print(f"Credentials file: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
    print(f"Credentials file exists: {'yes' if credentials_path.exists() else 'no'}")

    try:
        from google.cloud import speech

        client = speech.SpeechClient()
        _ = client
        print("OK: Speech client created")
    except Exception as exc:
        print(f"ERROR: Speech client failed: {exc}")


def run_storage_check() -> None:
    print_section("Testing Google Cloud Storage API...")

    try:
        from google.cloud import storage

        client = storage.Client()
        bucket_name = os.getenv("GCS_BUCKET")
        if bucket_name:
            _ = client.bucket(bucket_name)
            print(f"OK: Storage client ready for bucket: {bucket_name}")
        else:
            print("WARN: GCS_BUCKET not set. Skipping bucket check.")
    except Exception as exc:
        print(f"ERROR: Storage client failed: {exc}")


def run_sqlite_check() -> None:
    print_section("SQLite backend check...")

    configured_path = (os.getenv("SQLITE_PATH") or "").strip() or "<default ./data/calls.db>"
    db_path = get_db_path()
    db_exists_before = db_path.exists()
    calls_table_before = calls_table_exists(db_path)

    print(f"Loaded env file: {ENV_PATH}")
    print(f"Configured SQLITE_PATH: {configured_path}")
    print(f"Resolved SQLite DB path: {db_path}")
    print(f"SQLite DB file exists: {'yes' if db_exists_before else 'no'}")
    print(f"'calls' table exists before init: {'yes' if calls_table_before else 'no'}")

    if not db_exists_before or not calls_table_before:
        print("Initializing SQLite DB via the current backend service layer...")
        try:
            asyncio.run(init_db())
            print("OK: SQLite initialization completed")
        except Exception as exc:
            print(f"ERROR: SQLite initialization failed: {exc}")
            return
    else:
        print("OK: SQLite DB already initialized")

    db_exists_after = db_path.exists()
    calls_table_after = calls_table_exists(db_path)

    print(f"SQLite DB file exists after init: {'yes' if db_exists_after else 'no'}")
    print(f"'calls' table exists after init: {'yes' if calls_table_after else 'no'}")


def main() -> None:
    run_speech_check()
    run_storage_check()
    run_sqlite_check()


if __name__ == "__main__":
    main()
