# 📞 Telecom Call Intelligence System

> AI-powered telecom call analysis platform that converts Sinhala/English call recordings into structured, searchable intelligence with speaker diarization, intent classification, and sentiment analysis.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green?logo=fastapi)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?logo=mongodb)
![Google Cloud](https://img.shields.io/badge/Google%20Cloud-STT-4285F4?logo=googlecloud)

---

## 📋 Table of Contents

- [About the Project](#-about-the-project)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Running the Application](#-running-the-application)
- [API Endpoints](#-api-endpoints)
- [Frontend Components](#-frontend-components)
- [ML Models](#-ml-models)
- [Team Members](#-team-members)

---

## 🎯 About the Project

The **Telecom Call Intelligence System** is designed for Sri Lankan telecom companies to automatically analyze customer service call recordings. It processes audio files, separates speakers (agent vs. customer), transcribes the conversation in Sinhala and English, classifies the call intent (e.g., billing inquiry, fiber issue, complaint), and performs sentiment analysis — all through a modern web dashboard.

### Problem Statement

Telecom companies receive thousands of customer calls daily. Manually reviewing and categorizing these calls is time-consuming and error-prone. This system automates the entire process using AI/ML.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🎙️ **Speech-to-Text** | Converts audio to text using Google Cloud Speech-to-Text API |
| 🗣️ **Speaker Diarization** | Separates and labels Agent vs. Customer speakers |
| 🌐 **Multilingual Support** | Supports Sinhala (`si-LK`) and English (`en-US`) transcription |
| 🔍 **Intent Classification** | Classifies calls into categories using fine-tuned XLM-RoBERTa model |
| 😊 **Sentiment Analysis** | Detects positive/neutral/negative sentiment using XLM-RoBERTa |
| 📊 **Analytics Dashboard** | Visual analytics with category distribution and call statistics |
| 🔎 **Search & Filter** | Search transcripts by keyword and filter by category |
| ☁️ **Cloud Storage** | Audio files stored in Google Cloud Storage |
| 📱 **Responsive UI** | Modern React dashboard with real-time updates |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │  Upload   │ │Call List │ │  Details  │ │  Analytics    │  │
│  │Component  │ │Component │ │Component │ │  Dashboard    │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP REST API
┌────────────────────────▼────────────────────────────────────┐
│                  Backend (FastAPI + Python)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   API Routes (/api)                   │   │
│  │  POST /analyze  GET /calls  GET /calls/{id}          │   │
│  │  GET /calls/{id}/audio  GET /analytics               │   │
│  └──────────────────────────┬───────────────────────────┘   │
│                              │                               │
│  ┌──────────┐ ┌──────────┐ ┌▼─────────┐ ┌──────────────┐   │
│  │  Audio   │ │Google STT│ │  Intent  │ │  Sentiment   │   │
│  │  Utils   │ │ Service  │ │Classifier│ │  Analyzer    │   │
│  │(chunking)│ │(diarize) │ │(XLM-R)   │ │(XLM-R)      │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│                              │                               │
│  ┌──────────────────────────▼───────────────────────────┐   │
│  │           MongoDB (Atlas) + Google Cloud Storage      │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **Python 3.12** | Core programming language |
| **FastAPI** | REST API framework |
| **Uvicorn** | ASGI server |
| **Google Cloud Speech-to-Text** | Audio transcription with speaker diarization |
| **Google Cloud Storage** | Cloud audio file storage |
| **Google Cloud Translation** | Language detection |
| **MongoDB (Motor)** | Async database for storing call records |
| **Transformers (Hugging Face)** | ML model framework for intent & sentiment |
| **XLM-RoBERTa** | Fine-tuned multilingual model for intent classification |
| **PyDub** | Audio processing and chunking |
| **scikit-learn** | ML utilities |
| **PyTorch** | Deep learning framework |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **React 19** | UI library |
| **Vite 7** | Build tool and dev server |
| **CSS3** | Custom styling with CSS variables |
| **ESLint** | Code linting |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| **MongoDB Atlas** | Cloud-hosted database |
| **Google Cloud Platform** | STT, Storage, Translation APIs |
| **Git / GitHub** | Version control |

---

## 📁 Project Structure

```
Speech_to_Text/
│
├── backend/                          # FastAPI Backend
│   ├── main.py                       # App entry point & CORS config
│   ├── requirements.txt              # Python dependencies
│   ├── .env                          # Environment variables (API keys)
│   ├── .env.example                  # Template for environment variables
│   ├── google-credentials.json       # Google Cloud service account key
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   └── calls.py                  # All API route handlers
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audio_utils.py            # Audio chunking & preprocessing
│   │   ├── speech_to_text.py         # Google Cloud STT integration
│   │   ├── classification.py         # Intent classification (XLM-RoBERTa)
│   │   ├── sentiment.py              # Sentiment analysis
│   │   ├── mongodb.py                # MongoDB connection & queries
│   │   ├── storage.py                # Google Cloud Storage operations
│   │   └── translation.py            # Language detection
│   │
│   ├── models/
│   │   ├── schemas.py                # Pydantic data models
│   │   └── intent_model/             # Fine-tuned intent classification model
│   │       ├── config.json           # Model configuration
│   │       ├── label_mapping.json    # Intent label mappings
│   │       ├── tokenizer.json        # Tokenizer data
│   │       └── tokenizer_config.json # Tokenizer settings
│   │
│   ├── ml/                           # ML training resources
│   │   ├── README.md
│   │   ├── data/                     # Training data directories
│   │   ├── scripts/                  # Training scripts
│   │   └── trained_models/           # Exported models
│   │
│   ├── data/
│   │   └── dataset.json              # Intent classification training dataset
│   │
│   ├── train_model.py                # Model training script
│   ├── backfill_sentiment.py         # Backfill sentiment for existing records
│   ├── reclassify_all.py             # Re-classify all calls
│   ├── rebuild_transcripts.py        # Rebuild transcripts utility
│   └── test_*.py                     # Test scripts
│
├── frontend/                         # React Frontend
│   ├── index.html                    # HTML entry point
│   ├── package.json                  # Node.js dependencies
│   ├── vite.config.js                # Vite configuration
│   ├── eslint.config.js              # ESLint configuration
│   │
│   ├── src/
│   │   ├── main.jsx                  # React entry point
│   │   ├── App.jsx                   # Main application component
│   │   ├── App.css                   # Global application styles
│   │   ├── index.css                 # Base styles & CSS variables
│   │   │
│   │   ├── components/
│   │   │   ├── CallUploader.jsx      # Audio file upload component
│   │   │   ├── CallUploader.css
│   │   │   ├── CallList.jsx          # Call history list component
│   │   │   ├── CallList.css
│   │   │   ├── CallDetails.jsx       # Call detail view with transcript
│   │   │   ├── CallDetails.css
│   │   │   ├── AnalyticsPanel.jsx    # Analytics dashboard component
│   │   │   └── AnalyticsPanel.css
│   │   │
│   │   └── services/
│   │       └── api.js                # API service layer
│   │
│   └── public/
│       └── vite.svg                  # Vite logo
│
├── .gitignore                        # Git ignore rules
├── PROJECT_SUMMARY.md                # Project documentation
└── LOGBOOK_SUMMARY.md                # Development logbook
```

---

## 📌 Prerequisites

Before you begin, make sure you have the following installed:

| Requirement | Version | Download Link |
|------------|---------|---------------|
| **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
| **MongoDB** | Atlas or Local | [mongodb.com](https://www.mongodb.com/cloud/atlas) |
| **FFmpeg** | Latest | [ffmpeg.org](https://ffmpeg.org/download.html) |
| **Git** | Latest | [git-scm.com](https://git-scm.com/) |

### Google Cloud Setup

You need a **Google Cloud Platform** account with the following APIs enabled:

1. **Cloud Speech-to-Text API**
2. **Cloud Storage API**
3. **Cloud Translation API**

Create a **Service Account** and download the JSON credentials file.

---

## ⚙️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/SHEVINRUKSHAN12/Telecom-Call-Intelligence-System.git
cd Telecom-Call-Intelligence-System
```

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create a virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node.js dependencies
npm install
```

---

## 🔧 Configuration

### Backend Environment Variables

Create a `.env` file in the `backend/` directory (or copy from `.env.example`):

```bash
cp .env.example .env
```

Then edit the `.env` file with your actual values:

```env
# ─── Google Cloud ───────────────────────────────
GOOGLE_APPLICATION_CREDENTIALS=./google-credentials.json
GCS_BUCKET=your_gcs_bucket_name

# ─── MongoDB ────────────────────────────────────
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net
MONGODB_DB=telecom_call_analysis
MONGODB_COLLECTION=calls

# ─── Speech-to-Text Settings ────────────────────
PRIMARY_LANGUAGE_CODE=si-LK
ALT_LANGUAGE_CODES=en-US
DIARIZATION_SPEAKER_COUNT=2
STT_CHUNK_TARGET_SECONDS=22
STT_CHUNK_MAX_SECONDS=25
STT_CHUNK_MIN_SECONDS=20
STT_CHUNK_MIN_SILENCE_MS=700
STT_CHUNK_OVERLAP_SECONDS=1.0
STT_PREPROCESS_ENABLE=true
STT_PREPROCESS_HIGHPASS_HZ=120
STT_PREPROCESS_HEADROOM_DB=1.0

# ─── Hybrid Fallback ────────────────────────────
STT_ENABLE_HYBRID_FALLBACK=true
STT_MIN_CONFIDENCE=0.55
STT_MAX_EMPTY_CHUNK_RATIO=0.30
STT_MIN_TRANSCRIPT_CHARS=30

# ─── ML Features ────────────────────────────────
ENABLE_SENTIMENT=true
ENABLE_LANGUAGE_DETECTION=false
INTENT_MODEL_PATH=./models/intent_model
INTENT_LABELS=Fiber Issue,PEO TV Issue,Billing,Complaint,New Connection,Other

# ─── Server ──────────────────────────────────────
HOST=0.0.0.0
PORT=8000
```

### Google Credentials

Place your Google Cloud Service Account JSON key file as:

```
backend/google-credentials.json
```

---

## 🚀 Running the Application

### Start the Backend Server

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at: **http://localhost:8000**

API docs (Swagger UI): **http://localhost:8000/docs**

### Start the Frontend Dev Server

```bash
cd frontend
npm run dev
```

The frontend will be available at: **http://localhost:5173**

### Run Both Together

Open **two terminal windows**:

```bash
# Terminal 1 - Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check — returns API status |
| `GET` | `/health` | Health check endpoint |
| `POST` | `/api/analyze` | Upload and analyze a call recording |
| `GET` | `/api/calls` | List all calls (with search & filter) |
| `GET` | `/api/calls/{id}` | Get detailed call information |
| `GET` | `/api/calls/{id}/audio` | Get signed audio playback URL |
| `GET` | `/api/analytics` | Get aggregated analytics data |

### Upload & Analyze a Call

```bash
curl -X POST "http://localhost:8000/api/analyze" \
  -F "file=@recording.wav"
```

**Supported audio formats:** `.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`

### Search Calls

```bash
# Search by keyword
curl "http://localhost:8000/api/calls?q=billing"

# Filter by category
curl "http://localhost:8000/api/calls?category=Complaint"

# Filter by date range
curl "http://localhost:8000/api/calls?start=2026-01-01&end=2026-02-28"
```

### Get Analytics

```bash
curl "http://localhost:8000/api/analytics"
```

Returns:
```json
{
  "total_calls": 150,
  "category_distribution": {
    "Billing": 45,
    "Complaint": 30,
    "Fiber Issue": 25,
    "New Connection": 20,
    "PEO TV Issue": 15,
    "Other": 15
  },
  "avg_duration_seconds": 245.5
}
```

---

## 🎨 Frontend Components

| Component | File | Description |
|-----------|------|-------------|
| **App** | `App.jsx` | Main application with routing & state management |
| **CallUploader** | `CallUploader.jsx` | Drag-and-drop audio upload with progress |
| **CallList** | `CallList.jsx` | Scrollable list of analyzed calls with search |
| **CallDetails** | `CallDetails.jsx` | Detailed view with transcript, speaker segments, intent & sentiment results |
| **AnalyticsPanel** | `AnalyticsPanel.jsx` | Category distribution chart and statistics |

### Call Categories

| Category | Color | Description |
|----------|-------|-------------|
| 💰 Billing | Blue | Payment and billing inquiries |
| 😤 Complaint | Red | Customer complaints |
| 🌐 Fiber | Purple | Fiber internet issues |
| 📺 PEO TV | Teal | PEO TV service issues |
| 🆕 New Connection | Green | New service requests |
| 📋 Other | Gray | Uncategorized calls |

---

## 🤖 ML Models

### Intent Classification

- **Model:** Fine-tuned **XLM-RoBERTa** (cross-lingual transformer)
- **Training:** Custom dataset of labeled telecom call transcripts
- **Categories:** Fiber Issue, PEO TV Issue, Billing, Complaint, New Connection, Other
- **Location:** `backend/models/intent_model/`

### Sentiment Analysis

- **Model:** `cardiffnlp/twitter-xlm-roberta-base-sentiment`
- **Output:** Positive / Neutral / Negative with confidence score
- **Multilingual:** Supports Sinhala and English text

### Training the Intent Model

```bash
cd backend
python train_model.py
```

Training data is in `backend/data/dataset.json`.

---

## 🔧 Utility Scripts

| Script | Purpose |
|--------|---------|
| `train_model.py` | Train/fine-tune the intent classification model |
| `backfill_sentiment.py` | Add sentiment analysis to existing call records |
| `reclassify_all.py` | Re-run intent classification on all stored calls |
| `rebuild_transcripts.py` | Rebuild transcripts from stored audio |
| `test_api.py` | Test API endpoints |
| `test_intent.py` | Test intent classification |
| `test_mongo.py` | Test MongoDB connection |

---

## ⚠️ Important Notes

1. **Model Weight Files:** The large model weight files (`model.safetensors`, `optimizer.pt`) are **not included** in the repository due to GitHub's 100MB file size limit (each file is 1-2 GB). You need to either:
   - Run `python train_model.py` to train the model locally
   - Or download a pre-trained XLM-RoBERTa model from [Hugging Face](https://huggingface.co/)

2. **Google Credentials:** You need your own Google Cloud service account credentials. The `google-credentials.json` file is not included for security reasons.

3. **MongoDB:** Make sure your MongoDB instance is running and accessible. Update the `MONGODB_URI` in `.env`.

4. **FFmpeg:** Required for audio format conversion. Make sure it's installed and in your system PATH.

---

##  License

This project is developed for academic/research purposes.

---

<p align="center">
  Made with ❤️ for Telecom Intelligence
</p>
