import { useState } from 'react';

/**
 * OrgLogin — org ID login screen shown before the main app.
 */
export default function OrgLogin({ onLogin }) {
  const [orgId, setOrgId] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = orgId.trim();
    if (!trimmed) {
      setError('Please enter your Organization ID');
      return;
    }
    setError('');
    onLogin(trimmed);
  };

  return (
    <div className="org-login">
      <form className="org-login__card" onSubmit={handleSubmit}>
        <div className="org-login__icon">🏢</div>
        <h1 className="org-login__title">Welcome</h1>
        <p className="org-login__subtitle">
          Enter your Organization ID to access your database
        </p>
        <input
          className="org-login__input"
          type="text"
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
          placeholder="e.g. 101"
          autoFocus
        />
        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>
            {error}
          </div>
        )}
        <button className="btn btn-primary btn-lg" type="submit" style={{ width: '100%' }}>
          Continue →
        </button>
      </form>
    </div>
  );
}
