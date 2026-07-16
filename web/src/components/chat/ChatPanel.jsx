import { useRef, useEffect } from 'react';
import useChatStore from '../../stores/chatStore.js';
import useChat from '../../hooks/useChat.js';
import MessageBubble from './MessageBubble.jsx';
import ThinkingStream from './ThinkingStream.jsx';
import ChatInput from './ChatInput.jsx';

/**
 * ChatPanel — main chat container with message list, streaming, and input.
 */
export default function ChatPanel() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamingStatus = useChatStore((s) => s.streamingStatus);
  const thinkingTokens = useChatStore((s) => s.thinkingTokens);
  const { send, rerunSQL } = useChat();
  const bottomRef = useRef(null);

  /* Auto-scroll on new messages or thinking tokens */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinkingTokens, isStreaming]);

  const handleFollowUp = (text) => send(text);
  const handleRerun = (sql, question, msgId) => rerunSQL(sql, question, msgId);

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        <div className="chat-messages__inner">
          {messages.length === 0 ? (
            /* ── Welcome screen ── */
            <div className="chat-welcome">
              <div className="chat-welcome__icon">🗃️</div>
              <h1 className="chat-welcome__title">AI Database Assistant</h1>
              <p className="chat-welcome__subtitle">
                Ask questions about your database in plain English. 
                I'll generate SQL, run it, and show you results with charts, 
                insights, and confidence scoring.
              </p>
            </div>
          ) : (
            /* ── Message list ── */
            messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onFollowUp={handleFollowUp}
                onRerunSQL={handleRerun}
              />
            ))
          )}

          {/* ── Streaming thinking display ── */}
          {isStreaming && (thinkingTokens || streamingStatus) && (
            <div className="message message--assistant">
              <div className="message__avatar">🤖</div>
              <div className="message__body">
                <div className="message__content">
                  <ThinkingStream tokens={thinkingTokens} status={streamingStatus} />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <ChatInput onSend={send} />
    </div>
  );
}
