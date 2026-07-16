import { useCallback, useRef } from 'react';
import useChatStore from '../stores/chatStore.js';
import { sendChatStream, runSQL } from '../api/chat.js';
import { parseSSEStream } from '../utils/sseParser.js';
import { CHART_REQUEST_RE } from '../utils/constants.js';

/**
 * useChat — core chat hook that manages sending questions,
 * SSE streaming, chart re-render interception, and SQL re-runs.
 */
export default function useChat() {
  const store = useChatStore();
  const abortRef = useRef(null);

  const send = useCallback(async (question) => {
    if (!question.trim() || store.isStreaming) return;

    const {
      addMessage, updateMessage, setStreaming, setStreamingStatus,
      appendThinking, resetThinking, setLastResult, setConversationContext,
      addToHistory, conversationContext, orgId, lastResult,
    } = useChatStore.getState();

    /* ── Chart re-render interception ── */
    if (CHART_REQUEST_RE.test(question) && lastResult?.sql) {
      addMessage('user', question);
      const msgId = addMessage('assistant', '', { loading: true });
      try {
        const result = await runSQL(lastResult.sql, lastResult.question || question);
        updateMessage(msgId, {
          content: result.answer || 'Here is the updated visualization.',
          meta: { ...result, loading: false },
        });
        setLastResult(result);
      } catch (err) {
        updateMessage(msgId, {
          content: `Error: ${err.message}`,
          meta: { loading: false, error: true },
        });
      }
      return;
    }

    /* ── Normal chat flow ── */
    addMessage('user', question);
    const msgId = addMessage('assistant', '', { loading: true });
    setStreaming(true);
    resetThinking();

    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      const response = await sendChatStream(question, conversationContext, orgId);
      let finalData = null;

      for await (const { event, data } of parseSSEStream(response)) {
        if (abortController.signal.aborted) break;

        switch (event) {
          case 'message':
            if (data.type === 'status') {
              setStreamingStatus(data.message || data.status || '');
            } else if (data.type === 'thinking_token') {
              appendThinking(data.text || '');
            } else if (data.type === 'final') {
              finalData = data.data;
            } else if (data.type === 'error') {
              updateMessage(msgId, {
                content: `Error: ${data.message || 'Unknown error'}`,
                meta: { loading: false, error: true },
              });
            }
            break;
          default:
            break;
        }
      }

      if (finalData) {
        updateMessage(msgId, {
          content: finalData.answer || '',
          meta: { ...finalData, loading: false },
        });

        setLastResult(finalData);
        addToHistory(question, finalData.sql);

        if (finalData.sql) {
          setConversationContext({
            question,
            sql: finalData.sql,
            tables_used: finalData.tables_used || [],
          });
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        updateMessage(msgId, {
          content: `Connection error: ${err.message}`,
          meta: { loading: false, error: true },
        });
      }
    } finally {
      setStreaming(false);
      resetThinking();
      abortRef.current = null;
    }
  }, []);

  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      useChatStore.getState().setStreaming(false);
    }
  }, []);

  const rerunSQL = useCallback(async (sql, question, msgId) => {
    const { updateMessage, setLastResult } = useChatStore.getState();
    updateMessage(msgId, { meta: { rerunning: true } });
    try {
      const result = await runSQL(sql, question);
      updateMessage(msgId, {
        content: result.answer || 'SQL executed successfully.',
        meta: { ...result, loading: false, rerunning: false },
      });
      setLastResult(result);
    } catch (err) {
      updateMessage(msgId, {
        meta: { rerunning: false, rerunError: err.message },
      });
    }
  }, []);

  return { send, stopStreaming, rerunSQL };
}
