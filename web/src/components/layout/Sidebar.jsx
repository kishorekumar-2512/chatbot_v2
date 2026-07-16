import { useEffect } from 'react';
import useChatStore from '../../stores/chatStore.js';
import useSchema from '../../hooks/useSchema.js';
import { EXAMPLE_QUERIES } from '../../utils/constants.js';
import { formatTimeAgo, truncate } from '../../utils/formatters.js';
import SchemaExplorer from '../schema/SchemaExplorer.jsx';

/**
 * Sidebar — collapsible panel with quick queries, model health, schema browser, and history.
 */
export default function Sidebar({ onSelectQuery }) {
  const queryHistory = useChatStore((s) => s.queryHistory);
  const schemaData = useChatStore((s) => s.schemaData);
  const circuitStatus = useChatStore((s) => s.circuitStatus);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const { loadSchema, refreshCircuit } = useSchema();

  useEffect(() => {
    refreshCircuit();
  }, []);

  /* Parse circuit status into tier list */
  const tiers = [];
  if (circuitStatus) {
    const keys = ['primary', 'fallback1', 'fallback2'];
    for (const key of keys) {
      const data = circuitStatus[key];
      if (!data) continue;
      
      const label = data.name ? data.name.charAt(0).toUpperCase() + data.name.slice(1) : key;
      let state = 'unknown';
      if (data.circuit_open === false) state = 'closed';
      else if (data.circuit_open === true) state = data.seconds_until_recovery_attempt ? 'recovery' : 'open';
      
      const failures = data.consecutive_failures ?? '?';
      tiers.push({ label, state, failures });
    }
  }

  return (
    <div className="sidebar">
      {/* ── Header ── */}
      <div className="sidebar__header">
        <div className="sidebar__logo">
          <div className="sidebar__logo-icon">🗃️</div>
          <span className="sidebar__logo-text">AI Database</span>
        </div>
      </div>

      <div className="sidebar__content">
        {/* ── Quick Queries ── */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Quick Queries</div>
          {EXAMPLE_QUERIES.map((q, i) => (
            <button key={i} className="example-query" onClick={() => onSelectQuery(q)}>
              {q}
            </button>
          ))}
        </div>

        {/* ── Model Health ── */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Model Health</div>
          <div className="circuit-status">
            {tiers.length > 0 ? tiers.map((t) => (
              <div key={t.label} className="circuit-tier">
                <span className="circuit-tier__name">{t.label}</span>
                <span className={`circuit-tier__state ${t.state}`}>
                  {t.state === 'closed' ? '● Active' : t.state === 'open' ? '○ Open' : '◐ Recovery'}
                </span>
              </div>
            )) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
                Loading…
              </div>
            )}
          </div>
        </div>

        {/* ── Schema Browser ── */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Schema Browser</div>
          {schemaData ? (
            <SchemaExplorer data={schemaData} />
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={loadSchema}>
              📂 Load Schema
            </button>
          )}
        </div>

        {/* ── Recent Queries ── */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Recent Queries</div>
          {queryHistory.slice(0, 10).map((item, i) => (
            <div
              key={i}
              className="history-item"
              onClick={() => onSelectQuery(item.question)}
            >
              <div className="history-item__question">{truncate(item.question, 60)}</div>
              <div className="history-item__time">{formatTimeAgo(item.timestamp)}</div>
            </div>
          ))}
          {queryHistory.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>
              No queries yet
            </div>
          )}
        </div>
      </div>

      {/* ── Footer ── */}
      <div className="sidebar__footer">
        <button className="btn btn-ghost btn-sm" onClick={clearMessages} style={{ width: '100%' }}>
          ↺ New Conversation
        </button>
      </div>
    </div>
  );
}
