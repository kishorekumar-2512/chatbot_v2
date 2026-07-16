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
          <div className="message__content">{content}</div>
        ) : (
          /* ── Assistant message ── */
          <div className="message__content">
            {meta.loading ? (
              <TypingIndicator />
            ) : meta.error ? (
              <div style={{ color: 'var(--danger)' }}>
                ⚠️ {content || 'Something went wrong'}
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
