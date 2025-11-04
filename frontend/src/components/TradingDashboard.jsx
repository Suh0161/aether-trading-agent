import { useState, useEffect, useRef } from 'react'
import CoinInfo from './CoinInfo'
import MarketData from './MarketData'
import './TradingDashboard.css'

function TradingDashboard({ positions = [] }) {
    const [selectedCoin, setSelectedCoin] = useState('BTC/USDT')
    const [showCoinDropdown, setShowCoinDropdown] = useState(false)
    const [marketData, setMarketData] = useState(null)
    const [loading, setLoading] = useState(true)
    const dropdownRef = useRef(null)

    const availableCoins = [
        { symbol: 'BTC/USDT', name: 'Bitcoin', icon: '/image/Bitcoin.svg.webp' },
        { symbol: 'ETH/USDT', name: 'Ethereum', icon: '/image/eth.svg' },
        { symbol: 'SOL/USDT', name: 'Solana', icon: '/image/sol.svg' },
        { symbol: 'DOGE/USDT', name: 'Dogecoin', icon: '/image/dogecoin.svg' },
        { symbol: 'BNB/USDT', name: 'BNB', icon: '/image/bnb.svg' },
        { symbol: 'XRP/USDT', name: 'Ripple', icon: '/image/ripple-xrp-crypto.svg' },
    ]

    // Fetch market data for selected coin
    useEffect(() => {
        if (!selectedCoin) return
        
        // Reset market data when coin changes
        setMarketData(null)
        setLoading(true)
        
        const fetchMarketData = async () => {
            try {
                const symbolFormatted = selectedCoin.replace('/', '')
                
                // Fetch 24h ticker and mark price
                const [tickerResponse, markPriceResponse] = await Promise.all([
                    fetch(`https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${symbolFormatted}`),
                    fetch(`https://fapi.binance.com/fapi/v1/premiumIndex?symbol=${symbolFormatted}`)
                ])
                
                if (tickerResponse.ok && markPriceResponse.ok) {
                    const tickerData = await tickerResponse.json()
                    const markPriceData = await markPriceResponse.json()
                    
                    // Ensure all values are valid numbers
                    setMarketData({
                        price: parseFloat(markPriceData.markPrice) || 0,
                        high24h: parseFloat(tickerData.highPrice) || 0,
                        low24h: parseFloat(tickerData.lowPrice) || 0,
                        volume24h: parseFloat(tickerData.volume) || 0,
                        priceChange24h: parseFloat(tickerData.priceChangePercent) || 0,
                        lastPrice: parseFloat(tickerData.lastPrice) || 0,
                        quoteVolume: parseFloat(tickerData.quoteVolume) || 0,
                    })
                }
            } catch (e) {
                console.error('Failed to fetch market data:', e)
                setMarketData(null)
            } finally {
                setLoading(false)
            }
        }
        
        fetchMarketData()
        const interval = setInterval(fetchMarketData, 5000) // Update every 5s
        
        return () => clearInterval(interval)
    }, [selectedCoin])

    const coinSymbol = selectedCoin.split('/')[0]
    const coinPosition = positions.find(pos => pos.coin === coinSymbol)

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setShowCoinDropdown(false)
            }
        }

        if (showCoinDropdown) {
            document.addEventListener('mousedown', handleClickOutside)
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside)
        }
    }, [showCoinDropdown])

    return (
        <div className="trading-dashboard">
            <div className="dashboard-header">
                <div className="coin-selector-wrapper" ref={dropdownRef}>
                    <h2
                        className="dashboard-title clickable"
                        onClick={() => setShowCoinDropdown(!showCoinDropdown)}
                    >
                        <img
                            src={availableCoins.find(c => c.symbol === selectedCoin)?.icon}
                            alt={selectedCoin}
                            className="coin-icon-small"
                        />
                        {selectedCoin}
                        <svg
                            className={`dropdown-arrow ${showCoinDropdown ? 'open' : ''}`}
                            width="16"
                            height="16"
                            viewBox="0 0 16 16"
                            fill="none"
                        >
                            <path
                                d="M4 6L8 10L12 6"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            />
                        </svg>
                    </h2>
                    {showCoinDropdown && (
                        <div className="coin-dropdown">
                            {availableCoins.map(coin => (
                                <div
                                    key={coin.symbol}
                                    className={`coin-option ${selectedCoin === coin.symbol ? 'active' : ''}`}
                                    onClick={() => {
                                        setSelectedCoin(coin.symbol)
                                        setShowCoinDropdown(false)
                                    }}
                                >
                                    <img src={coin.icon} alt={coin.name} className="coin-icon" />
                                    <div className="coin-info">
                                        <span className="coin-symbol">{coin.symbol}</span>
                                        <span className="coin-name">{coin.name}</span>
                                    </div>
                                    {selectedCoin === coin.symbol && (
                                        <svg
                                            width="18"
                                            height="18"
                                            viewBox="0 0 20 20"
                                            fill="none"
                                            className="coin-checkmark"
                                        >
                                            <circle
                                                cx="10"
                                                cy="10"
                                                r="9"
                                                fill="#16a34a"
                                                opacity="0.15"
                                            />
                                            <path
                                                d="M6 10L8.5 12.5L14 7"
                                                stroke="#16a34a"
                                                strokeWidth="2.5"
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                            />
                                        </svg>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                
                {loading && !marketData ? (
                    <div className="dashboard-price-info">
                        <div className="price-main">
                            <span className="price-value">Loading...</span>
                        </div>
                    </div>
                ) : marketData ? (
                    <div className="dashboard-price-info">
                        <div className="price-main">
                            <span className="price-value">
                                ${marketData.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                            <span className={`price-change ${marketData.priceChange24h >= 0 ? 'positive' : 'negative'}`}>
                                {marketData.priceChange24h >= 0 ? '+' : ''}{marketData.priceChange24h.toFixed(2)}%
                            </span>
                        </div>
                    </div>
                ) : (
                    <div className="dashboard-price-info">
                        <div className="price-main">
                            <span className="price-value">Failed to load</span>
                        </div>
                    </div>
                )}
            </div>

            <div className="dashboard-content">
                <MarketData 
                    selectedCoin={selectedCoin} 
                    marketData={marketData} 
                    position={coinPosition} 
                />
            </div>
        </div>
    )
}

export default TradingDashboard

