import { get } from './client.js';

/**
 * Health check — returns { status, circuit_breaker, embedding_index_ready }.
 */
export async function getHealth() {
  return get('/health');
}

/**
 * Get circuit breaker status for all tiers.
 */
export async function getCircuitStatus() {
  return get('/circuit-status');
}

/**
 * Get full schema text + table list.
 */
export async function getSchema() {
  return get('/schema');
}

/**
 * Get structured table list with columns (for schema explorer).
 * Falls back to /schema if /schema/tables is not available.
 */
export async function getSchemaStructured() {
  try {
    return await get('/schema/tables');
  } catch {
    // Fallback: parse from /schema
    const data = await get('/schema');
    return { tables: data.tables || [], raw: data.schema };
  }
}
