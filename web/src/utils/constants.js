/* ── Intent icons ── */
export const INTENT_ICONS = {
  COUNT: '🔢',
  TOP_N: '🏆',
  AGGREGATE: '➕',
  TREND: '📈',
  COMPARE: '⚖️',
  EXISTS: '❓',
  LIST: '📋',
  META: '🗂',
};

/* ── Model labels ── */
export const MODEL_LABELS = {
  qwen: { label: 'Qwen 2.5 Coder', color: '#10B981', icon: '🟢' },
  groq: { label: 'Groq · Llama 3.3 70B', color: '#F59E0B', icon: '🟡' },
  gemini: { label: 'Gemini 2.0 Flash', color: '#EF4444', icon: '🔴' },
};

/* ── Provider info for settings ── */
export const PROVIDER_ICONS = {
  openai: '🤖',
  anthropic: '🧠',
  deepseek: '🐋',
  groq: '⚡',
  gemini: '✨',
  ollama: '🦙',
};

/* ── Example queries ── */
export const EXAMPLE_QUERIES = [
  'How many customers are there in total?',
  'Top 10 most installed software',
  'Show login trend by month for the last 6 months',
  'Which customers have the most devices?',
  'Count of patches by severity',
  'List all devices running Windows 11',
  'Compare active vs inactive users',
  'What is the average number of devices per customer?',
  'Show all tables in the database',
];

/* ── Chart re-render detection ── */
export const CHART_REQUEST_RE = /\b(show|display|render|make|give|draw|create|visualize|plot|graph|chart)\b.*\b(chart|graph|plot|bar|line|pie|donut|visual)/i;

/* ── Confidence level thresholds ── */
export const CONFIDENCE = {
  HIGH: 80,
  MEDIUM: 55,
};
