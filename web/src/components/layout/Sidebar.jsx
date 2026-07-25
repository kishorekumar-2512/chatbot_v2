import React, { useEffect } from 'react';
import useChatStore from '../../stores/chatStore.js';
import useSchema from '../../hooks/useSchema.js';
import { 
  Plus, 
  Home, 
  Activity, 
  Server,
  MessageSquare,
  ShieldCheck,
  ChevronLeft
} from 'lucide-react';
import { formatTimeAgo, truncate } from '../../utils/formatters.js';

/**
 * Sidebar — collapsible panel with dashboard navigation, system health alerts, and query history.
 */
export default function Sidebar({ onSelectQuery }) {
  const queryHistory = useChatStore((s) => s.queryHistory);
  const circuitStatus = useChatStore((s) => s.circuitStatus);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const toggleSidebar = useChatStore((s) => s.toggleSidebar);
  const { refreshCircuit } = useSchema();

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
      
      tiers.push({ label, state });
    }
  }

  return (
    <aside className="sidebar">
      {/* Header */}
      <div className="sidebar__header">
        <div className="sidebar__logo">
          <div className="sidebar__logo-icon">
            <Server className="w-5 h-5 text-indigo-400" />
          </div>
          <span className="sidebar__logo-text">Antigravity DB</span>
        </div>
        <button className="sidebar-collapse-btn" onClick={toggleSidebar} title="Collapse sidebar">
          <ChevronLeft className="w-4 h-4 text-zinc-500 hover:text-zinc-200" />
        </button>
      </div>

      <div className="sidebar__content">
        {/* New Chat Button */}
        <button className="new-chat-btn" onClick={() => {
          clearMessages();
          if (window.innerWidth <= 1024) toggleSidebar();
        }}>
          <Plus className="w-4 h-4 mr-2" />
          <span>New Query</span>
        </button>

        {/* Navigation */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Navigation</div>
          <nav className="sidebar__nav">
            <button className="nav-item active" onClick={() => {
              clearMessages();
              if (window.innerWidth <= 1024) toggleSidebar();
            }}>
              <Home className="w-4 h-4 mr-3" />
              <span>Home Dashboard</span>
            </button>
          </nav>
        </div>

        {/* Model Health */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Model Health</div>
          <div className="circuit-status">
            {tiers.length > 0 ? tiers.map((t) => (
              <div key={t.label} className="circuit-tier">
                <div className="circuit-tier__info">
                  <Activity className="w-3.5 h-3.5 text-zinc-500 mr-2" />
                  <span className="circuit-tier__name">{t.label}</span>
                </div>
                <span className={`circuit-tier__state ${t.state}`}>
                  <span className="heartbeat-dot" />
                  {t.state === 'closed' ? 'Active' : (t.state === 'open' ? 'Open' : 'Recovery')}
                </span>
              </div>
            )) : (
              <div className="sidebar-loading">
                <span>Checking health...</span>
              </div>
            )}
          </div>
        </div>

        {/* Recent Queries */}
        <div className="sidebar__section">
          <div className="sidebar__section-title">Recent Queries</div>
          <div className="recent-queries-list">
            {queryHistory.slice(0, 8).map((item, i) => (
              <div
                key={i}
                className="recent-query-item"
                onClick={() => onSelectQuery(item.question)}
                title={item.question}
              >
                <MessageSquare className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0 mr-2.5 mt-0.5" />
                <div className="recent-query-item__details">
                  <span className="recent-query-item__text">{truncate(item.question, 40)}</span>
                  <span className="recent-query-item__time">{formatTimeAgo(item.timestamp)}</span>
                </div>
              </div>
            ))}
            {queryHistory.length === 0 && (
              <div className="sidebar-empty">
                No recent queries
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="sidebar__footer">
        <div className="security-badge">
          <ShieldCheck className="w-4 h-4 text-indigo-400 mr-2" />
          <span>Tenant Isolation Active</span>
        </div>
      </div>
    </aside>
  );
}
