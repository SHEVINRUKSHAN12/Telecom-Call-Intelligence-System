from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime


class FileMetadata(BaseModel):
    filename: str
    content_type: Optional[str] = None
    size_bytes: int
    gcs_uri: str
    blob_name: Optional[str] = None


class SpeakerSegment(BaseModel):
    speaker_tag: int
    speaker_label: str
    text: str
    start_time: float
    end_time: float


class IntentPrediction(BaseModel):
    label: str
    confidence: float
    scores: Optional[Dict[str, float]] = None
    model: Optional[str] = None


class SentimentResult(BaseModel):
    label: Optional[str] = None
    score: Optional[float] = None
    model: Optional[str] = None


class TranscriptionMeta(BaseModel):
    pipeline_used: str
    chunk_count: int
    successful_chunk_count: int
    avg_confidence: float
    empty_chunk_ratio: float
    transcript_char_count: int
    detected_speaker_count: int
    quality_passed: bool
    fallback_used: bool = False
    fallback_attempted: bool = False
    diarization_mode: Optional[str] = None


class CallAnalysisResponse(BaseModel):
    id: str
    created_at: datetime
    file: FileMetadata
    detected_language: Optional[str] = None
    duration_seconds: Optional[float] = None
    full_transcript: str
    speaker_segments: List[SpeakerSegment]
    category: IntentPrediction
    sentiment: Optional[SentimentResult] = None
    transcription_meta: Optional[TranscriptionMeta] = None


class CallSummary(BaseModel):
    id: str
    created_at: datetime
    file_name: str
    detected_language: Optional[str] = None
    duration_seconds: Optional[float] = None
    category: IntentPrediction
    sentiment: Optional[SentimentResult] = None
    preview: Optional[str] = None


class CallListResponse(BaseModel):
    total: int
    items: List[CallSummary]


class CategoryCount(BaseModel):
    category: str
    count: int


class DailyCount(BaseModel):
    date: str
    count: int


class AnalyticsResponse(BaseModel):
    total_calls: int
    category_counts: List[CategoryCount]
    daily_counts: List[DailyCount]


class HealthResponse(BaseModel):
    status: str
