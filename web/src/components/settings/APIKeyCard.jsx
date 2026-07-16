import { PROVIDER_ICONS } from '../../utils/constants.js';

/**
 * APIKeyCard — displays a configured LLM provider key with toggle and delete.
 */
export default function APIKeyCard({ keyData, onToggle, onDelete }) {
  const { provider, model, key_preview, enabled } = keyData;
  const icon = PROVIDER_ICONS[provider] || '🔑';

  return (
    <div className="key-card" style={{ opacity: enabled ? 1 : 0.6 }}>
      <div className="key-card__header">
        <div className="key-card__provider">
          <span>{icon}</span>
          <span>{provider}</span>
        </div>
        <div className="key-card__actions">
          <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', cursor: 'pointer', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={() => onToggle(provider, !enabled)}
              style={{ accentColor: 'var(--accent-blue)' }}
            />
            {enabled ? 'On' : 'Off'}
          </label>
          <button className="btn btn-danger btn-sm" onClick={() => onDelete(provider)}>
            ✕
          </button>
        </div>
      </div>
      <div className="key-card__model">{model}</div>
      {key_preview && <div className="key-card__preview">{key_preview}</div>}
    </div>
  );
}
