import { useState, useEffect } from 'react'
import './CoinInfo.css'

function CoinInfo({ selectedCoin, position }) {
    const [marketData, setMarketData] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!selectedCoin) return
        
        const fetchMarketData = async () => {
            setLoading(true)
            try {
                const symbolFormatted = selectedCoin.replace('/', '')
                
                // Fetch 24h ticker stats
                const tickerUrl = `https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${symbolFormatted}`
                const tickerResponse = await fetch(tickerUrl)
                
                // Fetch mark price
                const markPriceUrl = `https://fapi.binance.com/fapi/v1/premiumIndex?symbol=${symbolFormatted}`
                const markPriceResponse = await fetch(markPriceUrl)
                
                if (tickerResponse.ok && markPriceResponse.ok) {
                    const tickerData = await tickerResponse.json()
                    const markPriceData = await markPriceResponse.json()
                    
                    setMarketData({
                        price: parseFloat(markPriceData.markPrice),
                        high24h: parseFloat(tickerData.highPrice),
                        low24h: parseFloat(tickerData.lowPrice),
                        volume24h: parseFloat(tickerData.volume),
                        priceChange24h: parseFloat(tickerData.priceChangePercent),
                        lastPrice: parseFloat(tickerData.lastPrice),
                    })
                }
            } catch (e) {
                console.error('Failed to fetch market data:', e)
            } finally {
                setLoading(false)
            }
        }
        
        fetchMarketData()
        const interval = setInterval(fetchMarketData, 10000) // Update every 10s
        
        return () => clearInterval(interval)
    }, [selectedCoin])

    if (!selectedCoin) return null

    const coinSymbol = selectedCoin.split('/')[0]
    const currentPrice = position?.currentPrice || marketData?.price || 0

    return (
        <div className="coin-info-panel">
            <div className="coin-info-header">
                <h3>{coinSymbol} Market Info</h3>
            </div>
            
            {loading && !marketData ? (
                <div className="coin-info-loading">Loading...</div>
            ) : marketData ? (
                <div className="coin-info-content">
                    <div className="info-row">
                        <span className="info-label">Current Price</span>
                        <span className="info-value price">${currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    
                    <div className="info-row">
                        <span className="info-label">24h High</span>
                        <span className="info-value positive">${marketData.high24h.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    
                    <div className="info-row">
                        <span className="info-label">24h Low</span>
                        <span className="info-value negative">${marketData.low24h.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    
                    <div className="info-row">
                        <span className="info-label">24h Change</span>
                        <span className={`info-value ${marketData.priceChange24h >= 0 ? 'positive' : 'negative'}`}>
                            {marketData.priceChange24h >= 0 ? '+' : ''}{marketData.priceChange24h.toFixed(2)}%
                        </span>
                    </div>
                    
                    <div className="info-row">
                        <span className="info-label">24h Volume</span>
                        <span className="info-value">{marketData.volume24h.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
                    </div>
                    
                    {position && (
                        <>
                            <div className="info-divider"></div>
                            <div className="info-row">
                                <span className="info-label">Your Entry</span>
                                <span className="info-value">${position.entryPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                            </div>
                            <div className="info-row">
                                <span className="info-label">Your P&L</span>
                                <span className={`info-value ${position.unrealPnL >= 0 ? 'positive' : 'negative'}`}>
                                    ${position.unrealPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                            </div>
                            <div className="info-row">
                                <span className="info-label">P&L %</span>
                                <span className={`info-value ${position.pnlPercent >= 0 ? 'positive' : 'negative'}`}>
                                    {position.pnlPercent >= 0 ? '+' : ''}{position.pnlPercent.toFixed(2)}%
                                </span>
                            </div>
                        </>
                    )}
                </div>
            ) : (
                <div className="coin-info-error">Failed to load market data</div>
            )}
        </div>
    )
}

export default CoinInfo

