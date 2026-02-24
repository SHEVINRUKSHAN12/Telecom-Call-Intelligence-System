import { useEffect, useState } from 'react';
import { getCategoryColor, getCategoryLabel, formatDuration } from '../App';
import { fetchCallAudioUrl } from '../services/api';
import './CallDetails.css';

const formatDate = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
};

/* ── Confidence Ring (SVG donut) ── */
function ConfidenceRing({ value = 0, size = 52, color }) {
  const radius = (size - 6) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value * circumference);
  const strokeColor = color || 'var(--accent-2)';

  return (
    <svg className="confidence-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(100,130,160,0.12)" strokeWidth="4" />
      <circle
        cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke={strokeColor} strokeWidth="4"
        strokeDasharray={circumference} strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 0.8s ease' }}
      />
      <text
        x={size / 2} y={size / 2}
        textAnchor="middle" dominantBaseline="central"
        fill="var(--text)" fontSize="12" fontWeight="700"
        fontFamily="Space Grotesk, sans-serif"
      >
        {(value * 100).toFixed(0)}%
      </text>
    </svg>
  );
}

/* ── Sentiment helpers ── */
const SENTIMENT_CONFIG = {
  positive: { emoji: '😊', label: 'Positive', color: '#10b981', bg: 'rgba(16, 185, 129, 0.10)', border: 'rgba(16, 185, 129, 0.25)', glow: 'rgba(16, 185, 129, 0.15)' },
  negative: { emoji: '😠', label: 'Negative', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.10)', border: 'rgba(239, 68, 68, 0.25)', glow: 'rgba(239, 68, 68, 0.15)' },
  neutral: { emoji: '😐', label: 'Neutral', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.10)', border: 'rgba(245, 158, 11, 0.25)', glow: 'rgba(245, 158, 11, 0.15)' },
};

function getSentimentConfig(label) {
  if (!label) return null;
  const key = label.toLowerCase().replace(/\s/g, '');
  return SENTIMENT_CONFIG[key] || SENTIMENT_CONFIG.neutral;
}

/* ── Intent Score Bar ── */
function ScoreBar({ label, score, maxScore, color }) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div className="score-bar-row">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="score-bar-value">{(score * 100).toFixed(1)}%</span>
    </div>
  );
}


