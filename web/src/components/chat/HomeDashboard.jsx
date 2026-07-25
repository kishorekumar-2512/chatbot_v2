import React, { useEffect, useState } from 'react';
import { 
  Building2, 
  Laptop, 
  Activity, 
  Layers, 
  FileText, 
  Zap, 
  ArrowRight,
  Sparkles,
  MessageSquare
} from 'lucide-react';
import useChatStore from '../../stores/chatStore.js';
import { getDashboardStats } from '../../api/dashboard.js';
import { formatLatency } from '../../utils/formatters.js';

/**
 * HomeDashboard — Welcomes user, shows real KPI stats, and provides interactive query triggers.
 */
export default function HomeDashboard({ onSelectSuggestion }) {
  const schemaData = useChatStore((s) => s.schemaData);
  const lastResult = useChatStore((s) => s.lastResult);
  const setRightSidebarOpen = useChatStore((s) => s.setRightSidebarOpen);
  const setRightSidebarTab = useChatStore((s) => s.setRightSidebarTab);

  /* null = still loading / unavailable, rendered as "—" rather than a
     fabricated-looking number that implies real data. */
  const [stats, setStats] = useState({
    organizations: null,
    devices: null,
    alerts: null,
    tables: schemaData?.table_count ?? null,
    reports: null,
  });
  const [statsError, setStatsError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Fetch live statistics from the backend. Uses the shared API client
    // (not a bare fetch) so the auth header is attached consistently with
    // every other request in the app.
    getDashboardStats()
      .then((data) => {
        if (cancelled) return;
        if (data && !data.error) {
          setStats({
            organizations: data.organizations,
            devices: data.devices,
            alerts: data.alerts,
            tables: data.tables,
            reports: data.reports,
          });
          setStatsError(false);
        } else {
          setStatsError(true);
        }
      })
      .catch(() => { if (!cancelled) setStatsError(true); });
    return () => { cancelled = true; };
  }, [schemaData]);

  const handleKpiClick = (type) => {
    if (!onSelectSuggestion) return;
    
    switch (type) {
      case 'organizations':
        onSelectSuggestion('Show organization details');
        break;
      case 'devices':
        onSelectSuggestion('List all managed devices');
        break;
      case 'alerts':
        onSelectSuggestion('List active application control violations');
        break;
      case 'tables':
        setRightSidebarTab('schema');
        setRightSidebarOpen(true);
        break;
      case 'reports':
        onSelectSuggestion('Show report categories');
        break;
      case 'latency':
        setRightSidebarTab('trace');
        setRightSidebarOpen(true);
        break;
      default:
        break;
    }
  };

  const fmt = (v) => (v == null ? '—' : String(v));

  const kpis = [
    { 
      id: 'organizations',
      label: 'Organizations', 
      value: fmt(stats.organizations), 
      change: statsError ? 'Unavailable — click ⚙️ Settings to check your connection' : 'Active tenants', 
      icon: Building2, 
      color: 'border-indigo-500/10 bg-indigo-950/10 text-indigo-400' 
    },
    { 
      id: 'devices',
      label: 'Managed Devices', 
      value: fmt(stats.devices), 
      change: statsError ? 'Unavailable' : 'Live count from your database', 
      icon: Laptop, 
      color: 'border-emerald-500/10 bg-emerald-950/10 text-emerald-400' 
    },
    { 
      id: 'alerts',
      label: 'Active Alerts', 
      value: fmt(stats.alerts), 
      change: statsError ? 'Unavailable' : 'Critical issues', 
      icon: Activity, 
      color: 'border-rose-500/10 bg-rose-950/10 text-rose-400' 
    },
    { 
      id: 'tables',
      label: 'Database Tables', 
      value: fmt(stats.tables), 
      change: 'Click to explore schema', 
      icon: Layers, 
      color: 'border-cyan-500/10 bg-cyan-950/10 text-cyan-400' 
    },
    { 
      id: 'reports',
      label: 'Reports Generated', 
      value: fmt(stats.reports), 
      change: statsError ? 'Unavailable' : 'PDF formatting templates', 
      icon: FileText, 
      color: 'border-violet-500/10 bg-violet-950/10 text-violet-400' 
    },
    { 
      id: 'latency',
      label: 'Last Query Latency', 
      value: lastResult?.latency_ms != null ? formatLatency(lastResult.latency_ms) : '—', 
      change: lastResult?.latency_ms != null ? 'Click to view execution trace' : 'Run a query to see timing', 
      icon: Zap, 
      color: 'border-amber-500/10 bg-amber-950/10 text-amber-400' 
    },
  ];

  const suggestions = [
    { 
      title: 'Antivirus compliance summary', 
      desc: 'Show active antivirus protection and engine status across all organizations', 
      query: 'Show antivirus status summary across organizations' 
    },
    { 
      title: 'Operating system distributions', 
      desc: 'List device operating system names and version distributions', 
      query: 'Count devices by operating system' 
    },
    { 
      title: 'Outdated agent installations', 
      desc: 'Show agent info tables filtered by offline status or outdated versions', 
      query: 'List agent info status where online is false or version is outdated' 
    },
    { 
      title: 'Security patch compliance', 
      desc: 'Aggregate missing critical security patches grouped by patch policies', 
      query: 'Show missing patch summary grouped by policy' 
    }
  ];

  return (
    <div className="home-dashboard">
      {/* Hero Welcome */}
      <div className="dashboard-hero">
        <div className="hero-badge">
          <Sparkles className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />
          <span>Intelligent Schema-Aware Assistant</span>
        </div>
        <h1>Enterprise Data Explorer</h1>
        <p className="hero-lead">
          Ask questions in natural language. The assistant will construct PostgreSQL queries, execute them in real-time, generate chart visualizations, and export clean PDF reports.
        </p>
      </div>

      {/* KPI Grid */}
      <div className="kpi-grid">
        {kpis.map((kpi, idx) => (
          <div 
            key={idx} 
            className={`kpi-card ${kpi.color} interactive-kpi-card`}
            onClick={() => handleKpiClick(kpi.id)}
            style={{ cursor: 'pointer', transition: 'all 0.2s ease-in-out' }}
            title={`Click to view details for ${kpi.label}`}
          >
            <div className="kpi-card__header">
              <span className="kpi-card__label">{kpi.label}</span>
              <kpi.icon className="w-5 h-5 flex-shrink-0" />
            </div>
            <div className="kpi-card__body">
              <span className="kpi-card__value">{kpi.value}</span>
              <span className="kpi-card__change">{kpi.change}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Suggestions Section */}
      <div className="suggestions-section">
        <div className="section-title">
          <MessageSquare className="w-4 h-4 mr-2 text-indigo-400 flex-shrink-0" />
          <h2>Quick Database Queries</h2>
        </div>
        <div className="suggestions-grid">
          {suggestions.map((s, idx) => (
            <div 
              key={idx} 
              className="suggestion-card"
              onClick={() => onSelectSuggestion && onSelectSuggestion(s.query)}
            >
              <div className="suggestion-card__content">
                <h3>{s.title}</h3>
                <p>{s.desc}</p>
              </div>
              <div className="suggestion-card__action">
                <ArrowRight className="w-4 h-4 flex-shrink-0" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
