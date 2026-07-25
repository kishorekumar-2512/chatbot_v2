import React, { useState, useMemo } from 'react';
import { 
  Search, 
  FolderOpen, 
  Folder, 
  Columns, 
  Key
} from 'lucide-react';

/**
 * SchemaExplorer — premium tree-view browser for database tables, columns, and descriptions.
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
      const desc = typeof t === 'object' ? (t.description || '') : '';
      return name.toLowerCase().includes(q) || desc.toLowerCase().includes(q);
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
      <div className="schema-search-container">
        <Search className="schema-search-icon" />
        <input
          className="schema-search"
          type="text"
          placeholder="Search tables or descriptions…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      
      <div className="schema-list">
        {tables.map((table) => {
          const name = typeof table === 'string' ? table : table.name;
          const columns = typeof table === 'object' ? table.columns : null;
          const tableDesc = typeof table === 'object' ? table.description : '';
          const isOpen = expanded.has(name);

          return (
            <div key={name} className="schema-table-group">
              <div className="schema-table" onClick={() => toggleTable(name)}>
                <span className="schema-table__icon">
                  {isOpen ? (
                    <FolderOpen className="w-4 h-4 text-indigo-400" />
                  ) : (
                    <Folder className="w-4 h-4 text-zinc-500" />
                  )}
                </span>
                <div className="schema-table__details">
                  <span className="schema-table__name">{name}</span>
                  {tableDesc && (
                    <span className="schema-table__desc" title={tableDesc}>
                      {tableDesc}
                    </span>
                  )}
                </div>
              </div>
              
              {isOpen && columns && columns.length > 0 && (
                <div className="schema-columns">
                  {columns.map((col) => {
                    const isKey = col.name.endsWith('_id') || col.name === 'id';
                    return (
                      <div key={col.name} className="schema-column">
                        <div className="schema-column__main">
                          {isKey ? (
                            <Key className="w-3 h-3 text-amber-500 mr-1.5" />
                          ) : (
                            <Columns className="w-3 h-3 text-zinc-500 mr-1.5" />
                          )}
                          <span className="schema-column__name">{col.name}</span>
                          {col.type && (
                            <span className="schema-column__type">
                              ({col.type})
                            </span>
                          )}
                        </div>
                        {col.description && (
                          <div className="schema-column__desc">
                            {col.description}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
        {tables.length === 0 && (
          <div className="schema-empty">
            No tables match search
          </div>
        )}
      </div>
    </div>
  );
}
