import { create } from 'zustand';
import { uid } from '../utils/formatters.js';

/**
 * Central chat state store (Zustand).
 *
 * Manages: messages, conversation context, org ID, sidebar state,
 * settings drawer, connection status, and query history.
 */
const useChatStore = create((set, get) => ({
  /* ── Auth / Org ──────────────────────────────────────── */
  orgId: localStorage.getItem('orgId') || '',
  setOrgId: (id) => {
    localStorage.setItem('orgId', id);
    set({ orgId: id });
  },
  /**
   * Switch back to the org login screen. Also clears messages and query
   * history: both were being kept under a single global (non-org-scoped)
   * localStorage key, so without this a person switching orgs would see
   * the previous org's recent queries and chat history bleed into the new
   * session — a cross-tenant leak in the UI even though the backend
   * itself scopes query data correctly per org.
   */
  logoutOrg: () => {
    localStorage.removeItem('orgId');
    localStorage.removeItem('queryHistory');
    set({ orgId: '', messages: [], conversationContext: null, queryHistory: [], lastResult: null });
  },

  /* ── Messages ────────────────────────────────────────── */
  messages: [],
  addMessage: (role, content, meta = {}) => {
    const msg = { id: uid(), role, content, meta, timestamp: Date.now() };
    set((s) => ({ messages: [...s.messages, msg] }));
    return msg.id;
  },
  updateMessage: (id, updates) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, ...updates, meta: { ...m.meta, ...updates.meta } } : m
      ),
    }));
  },
  clearMessages: () => set({ messages: [], conversationContext: null }),

  /* ── Streaming state ─────────────────────────────────── */
  isStreaming: false,
  streamingStatus: '',
  thinkingTokens: '',
  setStreaming: (val) => set({ isStreaming: val }),
  setStreamingStatus: (s) => set({ streamingStatus: s }),
  appendThinking: (t) => set((s) => ({ thinkingTokens: s.thinkingTokens + t })),
  resetThinking: () => set({ thinkingTokens: '', streamingStatus: '' }),

  /* ── Conversation context (multi-turn) ───────────────── */
  conversationContext: null,
  setConversationContext: (ctx) => set({ conversationContext: ctx }),
  clearContext: () => set({ conversationContext: null }),

  /* ── Last result (for chart re-render / PDF) ─────────── */
  lastResult: null,
  setLastResult: (r) => set({ lastResult: r }),

  /* ── UI state ────────────────────────────────────────── */
  sidebarOpen: window.innerWidth > 768,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (v) => set({ sidebarOpen: v }),

  settingsOpen: false,
  toggleSettings: () => set((s) => ({ settingsOpen: !s.settingsOpen })),
  setSettingsOpen: (v) => set({ settingsOpen: v }),

   rightSidebarOpen: true, // Default to open on desktop
  toggleRightSidebar: () => set((s) => ({ rightSidebarOpen: !s.rightSidebarOpen })),
  setRightSidebarOpen: (v) => set({ rightSidebarOpen: v }),
  
  rightSidebarTab: 'schema', // 'schema' | 'history' | 'trace'
  setRightSidebarTab: (tab) => set({ rightSidebarTab: tab }),

  /* ── Connection status ───────────────────────────────── */
  connectionStatus: 'checking', // 'online' | 'offline' | 'degraded' | 'checking'
  setConnectionStatus: (s) => set({ connectionStatus: s }),

  /* ── Circuit breaker ─────────────────────────────────── */
  circuitStatus: null,
  setCircuitStatus: (s) => set({ circuitStatus: s }),

  /* ── Query history ───────────────────────────────────── */
  queryHistory: JSON.parse(localStorage.getItem('queryHistory') || '[]'),
  addToHistory: (question, sql) => {
    const item = { question, sql, timestamp: Date.now() };
    set((s) => {
      const updated = [item, ...s.queryHistory].slice(0, 50);
      localStorage.setItem('queryHistory', JSON.stringify(updated));
      return { queryHistory: updated };
    });
  },

  /* ── Schema cache ────────────────────────────────────── */
  schemaData: null,
  setSchemaData: (d) => set({ schemaData: d }),

  /* ── Theme ────────────────────────────────────────────── */
  isDarkMode: (localStorage.getItem('theme') || 'dark') !== 'light',
  toggleDarkMode: () => set((s) => {
    const next = !s.isDarkMode;
    localStorage.setItem('theme', next ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light');
    return { isDarkMode: next };
  }),

  /* ── Notifications ────────────────────────────────────── */
  notifications: [],
  unreadCount: 0,
  notificationsOpen: false,
  toggleNotifications: () => set((s) => {
    const open = !s.notificationsOpen;
    return { notificationsOpen: open, unreadCount: open ? 0 : s.unreadCount };
  }),
  setNotificationsOpen: (v) => set({ notificationsOpen: v, unreadCount: v ? 0 : get().unreadCount }),
  addNotification: (type, title, message) => {
    const notif = { id: uid(), type, title, message, timestamp: Date.now(), read: false };
    set((s) => ({
      notifications: [notif, ...s.notifications].slice(0, 30),
      unreadCount: s.notificationsOpen ? 0 : s.unreadCount + 1,
    }));
    return notif.id;
  },
  clearNotifications: () => set({ notifications: [], unreadCount: 0 }),

  /* ── Toasts (transient, auto-dismissing) ─────────────────── */
  toasts: [],
  pushToast: (type, message) => {
    const toast = { id: uid(), type, message };
    set((s) => ({ toasts: [...s.toasts, toast] }));
    return toast.id;
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  /** Raise both a toast (transient, top-right) and a notification (persists in the bell dropdown). */
  notify: (type, title, message) => {
    get().addNotification(type, title, message);
    get().pushToast(type, message);
  },
}));

export default useChatStore;
