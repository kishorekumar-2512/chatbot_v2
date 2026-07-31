import { useState, useEffect, useMemo } from 'react';
import useChatStore from '../../stores/chatStore.js';
import { getKeys, saveKey, validateKey, toggleKey, deleteKey, getProviders, getLlmStatus } from '../../api/settings.js';
import { PROVIDER_ICONS } from '../../utils/constants.js';
import APIKeyCard from './APIKeyCard.jsx';

/** Extract a readable message from our API client errors (`API 400: {...}`). */
function parseApiError(err) {
  const raw = err?.message || String(err);
  const jsonMatch = raw.match(/API \d+: (.+)/s);
  if (!jsonMatch) return raw;
  try {
    const parsed = JSON.parse(jsonMatch[1]);
    return parsed.detail || parsed.error || raw;
  } catch {
    return jsonMatch[1];
  }
}

/**
 * SettingsDrawer — slide-in drawer for API key management and org ID.
 */
export default function SettingsDrawer() {
  const settingsOpen = useChatStore((s) => s.settingsOpen);
  const setSettingsOpen = useChatStore((s) => s.setSettingsOpen);
  const orgId = useChatStore((s) => s.orgId);
  const setOrgId = useChatStore((s) => s.setOrgId);

  const customerId = orgId?.trim() || '';

  const [keys, setKeys] = useState([]);
  const [providerCatalog, setProviderCatalog] = useState({});
  const [llmStatus, setLlmStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [newOrgId, setNewOrgId] = useState(orgId);

  const [provider, setProvider] = useState('groq');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);

  const providerOptions = useMemo(
    () => Object.keys(providerCatalog).length ? Object.keys(providerCatalog) : Object.keys(PROVIDER_ICONS),
    [providerCatalog],
  );

  const modelsForProvider = providerCatalog[provider]?.models || [];

  useEffect(() => {
    if (settingsOpen) {
      loadAll();
      setNewOrgId(orgId);
    }
  }, [settingsOpen, orgId]);

  useEffect(() => {
    if (modelsForProvider.length && !model) {
      setModel(modelsForProvider[0]);
    }
  }, [provider, modelsForProvider]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [keysData, providersData, statusData] = await Promise.all([
        getKeys(customerId),
        getProviders().catch(() => ({ providers: {} })),
        getLlmStatus(customerId).catch(() => null),
      ]);
      const list = keysData.keys
        ? Object.entries(keysData.keys).map(([p, v]) => ({ provider: p, ...v }))
        : [];
      setKeys(list);
      setProviderCatalog(providersData.providers || {});
      setLlmStatus(statusData);
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
      setTestResult(
        res.valid
          ? { ok: true, msg: '✅ Key is valid!' }
          : { ok: false, msg: `❌ ${res.error || 'Invalid'}` },
      );
    } catch (err) {
      setTestResult({ ok: false, msg: `❌ ${parseApiError(err)}` });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      await saveKey({ provider, api_key: apiKey, model, customer_id: customerId });
      setApiKey('');
      setTestResult({ ok: true, msg: '✅ Key saved!' });
      await loadAll();
    } catch (err) {
      setTestResult({ ok: false, msg: `❌ ${parseApiError(err)}` });
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (prov, enabled) => {
    try {
      await toggleKey(prov, enabled, customerId);
      await loadAll();
    } catch { /* ignore */ }
  };

  const handleDelete = async (prov) => {
    try {
      await deleteKey(prov, customerId);
      await loadAll();
    } catch { /* ignore */ }
  };

  const handleOrgSave = () => {
    if (newOrgId.trim()) setOrgId(newOrgId.trim());
  };

  const noLlmConfigured =
    llmStatus &&
    !llmStatus.byo_keys_configured &&
    !llmStatus.system?.any_system_provider_configured;

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
          {noLlmConfigured && (
            <div style={{
              padding: 'var(--space-3)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--danger-dim)',
              color: 'var(--danger)',
              fontSize: 'var(--text-sm)',
              marginBottom: 'var(--space-4)',
            }}>
              ⚠️ No LLM API keys configured. Add a key below or set{' '}
              <code>GROQ_API_KEY</code> / <code>GEMINI_API_KEY</code> in your backend <code>.env</code> file.
            </div>
          )}

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
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
              API keys are scoped to org <strong>{customerId || 'not selected'}</strong> and are never shared with other orgs.
            </p>
          </div>

          <div className="sidebar__section">
            <h3 className="sidebar__section-title">API Keys</h3>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginBottom: 'var(--space-3)' }}>
              Your keys are tried first, before the system fallback chain (
              {llmStatus?.system?.fallback_chain?.join(' → ') || 'Groq → Gemini → Ollama'}
              ).
            </p>
            {llmStatus?.key_store?.legacy_default_keys_quarantined > 0 && (
              <div style={{ color: 'var(--warning)', fontSize: 'var(--text-xs)', marginBottom: 'var(--space-3)' }}>
                A legacy shared API key was quarantined and is no longer used. Add or move a key into this organization to enable BYO routing.
              </div>
            )}
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
                No API keys configured for this org
              </div>
            )}
          </div>

          <div className="sidebar__section">
            <h3 className="sidebar__section-title">Add New Key</h3>
            <div className="form-group">
              <label className="form-label">Provider</label>
              <select
                className="form-select"
                value={provider}
                onChange={(e) => { setProvider(e.target.value); setModel(''); }}
              >
                {providerOptions.map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_ICONS[p] || '🔑'} {providerCatalog[p]?.name || p}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Model</label>
              {modelsForProvider.length > 0 ? (
                <select className="form-select" value={model} onChange={(e) => setModel(e.target.value)}>
                  {modelsForProvider.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="form-input"
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="e.g. gpt-4o-mini"
                />
              )}
            </div>
            <div className="form-group">
              <label className="form-label">{provider === 'ollama' ? 'Ollama Base URL' : 'API Key'}</label>
              <input
                className="form-input"
                type={provider === 'ollama' ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={provider === 'ollama' ? 'http://localhost:11434' : 'sk-...'}
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
                whiteSpace: 'pre-wrap',
              }}>
                {testResult.msg}
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <button
                className="btn btn-secondary"
                onClick={handleTest}
                disabled={provider !== 'ollama' && !apiKey}
              >
                🔍 Test Key
              </button>
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={(provider !== 'ollama' && !apiKey) || saving}
              >
                {saving ? 'Saving…' : '💾 Save Key'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
