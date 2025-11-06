import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import './Positions.css'

function Positions({ positions }) {
  const [hoveredRow, setHoveredRow] = useState(null)
  const [showExitPlan, setShowExitPlan] = useState(null)
  const rowRefs = useRef({})

  const totalUnrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealPnL, 0)
  
  // Calculate average leverage from positions (based on AI confidence, not hardcoded)
  // Leverage is whole numbers only (1x or 2x) - Binance doesn't support decimals
  const calculateAverageLeverage = () => {
    if (positions.length === 0) return null
    const leverages = positions.map(pos => {
      // Parse leverage string like "2X" or "1X" to number (whole numbers only)
      const leverageStr = pos.leverage || '1X'
      const leverageNum = parseInt(leverageStr.replace(/[Xx]/g, ''), 10) || 1
      return leverageNum
    })
    const sum = leverages.reduce((acc, lev) => acc + lev, 0)
    // Round to whole number (no decimals)
    return Math.round(sum / leverages.length)
  }
  
  const averageLeverage = calculateAverageLeverage()
  
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
    setShowExitPlan(newValue)
    if (newValue !== null) {
      setHoveredRow(index)
    }
  }
  
  const closeExitPlan = () => {
    setShowExitPlan(null)
  }

  return (
    <div className="positions-section">
      <div className="positions-header">
        <div className="positions-stats">
          <span className="stat-label">Total Unrealized P&L:</span>
          <span className={`stat-value ${totalUnrealizedPnL >= 0 ? 'positive' : 'negative'}`}>
            ${totalUnrealizedPnL.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </span>
        </div>
        {averageLeverage && (
          <div className="positions-stats" style={{ marginTop: '8px' }}>
            <span className="stat-label">Avg Leverage:</span>
            <span className="stat-value">{averageLeverage}x</span>
          </div>
        )}
      </div>

      {positions.length === 0 ? (
        <div className="empty-state">
          <p>No open positions</p>
        </div>
      ) : (
        <div className="positions-table">
          <div className="table-body">
            {positions.map((position, index) => {
              const pnlPercent = position.pnlPercent || 0
              const isHovered = hoveredRow === index
              const showPlan = showExitPlan === index
              
              const entryPrice = position.entryPrice || 0
              const currentPrice = position.currentPrice || 0
              const target = position.takeProfit || null
              const stop = position.stopLoss || null
              const side = position.side || 'LONG'
              const isLong = side === 'LONG'
              
              // Calculate distances to TP and SL
              let tpDistance = null
              let slDistance = null
              let riskReward = null
              
              if (target && currentPrice > 0) {
                tpDistance = isLong 
                  ? ((target - currentPrice) / currentPrice * 100)
                  : ((currentPrice - target) / currentPrice * 100)
              }
              
              if (stop && currentPrice > 0) {
                slDistance = isLong
                  ? ((currentPrice - stop) / currentPrice * 100)
                  : ((stop - currentPrice) / currentPrice * 100)
              }
              
              if (target && stop && entryPrice > 0) {
                const risk = Math.abs(entryPrice - stop)
                const reward = Math.abs(target - entryPrice)
                if (risk > 0) {
                  riskReward = (reward / risk).toFixed(2)
                }
              }
              
              return (
                <div 
                  key={index} 
                  ref={el => rowRefs.current[index] = el}
                  className="table-row"
                  onMouseEnter={() => setHoveredRow(index)}
                  onMouseLeave={(e) => {
                    try {
                      const target = e.relatedTarget
                      if (target && target.nodeType === 1 && typeof target.closest === 'function') {
                        if (target.closest('.exit-plan-modal') || target.closest('.row-menu-btn')) {
                          return
                        }
                      }
                      setHoveredRow(null)
                    } catch (err) {
                      setHoveredRow(null)
                    }
                  }}
                >
                  <div className="position-card-header">
                    <div className="position-main-info">
                      <span className="col-coin">{position.coin}</span>
                      <span className={`col-side ${position.side.toLowerCase()}`}>
                        {position.side}
                      </span>
                      {position.positionType && (
                        <span className={`position-type-badge ${position.positionType}`} title={position.positionType.toUpperCase()}>
                          {position.positionType.toUpperCase()}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="position-card-body">
                    <div className="position-metric">
                      <span className="metric-label-small">Leverage</span>
                      <span className="col-leverage">{position.leverage}</span>
                    </div>
                    <div className="position-metric">
                      <span className="metric-label-small">Notional</span>
                      <span className="col-notional">
                        ${position.notional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div className="position-metric">
                      <span className="metric-label-small">Return</span>
                      <span className={`metric-value-small ${position.unrealPnL >= 0 ? 'positive' : 'negative'}`}>
                        {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                      </span>
                    </div>
                  </div>

                  <div className={`position-pnl-section col-pnl ${position.unrealPnL >= 0 ? 'positive' : 'negative'}`}>
                    <div className="pnl-amount">${position.unrealPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
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
                      if (!rowEl) return null
                      
                      const rect = rowEl.getBoundingClientRect()
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
                            <div className="exit-plan-row">
                              <span className="exit-plan-label">Type</span>
                              <div className="exit-plan-value-wrapper">
                                <span className={`exit-plan-type-badge ${position.positionType === 'swing' ? 'swing' : 'scalp'}`}>
                                  {position.positionType ? position.positionType.toUpperCase() : 'SWING'}
                                </span>
                              </div>
                            </div>
                            <div className="exit-plan-row">
                              <span className="exit-plan-label">Entry</span>
                              <div className="exit-plan-value-wrapper">
                                <span className="exit-plan-value">${entryPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                <span className="exit-plan-note">{position.leverage}</span>
                              </div>
                            </div>
                            <div className="exit-plan-row">
                              <span className="exit-plan-label">Current</span>
                              <div className="exit-plan-value-wrapper">
                                <span className={`exit-plan-value ${position.unrealPnL >= 0 ? 'positive' : 'negative'}`}>
                                  ${currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                                <span className="exit-plan-note">{pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%</span>
                              </div>
                            </div>
                            
                            <div className="exit-plan-divider"></div>
                            
                            <div className="exit-plan-row exit-plan-target">
                              <span className="exit-plan-label">TP</span>
                              <div className="exit-plan-value-wrapper">
                                <span className="exit-plan-value">${target ? target.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                                {tpDistance !== null && (
                                  <span className="exit-plan-note positive">+{tpDistance.toFixed(2)}% • ${Math.abs(target - currentPrice).toFixed(2)}</span>
                                )}
                              </div>
                            </div>
                            <div className="exit-plan-row exit-plan-stop">
                              <span className="exit-plan-label">SL</span>
                              <div className="exit-plan-value-wrapper">
                                <span className="exit-plan-value">${stop ? stop.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}</span>
                                {slDistance !== null && (
                                  <span className="exit-plan-note negative">-{slDistance.toFixed(2)}% • ${Math.abs(currentPrice - stop).toFixed(2)}</span>
                                )}
                              </div>
                            </div>
                            
                            {riskReward && (
                              <>
                                <div className="exit-plan-divider"></div>
                                <div className="exit-plan-row">
                                  <span className="exit-plan-label">R:R</span>
                                  <div className="exit-plan-value-wrapper">
                                    <span className="exit-plan-value">1:{riskReward}</span>
                                    <span className="exit-plan-note">{parseFloat(riskReward) >= 2 ? 'Good' : parseFloat(riskReward) >= 1.5 ? 'Fair' : 'Low'}</span>
                                  </div>
                                </div>
                              </>
                            )}
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
  )
}

export default Positions
