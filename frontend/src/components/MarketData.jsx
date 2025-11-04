import { useState, useEffect } from 'react'
import './MarketData.css'

function MarketData({ selectedCoin, marketData, position }) {
    const [orderBook, setOrderBook] = useState({ bids: [], asks: [] })
    const [recentTrades, setRecentTrades] = useState([])
    const [loading, setLoading] = useState(true)
    const [spread, setSpread] = useState(0)

    useEffect(() => {
        if (!selectedCoin) return

        const fetchData = async () => {
            try {
                const symbolFormatted = selectedCoin.replace('/', '')
                
                const [orderBookRes, tradesRes] = await Promise.all([
                    fetch(`https://fapi.binance.com/fapi/v1/depth?symbol=${symbolFormatted}&limit=20`),
                    fetch(`https://fapi.binance.com/fapi/v1/trades?symbol=${symbolFormatted}&limit=30`)
                ])

                if (orderBookRes.ok) {
                    const orderData = await orderBookRes.json()
                    const bids = orderData.bids
                        .map(([p, q]) => ({ price: parseFloat(p), qty: parseFloat(q), total: parseFloat(p) * parseFloat(q) }))
                        .sort((a, b) => b.price - a.price)
                        .slice(0, 20)
                    const asks = orderData.asks
                        .map(([p, q]) => ({ price: parseFloat(p), qty: parseFloat(q), total: parseFloat(p) * parseFloat(q) }))
                        .sort((a, b) => a.price - b.price)
                        .slice(0, 20)
                    
                    setOrderBook({ bids, asks })
                    
                    if (bids.length > 0 && asks.length > 0) {
                        setSpread(asks[0].price - bids[0].price)
                    }
                }

                if (tradesRes.ok) {
                    const tradesData = await tradesRes.json()
                    setRecentTrades(tradesData.map(t => ({
                        price: parseFloat(t.price),
                        qty: parseFloat(t.qty),
                        time: new Date(t.time),
                        isBuy: !t.isBuyerMaker
                    })).slice(0, 30))
                }
            } catch (e) {
                console.error('Failed to fetch market data:', e)
            } finally {
                setLoading(false)
            }
        }

        setLoading(true)
        fetchData()
        const interval = setInterval(fetchData, 1000)
        return () => clearInterval(interval)
    }, [selectedCoin])

    const formatTime = (date) => {
        return date.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        })
    }

    const formatNumber = (val, opts = {}) => {
        if (!val || isNaN(val)) return 'N/A'
        return val.toLocaleString('en-US', opts)
    }

    return (
        <div className="market-data-container">
            {/* Market Stats */}
            <div className="market-stats-grid">
                <div className="stat-card">
                    <span className="stat-label">24H High</span>
                    <span className="stat-value positive">${formatNumber(marketData?.high24h, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
                <div className="stat-card">
                    <span className="stat-label">24H Low</span>
                    <span className="stat-value negative">${formatNumber(marketData?.low24h, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
                <div className="stat-card">
                    <span className="stat-label">24H Volume</span>
                    <span className="stat-value">{formatNumber(marketData?.volume24h, { maximumFractionDigits: 0 })}</span>
                </div>
                <div className="stat-card">
                    <span className="stat-label">Spread</span>
                    <span className="stat-value">${formatNumber(spread, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
                </div>
            </div>

            {/* Order Book & Recent Trades */}
            <div className="data-split">
                {/* Order Book */}
                <div className="orderbook-panel">
                    <div className="panel-title">Order Book</div>
                    {loading ? (
                        <div className="loading-state">Loading...</div>
                    ) : (
                        <div className="orderbook-content">
                            {/* Asks */}
                            <div className="orderbook-side asks-side">
                                {orderBook.asks.length > 0 && (
                                    <>
                                        <div className="orderbook-header">
                                            <span>Price (USDT)</span>
                                            <span>Qty</span>
                                            <span>Total</span>
                                        </div>
                                        {orderBook.asks.map((ask, i) => (
                                            <div key={i} className="orderbook-row ask">
                                                <span className="price">{formatNumber(ask.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                                <span className="qty">{formatNumber(ask.qty, { maximumFractionDigits: 4 })}</span>
                                                <span className="total">{formatNumber(ask.total, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>

                            {/* Mid Price */}
                            <div className="orderbook-mid">
                                <div className="mid-price">
                                    {spread > 0 && orderBook.bids.length > 0 && orderBook.asks.length > 0 && (
                                        <span>{formatNumber((orderBook.asks[0].price + orderBook.bids[0].price) / 2, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                    )}
                                </div>
                                <div className="mid-spread">
                                    {spread > 0 && <span>Spread: {formatNumber(spread, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>}
                                </div>
                            </div>

                            {/* Bids */}
                            <div className="orderbook-side bids-side">
                                {orderBook.bids.length > 0 && (
                                    <>
                                        <div className="orderbook-header">
                                            <span>Price (USDT)</span>
                                            <span>Qty</span>
                                            <span>Total</span>
                                        </div>
                                        {orderBook.bids.map((bid, i) => (
                                            <div key={i} className="orderbook-row bid">
                                                <span className="price">{formatNumber(bid.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                                <span className="qty">{formatNumber(bid.qty, { maximumFractionDigits: 4 })}</span>
                                                <span className="total">{formatNumber(bid.total, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* Recent Trades */}
                <div className="trades-panel">
                    <div className="panel-title">Recent Trades</div>
                    {loading ? (
                        <div className="loading-state">Loading...</div>
                    ) : (
                        <div className="trades-content">
                            <div className="trades-header">
                                <span>Price (USDT)</span>
                                <span>Qty</span>
                                <span>Time</span>
                            </div>
                            <div className="trades-list">
                                {recentTrades.length > 0 ? (
                                    recentTrades.map((trade, i) => (
                                        <div key={i} className={`trade-row ${trade.isBuy ? 'buy' : 'sell'}`}>
                                            <span className="trade-price">
                                                ${formatNumber(trade.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                            </span>
                                            <span className="trade-qty">{formatNumber(trade.qty, { maximumFractionDigits: 4 })}</span>
                                            <span className="trade-time">{formatTime(trade.time)}</span>
                                        </div>
                                    ))
                                ) : (
                                    <div className="empty-state">No trades available</div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

export default MarketData
