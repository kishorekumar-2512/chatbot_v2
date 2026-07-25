import { get } from './client.js';

/**
 * Get live KPI counts (organizations, devices, alerts, tables, reports)
 * for the home dashboard.
 */
export async function getDashboardStats() {
  return get('/dashboard/stats');
}
