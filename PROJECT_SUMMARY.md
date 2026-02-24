# Telecom Call Analysis — Full Project Summary

## Overview

A full-stack web application that analyzes telecom call recordings using AI. Users upload audio files, and the system automatically **diarizes speakers**, **transcribes speech**, **classifies intent**, and **analyzes sentiment** — storing all results in MongoDB.

---

## Architecture

```
┌──────────────┐     HTTP/REST     ┌──────────────────┐
│  React App   │ ──────────────→   │  FastAPI Backend  │
│  (Vite Dev)  │                   │  (Uvicorn)        │
└──────────────┘                   └────────┬─────────┘
                                            │
                    ┌───────────────────────┬┼──────────────────────┐
                    │                       ││                      │
              ┌─────▼──────┐    ┌───────────▼▼───────┐    ┌────────▼────────┐
              │  Google     │    │  Google Speech-to- │    │  MongoDB Atlas  │
              │  Cloud      │    │  Text API          │    │  (NoSQL DB)     │
              │  Storage    │    │  + Translation API │    │                 │
              └────────────┘    └────────────────────┘    └─────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  XLM-RoBERTa    │
                                   │  Intent Model   │
                                   │  (Local)        │
                                   └─────────────────┘
```

---

## Tech Stack

### Frontend
| Tool | Version | Purpose |
|------|---------|---------|
| React | 19.2.0 | UI framework |
| Vite | 7.2.4 | Build tool & dev server |
| Vanilla CSS | — | Styling (glassmorphism, animations, CSS variables) |
| Google Fonts | — | Inter (body) + Space Grotesk (headings) |

### Backend
| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12 | Runtime |
| FastAPI | latest | REST API framework |
| Uvicorn | latest | ASGI web server |
| Motor | latest | Async MongoDB driver |
| Transformers | latest | HuggingFace ML model inference |
| PyTorch | latest | ML tensor computation engine |
| python-dotenv | latest | Environment variable management |
| python-multipart | latest | File upload handling |

### Cloud Services (Google Cloud Platform)
| Service | Purpose | Free Tier |
|---------|---------|-----------|
| Cloud Storage (GCS) | Store uploaded audio files | 5 GB/month |
| Speech-to-Text API | Transcription + speaker diarization | 60 min/month |
| Cloud Translation API | Language detection (Sinhala/English) | 500K chars/month |

### Database
| Service | Purpose |
|---------|---------|
| MongoDB Atlas | Cloud-hosted NoSQL database for call records |
| Bucket: `telecom-calls` | GCS bucket for audio file storage |

