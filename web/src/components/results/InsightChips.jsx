/**
 * InsightChips — colored pills displaying auto-generated insights.
 */
export default function InsightChips({ insights }) {
  if (!insights || insights.length === 0) return null;

  return (
    <div className="insight-chips">
      {insights.map((text, i) => (
        <span key={i} className="insight-chip">✦ {text}</span>
      ))}
    </div>
  );
}
