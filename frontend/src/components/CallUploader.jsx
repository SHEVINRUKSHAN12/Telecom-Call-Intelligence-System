import { useCallback, useEffect, useRef, useState } from 'react';
import { uploadCall } from '../services/api';
import './CallUploader.css';

const supportedTypes = [
  'audio/wav',
  'audio/mp3',
  'audio/mpeg',
  'audio/flac',
  'audio/ogg',
  'audio/m4a',
  'audio/x-m4a',
];

const STAGES = [
  { key: 'upload', label: 'Uploading audio', icon: '⬆' },
  { key: 'transcribe', label: 'Transcribing speech', icon: '🎤' },
  { key: 'classify', label: 'Classifying intent', icon: '🧠' },
  { key: 'done', label: 'Complete', icon: '✓' },
];

function CallUploader({ onComplete, onError }) {
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    if (isLoading) {
      setElapsedTime(0);
      setCurrentStage(0);
      timerRef.current = setInterval(() => {
        setElapsedTime((prev) => prev + 1);
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isLoading]);

  // Advance stages based on elapsed time
  useEffect(() => {
    if (!isLoading) return;
    if (elapsedTime >= 3 && currentStage === 0) setCurrentStage(1);
    if (elapsedTime >= 8 && currentStage === 1) setCurrentStage(2);
  }, [elapsedTime, isLoading, currentStage]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (
        file &&
        (supportedTypes.includes(file.type) || file.name.match(/\.(wav|mp3|flac|ogg|m4a)$/i))
      ) {
        setSelectedFile(file);
      } else {
        onError?.('Please upload a supported audio file (WAV, MP3, FLAC, OGG, M4A).');
      }
    },
    [onError]
  );

  const handleFileSelect = useCallback((e) => {
    const file = e.target.files[0];
    if (file) setSelectedFile(file);
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsLoading(true);
    setUploadProgress(5);

    const progressInterval = setInterval(() => {
      setUploadProgress((prev) => Math.min(prev + 5, 92));
    }, 800);

    try {
      const result = await uploadCall(selectedFile);
      setUploadProgress(100);
      setCurrentStage(3);
      setTimeout(() => onComplete?.(result), 600);
    } catch (error) {
      onError?.(error.message);
    } finally {
      clearInterval(progressInterval);
      setTimeout(() => {
        setIsLoading(false);
        setUploadProgress(0);
        setSelectedFile(null);
        setCurrentStage(0);
      }, 800);
    }
  };

  const removeFile = () => setSelectedFile(null);

  return (
    <div className="call-uploader">
      <div className="uploader-header">
        <div>
          <p className="uploader-eyebrow">New Analysis</p>
          <h3>Upload Call Recording</h3>
          <p className="uploader-subtitle">
            AI-powered diarization, transcription & intent classification
          </p>
        </div>
        <div className="uploader-badge">
          <span className="lang-tag">SI</span>
          <span className="lang-divider">+</span>
          <span className="lang-tag">EN</span>
        </div>
      </div>

      <div
        className={`drop-zone ${isDragging ? 'dragging' : ''} ${selectedFile ? 'has-file' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {!selectedFile ? (
          <>
            <div className="drop-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p className="drop-text">Drop your audio file here</p>
            <p className="drop-hint">or click to browse files</p>
            <div className="supported-formats">
              {['WAV', 'MP3', 'FLAC', 'OGG', 'M4A'].map((fmt) => (
                <span key={fmt} className="format-chip">{fmt}</span>
              ))}
            </div>
            <input
              type="file"
              accept=".wav,.mp3,.flac,.ogg,.m4a,audio/*"
              onChange={handleFileSelect}
              className="file-input"
            />
          </>
        ) : (
          <div className="selected-file">
            <div className="file-info">
              <div className="file-icon-wrapper">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M9 18V5l12-2v13" />
                  <circle cx="6" cy="18" r="3" />
                  <circle cx="18" cy="16" r="3" />
                </svg>
              </div>
              <div className="file-details">
                <span className="file-name">{selectedFile.name}</span>
                <span className="file-size">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</span>
              </div>
            </div>
            <button className="remove-file" onClick={removeFile} disabled={isLoading}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="progress-container">
          <div className="progress-stages">
            {STAGES.map((stage, i) => (
              <div
                key={stage.key}
                className={`stage ${i < currentStage ? 'done' : ''} ${i === currentStage ? 'active' : ''}`}
              >
                <span className="stage-icon">{stage.icon}</span>
                <span className="stage-label">{stage.label}</span>
              </div>
            ))}
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${uploadProgress}%` }}></div>
          </div>
          <div className="progress-footer">
            <span className="progress-percent">{uploadProgress}%</span>
            <span className="elapsed-time">{formatTime(elapsedTime)}</span>
          </div>
        </div>
      )}

      <button className="upload-button" onClick={handleUpload} disabled={!selectedFile || isLoading}>
        {isLoading ? (
          <>
            <span className="btn-spinner"></span>
            Analyzing...
          </>
        ) : (
          'Analyze Call'
        )}
      </button>
    </div>
  );
}

export default CallUploader;
