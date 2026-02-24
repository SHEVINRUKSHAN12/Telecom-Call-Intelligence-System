# Telecom Call Analysis System — Project Logbook Summary

## Introduction and Project Motivation

The Telecom Call Analysis System was developed to address a critical need in the telecommunications industry: the automated analysis of customer service call recordings. In a typical telecom call center, thousands of calls are handled daily, and manually reviewing each call for quality assurance, intent classification, and sentiment tracking is impractical and resource-intensive. This project aims to build an intelligent, AI-powered web application that can automatically process call recordings by identifying individual speakers, transcribing their speech, classifying the purpose of the call, and storing the results in a searchable database for further analysis.

The system is designed specifically for the Sri Lankan telecom context, supporting both Sinhala and English languages — the two primary languages used in customer service interactions. By automating the analysis pipeline, telecom operators can gain real-time insights into call volume, customer intent distribution, and service quality without manual intervention.

---

## System Architecture and Design Decisions

The application follows a modern full-stack architecture with a clear separation between the frontend (client-side) and backend (server-side). The frontend is a single-page application built with React, while the backend is a RESTful API built with Python's FastAPI framework. Communication between the two happens over standard HTTP requests.

The system integrates with several cloud services and machine learning components. Google Cloud Platform was chosen as the primary cloud provider due to its industry-leading Speech-to-Text capabilities, particularly its support for Sinhala language transcription. MongoDB Atlas was selected as the database because its document-based storage model naturally fits the structure of call analysis records, where each call has nested data such as speaker segments, transcripts, and classification results.

---

## Backend Development

### Framework and Server Setup

The backend was built using FastAPI, a modern Python web framework known for its high performance and automatic API documentation generation. The server runs on Uvicorn, an ASGI (Asynchronous Server Gateway Interface) web server that supports concurrent request handling. We used python-dotenv to manage environment variables such as API keys, database connection strings, and model paths, keeping sensitive configuration separate from the codebase.

CORS (Cross-Origin Resource Sharing) middleware was configured to allow the frontend application to communicate with the backend API. The backend exposes five REST API endpoints: a POST endpoint for uploading and analyzing calls, two GET endpoints for retrieving call lists and individual call details, a GET endpoint for analytics data, and a health check endpoint.

### Google Cloud Storage Integration

When a user uploads an audio file, the backend first stores the file in a Google Cloud Storage (GCS) bucket named "telecom-calls". We chose GCS because Google's Speech-to-Text API can directly access files stored in GCS, which eliminates the need to stream large audio files during transcription. The storage service was implemented using the google-cloud-storage Python library, which provides authenticated access to the bucket using a service account credentials JSON file.

### Speech-to-Text and Speaker Diarization

The core transcription functionality uses Google Cloud's Speech-to-Text API. This service was selected because it is one of the few commercial APIs that supports Sinhala language (si-LK) transcription with reasonable accuracy. The API was configured with speaker diarization enabled, which means it can distinguish between two speakers in a call — typically the customer and the agent. The primary language was set to Sinhala (si-LK) with English (en-US) as an alternative language, allowing the system to handle bilingual conversations common in Sri Lankan call centers.

The diarization feature outputs speaker-labeled transcript segments, where each segment includes the speaker tag (Speaker 1 or Speaker 2), the transcribed text, and the timestamp. These segments are stored as part of the call record and displayed in the frontend as an interactive conversation timeline.

### Language Detection

Google Cloud's Translation API is optionally used to detect the language of the transcribed text. This helps in categorizing calls by language and can be enabled or disabled through the ENABLE_LANGUAGE_DETECTION environment variable.

### MongoDB Atlas Database

All call analysis results are stored in MongoDB Atlas, a cloud-hosted NoSQL database. We used the Motor library, which is an asynchronous MongoDB driver for Python, allowing the FastAPI backend to perform non-blocking database operations. The database is named "telecom_call_analysis" and uses a single collection called "calls" where each document represents one analyzed call.

