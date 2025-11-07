import { useEffect, useState, useRef } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import './Chart.css'

function Chart({ symbol, trades = [], positions = [] }) {
    const [selectedCoin, setSelectedCoin] = useState(symbol || 'BTC/USDT')
    const [currentPrice, setCurrentPrice] = useState(null)
    const [priceChange, setPriceChange] = useState(0)
    const [timeframe, setTimeframe] = useState('1h')
    const [chartType, setChartType] = useState('candlestick')
    const [isUpdating, setIsUpdating] = useState(false)
    const [showCoinDropdown, setShowCoinDropdown] = useState(false)
    const [viewMode, setViewMode] = useState('single') // 'single' or 'multi'
    const [showViewModeToggle, setShowViewModeToggle] = useState(false) // Show full toggle or just Multi button
    
    // Track prices for all coins in multi-view
    const [coinPrices, setCoinPrices] = useState({})
    const [coinPriceChanges, setCoinPriceChanges] = useState({})

    const chartRefs = useRef({})
    const seriesRefs = useRef({})
    const containerRefs = useRef({})
    const wsRefs = useRef({})
    const tickerWsRefs = useRef({})
    const lastCandleRefs = useRef({})
    const priceLineRefs = useRef({})
    const dropdownRef = useRef(null)

    // Available coins
    const availableCoins = [
        { symbol: 'BTC/USDT', name: 'Bitcoin', icon: '/image/Bitcoin.svg.webp' },
        { symbol: 'ETH/USDT', name: 'Ethereum', icon: '/image/eth.svg' },
        { symbol: 'SOL/USDT', name: 'Solana', icon: '/image/sol.svg' },
        { symbol: 'DOGE/USDT', name: 'Dogecoin', icon: '/image/dogecoin.svg' },
        { symbol: 'BNB/USDT', name: 'BNB', icon: '/image/bnb.svg' },
        { symbol: 'XRP/USDT', name: 'Ripple', icon: '/image/ripple-xrp-crypto.svg' },
    ]
    
    // Coins to display in multi-view (all 6 coins)
    const multiViewCoins = availableCoins

    // Map timeframe to Binance interval
    const getInterval = () => {
        const intervalMap = {
            '5m': '5m',
            '15m': '15m',
            '1h': '1h',
            '4h': '4h',
            '1d': '1d',
            '1w': '1w',
        }
        return intervalMap[timeframe] || '1h'
    }

    const viewModeToggleRef = useRef(null)

    // Close dropdown on outside click
    useEffect(() => {
        const handler = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setShowCoinDropdown(false)
            }
            // Only close view mode toggle if it's expanded and clicking outside
            if (showViewModeToggle && viewModeToggleRef.current && !viewModeToggleRef.current.contains(e.target)) {
                setShowViewModeToggle(false)
            }
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [showViewModeToggle])

    // Real-time price update (24h stats) - WebSocket handles tick-by-tick price
    useEffect(() => {
        // Always track all coins for ticker bar
        const coinsToTrack = availableCoins.map(c => c.symbol)
        if (coinsToTrack.length === 0) return

        let isMounted = true
        let updateInterval = null

        const updatePrice = async () => {
            try {
                const updates = {}
                const changeUpdates = {}
                
                await Promise.all(coinsToTrack.map(async (coinSymbol) => {
                    try {
                        const symbolFormatted = coinSymbol.replace('/', '')
                        // Use Binance Futures API
                        const response = await fetch(`https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${symbolFormatted}`)
                        
                        if (!response.ok) throw new Error(`HTTP ${response.status}`)
                        
                        const data = await response.json()
                        const change24h = parseFloat(data.priceChangePercent)
                        const lastPrice = parseFloat(data.lastPrice)
                        
                        updates[coinSymbol] = lastPrice
                        changeUpdates[coinSymbol] = change24h
                    } catch (error) {
                        console.error(`Price update failed for ${coinSymbol}:`, error)
                    }
                }))

                if (!isMounted) return

                // Always update coinPrices and coinPriceChanges for ticker
                setCoinPrices(prev => ({ ...prev, ...updates }))
                setCoinPriceChanges(prev => ({ ...prev, ...changeUpdates }))
                
                // Update shared price context
                Object.entries(updates).forEach(([symbol, price]) => {
                    updatePrice(symbol, price)
                })

                // Update selected coin price for single view
                if (viewMode === 'single') {
                    if (updates[selectedCoin] !== undefined) {
                        setCurrentPrice(updates[selectedCoin])
                    }
                    if (changeUpdates[selectedCoin] !== undefined) {
                        setPriceChange(changeUpdates[selectedCoin])
                    }
                }
            } catch (error) {
                console.error('Price update failed:', error)
            }
        }

        updatePrice()
        updateInterval = setInterval(updatePrice, 10000) // Update 24h stats every 10s

        return () => {
            isMounted = false
            if (updateInterval) {
                clearInterval(updateInterval)
            }
        }
    }, [selectedCoin, viewMode])

    // Initialize charts
    useEffect(() => {
        // Clean up ALL charts first when viewMode changes
        Object.keys(chartRefs.current).forEach((key) => {
            if (chartRefs.current[key]) {
                chartRefs.current[key].remove()
                delete chartRefs.current[key]
            }
        })
        seriesRefs.current = {}
        containerRefs.current = {}

        // Wait for DOM to be ready
        const initializeCharts = () => {
            const coinsToRender = viewMode === 'multi' ? multiViewCoins.map(c => c.symbol) : [selectedCoin]

            coinsToRender.forEach((coinSymbol) => {
                const containerId = `chart-${coinSymbol.replace('/', '-')}`
                const container = document.getElementById(containerId)
                
                if (!container) {
                    console.warn(`Container not found for ${coinSymbol}: ${containerId}`)
                    return
                }

                containerRefs.current[coinSymbol] = container

                // Create new chart with professional styling
                const chart = createChart(container, {
                    layout: {
                        background: { type: ColorType.Solid, color: '#ffffff' },
                        textColor: '#475569',
                        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                        fontSize: 13,
                    },
                    grid: {
                        vertLines: { 
                            color: '#f1f5f9',
                            style: 0,
                            visible: true,
                        },
                        horzLines: { 
                            color: '#f1f5f9',
                            style: 0,
                            visible: true,
                        },
                    },
                    width: container.clientWidth,
                    height: viewMode === 'multi' ? Math.max(container.clientHeight || 300, 300) : Math.min(container.clientHeight || 520, 520),
                    timeScale: {
                        timeVisible: true,
                        secondsVisible: false,
                        borderColor: '#e2e8f0',
                        rightOffset: 12,
                        barSpacing: 8,
                    },
                    rightPriceScale: {
                        borderColor: '#e2e8f0',
                        scaleMargins: {
                            top: 0.05,
                            bottom: 0.05,
                        },
                        entireTextOnly: true,
                    },
                    crosshair: {
                        mode: 1,
                        vertLine: {
                            color: '#94a3b8',
                            width: 1,
                            style: 2,
                            labelBackgroundColor: '#475569',
                        },
                        horzLine: {
                            color: '#94a3b8',
                            width: 1,
                            style: 2,
                            labelBackgroundColor: '#475569',
                        },
                    },
                })

                chartRefs.current[coinSymbol] = chart

                // Create series with professional styling
                let series
                if (chartType === 'area') {
                    series = chart.addAreaSeries({
                        topColor: 'rgba(37, 99, 235, 0.28)',
                        bottomColor: 'rgba(37, 99, 235, 0.02)',
                        lineColor: '#2563eb',
                        lineWidth: 2.5,
                        priceLineVisible: false,
                        lastValueVisible: false, // Disabled - we use ticker price line instead
                        priceFormat: {
                            type: 'price',
                            precision: 2,
                            minMove: 0.01,
                        },
                    })
                } else {
                    series = chart.addCandlestickSeries({
                        upColor: '#10b981',
                        downColor: '#ef4444',
                        borderUpColor: '#10b981',
                        borderDownColor: '#ef4444',
                        wickUpColor: '#10b981',
                        wickDownColor: '#ef4444',
                        priceLineVisible: false,
                        lastValueVisible: false, // Disabled - we use ticker price line instead
                        priceFormat: {
                            type: 'price',
                            precision: 2,
                            minMove: 0.01,
                        },
                    })
                }
                seriesRefs.current[coinSymbol] = series

                // Create price line for real-time ticker price (will be updated from ticker WebSocket)
                const priceLineId = `priceLine-${coinSymbol}`
                // Price line will be added when ticker price is received

                // Fetch and set data
                const fetchData = async () => {
                    setIsUpdating(true)
                    try {
                        const symbolFormatted = coinSymbol.replace('/', '')
                        const interval = getInterval()
                        // Use Binance Futures API
                        const response = await fetch(
                            `https://fapi.binance.com/fapi/v1/klines?symbol=${symbolFormatted}&interval=${interval}&limit=200`
                        )

                        if (!response.ok) throw new Error(`HTTP ${response.status}`)

                        const rawData = await response.json()
                        const transformedData = rawData.map(item => ({
                            time: Math.floor(item[0] / 1000),
                            open: parseFloat(item[1]),
                            high: parseFloat(item[2]),
                            low: parseFloat(item[3]),
                            close: parseFloat(item[4]),
                            volume: parseFloat(item[5])
                        }))

                        if (chartType === 'area') {
                            series.setData(transformedData.map(d => ({
                                time: d.time,
                                value: d.close
                            })))
                        } else {
                            series.setData(transformedData)
                        }

                        chart.timeScale().fitContent()
                    } catch (error) {
                        console.error(`Chart data fetch failed for ${coinSymbol}:`, error)
                    } finally {
                        setIsUpdating(false)
                    }
                }

                fetchData()

                // Handle resize
                const handleResize = () => {
                    if (container && chart) {
                        const height = viewMode === 'multi' ? Math.max(container.clientHeight || 300, 300) : Math.min(container.clientHeight || 520, 520)
                        chart.applyOptions({ 
                            width: container.clientWidth,
                            height: height
                        })
                    }
                }
                window.addEventListener('resize', handleResize)
            })
        }

        // Use setTimeout + requestAnimationFrame to ensure DOM is ready
        // Small delay gives React time to render all elements, especially in multi-view
        const timeoutId = setTimeout(() => {
            requestAnimationFrame(() => {
                initializeCharts()
            })
        }, 50)

        return () => {
            clearTimeout(timeoutId)
            // Clean up all charts on unmount or view change
            Object.keys(chartRefs.current).forEach((key) => {
                if (chartRefs.current[key]) {
                    chartRefs.current[key].remove()
                    delete chartRefs.current[key]
                }
            })
            seriesRefs.current = {}
            containerRefs.current = {}
            priceLineRefs.current = {}
        }
    }, [selectedCoin, timeframe, chartType, viewMode])

    // WebSocket real-time updates
    useEffect(() => {
        // Always connect WebSocket for all coins to update ticker bar in real-time
        const coinsToRender = viewMode === 'multi' ? multiViewCoins.map(c => c.symbol) : availableCoins.map(c => c.symbol)
        const interval = getInterval().toLowerCase()

        coinsToRender.forEach((coinSymbol) => {
            const symbolFormatted = coinSymbol.replace('/', '').toLowerCase()
            const wsKey = `${coinSymbol}-${interval}`
            
            // Close existing WebSocket if any
            if (wsRefs.current[wsKey]) {
                wsRefs.current[wsKey].close()
                delete wsRefs.current[wsKey]
            }

            const series = seriesRefs.current[coinSymbol]
            if (!series) return

            // Connect to Binance Futures WebSocket for kline updates
            const ws = new WebSocket(`wss://fstream.binance.com/ws/${symbolFormatted}@kline_${interval}`)
            wsRefs.current[wsKey] = ws

            ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data)
                    const kline = message.k

                    if (!kline) return

                    const candleData = {
                        time: Math.floor(kline.t / 1000),
                        open: parseFloat(kline.o),
                        high: parseFloat(kline.h),
                        low: parseFloat(kline.l),
                        close: parseFloat(kline.c),
                        volume: parseFloat(kline.v)
                    }

                    // Update last candle or add new one (update both forming and final candles)
                    const lastCandle = lastCandleRefs.current[coinSymbol]
                    if (lastCandle && lastCandle.time === candleData.time) {
                        // Update existing candle (real-time update as it forms)
                        lastCandleRefs.current[coinSymbol] = candleData
                        if (chartType === 'area') {
                            series.update({
                                time: candleData.time,
                                value: candleData.close
                            })
                        } else {
                            series.update(candleData)
                        }
                    } else {
                        // New candle (candle period completed)
                        lastCandleRefs.current[coinSymbol] = candleData
                        if (chartType === 'area') {
                            series.update({
                                time: candleData.time,
                                value: candleData.close
                            })
                        } else {
                            series.update(candleData)
                        }
                    }

                    // Note: Price updates come from ticker WebSocket below for accuracy
                } catch (error) {
                    console.error(`WebSocket message error for ${coinSymbol}:`, error)
                }
            }

            ws.onerror = (error) => {
                console.error(`WebSocket error for ${coinSymbol}:`, error)
            }

            ws.onclose = () => {
                // Reconnect after 3 seconds
                setTimeout(() => {
                    if (wsRefs.current[wsKey] === ws) {
                        delete wsRefs.current[wsKey]
                        // Reconnect by re-running effect (component will handle)
                    }
                }, 3000)
            }
        })

        return () => {
            // Cleanup WebSockets
            Object.keys(wsRefs.current).forEach(key => {
                if (wsRefs.current[key]) {
                    wsRefs.current[key].close()
                    delete wsRefs.current[key]
                }
            })
        }
    }, [selectedCoin, timeframe, chartType, viewMode])

    // Ticker WebSocket for real-time price updates (matches Binance Futures exactly)
    useEffect(() => {
        // Always connect ticker WebSocket for all coins for accurate price display
        const coinsToTrack = availableCoins.map(c => c.symbol)
        
        coinsToTrack.forEach((coinSymbol) => {
            const symbolFormatted = coinSymbol.replace('/', '').toLowerCase()
            const tickerWsKey = `ticker-${coinSymbol}`
            
            // Close existing ticker WebSocket if any
            if (tickerWsRefs.current[tickerWsKey]) {
                tickerWsRefs.current[tickerWsKey].close()
                delete tickerWsRefs.current[tickerWsKey]
            }

            // Connect to Binance Futures ticker stream for real-time last price
            const tickerWs = new WebSocket(`wss://fstream.binance.com/ws/${symbolFormatted}@ticker`)
            tickerWsRefs.current[tickerWsKey] = tickerWs

            tickerWs.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data)
                    const lastPrice = parseFloat(data.c) // 'c' is the last price in ticker stream
                    
                    if (!lastPrice || isNaN(lastPrice)) return

                    // Update prices in real-time - this matches Binance Futures exactly
                    setCoinPrices(prev => ({ ...prev, [coinSymbol]: lastPrice }))
                    
                    // Update shared price context for other components (Positions, etc.)
                    updatePrice(coinSymbol, lastPrice)
                    
                    // Update selected coin price for single view header
                    if (viewMode === 'single' && coinSymbol === selectedCoin) {
                        setCurrentPrice(lastPrice)
                    }

                    // Update chart price line to match ticker price
                    const series = seriesRefs.current[coinSymbol]
                    if (series) {
                        // Remove existing price line if any
                        const existingPriceLine = priceLineRefs.current[coinSymbol]
                        if (existingPriceLine) {
                            try {
                                series.removePriceLine(existingPriceLine)
                            } catch (e) {
                                // Price line might already be removed
                            }
                        }
                        
                        // Add new price line with current ticker price
                        try {
                            const priceLine = series.createPriceLine({
                                price: lastPrice,
                                color: '#ef4444',
                                lineWidth: 1,
                                lineStyle: 2, // Dashed line
                                axisLabelVisible: true,
                                title: ''
                            })
                            priceLineRefs.current[coinSymbol] = priceLine
                        } catch (e) {
                            console.error(`Failed to create price line for ${coinSymbol}:`, e)
                        }
                    }
                } catch (error) {
                    console.error(`Ticker WebSocket error for ${coinSymbol}:`, error)
                }
            }

            tickerWs.onerror = (error) => {
                console.error(`Ticker WebSocket error for ${coinSymbol}:`, error)
            }

            tickerWs.onclose = () => {
                // Reconnect after 3 seconds
                setTimeout(() => {
                    if (tickerWsRefs.current[tickerWsKey] === tickerWs) {
                        delete tickerWsRefs.current[tickerWsKey]
                    }
                }, 3000)
            }
        })

        return () => {
            // Cleanup ticker WebSockets
            Object.keys(tickerWsRefs.current).forEach(key => {
                if (tickerWsRefs.current[key]) {
                    tickerWsRefs.current[key].close()
                    delete tickerWsRefs.current[key]
                }
            })
        }
    }, [selectedCoin, viewMode])

    // Update chart data when timeframe changes
    useEffect(() => {
        const coinsToRender = viewMode === 'multi' ? multiViewCoins.map(c => c.symbol) : [selectedCoin]

        coinsToRender.forEach(async (coinSymbol) => {
            const series = seriesRefs.current[coinSymbol]
            if (!series) return

            setIsUpdating(true)
            try {
                const symbolFormatted = coinSymbol.replace('/', '')
                const interval = getInterval()
                // Use Binance Futures API
                const response = await fetch(
                    `https://fapi.binance.com/fapi/v1/klines?symbol=${symbolFormatted}&interval=${interval}&limit=200`
                )

                if (!response.ok) throw new Error(`HTTP ${response.status}`)

                const rawData = await response.json()
                const transformedData = rawData.map(item => ({
                    time: Math.floor(item[0] / 1000),
                    open: parseFloat(item[1]),
                    high: parseFloat(item[2]),
                    low: parseFloat(item[3]),
                    close: parseFloat(item[4]),
                    volume: parseFloat(item[5])
                }))

                // Store last candle for WebSocket updates
                if (transformedData.length > 0) {
                    lastCandleRefs.current[coinSymbol] = transformedData[transformedData.length - 1]
                }

                if (chartType === 'area') {
                    series.setData(transformedData.map(d => ({
                        time: d.time,
                        value: d.close
                    })))
                } else {
                    series.setData(transformedData)
                }

                if (chartRefs.current[coinSymbol]) {
                    chartRefs.current[coinSymbol].timeScale().fitContent()
                }
            } catch (error) {
                console.error(`Chart update failed for ${coinSymbol}:`, error)
            } finally {
                setIsUpdating(false)
            }
        })
    }, [timeframe, chartType, selectedCoin, viewMode])

    // Find position for selected coin
    const coinSymbol = selectedCoin.split('/')[0]
    const coinPosition = positions.find(pos => pos.coin === coinSymbol)

    // Format price
    const formatPrice = (price) => {
        if (price === null || price === undefined) return '--'
        if (price >= 1000) {
            return price.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            })
        } else if (price >= 1) {
            return price.toFixed(4)
        } else {
            return price.toFixed(6)
        }
    }

    return (
        <div className="chart-container">
            {viewMode === 'single' ? (
                <div className="chart-card">
                    <div className="chart-header">
                        <div className="chart-header-left" ref={dropdownRef}>
                            <button
                                className="coin-select"
                                onClick={() => setShowCoinDropdown(!showCoinDropdown)}
                                aria-haspopup="listbox"
                                aria-expanded={showCoinDropdown}
                                title={selectedCoin}
                            >
                                <img
                                    src={availableCoins.find(c => c.symbol === selectedCoin)?.icon}
                                    alt={selectedCoin}
                                    className="coin-selector-icon"
                                />
                                <svg className={`dropdown-arrow ${showCoinDropdown ? 'open' : ''}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m6 9 6 6 6-6"/></svg>
                            </button>
                            {showCoinDropdown && (
                                <div className="coin-dropdown" role="listbox">
                                    {availableCoins.map(coin => (
                                        <button
                                            key={coin.symbol}
                                            className={`coin-option ${selectedCoin === coin.symbol ? 'selected' : ''}`}
                                            onClick={() => { setSelectedCoin(coin.symbol); setShowCoinDropdown(false) }}
                                            role="option"
                                            aria-selected={selectedCoin === coin.symbol}
                                        >
                                            <img src={coin.icon} alt={coin.name} className="coin-option-icon" />
                                            <div className="coin-option-info">
                                                <span className="coin-option-name">{coin.name}</span>
                                                <span className="coin-option-symbol">{coin.symbol}</span>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="chart-controls-center">
                            <div className="view-mode-toggle" ref={viewModeToggleRef}>
                                <button
                                    className="view-mode-btn-multi-only"
                                    onClick={() => setViewMode('multi')}
                                >
                                    Multi
                                </button>
                            </div>
                            <div className="timeframe-controls">
                                {['5m', '15m', '1h', '4h', '1d', '1w'].map((tf) => (
                                    <button
                                        key={tf}
                                        className={`timeframe-btn ${timeframe === tf ? 'active' : ''}`}
                                        onClick={() => setTimeframe(tf)}
                                    >
                                        {tf.toUpperCase()}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="chart-header-right">
                            <div className="price-display-main">
                                <div className="price-coin-name">{selectedCoin}</div>
                                <div className="price-separator">|</div>
                                <div className="price-value-main">
                                    ${formatPrice(currentPrice)}
                                </div>
                                <div className={`price-change-main ${priceChange >= 0 ? 'positive' : 'negative'}`}>
                                    {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="chart-canvas-wrapper">
                        <div 
                            id={`chart-${selectedCoin.replace('/', '-')}`}
                            className="chart-canvas"
                        />
                        {isUpdating && (
                            <div className="chart-loading-overlay">
                                <div className="loading-spinner"></div>
                            </div>
                        )}
                    </div>

                    {/* Ticker Bar */}
                    <div className="ticker-bar">
                        <div className="ticker-content">
                            {/* First set of coins */}
                            {availableCoins.map((coin) => {
                                const coinPrice = coinPrices[coin.symbol] || null
                                const coinChange = coinPriceChanges[coin.symbol] || 0
                                const isSelected = coin.symbol === selectedCoin
                                
                                return (
                                    <button
                                        key={`ticker-${coin.symbol}`}
                                        className={`ticker-item ${isSelected ? 'active' : ''}`}
                                        onClick={() => setSelectedCoin(coin.symbol)}
                                    >
                                        <span className="ticker-symbol">{coin.symbol.replace('/USDT', '')}</span>
                                        <span className="ticker-price">${formatPrice(coinPrice)}</span>
                                        <span className={`ticker-change ${coinChange >= 0 ? 'positive' : 'negative'}`}>
                                            {coinChange >= 0 ? '+' : ''}{coinChange.toFixed(2)}%
                                        </span>
                                    </button>
                                )
                            })}
                            {/* Duplicate set for seamless loop */}
                            {availableCoins.map((coin) => {
                                const coinPrice = coinPrices[coin.symbol] || null
                                const coinChange = coinPriceChanges[coin.symbol] || 0
                                const isSelected = coin.symbol === selectedCoin
                                
                                return (
                                    <button
                                        key={`ticker-duplicate-${coin.symbol}`}
                                        className={`ticker-item ${isSelected ? 'active' : ''}`}
                                        onClick={() => setSelectedCoin(coin.symbol)}
                                    >
                                        <span className="ticker-symbol">{coin.symbol.replace('/USDT', '')}</span>
                                        <span className="ticker-price">${formatPrice(coinPrice)}</span>
                                        <span className={`ticker-change ${coinChange >= 0 ? 'positive' : 'negative'}`}>
                                            {coinChange >= 0 ? '+' : ''}{coinChange.toFixed(2)}%
                                        </span>
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                </div>
            ) : (
                <>
                    <div className="chart-header-multi">
                        <div className="chart-controls-center">
                            <div className="view-mode-toggle" ref={viewModeToggleRef}>
                                <button
                                    className={`view-mode-btn ${viewMode === 'single' ? 'active' : ''}`}
                                    onClick={() => setViewMode('single')}
                                >
                                    Single
                                </button>
                                <button
                                    className={`view-mode-btn ${viewMode === 'multi' ? 'active' : ''}`}
                                    onClick={() => setViewMode('multi')}
                                >
                                    Multi
                                </button>
                            </div>
                            <div className="timeframe-controls">
                                {['5m', '15m', '1h', '4h', '1d', '1w'].map((tf) => (
                                    <button
                                        key={tf}
                                        className={`timeframe-btn ${timeframe === tf ? 'active' : ''}`}
                                        onClick={() => setTimeframe(tf)}
                                    >
                                        {tf.toUpperCase()}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="chart-wrapper-multi">
                        {multiViewCoins.map((coin) => {
                            const coinPosition = positions.find(pos => pos.coin === coin.symbol.split('/')[0])
                            const coinPrice = coinPrices[coin.symbol] || null
                            const coinChange = coinPriceChanges[coin.symbol] || 0
                            
                            return (
                                <div key={coin.symbol} className="multi-chart-item">
                                    <div className="multi-chart-header">
                                        <img src={coin.icon} alt={coin.name} className="multi-chart-icon" />
                                        <div className="multi-chart-symbol">{coin.symbol}</div>
                                        {coinPosition && (
                                            <div className={`multi-chart-position ${coinPosition.side?.toLowerCase() || 'long'}`}>
                                                {coinPosition.side || 'LONG'}
                                            </div>
                                        )}
                                        <div className="multi-chart-price">
                                            <div className="multi-price-value">${formatPrice(coinPrice)}</div>
                                            <div className={`multi-price-change ${coinChange >= 0 ? 'positive' : 'negative'}`}>
                                                {coinChange >= 0 ? '+' : ''}{coinChange.toFixed(2)}%
                                            </div>
                                        </div>
                                    </div>
                                    <div className="chart-canvas-wrapper-multi">
                                        <div 
                                            id={`chart-${coin.symbol.replace('/', '-')}`}
                                            className="chart-canvas-multi"
                                        />
                                        {isUpdating && (
                                            <div className="chart-loading-overlay">
                                                <div className="loading-spinner"></div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </>
            )}
        </div>
    )
}

export default Chart