function CallDetails({ call }) {
  const [copied, setCopied] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const [audioError, setAudioError] = useState('');
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);

  useEffect(() => {
    let active = true;
    const loadAudioUrl = async () => {
      if (!call?.id) {
        setAudioUrl('');
        setAudioError('');
        return;
      }
      try {
        const data = await fetchCallAudioUrl(call.id);
        if (!active) return;
        setAudioUrl(data.url || '');
        setAudioError('');
      } catch (error) {
        if (!active) return;
        setAudioUrl('');
        setAudioError(error.message || 'Audio playback unavailable.');
      }
    };
    loadAudioUrl();
    return () => { active = false; };
  }, [call?.id]);

  if (!call) {
    return (
      <div className="call-details empty">
        <div className="empty-icon">📞</div>
        <h3>Select a call to view insights</h3>
        <p>Upload a recording or pick a recent call to inspect the transcript and predictions.</p>
      </div>
    );
  }

  const speakers = Array.from(
    new Set((call.speaker_segments || []).map((seg) => seg.speaker_label))
  );

  const getSpeakerClass = (seg) => {
    const tag = Number(seg?.speaker_tag || 0);
    if (tag === 1) return 'caller-1';
    if (tag === 2) return 'caller-2';
    return 'speaker-default';
  };

  const callIdSuffix = call.id ? call.id.slice(-6).toUpperCase() : '------';
  const catLabel = call.category?.label;
  const catColor = getCategoryColor(catLabel);
  const catConfidence = call.category?.confidence || 0;
  const intentScores = call.category?.scores || {};
  const maxIntentScore = Math.max(...Object.values(intentScores), 0.01);

  const sentimentData = call.sentiment;
  const sentCfg = getSentimentConfig(sentimentData?.label);

  const handleCopy = () => {
    if (call.full_transcript) {
      navigator.clipboard.writeText(call.full_transcript);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const buildTranscriptContent = () => {
    const fileName = call.file?.filename || 'Untitled Call';
    const date = call.created_at ? new Date(call.created_at).toLocaleString() : 'Unknown';
    const language = call.detected_language || 'Unknown';
    const catLabel = call.category?.label || 'Unknown';
    const sentLabel = call.sentiment?.label || 'N/A';
    let text = `Call Transcript\n${'='.repeat(50)}\n`;
    text += `File: ${fileName}\nDate: ${date}\nLanguage: ${language}\nCategory: ${catLabel}\nSentiment: ${sentLabel}\n\n`;
    const segs = call.speaker_segments || [];
    if (segs.length > 0) {
      text += `Conversation Timeline\n${'-'.repeat(40)}\n`;
      segs.forEach(seg => {
        const start = typeof seg.start_time === 'number' ? seg.start_time.toFixed(1) : '0.0';
        const end = typeof seg.end_time === 'number' ? seg.end_time.toFixed(1) : '0.0';
        text += `[${start}s - ${end}s] ${seg.speaker_label || 'Speaker'}:\n${seg.text}\n\n`;
      });
    }
    text += `\nFull Transcript\n${'-'.repeat(40)}\n${call.full_transcript || 'Not available.'}\n`;
    return text;
  };

  const handleDownloadTxt = () => {
    const content = buildTranscriptContent();
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript_${callIdSuffix}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    setShowDownloadMenu(false);
  };

  const handleDownloadPdf = () => {
    const content = buildTranscriptContent();
    const win = window.open('', '_blank');
    win.document.write(`<!DOCTYPE html><html><head><title>Transcript ${callIdSuffix}</title>
      <style>body{font-family:'Segoe UI',system-ui,sans-serif;padding:40px;color:#222;line-height:1.7;max-width:800px;margin:0 auto}
      h1{font-size:1.4rem;border-bottom:2px solid #333;padding-bottom:8px}h2{font-size:1.1rem;color:#555;margin-top:24px}
      .meta{color:#666;font-size:0.9rem;margin-bottom:20px}.seg{margin:8px 0;padding:8px 12px;background:#f5f5f5;border-radius:6px;border-left:3px solid #3b82f6}
      .seg .label{font-weight:700;color:#3b82f6;font-size:0.85rem}.seg .time{color:#999;font-size:0.75rem}
      .transcript{white-space:pre-wrap;background:#fafafa;padding:16px;border-radius:8px;border:1px solid #eee}</style></head><body>`);
    win.document.write(`<h1>Call Transcript — #${callIdSuffix}</h1>`);
    win.document.write(`<div class="meta">File: ${call.file?.filename || 'Unknown'}<br>Date: ${call.created_at ? new Date(call.created_at).toLocaleString() : 'Unknown'}<br>Language: ${call.detected_language || 'Unknown'}<br>Category: ${call.category?.label || 'Unknown'}<br>Sentiment: ${call.sentiment?.label || 'N/A'}</div>`);
    const segs = call.speaker_segments || [];
    if (segs.length > 0) {
      win.document.write('<h2>Conversation Timeline</h2>');
      segs.forEach(seg => {
        const start = typeof seg.start_time === 'number' ? seg.start_time.toFixed(1) : '0.0';
        const end = typeof seg.end_time === 'number' ? seg.end_time.toFixed(1) : '0.0';
        win.document.write(`<div class="seg"><span class="label">${seg.speaker_label || 'Speaker'}</span> <span class="time">[${start}s — ${end}s]</span><br>${seg.text}</div>`);
      });
    }
    win.document.write(`<h2>Full Transcript</h2><div class="transcript">${call.full_transcript || 'Not available.'}</div>`);
    win.document.write('</body></html>');
    win.document.close();
    setTimeout(() => { win.print(); }, 500);
    setShowDownloadMenu(false);
  };

  /* ── Category color mapping for score bars ── */
  const catBarColors = {
    Billing: 'var(--cat-billing)',
    Complaint: 'var(--cat-complaint)',
    Fiber: 'var(--cat-fiber)',
    New_Connection: 'var(--cat-new-connection)',
    'New Connection': 'var(--cat-new-connection)',
    Other: 'var(--cat-other)',
    PEO_TV: 'var(--cat-peo-tv)',
    'Peo Tv': 'var(--cat-peo-tv)',
  };

  return (
    <div className="call-details animate-fade-in-up">
      {/* ── Header ── */}
      <div className="call-details-header">
        <div>
          <p className="call-id">Call #{callIdSuffix}</p>
          <h2>{call.file?.filename || 'Untitled Call'}</h2>
          <p className="call-date">{formatDate(call.created_at)}</p>
        </div>
      </div>

      {/* ── Quick Stats ── */}
      <div className="call-stats">
        <div className="stat-card">
          <span>Language</span>
          <strong>{call.detected_language || 'Unknown'}</strong>
        </div>
        <div className="stat-card">
          <span>Duration</span>
          <strong>{formatDuration(call.duration_seconds)}</strong>
        </div>
        <div className="stat-card">
          <span>Speakers</span>
          <strong>{speakers.length || '—'}</strong>
        </div>
        <div className="stat-card">
          <span>Storage</span>
          <strong>{call.file?.gcs_uri ? 'GCS' : 'Local'}</strong>
        </div>
      </div>

      {/* ── ML Results: Intent + Sentiment ── */}
      <div className="ml-results-grid">

        {/* ── Intent Classification Card ── */}
        <div className="ml-card intent-card" style={{ '--card-accent': catColor }}>
          <div className="ml-card-header">
            <div className="ml-card-icon">🎯</div>
            <div>
              <h3 className="ml-card-title">Intent Classification</h3>
              <p className="ml-card-subtitle">XLM-RoBERTa prediction</p>
            </div>
          </div>

          <div className="ml-card-result">
            <div className="intent-badge" style={{ '--badge-color': catColor }}>
              {getCategoryLabel(catLabel) || 'Unknown'}
            </div>
            <ConfidenceRing value={catConfidence} size={64} color={catColor} />
          </div>

          {/* Score breakdown */}
          {Object.keys(intentScores).length > 0 && (
            <div className="ml-card-breakdown">
              <p className="breakdown-title">Score Breakdown</p>
              {Object.entries(intentScores)
                .sort(([, a], [, b]) => b - a)
                .map(([label, score]) => (
                  <ScoreBar
                    key={label}
                    label={label.replace(/_/g, ' ')}
                    score={score}
                    maxScore={maxIntentScore}
                    color={catBarColors[label] || 'var(--accent)'}
                  />
                ))}
            </div>
          )}
        </div>

        {/* ── Sentiment Analysis Card ── */}
        <div
          className="ml-card sentiment-card"
          style={{
            '--card-accent': sentCfg?.color || 'var(--muted)',
            '--sent-bg': sentCfg?.bg || 'rgba(100,130,160,0.06)',
            '--sent-border': sentCfg?.border || 'var(--border)',
            '--sent-glow': sentCfg?.glow || 'transparent',
          }}
        >
          <div className="ml-card-header">
            <div className="ml-card-icon">💬</div>
            <div>
              <h3 className="ml-card-title">Sentiment Analysis</h3>
              <p className="ml-card-subtitle">XLM-RoBERTa sentiment</p>
            </div>
          </div>

          {sentCfg ? (
            <>
              <div className="ml-card-result sentiment-result">
                <div className="sentiment-emoji-wrap">
                  <span className="sentiment-emoji">{sentCfg.emoji}</span>
                </div>
                <div className="sentiment-label-group">
                  <span className="sentiment-badge" style={{ background: sentCfg.bg, borderColor: sentCfg.border, color: sentCfg.color }}>
                    {sentCfg.label}
                  </span>
                  <span className="sentiment-score">
                    {((sentimentData?.score || 0) * 100).toFixed(1)}% confidence
                  </span>
                </div>
              </div>
              <div className="sentiment-bar-wrap">
                <div className="sentiment-bar-track">
                  <div
                    className="sentiment-bar-fill"
                    style={{
                      width: `${(sentimentData?.score || 0) * 100}%`,
                      background: `linear-gradient(90deg, ${sentCfg.color}, ${sentCfg.color}88)`,
                    }}
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="ml-card-result sentiment-result">
              <div className="sentiment-emoji-wrap">
                <span className="sentiment-emoji faded">—</span>
              </div>
              <div className="sentiment-label-group">
                <span className="sentiment-badge disabled">Not Analyzed</span>
                <span className="sentiment-score">Enable sentiment in backend to see results</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Audio Playback ── */}
      <div className="call-section">
        <h3>Audio Playback</h3>
        {audioUrl ? (
          <audio className="audio-player" controls preload="none" src={audioUrl}>
            Your browser does not support audio playback.
          </audio>
        ) : (
          <p className="empty-text">{audioError || 'Loading audio...'}</p>
        )}
      </div>

      {/* ── Conversation Timeline ── */}
      <div className="call-section">
        <h3>Conversation Timeline</h3>
        <div className="timeline">
          {(call.speaker_segments || []).length === 0 && (
            <p className="empty-text">No diarized segments available.</p>
          )}
          {(call.speaker_segments || []).map((seg, index) => (
            <div
              key={`${seg.start_time || index}-${index}`}
              className={`timeline-item ${getSpeakerClass(seg)}`}
              style={{ animationDelay: `${index * 0.04}s` }}
            >
              <div className="speaker-badge">{seg.speaker_label || 'Speaker'}</div>
              <div className="timeline-content">
                <p>{seg.text}</p>
                <span className="timeline-time">
                  {(typeof seg.start_time === 'number' ? seg.start_time.toFixed(1) : '0.0')}s —{' '}
                  {(typeof seg.end_time === 'number' ? seg.end_time.toFixed(1) : '0.0')}s
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Speaker Split ── */}
      <div className="call-section">
        <h3>Speaker Split</h3>
        <div className="speaker-grid">
          {speakers.length === 0 && <p className="empty-text">No speaker segments available.</p>}
          {speakers.map((speaker) => (
            <div key={speaker} className="speaker-column">
              <h4>{speaker}</h4>
              <div className="speaker-bubbles">
                {(call.speaker_segments || [])
                  .filter((seg) => seg.speaker_label === speaker)
                  .map((seg, index) => (
                    <div key={`${speaker}-${index}`} className="bubble">
                      {seg.text}
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Full Transcript ── */}
      <div className="call-section transcript">
        <div className="transcript-header">
          <h3>Full Transcript</h3>
          <div className="transcript-actions">
            <button className="copy-btn" onClick={handleCopy}>
              {copied ? '✓ Copied' : 'Copy'}
            </button>
            <div className="download-dropdown">
              <button className="copy-btn download-btn" onClick={() => setShowDownloadMenu(!showDownloadMenu)}>
                ⬇ Download
              </button>
              {showDownloadMenu && (
                <div className="download-menu">
                  <button onClick={handleDownloadTxt}>📄 Download as TXT</button>
                  <button onClick={handleDownloadPdf}>📑 Download as PDF</button>
                </div>
              )}
            </div>
          </div>
        </div>
        <p>{call.full_transcript || 'Transcript not available.'}</p>
      </div>
    </div>
  );
}

export default CallDetails;