Each call document contains the following fields: a unique identifier, the original filename, the GCS URI where the audio is stored, the full transcript, speaker-segmented conversation data, the classified intent category with confidence score, sentiment analysis results, language information, and timestamps. MongoDB indexes were created on the category and timestamp fields to optimize query performance for filtering and sorting operations.

The connection to MongoDB Atlas uses a connection string with SRV records (mongodb+srv://), which provides automatic DNS-based service discovery and TLS encryption for secure data transmission.

---

## Machine Learning: Intent Classification Model

### Model Selection and Architecture

For intent classification, we chose the XLM-RoBERTa model (Cross-lingual Language Model - Robustly Optimized BERT Approach). This is a multilingual transformer model developed by Facebook AI Research that has been pre-trained on 100 languages, including Sinhala and English. We selected this model specifically because our application needs to classify call intents from text that may be in Sinhala, English, or a mix of both languages.

The base model (xlm-roberta-base) was fine-tuned for sequence classification on our custom dataset. The model architecture consists of a transformer encoder with 12 attention layers, followed by a classification head that maps the encoded representation to one of six intent categories.

### Training Dataset

We created a custom training dataset of 1,200 labeled samples (200 per category) with text in both Sinhala and English. The six intent categories were designed to cover the most common types of telecom customer service inquiries:

1. **Billing** — Calls related to bill payments, charges, and account balance inquiries.
2. **Complaint** — Calls where customers report service issues, poor quality, or file formal complaints.
3. **Fiber** — Calls about fiber optic internet service, installation, speed issues, and technical support.
4. **New_Connection** — Calls requesting new service connections, plan activations, or new subscriptions.
5. **Other** — General inquiries that do not fit into the above categories.
6. **PEO_TV** — Calls related to PEO TV (an IPTV service), including channel issues, set-top box problems, and subscription inquiries.

The dataset was split into 80% training (960 samples) and 20% validation (240 samples).

### Training Process

The model was trained using the HuggingFace Transformers library with PyTorch as the backend computation engine. The training script (train_model.py) performs the following steps: loads the dataset from a JSON file, tokenizes the text using the XLM-RoBERTa tokenizer, fine-tunes the model using the Trainer API with appropriate hyperparameters (learning rate, batch size, number of epochs), evaluates the model on the validation set, and saves the trained model weights to disk.

The trained model files are stored in the backend/models/intent_model/ directory, which includes the model weights (model.safetensors), the tokenizer configuration, and a label mapping file that maps numerical IDs to human-readable category names.

### Inference

During inference, when a call is analyzed, the transcribed text is passed to the classification service. The service loads the trained model, tokenizes the input text, and runs a forward pass through the model. The output is a probability distribution over the six categories, from which we extract the predicted category and its confidence score. This information is stored alongside the transcript in MongoDB and displayed to the user in the frontend.

---

## Frontend Development

### Technology Stack

The frontend was built using React 19, a popular JavaScript library for building user interfaces. We used Vite 7 as the build tool and development server, chosen for its extremely fast hot module replacement (HMR) and efficient bundling. Styling was done entirely with vanilla CSS using CSS custom properties (variables) for consistent theming — no CSS frameworks like Tailwind or Bootstrap were used, giving us full control over the design.

### Design System

We established a comprehensive design system with a dark, premium aesthetic. The color palette uses deep navy and slate backgrounds with glassmorphism effects (semi-transparent panels with backdrop blur). Two Google Fonts were imported: Inter for body text (chosen for its excellent readability at small sizes) and Space Grotesk for headings (chosen for its modern, technical feel).

A key design decision was implementing category color coding — each of the six intent categories has a unique color that is consistent across all components. For example, Billing is shown in blue, Complaints in red/coral, Fiber in purple, New Connection in green, Other in slate, and PEO TV in amber. These colors appear on list item borders, analytics bars, and intent tags, providing immediate visual identification of call categories.

Six CSS animation keyframes were defined for micro-interactions: fadeInUp and fadeIn for entry animations, pulse and shimmer for loading states, spin for the processing spinner, and fillBar for animated progress and chart bars.

### Components

The frontend consists of four main components plus a service layer:

**CallUploader** is the primary interface for uploading audio files. It features a drag-and-drop zone that accepts WAV, MP3, FLAC, OGG, and M4A formats, displayed as interactive format chips. When a file is being processed, the component shows an animated four-stage progress indicator: Uploading, Transcribing, Classifying, and Done, each with its own icon and animation.

**CallList** displays all analyzed calls in a scrollable sidebar list. Each call item shows the filename, a relative timestamp (e.g., "2h ago"), the detected intent category, and a category-colored left border for quick visual identification. Items appear with staggered entry animations for a polished feel.

**CallDetails** provides a comprehensive view of a selected call's analysis results. It features an SVG-based confidence ring that visually represents the model's prediction confidence as a circular progress indicator. The intent category is displayed as a color-coded tag. The speaker timeline shows the conversation with different styling for Agent and Customer speakers. The full transcript is displayed with a one-click copy button.

**AnalyticsPanel** visualizes aggregate data across all calls. It includes a horizontal bar chart showing the distribution of calls by category, where each bar uses its assigned category color and animates from zero to its target width on mount. A daily volume sparkline shows call volume trends over time.

**api.js** is the service layer that handles all HTTP communication with the backend. It dynamically constructs the API base URL using the current hostname, which ensures the application works correctly regardless of whether it is accessed via localhost or a network IP address.

---

## Development Process and Challenges

### Database Setup

We initially set up MongoDB Atlas by creating a cluster on the free tier (M0), configuring network access to allow connections from any IP, and creating a database user with read/write permissions. The connection was tested using a dedicated test script (test_mongo.py) before integrating it into the main application.

### Model Training and Verification

The intent classification model was trained locally on the developer's machine. After training, we verified the model's predictions using a dedicated test script (test_intent.py) that runs sample texts in both Sinhala and English through the model and checks the predicted categories against expected results. The model's environment configuration was updated to point to the correct local model path.

### Frontend Redesign

The frontend underwent a significant redesign to transition from a basic functional interface to a premium, modern design. This involved rewriting all CSS files with the new design system, updating all React components to use category color coding, adding animation effects, and improving the overall user experience with features like relative timestamps, confidence visualizations, and copyable transcripts.

### Google Cloud Configuration

Setting up Google Cloud services required creating a project, enabling billing (free trial with $299 credit), creating a Cloud Storage bucket, enabling three APIs (Speech-to-Text, Cloud Translation, and Cloud Storage), and generating service account credentials. The credentials JSON file was placed in the backend directory and referenced through the .env configuration file.

### Proxy and Networking Issues

During development, we encountered networking challenges due to the development environment using Proxifier and HTTP Proxy Injector for internet access. These tools intercept all network traffic, including requests to localhost, which prevented the frontend from communicating with the backend. This was resolved by binding both servers to all network interfaces (0.0.0.0), using the machine's network IP instead of localhost, dynamically constructing API URLs based on the browser's hostname, and configuring CORS to allow requests from any origin during development.

---

## Technologies and Tools Summary

**Programming Languages:** Python 3.12 (backend, ML), JavaScript/JSX (frontend), CSS (styling), HTML (structure).

**Frontend:** React 19 for UI components, Vite 7 for build tooling, vanilla CSS with custom properties for styling, Google Fonts (Inter, Space Grotesk) for typography.

**Backend:** FastAPI for the REST API framework, Uvicorn for the ASGI web server, Motor for asynchronous MongoDB access, python-dotenv for environment configuration, python-multipart for file upload handling.

**Machine Learning:** HuggingFace Transformers library for model training and inference, PyTorch as the deep learning framework, XLM-RoBERTa (xlm-roberta-base) as the pre-trained multilingual model, custom dataset of 1,200 labeled samples across six categories.

**Cloud Services (Google Cloud Platform):** Cloud Storage for audio file storage, Speech-to-Text API for transcription and speaker diarization, Cloud Translation API for language detection, service account authentication via JSON credentials.

**Database:** MongoDB Atlas (cloud-hosted) with Motor async driver, document-based storage for call analysis records.

**Development Tools:** Visual Studio Code as the IDE, Git for version control, npm for JavaScript package management, pip for Python package management, Vite dev server with hot module replacement.
