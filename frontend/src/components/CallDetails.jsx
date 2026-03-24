import { useEffect, useState } from 'react';
import { formatDuration } from '../App';
import { fetchCallAudioUrl } from '../services/api';
import './CallDetails.css';

const parseBackendUtcDate = (iso) => {
  if (!iso) return null;
  const normalizedIso = /(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`;
  return new Date(normalizedIso);
};

const formatDate = (iso) => {
  if (!iso) return '';
  return parseBackendUtcDate(iso).toLocaleString('en-LK', { timeZone: 'Asia/Colombo' });
};

// ── WER helpers (pure JS, no backend needed) ──────────────────────────────
function computeWER(reference, hypothesis) {
  // Normalise: lowercase, strip punctuation
  const normalise = (s) =>
    s.toLowerCase().replace(/[^\u0D80-\u0DFFa-z0-9\s]/g, '').trim();
  const refWords = normalise(reference).split(/\s+/).filter(Boolean);
  const hypWords = normalise(hypothesis).split(/\s+/).filter(Boolean);
  const R = refWords.length;
  const H = hypWords.length;
  if (R === 0) return null;

  // Levenshtein at word level
  const dp = Array.from({ length: R + 1 }, (_, i) =>
    Array.from({ length: H + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= R; i++) {
    for (let j = 1; j <= H; j++) {
      dp[i][j] =
        refWords[i - 1] === hypWords[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  const wer = dp[R][H] / R;
  return { wer, accuracy: Math.max(0, 1 - wer), refWords: R };
}

function getQualityFromConfidence(conf) {
  if (conf === null || conf === undefined) return { label: 'Unknown', color: '#6b7280', bg: 'rgba(107,114,128,0.12)', wer: 'n/a' };
  if (conf >= 0.85) return { label: 'Excellent', color: '#10b981', bg: 'rgba(16,185,129,0.12)', wer: '< 10%' };
  if (conf >= 0.70) return { label: 'Good',      color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', wer: '10–25%' };
  if (conf >= 0.55) return { label: 'Fair',      color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', wer: '25–40%' };
  return                     { label: 'Poor',      color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  wer: '> 40%' };
}

function getQualityFromWER(wer) {
  if (wer <= 0.10) return { label: 'Excellent', color: '#10b981', bg: 'rgba(16,185,129,0.12)' };
  if (wer <= 0.25) return { label: 'Good',      color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' };
  if (wer <= 0.40) return { label: 'Fair',      color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' };
  return                   { label: 'Poor',      color: '#ef4444', bg: 'rgba(239,68,68,0.12)'  };
}

const WER_RANGES = [
  { label: 'Excellent', range: '90–100%', wer: '0–10%',  color: '#10b981', note: 'Production ready' },
  { label: 'Good',      range: '75–90%',  wer: '10–25%', color: '#3b82f6', note: 'Minor corrections needed' },
  { label: 'Fair',      range: '60–75%',  wer: '25–40%', color: '#f59e0b', note: 'Needs editing' },
  { label: 'Poor',      range: '< 60%',   wer: '> 40%',  color: '#ef4444', note: 'Major errors' },
];
// ─────────────────────────────────────────────────────────────────────────────

function CallDetails({ call }) {
  const [copied, setCopied] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const [audioError, setAudioError] = useState('');
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [refTranscript, setRefTranscript] = useState('');
  const [werResult, setWerResult] = useState(null);

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
        <h3>Select a call to view details</h3>
        <p>Upload a recording or pick a recent call to inspect the transcript.</p>
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

  const avgConf = call.transcription_meta?.avg_confidence ?? null;
  const confQuality = getQualityFromConfidence(avgConf);

  const handleCalculateWER = () => {
    if (!refTranscript.trim() || !call.full_transcript) return;
    const result = computeWER(refTranscript, call.full_transcript);
    setWerResult(result);
  };

  const handleCopy = () => {
    if (call.full_transcript) {
      navigator.clipboard.writeText(call.full_transcript);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const buildTranscriptContent = () => {
    const fileName = call.file?.filename || 'Untitled Call';
    const date = call.created_at ? formatDate(call.created_at) : 'Unknown';
    const language = call.detected_language || 'Unknown';
    let text = `Call Transcript\n${'='.repeat(50)}\n`;
    text += `File: ${fileName}\nDate: ${date}\nLanguage: ${language}\n\n`;
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
    const win = window.open('', '_blank');
    win.document.write(`<!DOCTYPE html><html><head><title>Transcript ${callIdSuffix}</title>
      <style>body{font-family:'Segoe UI',system-ui,sans-serif;padding:40px;color:#222;line-height:1.7;max-width:800px;margin:0 auto}
      h1{font-size:1.4rem;border-bottom:2px solid #333;padding-bottom:8px}h2{font-size:1.1rem;color:#555;margin-top:24px}
      .meta{color:#666;font-size:0.9rem;margin-bottom:20px}.seg{margin:8px 0;padding:8px 12px;background:#f5f5f5;border-radius:6px;border-left:3px solid #3b82f6}
      .seg .label{font-weight:700;color:#3b82f6;font-size:0.85rem}.seg .time{color:#999;font-size:0.75rem}
      .transcript{white-space:pre-wrap;background:#fafafa;padding:16px;border-radius:8px;border:1px solid #eee}</style></head><body>`);
    win.document.write(`<h1>Call Transcript — #${callIdSuffix}</h1>`);
    win.document.write(`<div class="meta">File: ${call.file?.filename || 'Unknown'}<br>Date: ${call.created_at ? formatDate(call.created_at) : 'Unknown'}<br>Language: ${call.detected_language || 'Unknown'}</div>`);
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
        <div className="stat-card">
          <span>Confidence</span>
          <strong style={{ color: confQuality.color }}>
            {avgConf !== null ? `${(avgConf * 100).toFixed(1)}%` : '—'}
          </strong>
        </div>
        <div className="stat-card quality-card" style={{ '--quality-color': confQuality.color, '--quality-bg': confQuality.bg }}>
          <span>STT Quality</span>
          <strong className="quality-badge-inline" style={{ color: confQuality.color }}>
            {confQuality.label}
          </strong>
          <span className="quality-wer-hint">WER ≈ {confQuality.wer}</span>
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

      {/* ── WER Accuracy Calculator ── */}
      <div className="call-section wer-section">
        <h3>Accuracy Calculator (WER)</h3>
        <p className="wer-description">
          Paste the correct human-verified transcript below to calculate Word Error Rate (WER) and real accuracy for this call.
        </p>

        {/* Reference table */}
        <div className="wer-range-table">
          <div className="wer-range-header">
            <span>Quality</span>
            <span>Accuracy</span>
            <span>WER</span>
            <span>Meaning</span>
          </div>
          {WER_RANGES.map((row) => (
            <div key={row.label} className="wer-range-row">
              <span className="wer-range-label" style={{ color: row.color }}>{row.label}</span>
              <span>{row.range}</span>
              <span>{row.wer}</span>
              <span className="wer-range-note">{row.note}</span>
            </div>
          ))}
        </div>

        {/* Input area */}
        <textarea
          className="wer-textarea"
          placeholder="Paste the correct Sinhala transcript here..."
          value={refTranscript}
          onChange={(e) => { setRefTranscript(e.target.value); setWerResult(null); }}
          rows={5}
        />
        <button className="wer-calc-btn" onClick={handleCalculateWER} disabled={!refTranscript.trim()}>
          Calculate Accuracy
        </button>

        {/* Results */}
        {werResult && (() => {
          const q = getQualityFromWER(werResult.wer);
          return (
            <div className="wer-results" style={{ '--wer-color': q.color, '--wer-bg': q.bg }}>
              <div className="wer-result-row">
                <div className="wer-result-block">
                  <span>Accuracy</span>
                  <strong style={{ color: q.color }}>{(werResult.accuracy * 100).toFixed(1)}%</strong>
                </div>
                <div className="wer-result-block">
                  <span>Word Error Rate</span>
                  <strong style={{ color: q.color }}>{(werResult.wer * 100).toFixed(1)}%</strong>
                </div>
                <div className="wer-result-block">
                  <span>Reference Words</span>
                  <strong>{werResult.refWords}</strong>
                </div>
                <div className="wer-result-block">
                  <span>Quality</span>
                  <strong className="wer-quality-pill" style={{ color: q.color, background: q.bg }}>
                    {q.label}
                  </strong>
                </div>
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

export default CallDetails;
