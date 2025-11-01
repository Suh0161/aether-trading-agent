import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import './Sidebar.css'

function Sidebar({ positions, trades, agentMessages }) {
  const [activeTab, setActiveTab] = useState('positions')
  const [hoveredRow, setHoveredRow] = useState(null)
  const [showExitPlan, setShowExitPlan] = useState(null)
  const rowRefs = useRef({})
  const [userMessage, setUserMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const chatScrollRef = useRef(null)
  const [isAutoStick, setIsAutoStick] = useState(true)
  const [optimisticMessages, setOptimisticMessages] = useState([])

  const totalUnrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealPnL, 0)
  
  // Handle sending user message
  const handleSendMessage = async (e) => {
    e.preventDefault()
    if (!userMessage.trim() || isSending) return
    
    const messageText = userMessage.trim()
    const tempId = `temp_${Date.now()}`
    
    // Add optimistic user message immediately
    const optimisticUserMsg = {
      id: tempId,
      sender: 'USER',
      text: messageText,
      timestamp: new Date().toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '')
    }
    setOptimisticMessages(prev => [...prev, optimisticUserMsg])
    setUserMessage('')
    setIsSending(true)
    
    // Scroll to bottom immediately
    requestAnimationFrame(() => {
      const el = chatScrollRef.current
      if (el) {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
      }
    })
    
    try {
      const response = await fetch('http://localhost:8000/api/agent-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
      })
      
      if (!response.ok) {
        const error = await response.json()
        console.error('Error sending message:', error)
        alert(error.detail || 'Failed to send message')
        // Remove optimistic message on error
        setOptimisticMessages(prev => prev.filter(m => m.id !== tempId))
      } else {
        // Clear optimistic message immediately (will be filtered out by duplicate check anyway)
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
  
  // Auto-stick to bottom when new messages arrive only if user is near bottom
  useEffect(() => {
    if (activeTab !== 'chat') return
    const el = chatScrollRef.current
    if (!el) return
    if (isAutoStick) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [agentMessages, optimisticMessages, activeTab, isAutoStick])

  const handleChatScroll = () => {
    const el = chatScrollRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setIsAutoStick(distanceFromBottom < 120)
  }
  
  // Close exit plan when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (showExitPlan !== null) {
        const modal = document.querySelector('.exit-plan-modal')
        const button = e.target.closest('.row-menu-btn')
        if (modal && !modal.contains(e.target) && !button) {
          setShowExitPlan(null)
        }
      }
    }
    
    if (showExitPlan !== null) {
      // Use setTimeout to avoid immediate closure
      setTimeout(() => {
        document.addEventListener('click', handleClickOutside)
      }, 100)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [showExitPlan])
  
  const handleMenuClick = (index, e) => {
    e.stopPropagation()
    e.preventDefault()
    const newValue = showExitPlan === index ? null : index
    console.log('Menu clicked, index:', index, 'newValue:', newValue)
    setShowExitPlan(newValue)
    // Keep row hovered when showing modal
    if (newValue !== null) {
      setHoveredRow(index)
    }
  }
  
  const closeExitPlan = () => {
    setShowExitPlan(null)
  }

  return (
    <div className="sidebar">
      <div className="sidebar-tabs">
        <button
          className={`tab ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => setActiveTab('positions')}
        >
          Positions
        </button>
        <button
          className={`tab ${activeTab === 'trades' ? 'active' : ''}`}
          onClick={() => setActiveTab('trades')}
        >
          Completed Trades
        </button>
        <button
          className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          Agent Chat
        </button>
      </div>

      <div 
        className={`sidebar-content ${activeTab === 'chat' ? 'no-padding' : ''}`}
      >
        {activeTab === 'positions' && (
          <div className="positions-section">
            <div className="positions-header">
              <div className="positions-stats">
                <span className="stat-label">Total Unrealized P&L:</span>
                <span className={`stat-value ${totalUnrealizedPnL >= 0 ? 'positive' : 'negative'}`}>
                  ${totalUnrealizedPnL.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            {positions.length === 0 ? (
              <div className="empty-state">
                <p>No open positions</p>
              </div>
            ) : (
              <div className="positions-table">
                <div className="table-header">
                  <div className="col-side">SIDE</div>
                  <div className="col-coin">COIN</div>
                  <div className="col-leverage">LEVERAGE</div>
                  <div className="col-notional">NOTIONAL</div>
                  <div className="col-pnl">UNREAL P&L</div>
                </div>

                <div className="table-body">
                  {positions.map((position, index) => {
                    const entryPrice = position.entryPrice || 0
                    const currentPrice = position.currentPrice || 0
                    const pnlPercent = position.pnlPercentage || 0
                    const isHovered = hoveredRow === index
                    const showPlan = showExitPlan === index
                    
                    // Format exit plan values
                    const target = position.takeProfit || null
                    const stop = position.stopLoss || null
                    const invalidCondition = position.invalidCondition || 
                      "Close early only if a 4h candle closes above target AND the 4h MACD histogram turns positive for 2 consecutive bars."
                    
                    return (
                      <div 
                        key={index} 
                        ref={el => rowRefs.current[index] = el}
                        className="table-row"
                        onMouseEnter={() => setHoveredRow(index)}
                        onMouseLeave={(e) => {
                          // Don't hide if mouse is moving to modal or button
                          try {
                            const target = e.relatedTarget
                            // Check if target is a valid DOM element with closest method
                            if (target && target.nodeType === 1 && typeof target.closest === 'function') {
                              // Don't hide if moving to modal or button
                              if (target.closest('.exit-plan-modal') || target.closest('.row-menu-btn')) {
                                return
                              }
                            }
                            // Hide in all other cases
                            setHoveredRow(null)
                          } catch (err) {
                            // On any error, just hide
                            setHoveredRow(null)
                          }
                        }}
                      >
                        <div className={`col-side ${position.side.toLowerCase()}`}>
                          {position.side}
                        </div>
                        <div className="col-coin">
                          <span className="coin-name">{position.coin}</span>
                        </div>
                        <div className="col-leverage">{position.leverage}</div>
                        <div className="col-notional">
                          ${position.notional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <div className={`col-pnl ${position.unrealPnL >= 0 ? 'positive' : 'negative'}`}>
                          <div className="pnl-amount">${position.unrealPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                          <div className={`pnl-percent ${position.unrealPnL >= 0 ? 'positive' : 'negative'}`}>
                            {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                          </div>
                        </div>
                        {(isHovered || showPlan) && (
                          <button 
                            className="row-menu-btn"
                            onClick={(e) => handleMenuClick(index, e)}
                            onMouseEnter={() => setHoveredRow(index)}
                          >
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                              <circle cx="8" cy="4" r="1.5" fill="currentColor"/>
                              <circle cx="8" cy="8" r="1.5" fill="currentColor"/>
                              <circle cx="8" cy="12" r="1.5" fill="currentColor"/>
                            </svg>
                          </button>
                        )}
                        {showPlan && createPortal(
                          (() => {
                            const rowEl = rowRefs.current[index]
                            if (!rowEl) {
                              return null
                            }
                            // Force layout calculation
                            const rect = rowEl.getBoundingClientRect()
                            // Ensure modal stays within viewport
                            const modalWidth = 260
                            const modalLeft = Math.min(rect.right + 10, window.innerWidth - modalWidth - 20)
                            
                            return (
                              <div 
                                className="exit-plan-modal" 
                                style={{
                                  position: 'fixed',
                                  top: `${rect.top}px`,
                                  left: `${modalLeft}px`,
                                  display: 'block',
                                  zIndex: 10000,
                                  transform: 'translateZ(0)'
                                }}
                                onClick={(e) => e.stopPropagation()}
                                onMouseEnter={() => setHoveredRow(index)}
                              >
                                <div className="exit-plan-header">
                                  <h3>Exit Plan</h3>
                                  <button className="exit-plan-close" onClick={(e) => {
                                    e.stopPropagation()
                                    closeExitPlan()
                                  }}>×</button>
                                </div>
                                <div className="exit-plan-content">
                                  <div className="exit-plan-item">
                                    <span className="exit-plan-label">Target:</span>
                                    <span className="exit-plan-value">
                                      {target ? `$${target.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'Not set'}
                                    </span>
                                  </div>
                                  <div className="exit-plan-item">
                                    <span className="exit-plan-label">Stop:</span>
                                    <span className="exit-plan-value">
                                      {stop ? `$${stop.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'Not set'}
                                    </span>
                                  </div>
                                  <div className="exit-plan-item invalid-condition">
                                    <span className="exit-plan-label">Invalid Condition:</span>
                                    <span className="exit-plan-value">{invalidCondition}</span>
                                  </div>
                                </div>
                              </div>
                            )
                          })(),
                          document.body
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'trades' && (
          <div className="trades-section">
            {trades.length === 0 ? (
              <div className="empty-state">
                <p>No completed trades yet</p>
              </div>
            ) : (
              <div className="trades-list">
                {[...trades].reverse().map((trade) => (
                  <div key={trade.id} className={`trade-card ${trade.pnl >= 0 ? 'profit' : 'loss'}`}>
                    <div className="trade-content">
                      <div className="trade-header-section">
                        <div className="trade-header-top">
                          <div className="agent-badge">
                            <img src="/deepseek.png" alt="DeepSeek" className="agent-badge-logo" />
                            <span>DeepSeek</span>
                          </div>
                          <span className="trade-time">{trade.timestamp}</span>
                        </div>
                        <div className="trade-summary">
                          completed a <span className={`trade-side ${trade.side.toLowerCase()}`}>{trade.side.toLowerCase()}</span> trade on <span className="trade-coin">{trade.coin}</span>
                        </div>
                      </div>
                      
                      <div className="trade-metrics">
                        <div className="metric-row">
                          <div className="metric-item">
                            <span className="metric-label">Price:</span>
                            <span className="metric-value">
                              ${typeof trade.entryPrice === 'number' 
                                ? trade.entryPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                : trade.entryPrice} → ${typeof trade.exitPrice === 'number'
                                ? trade.exitPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                : trade.exitPrice}
                            </span>
                          </div>
                          <div className="metric-item">
                            <span className="metric-label">Quantity:</span>
                            <span className="metric-value">
                              {typeof trade.quantity === 'number' 
                                ? trade.quantity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })
                                : trade.quantity}
                            </span>
                          </div>
                        </div>
                        
                        <div className="metric-row">
                          <div className="metric-item">
                            <span className="metric-label">Notional:</span>
                            <span className="metric-value">
                              ${trade.entryNotional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} → ${trade.exitNotional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                          </div>
                          <div className="metric-item">
                            <span className="metric-label">Holding Time:</span>
                            <span className="metric-value">{trade.holdingTime}</span>
                          </div>
                        </div>
                        
                        <div className="metric-row pnl-row">
                          <div className="metric-item pnl-item">
                            <span className="metric-label">NET P&L:</span>
                            <span className={`metric-value pnl-value ${trade.pnl >= 0 ? 'positive' : 'negative'}`}>
                              ${trade.pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="chat-section">
            {agentMessages.length === 0 && optimisticMessages.length === 0 ? (
              <div className="empty-state">
                <p>No agent messages yet</p>
              </div>
            ) : (
              <div className="chat-messages" ref={chatScrollRef} onScroll={handleChatScroll}>
                {[...agentMessages, ...optimisticMessages.filter(opt => !agentMessages.some(msg => msg.id === opt.id || (msg.text === opt.text && msg.sender === opt.sender)))].map((message) => (
                  <div key={message.id} className={`chat-message ${message.sender === 'USER' ? 'user-message' : ''}`}>
                    <div className="message-header">
                      {message.sender === 'USER' ? (
                        <>
                          <span className="message-sender user-sender">YOU</span>
                          <span className="message-time">{message.timestamp}</span>
                        </>
                      ) : (
                        <>
                          <div className="message-sender-wrapper">
                            <img src="/deepseek.png" alt="DeepSeek" className="message-avatar-logo" />
                            <span className="message-sender">DEEPSEEK</span>
                          </div>
                          <span className="message-time">{message.timestamp}</span>
                        </>
                      )}
                    </div>
                    <div className="message-content">
                      {message.text}
                    </div>
                  </div>
                ))}
              </div>
            )}
            
            <form className="chat-input-form" onSubmit={handleSendMessage}>
              <div className="chat-input-wrapper">
                <input
                  type="text"
                  className="chat-input"
                  placeholder="Ask the agent anything..."
                  value={userMessage}
                  onChange={(e) => setUserMessage(e.target.value)}
                  disabled={isSending}
                />
                <button
                  type="submit"
                  className="chat-send-btn"
                  disabled={isSending || !userMessage.trim()}
                  aria-label="Send message"
                >
                  {isSending ? (
                    <svg className="send-icon spinning" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" opacity="0.25"/>
                      <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round"/>
                    </svg>
                  ) : (
                    <svg className="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                    </svg>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  )
}

export default Sidebar
