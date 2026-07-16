/**
 * Parse Server-Sent Events (SSE) from a ReadableStream.
 *
 * Yields objects: { event, data } for each SSE message.
 * Handles multi-line data fields and reconnection.
 */
export async function* parseSSEStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent = 'message';
      let currentData = '';

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          currentData += line.slice(5).trim();
        } else if (line === '') {
          // Empty line = end of message
          if (currentData) {
            try {
              yield { event: currentEvent, data: JSON.parse(currentData) };
            } catch {
              yield { event: currentEvent, data: currentData };
            }
          }
          currentEvent = 'message';
          currentData = '';
        }
      }
    }

    // Flush remaining buffer
    if (buffer.trim()) {
      const lines = buffer.split('\n');
      let currentData = '';
      for (const line of lines) {
        if (line.startsWith('data:')) {
          currentData += line.slice(5).trim();
        }
      }
      if (currentData) {
        try {
          yield { event: 'message', data: JSON.parse(currentData) };
        } catch {
          yield { event: 'message', data: currentData };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
