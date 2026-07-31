import { get, post, patch, del } from './client.js';

/**
 * List all supported LLM providers + their models.
 */
export async function getProviders() {
  return get('/settings/providers');
}

/**
 * List configured API keys (masked).
 */
export async function getKeys(customerId = '') {
  return get(`/settings/keys?customer_id=${encodeURIComponent(customerId)}`);
}

/**
 * System + BYO LLM configuration status.
 */
export async function getLlmStatus(customerId = '') {
  return get(`/settings/llm-status?customer_id=${encodeURIComponent(customerId)}`);
}

/**
 * Save an API key.
 */
export async function saveKey(data) {
  return post('/settings/keys', data);
}

/**
 * Validate an API key without saving.
 */
export async function validateKey(data) {
  return post('/settings/keys/validate', data);
}

/**
 * Toggle a key enabled/disabled.
 */
export async function toggleKey(provider, enabled, customerId = '') {
  return patch('/settings/keys/toggle', { provider, enabled, customer_id: customerId });
}

/**
 * Delete a saved key.
 */
export async function deleteKey(provider, customerId = '') {
  return del(`/settings/keys/${provider}?customer_id=${customerId}`);
}
