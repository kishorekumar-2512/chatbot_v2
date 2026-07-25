import React, { useState } from 'react';
import useChatStore from '../../stores/chatStore.js';
import SchemaExplorer from '../schema/SchemaExplorer.jsx';
import { 
  History, 
  Database, 
  Terminal, 
  ChevronRight, 
  ChevronLeft,
  Clock,
  AlertTriangle,
  Zap,
  RefreshCw
} from 'lucide-react';

/**
 * RightSidebar — Collapsible utility panel for schema explorer, query history, and execution trace.
 */
export default function RightSidebar({ onSelectQuery }) {
  const rightSidebarOpen = useChatStore((s) => s.rightSidebarOpen);
  const toggleRightSidebar = useChatStore((s) => s.toggleRightSidebar);
  const queryHistory = useChatStore((s) => s.queryHistory);
  const schemaData = useChatStore((s) => s.schemaData);
  const messages = useChatStore((s) => s.messages);
  
  // Find the last assistant message with query metadata
  const lastAssistantMsg = [...messages].reverse().find(m => m.role === 'assistant' && m.meta?.sql);
  const traceMeta = lastAssistantMsg?.meta || {};

  const activeTab = useChatStore((s) => s.rightSidebarTab);
  const setActiveTab = useChatStore((s) => s.setRightSidebarTab);

  if (!rightSidebarOpen) {
    return (
      <button 
        className="right-sidebar-toggle-collapsed"
        onClick={toggleRightSidebar}
        title="Open utility panel"
      >
        <ChevronLeft className="w-5 h-5 text-zinc-400" />
      </button>
    );
  }

  return (
    <aside className="right-sidebar">
      {/* Sidebar Header / Tab Selector */}
      <div className="right-sidebar__header">
        <div className="right-sidebar__tabs">
          <button 
            className={`right-sidebar__tab ${activeTab === 'schema' ? 'active' : ''}`}
            onClick={() => setActiveTab('schema')}
            title="Database Schema"
          >
            <Database className="w-4 h-4" />
            <span>Schema</span>
          </button>
          
          <button 
            className={`right-sidebar__tab ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
            title="Query History"
          >
            <History className="w-4 h-4" />
            <span>History</span>
          </button>
          
          <button 
            className={`right-sidebar__tab ${activeTab === 'trace' ? 'active' : ''}`}
            onClick={() => setActiveTab('trace')}
            title="Execution Trace"
          >
            <Terminal className="w-4 h-4" />
            <span>Trace</span>
          </button>
        </div>

        <button 
          className="right-sidebar-close" 
          onClick={toggleRightSidebar}
          title="Collapse panel"
        >
          <ChevronRight className="w-5 h-5 text-zinc-400" />
        </button>
      </div>

      {/* Sidebar Content */}
      <div className="right-sidebar__content">
        {/* Tab 1: Schema */}
        {activeTab === 'schema' && (
          <div className="right-sidebar__panel">
            <div className="panel-title">
              <h3>Schema Explorer</h3>
              <span className="panel-subtitle">Browse database tables & columns</span>
            </div>
            <SchemaExplorer data={schemaData} />
          </div>
        )}

        {/* Tab 2: Query History */}
        {activeTab === 'history' && (
          <div className="right-sidebar__panel">
            <div className="panel-title">
              <h3>Query History</h3>
              <span className="panel-subtitle">Click to re-run past requests</span>
            </div>
            
            <div className="history-list">
              {queryHistory.length > 0 ? (
                queryHistory.map((item, idx) => (
                  <div 
                    key={idx} 
                    className="history-item"
                    onClick={() => {
                      if (onSelectQuery) onSelectQuery(item.question);
                      if (window.innerWidth <= 1024) toggleRightSidebar();
                    }}
                  >
                    <div className="history-item__header">
                      <Clock className="w-3.5 h-3.5 text-zinc-500" />
                      <span className="history-item__time">
                        {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p className="history-item__question">{item.question}</p>
                    {item.sql && (
                      <pre className="history-item__sql">
                        <code>{item.sql.substring(0, 100)}{item.sql.length > 100 ? '...' : ''}</code>
                      </pre>
                    )}
                  </div>
                ))
              ) : (
                <div className="empty-state">
                  <History className="w-8 h-8 text-zinc-600 mb-2" />
                  <p>No queries run yet</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Execution Trace */}
        {activeTab === 'trace' && (
          <div className="right-sidebar__panel">
            <div className="panel-title">
              <h3>Execution Trace</h3>
              <span className="panel-subtitle">LLM generation & execution stats</span>
            </div>

            {traceMeta.latency_ms || traceMeta.confidence ? (
              <div className="trace-details">
                {/* Latency card */}
                {traceMeta.latency_ms && (
                  <div className="trace-card">
                    <div className="trace-card__icon">
                      <Zap className="w-5 h-5 text-amber-400" />
                    </div>
                    <div className="trace-card__info">
                      <span className="trace-card__label">Latency</span>
                      <span className="trace-card__value">{traceMeta.latency_ms} ms</span>
                    </div>
                  </div>
                )}

                {/* Attempts card */}
                {traceMeta.attempts !== undefined && (
                  <div className="trace-card">
                    <div className="trace-card__icon">
                      <RefreshCw className="w-5 h-5 text-indigo-400" />
                    </div>
                    <div className="trace-card__info">
                      <span className="trace-card__label">Attempts Run</span>
                      <span className="trace-card__value">{traceMeta.attempts}</span>
                    </div>
                  </div>
                )}

                {/* Confidence Scores */}
                {traceMeta.confidence && (
                  <div className="trace-section">
                    <h4 className="section-title">Confidence Scores</h4>
                    <div className="confidence-bars">
                      {Object.entries(traceMeta.confidence).map(([key, score]) => (
                        <div key={key} className="confidence-bar-group">
                          <div className="confidence-bar-labels">
                            <span className="confidence-key">{key.replace('_', ' ')}</span>
                            <span className="confidence-value">{score}%</span>
                          </div>
                          <div className="confidence-bar-track">
                            <div 
                              className="confidence-bar-fill" 
                              style={{ 
                                width: `${score}%`, 
                                backgroundColor: score > 80 ? 'var(--success)' : (score > 50 ? 'var(--warning)' : 'var(--danger)') 
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Warnings */}
                {traceMeta.sql_warnings && traceMeta.sql_warnings.length > 0 && (
                  <div className="trace-section">
                    <h4 className="section-title text-warning">SQL Warnings</h4>
                    <ul className="trace-warnings">
                      {traceMeta.sql_warnings.map((w, idx) => (
                        <li key={idx} className="warning-item">
                          <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0" />
                          <span>{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-state">
                <Terminal className="w-8 h-8 text-zinc-600 mb-2" />
                <p>Run a query to view execution metadata</p>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
