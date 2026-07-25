import { useEffect } from 'react';
import { AlertTriangle, XCircle, CheckCircle2, Info } from 'lucide-react';
import useChatStore from '../../stores/chatStore.js';

const ICONS = {
  warning: AlertTriangle,
  error: XCircle,
  success: CheckCircle2,
  info: Info,
};

const AUTO_DISMISS_MS = 6000;

function ToastItem({ toast }) {
  const dismissToast = useChatStore((s) => s.dismissToast);
  const Icon = ICONS[toast.type] || Info;

  useEffect(() => {
    const t = setTimeout(() => dismissToast(toast.id), AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [toast.id, dismissToast]);

  return (
    <div className={`toast ${toast.type}`}>
      <Icon className="w-4 h-4" style={{ flexShrink: 0, marginTop: 2 }} />
      <span className="toast__message">{toast.message}</span>
      <button className="toast__close" onClick={() => dismissToast(toast.id)} title="Dismiss">✕</button>
    </div>
  );
}

/**
 * ToastStack — transient, auto-dismissing notifications shown top-right.
 * Fires for real-time events like model fallbacks, so they're visible even
 * if the person never opens the notification bell.
 */
export default function ToastStack() {
  const toasts = useChatStore((s) => s.toasts);
  if (toasts.length === 0) return null;

  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
