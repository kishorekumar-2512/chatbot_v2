import { useState, useMemo } from 'react';

/**
 * SchemaExplorer — tree-view browser for database tables and columns.
 */
export default function SchemaExplorer({ data }) {
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(new Set());

  const tables = useMemo(() => {
    if (!data) return [];
    const list = data.tables || [];
    if (!search.trim()) return list;
    const q = search.toLowerCase();
    return list.filter((t) => {
      const name = typeof t === 'string' ? t : t.name;
      return name.toLowerCase().includes(q);
    });
  }, [data, search]);

  const toggleTable = (name) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  if (!data) return null;

  return (
    <div className="schema-explorer">
      <input
        className="schema-search"
        type="text"
        placeholder="Search tables…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div style={{ maxHeight: 300, overflowY: 'auto' }}>
        {tables.map((table) => {
          const name = typeof table === 'string' ? table : table.name;
          const columns = typeof table === 'object' ? table.columns : null;
          const isOpen = expanded.has(name);

          return (
            <div key={name}>
              <div className="schema-table" onClick={() => toggleTable(name)}>
                <span className="schema-table__icon">
                  {isOpen ? '📂' : '📋'}
                </span>
                <span className="schema-table__name">{name}</span>
              </div>
              {isOpen && columns && columns.length > 0 && (
                <div className="schema-columns">
                  {columns.map((col) => (
                    <div key={col.name} className="schema-column">
                      <span>├</span>
                      <span>{col.name}</span>
                      {col.type && (
                        <span className="schema-column__type">{col.type}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {tables.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: 'var(--space-3)' }}>
            No tables found
          </div>
        )}
      </div>
    </div>
  );
}
