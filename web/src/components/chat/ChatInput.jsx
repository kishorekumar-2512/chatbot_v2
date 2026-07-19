import { useState, useRef } from 'react';
import useChatStore from '../../stores/chatStore.js';

/**
 * ChatInput — message input bar with send button.
 */
export default function ChatInput({ onSend }) {
  const [text, setText] = useState('');
  const [imageBase64, setImageBase64] = useState(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImageBase64(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const removeImage = () => {
    setImageBase64(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = text.trim();
    if ((!q && !imageBase64) || isStreaming) return;
    onSend(q, imageBase64);
    setText('');
    setImageBase64(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    inputRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e);
    }
  };

  return (
    <div className="chat-input-container">
      {imageBase64 && (
        <div className="image-preview">
          <img src={imageBase64} alt="Upload preview" />
          <button type="button" onClick={removeImage} className="remove-image-btn" title="Remove image">×</button>
        </div>
      )}
      <form className="chat-input-wrapper" onSubmit={handleSubmit}>
        <button
          type="button"
          className="chat-input-attach"
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          title="Upload image (Multimodal RAG)"
        >
          📎
        </button>
        <input
          type="file"
          accept="image/*"
          ref={fileInputRef}
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <input
          ref={inputRef}
          className="chat-input"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything or attach a chart image..."
          disabled={isStreaming}
          autoFocus
        />
        <button
          className="chat-input-send"
          type="submit"
          disabled={(!text.trim() && !imageBase64) || isStreaming}
          title="Send message"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
