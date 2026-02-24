from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(mongo_uri)
    return _client


def get_database():
    client = get_client()
    db_name = os.getenv("MONGODB_DB", "telecom_call_analysis")
    return client[db_name]


def get_collection():
    db = get_database()
    collection_name = os.getenv("MONGODB_COLLECTION", "calls")
    return db[collection_name]


async def init_indexes():
    collection = get_collection()
    await collection.create_index("created_at")
    await collection.create_index("category.label")
    await collection.create_index("detected_language")
    await collection.create_index(
        [("full_transcript", "text"), ("speaker_segments.text", "text")],
        name="transcript_text_index",
        default_language="none",
    )
