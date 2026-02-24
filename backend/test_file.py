"""
Test script to transcribe a specific local audio file with diarization.
"""
import os
from dotenv import load_dotenv
from services.storage import upload_audio_to_gcs
from services.speech_to_text import transcribe_gcs_with_diarization
from services.classification import predict_intent

load_dotenv()

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "./google-credentials.json",
)

file_path = r"C:\Users\ruksh\IT_Projects\Text_to_Speech\backend\example\sample.mp3"

print(f"Testing diarization for: {file_path}")

if not os.path.exists(file_path):
    print("ERROR: File not found. Update the file_path in test_file.py")
    raise SystemExit(1)

with open(file_path, "rb") as audio_file:
    audio_bytes = audio_file.read()

upload = upload_audio_to_gcs(audio_bytes, os.path.basename(file_path), "audio/mpeg")

result = transcribe_gcs_with_diarization(
    gcs_uri=upload["gcs_uri"],
    file_extension=os.path.splitext(file_path)[1].lower(),
)

print("\nTranscript:")
print(result["full_transcript"])

print("\nSegments:")
for seg in result["speaker_segments"]:
    print(f"{seg['speaker_label']}: {seg['text']}")

intent = predict_intent(result["full_transcript"])
print("\nPredicted intent:")
print(intent)
