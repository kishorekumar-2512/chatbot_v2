import { formatTimeAgo } from '../../utils/formatters.js';
import TypingIndicator from './TypingIndicator.jsx';
import SQLResultCard from '../results/SQLResultCard.jsx';

/**
 * MessageBubble — renders a single user or assistant message.
 */
export default function MessageBubble({ message, onFollowUp, onRerunSQL }) {
  const { id, role, content, meta = {}, timestamp } = message;
  const isUser = role === 'user';

  return (
    <div className={`message message--${role}`}>
      <div className="message__avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="message__body">
        {isUser ? (
          /* ── User message ── */
          <div className="message__content">
            {meta.image && (
              <div className="message__image">
                <img src={meta.image} alt="Uploaded" />
              </div>
            )}
            {content}
          </div>
        ) : (
          /* ── Assistant message ── */
          <div className="message__content">
            {meta.loading ? (
              <TypingIndicator />
            ) : meta.error ? (
              <div style={{ color: 'var(--danger)' }}>
                ⚠️ {content || 'Something went wrong'}
              </div>
            ) : meta.multiResults ? (
              /* ── Multi-chart dashboard results ── */
              <div className="multi-results">
                {meta.multiResults.map((result, idx) => (
                  <div className="multi-results__card" key={idx}>
                    <div className="multi-results__header">
                      📊 Chart {idx + 1}{result.chart_info?.chart_type ? ` — ${result.chart_info.chart_type}` : ''}
                    </div>
                    {result.error ? (
                      <div style={{ color: 'var(--danger)', padding: 'var(--space-2)' }}>
                        ⚠️ {result.error}
                      </div>
                    ) : (
                      <div className="result-card">
                        {result.answer && (
                          <div className="result-card__answer">{result.answer}</div>
                        )}
                        <SQLResultCard
                          data={{ ...result, answer: result.answer, question: result.chart_info?.description }}
                          messageId={`${id}-chart-${idx}`}
                          onFollowUp={onFollowUp}
                          onRerunSQL={onRerunSQL}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="result-card">
                {/* Answer text */}
                {content && (
                  <div className="result-card__answer">{content}</div>
                )}
                {/* Full result card with all sub-components */}
                <SQLResultCard
                  data={{ ...meta, answer: content, question: meta.question }}
                  messageId={id}
                  onFollowUp={onFollowUp}
                  onRerunSQL={onRerunSQL}
                />
              </div>
            )}
          </div>
        )}
        <div className="message__timestamp">{formatTimeAgo(timestamp)}</div>
      </div>
    </div>
  );
}
