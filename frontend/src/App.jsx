import { useEffect, useMemo, useState } from 'react';
import { fetchAnalytics, fetchCallById, fetchCalls } from './services/api';
import CallUploader from './components/CallUploader';
import CallList from './components/CallList';
import CallDetails from './components/CallDetails';
import AnalyticsPanel from './components/AnalyticsPanel';
import './App.css';

const categories = [
  'All',
  'Billing',
  'Complaint',
  'Fiber',
  'New_Connection',
  'Other',
  'PEO_TV',
];

export const CATEGORY_COLORS = {
  Billing: 'var(--cat-billing)',
  Complaint: 'var(--cat-complaint)',
  Fiber: 'var(--cat-fiber)',
  New_Connection: 'var(--cat-new-connection)',
  Other: 'var(--cat-other)',
  PEO_TV: 'var(--cat-peo-tv)',
};

export const CATEGORY_LABELS = {
  Billing: 'Billing',
  Complaint: 'Complaint',
  Fiber: 'Fiber',
  New_Connection: 'New Connection',
  Other: 'Other',
  PEO_TV: 'PEO TV',
};

export function getCategoryColor(label) {
  return CATEGORY_COLORS[label] || 'var(--cat-other)';
}

export function getCategoryLabel(label) {
  return CATEGORY_LABELS[label] || label || 'Other';
}

export function formatDuration(totalSeconds) {
  if (!totalSeconds) return '—';
  const sec = Math.round(totalSeconds);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function App() {
  const [calls, setCalls] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [filters, setFilters] = useState({ q: '', category: 'All' });
  const [status, setStatus] = useState({ list: false, details: false });
  const [error, setError] = useState(null);

  const loadCalls = async (params = {}) => {
    setStatus((prev) => ({ ...prev, list: true }));
    try {
      const data = await fetchCalls(params);
      setCalls(data.items || []);
      if (!selectedCall && data.items?.length) {
        const firstWithTranscript = data.items.find((c) => c.preview?.trim());
        handleSelectCall((firstWithTranscript || data.items[0]).id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus((prev) => ({ ...prev, list: false }));
    }
  };

  const loadAnalytics = async () => {
    try {
      const data = await fetchAnalytics();
      setAnalytics(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSelectCall = async (callId) => {
    setStatus((prev) => ({ ...prev, details: true }));
    try {
      const data = await fetchCallById(callId);
      setSelectedCall(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus((prev) => ({ ...prev, details: false }));
    }
  };

  const handleUploadComplete = (call) => {
    setSelectedCall(call);
    const summary = {
      id: call.id,
      created_at: call.created_at,
      file_name: call.file?.filename,
      detected_language: call.detected_language,
      duration_seconds: call.duration_seconds,
      category: call.category,
      preview: call.full_transcript?.slice(0, 160),
    };
    setCalls((prev) => [summary, ...prev]);
    loadAnalytics();
  };

  const handleError = (message) => {
    setError(message);
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  useEffect(() => {
    const timeout = setTimeout(() => {
      loadCalls(filters);
    }, 350);
    return () => clearTimeout(timeout);
  }, [filters]);

  const clearError = () => setError(null);
  const filteredCount = useMemo(() => calls.length, [calls]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <div className="logo-mark">AI</div>
          <div>
            <p className="brand-eyebrow">Telecom Intelligence</p>
            <h1>Call Analysis</h1>
            <p className="brand-subtitle">
              Multilingual speaker diarization, intent classification & sentiment analysis
            </p>
          </div>
        </div>
        <div className="header-stats">
          <div>
            <span>Total Calls</span>
            <strong>{analytics?.total_calls || 0}</strong>
          </div>
          <div>
            <span>Visible</span>
            <strong>{filteredCount}</strong>
          </div>
        </div>
      </header>

      {error && (
        <div className="error-message">
          <span>{error}</span>
          <button onClick={clearError}>Dismiss</button>
        </div>
      )}

      <main className="dashboard">
        <section className="left-column">
          <CallUploader onComplete={handleUploadComplete} onError={handleError} />

          <div className="filters-card">
            <div>
              <label>Search transcript</label>
              <input
                type="text"
                value={filters.q}
                onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
                placeholder="Search by keyword..."
              />
            </div>
            <div>
              <label>Category</label>
              <select
                value={filters.category}
                onChange={(e) => setFilters((prev) => ({ ...prev, category: e.target.value }))}
              >
                {categories.map((cat) => (
                  <option key={cat} value={cat}>
                    {getCategoryLabel(cat)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <CallList
            calls={calls}
            selectedId={selectedCall?.id}
            onSelect={handleSelectCall}
            loading={status.list}
          />
        </section>

        <section className="right-column">
          <AnalyticsPanel analytics={analytics} />
          {status.details ? (
            <div className="loading-card">Loading call details...</div>
          ) : (
            <CallDetails call={selectedCall} />
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
