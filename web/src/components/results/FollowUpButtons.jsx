/**
 * FollowUpButtons — suggestion chips for follow-up queries.
 */
export default function FollowUpButtons({ followups, onSelect }) {
  if (!followups || followups.length === 0) return null;

  return (
    <div className="followup-buttons">
      {followups.map((text, i) => (
        <button key={i} className="followup-btn" onClick={() => onSelect(text)}>
          {text}
        </button>
      ))}
    </div>
  );
}
