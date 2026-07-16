import { useState, useRef } from 'react';
import useChatStore from '../../stores/chatStore.js';

/**
 * ChatInput — message input bar with send button.
 */
export default function ChatInput({ onSend }) {
  const [text, setText] = useState('');
  const inputRef = useRef(null);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = text.trim();
    if (!q || isStreaming) return;
    onSend(q);
    setText('');
    inputRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e);
    }
  };

  return (
    <div className="chat-input-container">
      <form className="chat-input-wrapper" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          className="chat-input"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your database…"
          disabled={isStreaming}
          autoFocus
        />
        <button
          className="chat-input-send"
          type="submit"
          disabled={!text.trim() || isStreaming}
          title="Send message"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
