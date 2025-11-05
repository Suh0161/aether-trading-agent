import { useState, useEffect, useRef } from 'react'
import ChatInput from '../ChatInput'
import './AgentChat.css'

function AgentChat({ agentMessages }) {
  const [userMessage, setUserMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const chatScrollRef = useRef(null)
  const [isAutoStick, setIsAutoStick] = useState(true)
  const [optimisticMessages, setOptimisticMessages] = useState([])
  const isUserScrolling = useRef(false)
  const scrollTimeoutRef = useRef(null)
  const [showScrollToBottom, setShowScrollToBottom] = useState(false)

  const handleSendMessage = async () => {
    if (!userMessage.trim() || isSending) return
    
    const messageText = userMessage.trim()
    const tempId = `temp_${Date.now()}`
    
    const optimisticUserMsg = {
      id: tempId,
      sender: 'USER',
      text: messageText,
      timestamp: new Date().toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '')
    }
    setOptimisticMessages(prev => [...prev, optimisticUserMsg])
    setUserMessage('')
    setIsSending(true)
    
    requestAnimationFrame(() => {
      const el = chatScrollRef.current
      if (el) {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
      }
    })
    
    try {
      const response = await fetch('/api/agent-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      
      if (!response.ok) {
        const error = await response.json()
        console.error('Error sending message:', error)
        alert(error.detail || 'Failed to send message')
        setOptimisticMessages(prev => prev.filter(m => m.id !== tempId))
      } else {
        setTimeout(() => {
          setOptimisticMessages(prev => prev.filter(m => m.id !== tempId))
        }, 100)
      }
    } catch (error) {
      console.error('Error sending message:', error)
      alert('Failed to send message. Is the backend running?')
      setOptimisticMessages(prev => prev.filter(m => m.id !== tempId))
    } finally {
      setIsSending(false)
    }
  }
  
  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    // Only auto-scroll if user is not actively scrolling and is near the bottom
    if (isAutoStick && !isUserScrolling.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
      // Hide scroll-to-bottom button when auto-scrolling
      setShowScrollToBottom(false)
    }
  }, [agentMessages, optimisticMessages, isAutoStick])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
    }
  }, [])

  const handleChatScroll = () => {
    const el = chatScrollRef.current
    if (!el) return
    
    // Mark that user is actively scrolling
    isUserScrolling.current = true
    
    // Clear any existing timeout
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current)
    }
    
    // Calculate distance from bottom
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    
    // Show scroll-to-bottom button if user is scrolled up more than 100px
    setShowScrollToBottom(distanceFromBottom > 100)
    
    // After scrolling stops, check position
    scrollTimeoutRef.current = setTimeout(() => {
      isUserScrolling.current = false
      // Only enable auto-stick if user is very close to bottom (within 50px)
      setIsAutoStick(distanceFromBottom < 50)
      // Hide button if user is near bottom
      setShowScrollToBottom(distanceFromBottom > 100)
    }, 150)
    
    // Disable auto-stick if user scrolls up significantly
    if (distanceFromBottom > 100) {
      setIsAutoStick(false)
    }
  }

  const handleScrollToBottom = () => {
    const el = chatScrollRef.current
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
      setShowScrollToBottom(false)
      setIsAutoStick(true)
    }
  }

  return (
    <div className="chat-section">
      {agentMessages.length === 0 && optimisticMessages.length === 0 ? (
        <div className="empty-state">
          <p>No messages from Aether yet</p>
        </div>
      ) : (
        <div className="chat-messages" ref={chatScrollRef} onScroll={handleChatScroll}>
          {[...agentMessages, ...optimisticMessages.filter(opt => !agentMessages.some(msg => msg.id === opt.id || (msg.text === opt.text && msg.sender === opt.sender)))].map((message) => {
            // Detect if message contains trade execution keywords
            const isTradeExecution = message.sender !== 'USER' && (
              message.text.toLowerCase().includes('executed') || 
              message.text.toLowerCase().includes('short') || 
              message.text.toLowerCase().includes('long') ||
              message.text.toLowerCase().includes('position')
            )
            
            return (
              <div key={message.id} className={`chat-message ${message.sender === 'USER' ? 'user-message' : ''} ${isTradeExecution ? 'trade-execution' : ''}`}>
                <div className={`message-avatar ${message.sender === 'USER' ? 'user' : 'ai'}`}>
                  {message.sender === 'USER' ? (
                    <img 
                      src="/kungfu_car.png" 
                      alt="User" 
                      className="message-avatar-logo"
                      onError={(e) => {
                        // Fallback to aether.png if kungfu_car.png is missing
                        e.target.onerror = null;
                        e.target.src = '/aether.png';
                      }}
                    />
                  ) : (
                    <img 
                      src="/deepseek.png" 
                      alt="DeepSeek" 
                      className="message-avatar-logo"
                      onError={(e) => {
                        // Fallback to aether.png if deepseek.png is missing
                        e.target.onerror = null;
                        e.target.src = '/aether.png';
                      }}
                    />
                  )}
                </div>
                <div className="message-bubble">
                  <div className="message-content-wrapper">
                    {message.sender !== 'USER' && (
                      <div className="message-header">
                        <span className="message-sender">DeepSeek</span>
                        <span className="message-time">{message.timestamp}</span>
                      </div>
                    )}
                    <div className="message-content">
                      {message.text}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      
      {showScrollToBottom && (
        <button 
          className="scroll-to-bottom-btn"
          onClick={handleScrollToBottom}
          aria-label="Scroll to bottom"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5V19M5 12l7 7l7-7"/>
          </svg>
        </button>
      )}
      
      <ChatInput
        value={userMessage}
        onChange={(e) => setUserMessage(e.target.value)}
        onSubmit={handleSendMessage}
        loading={isSending}
        onStop={() => setIsSending(false)}
        placeholder="Ask Aether anything..."
      />
    </div>
  )
}

export default AgentChat
