import useChatStore from '../../stores/chatStore.js';

/**
 * StatusBar — top bar with connection status, sidebar toggle, org badge, and settings.
 */
export default function StatusBar() {
  const connectionStatus = useChatStore((s) => s.connectionStatus);
  const orgId = useChatStore((s) => s.orgId);
  const toggleSidebar = useChatStore((s) => s.toggleSidebar);
  const toggleSettings = useChatStore((s) => s.toggleSettings);

  const statusText = {
    online: 'Connected',
    offline: 'Disconnected',
    degraded: 'Degraded',
    checking: 'Connecting…',
  };

  const dotClass = connectionStatus === 'online' ? ''
    : connectionStatus === 'offline' ? ' offline'
    : connectionStatus === 'degraded' ? ' degraded'
    : '';

  return (
    <div className="status-bar">
      <div className="status-bar__left">
        <button className="sidebar-toggle" onClick={toggleSidebar} title="Toggle sidebar">
          ☰
        </button>
        <div className="status-indicator">
          <div className={`status-dot${dotClass}`} />
          <span>{statusText[connectionStatus] || 'Unknown'}</span>
        </div>
      </div>

      <div className="status-bar__right">
        {orgId && (
          <div className="org-badge">🏢 Org {orgId}</div>
        )}
        <button className="btn btn-ghost" onClick={toggleSettings} title="Settings">
          ⚙️
        </button>
      </div>
    </div>
  );
}
