import { AlertTriangle, XCircle, CheckCircle2, Info, Bell } from 'lucide-react';
import useChatStore from '../../stores/chatStore.js';
import { formatTimeAgo } from '../../utils/formatters.js';

const ICONS = {
  warning: AlertTriangle,
  error: XCircle,
  success: CheckCircle2,
  info: Info,
};

/**
 * NotificationCenter — dropdown panel listing model fallback events, connection
 * issues, and other system health notifications. Opened from the TopNav bell icon.
 */
export default function NotificationCenter() {
  const notifications = useChatStore((s) => s.notifications);
  const clearNotifications = useChatStore((s) => s.clearNotifications);

  return (
    <div className="notification-center">
      <div className="notification-center__header">
        <span className="notification-center__title">Notifications</span>
        {notifications.length > 0 && (
          <button className="notification-center__clear" onClick={clearNotifications}>
            Clear all
          </button>
        )}
      </div>
      <div className="notification-center__list">
        {notifications.length === 0 ? (
          <div className="notification-center__empty">
            <Bell className="w-6 h-6" style={{ margin: '0 auto var(--space-2)', opacity: 0.5 }} />
            No notifications yet.<br />You'll see model fallbacks and connection issues here.
          </div>
        ) : (
          notifications.map((n) => {
            const Icon = ICONS[n.type] || Info;
            return (
              <div key={n.id} className="notification-item">
                <div className={`notification-item__icon ${n.type}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div>
                  <div className="notification-item__title">{n.title}</div>
                  <div className="notification-item__message">{n.message}</div>
                  <div className="notification-item__time">{formatTimeAgo(n.timestamp)}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
