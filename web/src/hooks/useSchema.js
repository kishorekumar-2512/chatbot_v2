import { useEffect, useRef, useCallback } from 'react';
import useChatStore from '../stores/chatStore.js';
import { getHealth, getCircuitStatus, getSchemaStructured } from '../api/schema.js';

/**
 * useSchema — manages backend health polling, circuit status, and schema loading.
 * Polls health every 30s. Loads schema on first call.
 */
export default function useSchema() {
  const intervalRef = useRef(null);
  const {
    setConnectionStatus, setCircuitStatus, setSchemaData,
    connectionStatus, circuitStatus, schemaData,
  } = useChatStore();

  const checkHealth = useCallback(async () => {
    try {
      const data = await getHealth();
      useChatStore.getState().setConnectionStatus('online');
      if (data.circuit_breaker) {
        useChatStore.getState().setCircuitStatus(data.circuit_breaker);
      }
    } catch {
      useChatStore.getState().setConnectionStatus('offline');
    }
  }, []);

  const refreshCircuit = useCallback(async () => {
    try {
      const data = await getCircuitStatus();
      setCircuitStatus(data);
    } catch {
      // silently fail
    }
  }, [setCircuitStatus]);

  const loadSchema = useCallback(async () => {
    try {
      const data = await getSchemaStructured();
      setSchemaData(data);
    } catch {
      // silently fail
    }
  }, [setSchemaData]);

  // Start health polling on mount
  useEffect(() => {
    checkHealth();
    intervalRef.current = setInterval(checkHealth, 30_000);
    return () => clearInterval(intervalRef.current);
  }, [checkHealth]);

  return { checkHealth, refreshCircuit, loadSchema, connectionStatus, circuitStatus, schemaData };
}
