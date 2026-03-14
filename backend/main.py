from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import os
import sys
from pathlib import Path

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env", override=True)

# Ensure package-qualified imports work whether the app is launched
# from the repo root or from the backend folder.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Resolve repo-local credential paths against backend/.
credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if credentials and not os.path.isabs(credentials):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str((BASE_DIR / credentials).resolve())

logging.basicConfig(level=logging.INFO)

# Import routes
from backend.routes.calls import router as calls_router
from backend.services.mongodb import init_db

app = FastAPI(
    title="Telecom Call Analysis API",
    description="Upload call audio, diarize speakers, transcribe, classify intent, and store results",
    version="2.0.0",
)

# CORS configuration - allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(calls_router, prefix="/api", tags=["Calls"])


@app.on_event("startup")
async def startup_event():
    await init_db()

@app.get("/")
async def root():
    return {"message": "Telecom Call Analysis API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
