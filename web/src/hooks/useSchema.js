import { useEffect, useRef, useCallback } from 'react';
import useChatStore from '../stores/chatStore.js';
import { getHealth, getCircuitStatus, getSchemaStructured } from '../api/schema.js';

const TIER_LABELS = { primary: 'Primary model', fallback1: 'Fallback model', fallback2: 'Second fallback model' };

/**
 * useSchema — manages backend health polling, circuit status, and schema loading.
 * Polls health every 30s. Loads schema on first call.
 */
export default function useSchema() {
  const intervalRef = useRef(null);
  const prevConnectionRef = useRef(null);
  const prevCircuitRef = useRef(null);
  const {
    setConnectionStatus, setCircuitStatus, setSchemaData,
    connectionStatus, circuitStatus, schemaData,
  } = useChatStore();

  /* Diff the new circuit breaker snapshot against the last one and notify
     on state changes (a tier going down or recovering), rather than
     silently re-rendering the sidebar every 30s. */
  const diffCircuitStatus = useCallback((next) => {
    const prev = prevCircuitRef.current;
    if (prev && next) {
      for (const tier of ['primary', 'fallback1', 'fallback2']) {
        const before = prev[tier]?.circuit_open;
        const after = next[tier]?.circuit_open;
        if (before === undefined || after === undefined || before === after) continue;
        const label = TIER_LABELS[tier] || tier;
        const modelName = next[tier]?.name || tier;
        if (after === true) {
          useChatStore.getState().notify('warning', `${label} unavailable`, `${modelName} is failing repeatedly — routing moved to the next fallback.`);
        } else {
          useChatStore.getState().notify('success', `${label} recovered`, `${modelName} is back online and active again.`);
        }
      }
    }
    prevCircuitRef.current = next;
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const data = await getHealth();
      const prevStatus = prevConnectionRef.current;
      useChatStore.getState().setConnectionStatus('online');
      if (prevStatus === 'offline') {
        useChatStore.getState().notify('success', 'Reconnected', 'Connection to the backend has been restored.');
      }
      prevConnectionRef.current = 'online';
      if (data.circuit_breaker) {
        diffCircuitStatus(data.circuit_breaker);
        useChatStore.getState().setCircuitStatus(data.circuit_breaker);
      }
    } catch {
      const prevStatus = prevConnectionRef.current;
      useChatStore.getState().setConnectionStatus('offline');
      if (prevStatus === 'online' || prevStatus === null) {
        useChatStore.getState().notify('error', 'Connection lost', 'Cannot reach the backend — check that the server is running.');
      }
      prevConnectionRef.current = 'offline';
    }
  }, [diffCircuitStatus]);

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

  // Start health polling and load schema on mount
  useEffect(() => {
    checkHealth();
    loadSchema();
    intervalRef.current = setInterval(checkHealth, 30_000);
    return () => clearInterval(intervalRef.current);
  }, [checkHealth, loadSchema]);

  return { checkHealth, refreshCircuit, loadSchema, connectionStatus, circuitStatus, schemaData };
}
