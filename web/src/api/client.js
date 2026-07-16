/**
 * API Client — base fetch wrapper.
 *
 * In development, Vite proxies /api/* to http://localhost:8000/*.
 * In production, set VITE_API_URL to the backend URL.
 */
const BASE = import.meta.env.VITE_API_URL || '/api';

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }

  return res;
}

export async function get(path) {
  const res = await request(path);
  return res.json();
}

export async function post(path, body) {
  const res = await request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function patch(path, body) {
  const res = await request(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function del(path) {
  const res = await request(path, { method: 'DELETE' });
  return res.json();
}

/**
 * Stream a POST request (for SSE). Returns the raw Response for stream parsing.
 */
export async function postStream(path, body) {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }

  return res;
}

/**
 * Download a binary response (for PDF).
 */
export async function postDownload(path, body) {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }

  return res.blob();
}
