import { useRef, useEffect } from 'react';

/**
 * ThinkingStream — displays live model reasoning tokens with auto-scroll.
 */
export default function ThinkingStream({ tokens, status }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [tokens]);

  if (!tokens && !status) return null;

  return (
    <div className="thinking-stream">
      <div className="thinking-stream__header">
        🧠 Model reasoning…
      </div>
      {status && (
        <>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-accent)', marginBottom: 'var(--space-2)' }}>
            {status}
          </div>
          <div className="shimmer-bar"><div className="shimmer-bar__fill" /></div>
        </>
      )}
      {tokens && (
        <div className="thinking-stream__content">
          {tokens}
          <span ref={endRef} />
        </div>
      )}
    </div>
  );
}
