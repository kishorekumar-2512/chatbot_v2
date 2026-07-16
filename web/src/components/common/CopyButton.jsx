import { useState } from 'react';

/**
 * CopyButton — copies text to clipboard with visual feedback.
 */
export default function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* fallback for older browsers */
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button className={`copy-btn${copied ? ' copied' : ''}`} onClick={handleCopy}>
      {copied ? '✓ Copied!' : `📋 ${label}`}
    </button>
  );
}
