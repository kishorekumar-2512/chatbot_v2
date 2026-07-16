import { useState } from 'react';
import CopyButton from '../common/CopyButton.jsx';

/**
 * EditableSQL — collapsible SQL viewer/editor with re-run capability.
 */
export default function EditableSQL({ sql, messageId, question, onRerun }) {
  const [open, setOpen] = useState(false);
  const [editedSql, setEditedSql] = useState(sql || '');
  const [running, setRunning] = useState(false);

  if (!sql) return null;

  const handleRun = async () => {
    setRunning(true);
    try {
      await onRerun(editedSql, question, messageId);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="sql-section">
      <button className="sql-toggle" onClick={() => setOpen(!open)}>
        <span className={`sql-toggle__chevron${open ? ' open' : ''}`}>›</span>
        SQL Query
      </button>

      {open && (
        <div className="sql-editor">
          <textarea
            className="sql-editor__textarea"
            value={editedSql}
            onChange={(e) => setEditedSql(e.target.value)}
            rows={Math.min(editedSql.split('\n').length + 1, 12)}
          />
          <div className="sql-editor__actions">
            <button
              className="btn btn-secondary btn-sm"
              onClick={handleRun}
              disabled={running || !editedSql.trim()}
            >
              {running ? '⏳ Running…' : '▶ Run this SQL'}
            </button>
            <CopyButton text={editedSql} label="Copy SQL" />
            {editedSql !== sql && (
              <button className="btn btn-ghost btn-sm" onClick={() => setEditedSql(sql)}>
                ↺ Reset
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
