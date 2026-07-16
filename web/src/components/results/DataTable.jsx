import { useState, useMemo } from 'react';
import { truncate } from '../../utils/formatters.js';

/**
 * DataTable — sortable data table with column click sorting and row limiting.
 */
export default function DataTable({ rows, maxRows = 100 }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);

  const columns = useMemo(() => {
    if (!rows || rows.length === 0) return [];
    return Object.keys(rows[0]);
  }, [rows]);

  const sortedRows = useMemo(() => {
    if (!rows) return [];
    let data = [...rows];
    if (sortCol !== null) {
      data.sort((a, b) => {
        const va = a[sortCol];
        const vb = b[sortCol];
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        if (typeof va === 'number' && typeof vb === 'number') {
          return sortAsc ? va - vb : vb - va;
        }
        const sa = String(va).toLowerCase();
        const sb = String(vb).toLowerCase();
        return sortAsc ? sa.localeCompare(sb) : sb.localeCompare(sa);
      });
    }
    return data.slice(0, maxRows);
  }, [rows, sortCol, sortAsc, maxRows]);

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
  };

  if (!rows || rows.length === 0) return null;

  return (
    <div className="data-table-wrapper">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className={sortCol === col ? 'sorted' : ''}
                onClick={() => handleSort(col)}
              >
                {col}
                {sortCol === col && (
                  <span style={{ marginLeft: 4 }}>{sortAsc ? '▲' : '▼'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col} title={String(row[col] ?? '')}>
                  {truncate(String(row[col] ?? '—'), 50)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="data-table__footer">
        <span>Showing {sortedRows.length} of {rows.length} rows</span>
        {sortCol && (
          <button className="btn btn-ghost btn-sm" onClick={() => { setSortCol(null); }}>
            Clear sort
          </button>
        )}
      </div>
    </div>
  );
}
