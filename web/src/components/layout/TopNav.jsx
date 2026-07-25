import { useState } from 'react';
import useChatStore from '../../stores/chatStore.js';
import { MODEL_LABELS } from '../../utils/constants.js';
import NotificationCenter from './NotificationCenter.jsx';
import {
  Database,
  Settings,
  Bell,
  Sun,
  Moon,
  Building2,
  Sparkles,
  Bot,
  LogOut,
  Menu,
} from 'lucide-react';

/**
 * TopNav — Premium 72px navigation bar (replaces old StatusBar)
 */
export default function TopNav() {
  const connectionStatus = useChatStore((s) => s.connectionStatus);
  const orgId = useChatStore((s) => s.orgId);
  const toggleSettings = useChatStore((s) => s.toggleSettings);
  const isDarkMode = useChatStore((s) => s.isDarkMode);
  const toggleDarkMode = useChatStore((s) => s.toggleDarkMode);
  const sidebarOpen = useChatStore((s) => s.sidebarOpen);
  const toggleSidebar = useChatStore((s) => s.toggleSidebar);
  const notificationsOpen = useChatStore((s) => s.notificationsOpen);
  const toggleNotifications = useChatStore((s) => s.toggleNotifications);
  const setNotificationsOpen = useChatStore((s) => s.setNotificationsOpen);
  const unreadCount = useChatStore((s) => s.unreadCount);
  const circuitStatus = useChatStore((s) => s.circuitStatus);
  const lastResult = useChatStore((s) => s.lastResult);
  const logoutOrg = useChatStore((s) => s.logoutOrg);

  const [profileOpen, setProfileOpen] = useState(false);

  // Status mapping
  const statusColors = {
    online: 'bg-emerald-500 shadow-[0_0_8px_#10b981]',
    offline: 'bg-rose-500 shadow-[0_0_8px_#ef4444]',
    degraded: 'bg-amber-500 shadow-[0_0_8px_#f59e0b]',
    checking: 'bg-blue-500 shadow-[0_0_8px_#3b82f6] animate-pulse',
  };

  const statusText = {
    online: 'Active',
    offline: 'Disconnected',
    degraded: 'Degraded',
    checking: 'Connecting…',
  };

  /* ── Active model, derived rather than hardcoded ──
     Prefer the model that actually answered the last query; fall back to
     whichever circuit-breaker tier is currently closed (i.e. healthy). */
  const activeModelName = (() => {
    if (lastResult?.model_used) return lastResult.model_used;
    if (circuitStatus) {
      for (const tier of ['primary', 'fallback1', 'fallback2']) {
        if (circuitStatus[tier] && circuitStatus[tier].circuit_open === false) {
          return circuitStatus[tier].name;
        }
      }
    }
    return null;
  })();

  const modelInfo = (() => {
    if (!activeModelName) return { label: 'Detecting model…', icon: '🤖' };
    const key = activeModelName.toLowerCase();
    for (const [k, v] of Object.entries(MODEL_LABELS)) {
      if (key.includes(k)) return v;
    }
    return { label: activeModelName, icon: '🤖' };
  })();

  const closeOverlays = () => {
    setNotificationsOpen(false);
    setProfileOpen(false);
  };

  return (
    <header className="top-nav">
      {/* Left: Brand & DB Info */}
      <div className="top-nav__left">
        {!sidebarOpen && (
          <button 
            className="top-nav__btn sidebar-toggle-btn" 
            onClick={toggleSidebar} 
            title="Open sidebar"
            style={{ 
              marginRight: '8px',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer'
            }}
          >
            <Menu className="w-5 h-5 text-zinc-400 hover:text-zinc-200" />
          </button>
        )}
        <div className="top-nav__brand">
          <div className="top-nav__logo">
            <Database className="w-5 h-5 text-indigo-400" />
            <Sparkles className="w-3.5 h-3.5 text-indigo-300 logo-spark" />
          </div>
          <span className="top-nav__title">Antigravity DB</span>
        </div>
        
        <div className="db-badge">
          <div className={`w-2 h-2 rounded-full ${statusColors[connectionStatus] || 'bg-zinc-500'}`} />
          <span className="db-badge__text">intern_db ({statusText[connectionStatus] || 'Unknown'})</span>
        </div>
      </div>

      {/* Middle: Selector indicators */}
      <div className="top-nav__middle">
        {orgId && (
          <div className="org-selector" title="Org ID">
            <Building2 className="w-4 h-4 text-indigo-400" />
            <span className="org-selector__text">Org ID: {orgId}</span>
          </div>
        )}

        <div className="model-selector" title="Model that answered your last query">
          <Bot className="w-4 h-4 text-indigo-400" />
          <span className="model-selector__text">{modelInfo.icon} {modelInfo.label}</span>
        </div>
      </div>

      {/* Right: Actions & User */}
      <div className="top-nav__right">
        {/* Notifications */}
        <button className="top-nav__btn" onClick={toggleNotifications} title="Notifications">
          <Bell className="w-5 h-5 text-zinc-400 hover:text-zinc-200" />
          {unreadCount > 0 && <span className="nav-badge" />}
        </button>

        {/* Theme Toggle */}
        <button className="top-nav__btn" onClick={toggleDarkMode} title={isDarkMode ? 'Switch to light theme' : 'Switch to dark theme'}>
          {isDarkMode ? (
            <Sun className="w-5 h-5 text-zinc-400 hover:text-zinc-200" />
          ) : (
            <Moon className="w-5 h-5 text-zinc-400 hover:text-zinc-200" />
          )}
        </button>

        {/* Settings */}
        <button className="top-nav__btn" onClick={toggleSettings} title="Settings">
          <Settings className="w-5 h-5 text-zinc-400 hover:text-indigo-400 transition-colors" />
        </button>

        {/* Profile */}
        <div className="nav-profile" onClick={() => setProfileOpen((v) => !v)}>
          <div className="nav-profile__avatar">
            <span>{orgId ? orgId.charAt(0).toUpperCase() : 'U'}</span>
          </div>
        </div>
      </div>

      {/* Click-away overlay + dropdowns */}
      {(notificationsOpen || profileOpen) && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 800 }}
          onClick={closeOverlays}
        />
      )}
      {notificationsOpen && <NotificationCenter />}
      {profileOpen && (
        <div className="nav-profile__menu">
          <div className="nav-profile__menu-header">Org {orgId}</div>
          <button className="nav-profile__menu-item" onClick={() => { toggleSettings(); setProfileOpen(false); }}>
            <Settings className="w-4 h-4" /> Manage API keys
          </button>
          <button className="nav-profile__menu-item" onClick={logoutOrg}>
            <LogOut className="w-4 h-4" /> Switch organization
          </button>
        </div>
      )}
    </header>
  );
}
