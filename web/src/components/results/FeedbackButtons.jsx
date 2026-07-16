import { useState } from 'react';
import { sendFeedback } from '../../api/chat.js';

/**
 * FeedbackButtons — thumbs up / down feedback with API submission.
 */
export default function FeedbackButtons({ messageId, question, sql, modelUsed, confidence }) {
  const [sent, setSent] = useState(null); // 'up' | 'down' | null

  const handleFeedback = async (rating) => {
    if (sent) return;
    setSent(rating);
    try {
      await sendFeedback({
        question: question || '',
        sql: sql || '',
        rating,
        model_used: modelUsed || '',
        confidence: confidence || {},
      });
    } catch {
      /* best-effort, keep the UI state */
    }
  };

  return (
    <div className="feedback-row">
      <button
        className={`feedback-btn${sent === 'up' ? ' active-up' : ''}${sent ? ' sent' : ''}`}
        onClick={() => handleFeedback('up')}
        disabled={!!sent}
        title="Helpful"
      >
        👍
      </button>
      <button
        className={`feedback-btn${sent === 'down' ? ' active-down' : ''}${sent ? ' sent' : ''}`}
        onClick={() => handleFeedback('down')}
        disabled={!!sent}
        title="Not helpful"
      >
        👎
      </button>
      {sent && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          Thanks for the feedback!
        </span>
      )}
    </div>
  );
}
