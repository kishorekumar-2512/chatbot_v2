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
}));

export default useChatStore;
