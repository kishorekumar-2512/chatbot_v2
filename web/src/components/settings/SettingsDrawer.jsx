import { useState, useEffect } from 'react';
import useChatStore from '../../stores/chatStore.js';
import { getKeys, saveKey, validateKey, toggleKey, deleteKey } from '../../api/settings.js';
import { PROVIDER_ICONS } from '../../utils/constants.js';
import APIKeyCard from './APIKeyCard.jsx';

/**
 * SettingsDrawer — slide-in drawer for API key management and org ID.
 */
export default function SettingsDrawer() {
  const settingsOpen = useChatStore((s) => s.settingsOpen);
  const setSettingsOpen = useChatStore((s) => s.setSettingsOpen);
  const orgId = useChatStore((s) => s.orgId);
  const setOrgId = useChatStore((s) => s.setOrgId);

  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newOrgId, setNewOrgId] = useState(orgId);

  /* Form state for adding a key */
  const [provider, setProvider] = useState('groq');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);

  const providers = Object.keys(PROVIDER_ICONS);

  /* Load existing keys on open */
  useEffect(() => {
    if (settingsOpen) {
      loadKeys();
      setNewOrgId(orgId);
    }
  }, [settingsOpen]);

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await getKeys();
      const list = data.keys ? Object.entries(data.keys).map(([p, v]) => ({ provider: p, ...v })) : [];
      setKeys(list);
    } catch {
      setKeys([]);
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTestResult(null);
    try {
      const res = await validateKey({ provider, api_key: apiKey, model });
      setTestResult(res.valid ? { ok: true, msg: '✅ Key is valid!' } : { ok: false, msg: `❌ ${res.error || 'Invalid'}` });
    } catch (err) {
      setTestResult({ ok: false, msg: `❌ ${err.message}` });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveKey({ provider, api_key: apiKey, model, customer_id: 'default' });
      setApiKey('');
      setModel('');
      setTestResult(null);
      await loadKeys();
    } catch {
      setTestResult({ ok: false, msg: '❌ Failed to save' });
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (prov, enabled) => {
    try {
      await toggleKey(prov, enabled);
      await loadKeys();
    } catch { /* ignore */ }
  };

  const handleDelete = async (prov) => {
    try {
      await deleteKey(prov);
      await loadKeys();
    } catch { /* ignore */ }
  };

  const handleOrgSave = () => {
    if (newOrgId.trim()) setOrgId(newOrgId.trim());
  };

  if (!settingsOpen) return null;

  return (
    <>
      <div className="drawer-overlay" onClick={() => setSettingsOpen(false)} />
      <div className="drawer">
        <div className="drawer__header">
          <h2 className="drawer__title">⚙️ Settings</h2>
          <button className="drawer__close" onClick={() => setSettingsOpen(false)}>✕</button>
        </div>

        <div className="drawer__body">
          {/* ── Org ID ── */}
          <div className="sidebar__section">
            <h3 className="sidebar__section-title">Organization</h3>
            <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              <input
                className="form-input"
                type="text"
                value={newOrgId}
                onChange={(e) => setNewOrgId(e.target.value)}
                placeholder="Org ID (e.g. 101)"
              />
              <button className="btn btn-primary btn-sm" onClick={handleOrgSave}>Save</button>
            </div>
          </div>

          {/* ── Configured Keys ── */}
          <div className="sidebar__section">
            <h3 className="sidebar__section-title">API Keys</h3>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
              Add your own API keys. They take priority over the built-in fallback chain.
            </p>
            {loading ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>Loading…</div>
            ) : keys.length > 0 ? (
              keys.map((k) => (
                <APIKeyCard
                  key={k.provider}
                  keyData={k}
                  onToggle={handleToggle}
                  onDelete={handleDelete}
                />
              ))
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>
                No API keys configured
              </div>
            )}
          </div>

          {/* ── Add Key Form ── */}
          <div className="sidebar__section">
            <h3 className="sidebar__section-title">Add New Key</h3>
            <div className="form-group">
              <label className="form-label">Provider</label>
              <select className="form-select" value={provider} onChange={(e) => setProvider(e.target.value)}>
                {providers.map((p) => (
                  <option key={p} value={p}>{PROVIDER_ICONS[p]} {p}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Model</label>
              <input
                className="form-input"
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="e.g. gpt-4o-mini"
              />
            </div>
            <div className="form-group">
              <label className="form-label">API Key</label>
              <input
                className="form-input"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
              />
            </div>

            {testResult && (
              <div style={{
                padding: 'var(--space-2) var(--space-3)',
                borderRadius: 'var(--radius-sm)',
                background: testResult.ok ? 'var(--success-dim)' : 'var(--danger-dim)',
                color: testResult.ok ? 'var(--success)' : 'var(--danger)',
                fontSize: 'var(--text-sm)',
                marginBottom: 'var(--space-3)',
              }}>
                {testResult.msg}
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button className="btn btn-secondary" onClick={handleTest} disabled={!apiKey}>
                🔍 Test Key
              </button>
              <button className="btn btn-primary" onClick={handleSave} disabled={!apiKey || saving}>
                {saving ? 'Saving…' : '💾 Save Key'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
