import { useState, useRef, useEffect } from 'react'
import './ChatInput.css'

function ChatInput({ value, onChange, onSubmit, loading, onStop, placeholder = "Type a message..." }) {
  const textareaRef = useRef(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = '20px'
      const scrollHeight = textarea.scrollHeight
      if (scrollHeight > 20) {
        textarea.style.height = `${Math.min(scrollHeight, 100)}px`
      }
    }
  }, [value])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value && value.trim().length > 0) {
        onSubmit()
      }
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (value && value.trim().length > 0 && !loading) {
      onSubmit()
    }
  }

  const isDisabled = !value || value.trim().length === 0 || loading

  return (
    <form className="chat-input-container" onSubmit={handleSubmit}>
      <div className="chat-input-wrapper">
        <textarea
          ref={textareaRef}
          className="chat-input-textarea"
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          onKeyDown={handleKeyDown}
          disabled={loading}
          rows={1}
        />
        <button
          type="submit"
          className="chat-input-submit"
          disabled={isDisabled || loading}
          onClick={loading && onStop ? (e) => {
            e.preventDefault()
            onStop()
          } : undefined}
        >
          {loading ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 19V5M5 12l7-7 7 7"/>
            </svg>
          )}
        </button>
      </div>
    </form>
  )
}

export default ChatInput
