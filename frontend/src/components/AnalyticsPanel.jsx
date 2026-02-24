import { getCategoryColor, getCategoryLabel } from '../App';
import './AnalyticsPanel.css';

const formatCount = (value) => {
  if (value === undefined || value === null) return '0';
  return value.toLocaleString();
};

function AnalyticsPanel({ analytics }) {
  const categoryCounts = analytics?.category_counts || [];
  const dailyCounts = analytics?.daily_counts || [];
  const maxCategory = Math.max(...categoryCounts.map((item) => item.count), 1);
  const maxDaily = Math.max(...dailyCounts.map((item) => item.count), 1);

  return (
    <div className="analytics-panel">
      <div className="analytics-header">
        <div>
          <p className="analytics-eyebrow">Analytics</p>
          <h3>Call Insights</h3>
        </div>
        <span className="total-calls">{formatCount(analytics?.total_calls || 0)} calls</span>
      </div>

      <div className="analytics-section">
        <p className="analytics-label">By Category</p>
        <div className="category-bars">
          {categoryCounts.length === 0 && <p className="empty-text">No analytics data yet.</p>}
          {categoryCounts.map((item, index) => {
            const color = getCategoryColor(item.category);
            const percentage = (item.count / maxCategory) * 100;
            return (
              <div
                key={item.category}
                className="bar-row"
                style={{ animationDelay: `${index * 0.08}s` }}
              >
                <span className="bar-label" style={{ color }}>
                  {getCategoryLabel(item.category)}
                </span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{
                      width: `${percentage}%`,
                      background: color,
                      animationDelay: `${index * 0.1 + 0.2}s`,
                    }}
                  ></div>
                </div>
                <strong className="bar-count">{item.count}</strong>
              </div>
            );
          })}
        </div>
      </div>

      <div className="analytics-section">
        <p className="analytics-label">Daily Volume</p>
        <div className="sparkline">
          {dailyCounts.length === 0 && <p className="empty-text">No daily data available.</p>}
          {dailyCounts.map((item) => (
            <div key={item.date} className="spark-bar" title={`${item.date}: ${item.count} calls`}>
              <div
                className="spark-fill"
                style={{ height: `${(item.count / maxDaily) * 100}%` }}
              ></div>
              <span>{item.date.slice(5)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default AnalyticsPanel;
