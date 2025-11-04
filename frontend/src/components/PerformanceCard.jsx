import { useEffect } from 'react'
import './PerformanceCard.css'

function PerformanceCard({ trades, balance, onClose }) {
  // Calculate performance metrics
  const totalTrades = trades.length
  const winningTrades = trades.filter(t => t.pnl > 0).length
  const losingTrades = trades.filter(t => t.pnl < 0).length
  const winRate = totalTrades > 0 ? (winningTrades / totalTrades * 100) : 0
  
  const totalPnL = trades.reduce((sum, t) => sum + t.pnl, 0)
  const avgWin = winningTrades > 0 
    ? trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) / winningTrades 
    : 0
  const avgLoss = losingTrades > 0 
    ? trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0) / losingTrades 
    : 0
  
  const bestTrade = trades.length > 0 
    ? Math.max(...trades.map(t => t.pnl)) 
    : 0
  const worstTrade = trades.length > 0 
    ? Math.min(...trades.map(t => t.pnl)) 
    : 0
  
  const profitFactor = avgLoss !== 0 ? Math.abs(avgWin / avgLoss) : 0

  // Close on ESC key
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  return (
    <div className="performance-overlay" onClick={onClose}>
      <div className="performance-card" onClick={(e) => e.stopPropagation()}>
        <div className="performance-header">
          <h2>Performance Metrics</h2>
          <button className="performance-close" onClick={onClose}>×</button>
        </div>
        
        <div className="performance-grid">
          <div className="metric-card">
            <div className="metric-label">Total Trades</div>
            <div className="metric-value">{totalTrades}</div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Win Rate</div>
            <div className={`metric-value ${winRate >= 50 ? 'positive' : 'negative'}`}>
              {winRate.toFixed(1)}%
            </div>
            <div className="metric-sub">{winningTrades}W / {losingTrades}L</div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Total P&L</div>
            <div className={`metric-value ${totalPnL >= 0 ? 'positive' : 'negative'}`}>
              ${totalPnL.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Profit Factor</div>
            <div className={`metric-value ${profitFactor >= 1 ? 'positive' : 'negative'}`}>
              {profitFactor.toFixed(2)}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Avg Win</div>
            <div className="metric-value positive">
              ${avgWin.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Avg Loss</div>
            <div className="metric-value negative">
              ${avgLoss.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Best Trade</div>
            <div className="metric-value positive">
              ${bestTrade.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Worst Trade</div>
            <div className="metric-value negative">
              ${worstTrade.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Available Cash</div>
            <div className="metric-value">
              ${balance.cash.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-label">Unrealized P&L</div>
            <div className={`metric-value ${balance.unrealizedPnL >= 0 ? 'positive' : 'negative'}`}>
              ${balance.unrealizedPnL.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            </div>
          </div>
        </div>
        
        <div className="performance-footer">
          <span className="performance-hint">Press ESC or click outside to close</span>
        </div>
      </div>
    </div>
  )
}

export default PerformanceCard
