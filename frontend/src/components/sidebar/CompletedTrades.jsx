import './CompletedTrades.css'

function CompletedTrades({ trades }) {
  return (
    <div className="trades-section">
      {trades.length === 0 ? (
        <div className="empty-state">
          <p>No completed trades yet</p>
        </div>
      ) : (
        <div className="trades-list">
          {[...trades].reverse().map((trade) => (
            <div key={trade.id} className={`trade-card ${trade.pnl >= 0 ? 'profit' : 'loss'}`}>
              <div className="trade-header">
                <div className="trade-header-left">
                  <div className="agent-info">
                    <img 
                      src="/deepseek.png" 
                      alt="DeepSeek" 
                      className="agent-logo"
                      onError={(e) => {
                        // Fallback to aether.png if deepseek.png is missing
                        e.target.onerror = null;
                        e.target.src = '/aether.png';
                      }}
                    />
                    <span className="agent-name">Aether</span>
                  </div>
                  <span className={`trade-type ${trade.side.toLowerCase()}`}>
                    {trade.side}
                  </span>
                  <span className="trade-symbol">{trade.coin}</span>
                </div>
                <div className="trade-header-right">
                  <span className={`trade-pnl ${trade.pnl >= 0 ? 'profit' : 'loss'}`}>
                    {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className="trade-time">{trade.timestamp}</span>
                </div>
              </div>

              <div className="trade-details">
                <div className="detail-row">
                  <div className="detail-group">
                    <span className="detail-label">Entry</span>
                    <span className="detail-value">
                      ${typeof trade.entryPrice === 'number' 
                        ? trade.entryPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                        : trade.entryPrice}
                    </span>
                  </div>
                  <div className="detail-group">
                    <span className="detail-label">Exit</span>
                    <span className="detail-value">
                      ${typeof trade.exitPrice === 'number'
                        ? trade.exitPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                        : trade.exitPrice}
                    </span>
                  </div>
                  <div className="detail-group">
                    <span className="detail-label">Qty</span>
                    <span className="detail-value">
                      {typeof trade.quantity === 'number' 
                        ? trade.quantity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
                        : trade.quantity}
                    </span>
                  </div>
                </div>

                <div className="detail-row">
                  <div className="detail-group">
                    <span className="detail-label">Size</span>
                    <span className="detail-value">
                      ${trade.entryNotional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="detail-group">
                    <span className="detail-label">Duration</span>
                    <span className="detail-value">{trade.holdingTime}</span>
                  </div>
                  <div className="detail-group">
                    <span className="detail-label">Return</span>
                    <span className={`detail-value ${trade.pnl >= 0 ? 'profit-text' : 'loss-text'}`}>
                      {((trade.pnl / trade.entryNotional) * 100).toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default CompletedTrades
