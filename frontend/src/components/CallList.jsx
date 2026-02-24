import { getCategoryColor, getCategoryLabel, formatDuration } from '../App';
import './CallList.css';

function timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function CallList({ calls, selectedId, onSelect, loading }) {
  return (
    <div className="call-list">
      <div className="call-list-header">
        <h3>Recent Calls</h3>
        <span className="call-count">{calls.length}</span>
      </div>

      {loading && <div className="call-list-status"><span className="list-spinner"></span>Loading calls...</div>}
      {!loading && calls.length === 0 && (
        <p className="call-list-status empty">No calls found. Upload a recording to get started.</p>
      )}

      <div className="call-list-items">
        {calls.map((call, index) => {
          const catLabel = call.category?.label;
          const catColor = getCategoryColor(catLabel);
          return (
            <button
              key={call.id}
              className={`call-item ${selectedId === call.id ? 'active' : ''}`}
              onClick={() => onSelect?.(call.id)}
              style={{ '--item-delay': `${index * 0.05}s`, '--cat-color': catColor }}
            >
              <div className="call-item-meta">
                <span className="call-item-category" style={{ color: catColor }}>
                  {getCategoryLabel(catLabel)}
                </span>
                <span className="call-item-date">{timeAgo(call.created_at)}</span>
              </div>
              <p className="call-item-preview">{call.preview || 'Transcript unavailable.'}</p>
              <div className="call-item-footer">
                <span>{call.file_name || 'Unknown file'}</span>
                <span>{formatDuration(call.duration_seconds)}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default CallList;
