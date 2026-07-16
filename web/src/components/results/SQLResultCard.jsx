import { useMemo } from 'react';
import { MODEL_LABELS, INTENT_ICONS } from '../../utils/constants.js';
import { formatLatency, getConfidenceLevel } from '../../utils/formatters.js';
import { downloadPDF } from '../../api/chat.js';
import ChartRenderer from './ChartRenderer.jsx';
import DataTable from './DataTable.jsx';
import AnimatedStat from './AnimatedStat.jsx';
import EditableSQL from './EditableSQL.jsx';
import InsightChips from './InsightChips.jsx';
import FollowUpButtons from './FollowUpButtons.jsx';
import FeedbackButtons from './FeedbackButtons.jsx';
import CopyButton from '../common/CopyButton.jsx';

/**
 * SQLResultCard — full result display with meta, chart, table, confidence, SQL, feedback.
 */
export default function SQLResultCard({ data, onFollowUp, onRerunSQL, messageId }) {
  if (!data) return null;

  const modelInfo = useMemo(() => {
    if (!data.model_used) return null;
    const key = data.model_used.toLowerCase();
    for (const [k, v] of Object.entries(MODEL_LABELS)) {
      if (key.includes(k)) return v;
    }
    return { label: data.model_used, icon: '🔵', color: '#3B82F6' };
  }, [data.model_used]);

  const confidence = data.confidence || {};
  const overall = confidence.overall ?? 0;
  const level = confidence.level || getConfidenceLevel(overall);

  const hasChart = !!data.chart_json;
  const hasStat = data.single_stat != null;
  const hasRows = data.rows && data.rows.length > 0;

  const handlePDF = () => {
    downloadPDF({
      question: data.question || '',
      sql: data.sql || '',
      rows: data.rows || [],
      chart_json: data.chart_json || null,
    });
  };

  return (
    <div className="result-card">
      {/* ── Meta Badges ── */}
      <div className="meta-badges">
        {modelInfo && (
          <span className="badge badge--model">{modelInfo.icon} {modelInfo.label}</span>
        )}
        {data.latency_ms != null && (
          <span className="badge badge--latency">⚡ {formatLatency(data.latency_ms)}</span>
        )}
        {data.attempts != null && (
          <span className={`badge badge--attempts-${Math.min(data.attempts, 3)}`}>
            🎯 Attempt {data.attempts}
          </span>
        )}
        {data.tables_used && data.tables_used.length > 0 && (
          <span className="badge badge--tables">📊 {data.tables_used.length} tables</span>
        )}
        {data.intent && (
          <span className="badge badge--intent">
            {INTENT_ICONS[data.intent] || '📋'} {data.intent}
          </span>
        )}
      </div>

      {/* ── Insights ── */}
      <InsightChips insights={data.insights} />

      {/* ── Visualization ── */}
      {hasChart && <ChartRenderer chartJson={data.chart_json} chartKind={data.chart_kind} />}
      {hasStat && !hasChart && (
        <AnimatedStat value={data.single_stat} label={data.question || ''} />
      )}
      {hasRows && !hasChart && !hasStat && <DataTable rows={data.rows} />}

      {/* ── Confidence ── */}
      {overall > 0 && (
        <div className="confidence-section">
          <div className="confidence-label">
            <span className="confidence-label__text">Confidence</span>
            <span className={`confidence-label__score ${level}`}>
              {Math.round(overall)}%
            </span>
          </div>
          <div className="confidence-gauge">
            <div
              className={`confidence-gauge__fill ${level}`}
              style={{ width: `${overall}%` }}
            />
          </div>
          <div className="confidence-breakdown">
            {[
              { key: 'table_relevance', label: 'Table Relevance' },
              { key: 'column_accuracy', label: 'Column Accuracy' },
              { key: 'attempt_score', label: 'Attempt Score' },
              { key: 'row_sanity', label: 'Row Sanity' },
            ].map(({ key, label }) => {
              const val = confidence[key] ?? 0;
              const barLevel = getConfidenceLevel(val);
              return (
                <div key={key} className="confidence-breakdown__item">
                  <span className="confidence-breakdown__label">
                    {label}: {Math.round(val)}%
                  </span>
                  <div className="confidence-breakdown__bar">
                    <div
                      className={`confidence-breakdown__bar-fill confidence-gauge__fill ${barLevel}`}
                      style={{ width: `${val}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Editable SQL ── */}
      <EditableSQL sql={data.sql} messageId={messageId} question={data.question} onRerun={onRerunSQL} />

      {/* ── Feedback + Actions ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <FeedbackButtons
          messageId={messageId}
          question={data.question}
          sql={data.sql}
          modelUsed={data.model_used}
          confidence={confidence}
        />
        <CopyButton text={data.answer || data.content || ''} label="Copy answer" />
        {hasRows && (
          <button className="btn btn-secondary btn-sm" onClick={handlePDF}>
            📄 Download PDF
          </button>
        )}
      </div>

      {/* ── Follow-ups ── */}
      <FollowUpButtons followups={data.followups} onSelect={onFollowUp} />
    </div>
  );
}
