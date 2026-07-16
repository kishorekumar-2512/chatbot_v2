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
export async function getKeys(customerId = 'default') {
  return get(`/settings/keys?customer_id=${customerId}`);
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
export async function toggleKey(provider, enabled, customerId = 'default') {
  return patch('/settings/keys/toggle', { provider, enabled, customer_id: customerId });
}

/**
 * Delete a saved key.
 */
export async function deleteKey(provider, customerId = 'default') {
  return del(`/settings/keys/${provider}?customer_id=${customerId}`);
}
