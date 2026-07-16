/**
 * Format a number with commas and optional decimal places.
 */
export function formatNumber(num, decimals = 0) {
  if (num == null || isNaN(num)) return '—';
  return Number(num).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format milliseconds to a human-readable latency string.
 */
export function formatLatency(ms) {
  if (ms == null) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format a timestamp to relative time (e.g., "2 min ago").
 */
export function formatTimeAgo(timestamp) {
  const now = Date.now();
  const ts = typeof timestamp === 'number' && timestamp < 1e12
    ? timestamp * 1000  // unix seconds → ms
    : timestamp;
  const diff = now - ts;

  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} min ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

/**
 * Truncate text with ellipsis.
 */
export function truncate(text, maxLen = 120) {
  if (!text || text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '…';
}

/**
 * Capitalize first letter.
 */
export function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Get confidence level from score.
 */
export function getConfidenceLevel(score) {
  if (score >= 80) return 'high';
  if (score >= 55) return 'medium';
  return 'low';
}

/**
 * Generate a unique ID for messages / keys.
 */
export function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