### Machine Learning Model
| Component | Details |
|-----------|---------|
| Base Model | `xlm-roberta-base` (XLM-RoBERTa, multilingual transformer) |
| Task | Sequence classification (intent recognition) |
| Categories | Billing, Complaint, Fiber, New_Connection, Other, PEO_TV |
| Training Data | 1,200 samples (960 train / 240 validation) |
| Languages Supported | Sinhala (si-LK) + English (en-US) |
| Model Location | `backend/models/intent_model/` |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/calls` | Upload & analyze a call recording |
| `GET` | `/api/calls` | List all calls (supports `?q=` search & `?category=` filter) |
| `GET` | `/api/calls/{id}` | Get detailed call analysis by ID |
| `GET` | `/api/analytics` | Get category counts & daily call volume |
| `GET` | `/health` | Server health check |

---

## Data Flow (Upload → Analysis Pipeline)

1. **User uploads** audio file via drag-and-drop (WAV, MP3, FLAC, OGG, M4A)
2. **GCS Upload** — file uploaded to `telecom-calls` bucket on Google Cloud Storage
3. **Speech-to-Text** — Google STT transcribes audio with speaker diarization (2 speakers)
4. **Language Detection** — Google Translation API identifies Sinhala or English
5. **Intent Classification** — Local XLM-RoBERTa model predicts category with confidence score
6. **Sentiment Analysis** — (optional, configurable) analyzes overall call sentiment
7. **MongoDB Storage** — complete record stored: transcript, speaker segments, category, sentiment, metadata
8. **API Response** — frontend receives and renders all analysis results

---

## Frontend Components

| Component | Function |
|-----------|----------|
| `App.jsx` | Main shell — state management, category filters, API orchestration |
| `CallUploader.jsx` | Drag-and-drop audio upload with 4-stage animated processing indicator |
| `CallList.jsx` | Scrollable call list with category-colored left borders, relative timestamps |
| `CallDetails.jsx` | Full call view — SVG confidence ring, speaker timeline, copyable transcript |
| `AnalyticsPanel.jsx` | Category distribution bar chart + daily volume sparkline |
| `api.js` | API service layer — fetch wrappers for all backend endpoints |

### Design Features
- Dark glassmorphism theme with backdrop blur
- Category color coding (6 colors for 6 intent categories)
- Animated progress stages during analysis
- Micro-animations (hover, entry, loading states)
- Responsive layout for mobile/tablet/desktop

---

## Configuration Files

| File | Purpose |
|------|---------|
| `backend/.env` | Environment config — API keys, MongoDB URI, model path, GCS bucket |
| `backend/google-credentials.json` | Google Cloud service account credentials |
| `backend/requirements.txt` | Python dependencies |
| `frontend/package.json` | Node.js dependencies |

### Environment Variables (`.env`)
```env
GOOGLE_APPLICATION_CREDENTIALS=./google-credentials.json
GCS_BUCKET=telecom-calls
MONGODB_URI=mongodb+srv://...
MONGODB_DB=telecom_call_analysis
MONGODB_COLLECTION=calls
PRIMARY_LANGUAGE_CODE=si-LK
ALT_LANGUAGE_CODES=en-US
DIARIZATION_SPEAKER_COUNT=2
INTENT_MODEL_PATH=<absolute-path>/backend/models/intent_model
INTENT_LABELS=Billing,Complaint,Fiber,New_Connection,Other,PEO_TV
```

---

## Project Structure

```
Text_to_Speech/
├── backend/
│   ├── main.py                     # FastAPI app entry point + CORS config
│   ├── routes/
│   │   └── calls.py                # All API endpoint handlers
│   ├── services/
│   │   ├── mongodb.py              # MongoDB connection (Motor async driver)
│   │   ├── classification.py       # XLM-RoBERTa intent prediction
│   │   ├── storage.py              # Google Cloud Storage upload
│   │   ├── stt.py                  # Google Speech-to-Text + diarization
│   │   └── sentiment.py            # Sentiment analysis service
│   ├── models/
│   │   ├── schemas.py              # Pydantic response models
│   │   └── intent_model/           # Trained XLM-RoBERTa model files
│   │       ├── model.safetensors   # Model weights
│   │       ├── config.json         # Model configuration
│   │       ├── tokenizer.json      # Tokenizer
│   │       └── label_mapping.json  # Label ↔ ID mapping
│   ├── data/
│   │   └── dataset.json            # Training dataset (1,200 samples)
│   ├── train_model.py              # Model training script
│   ├── test_intent.py              # Model verification tests
│   ├── test_mongo.py               # MongoDB connection test
│   ├── test_api.py                 # API configuration test
│   ├── .env                        # Environment variables
│   ├── google-credentials.json     # GCP service account key
│   └── requirements.txt            # Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Main application + state management
│   │   ├── App.css                 # Layout styles
│   │   ├── index.css               # Design system (tokens, fonts, animations)
│   │   ├── services/
│   │   │   └── api.js              # Backend API client
│   │   └── components/
│   │       ├── CallUploader.jsx    # Audio file upload component
│   │       ├── CallUploader.css
│   │       ├── CallList.jsx        # Call list sidebar
│   │       ├── CallList.css
│   │       ├── CallDetails.jsx     # Detailed call view
│   │       ├── CallDetails.css
│   │       ├── AnalyticsPanel.jsx  # Analytics dashboard
│   │       └── AnalyticsPanel.css
│   ├── package.json                # Node.js dependencies
│   └── vite.config.js              # Vite configuration
```

---

## How to Run

### Backend
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev -- --host
```

### Train Model (if needed)
```bash
cd backend
python train_model.py
```
