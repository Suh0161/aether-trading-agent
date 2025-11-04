import { useEffect, useState, useRef } from 'react'
import { createChart, ColorType } from 'lightweight-charts'
import CoinInfo from './CoinInfo'
import { CoinSelector, ChartControls, PriceDisplay } from './chart/components'
import './Chart.css'

function Chart({ symbol, trades = [], positions = [] }) {
    const [currentPrice, setCurrentPrice] = useState(null) // null = not loaded yet
    const [priceChange, setPriceChange] = useState(0)
    const [chartType, setChartType] = useState('candlestick') // 'candlestick' or 'area'
    const [timeframe, setTimeframe] = useState('1h')
    const [isUpdating, setIsUpdating] = useState(false)
    const [selectedCoin, setSelectedCoin] = useState(symbol || 'BTC/USDT')
    const [chartData, setChartData] = useState([])

    const chartContainerRef = useRef(null)
    const chartRef = useRef(null)
    const seriesRef = useRef(null)
    const fetchingRef = useRef(false)
    const abortControllerRef = useRef(null)
    const debounceTimeoutRef = useRef(null)

    // Available coins
    const availableCoins = [
        { symbol: 'BTC/USDT', name: 'Bitcoin', icon: '/image/Bitcoin.svg.webp' },
        { symbol: 'ETH/USDT', name: 'Ethereum', icon: '/image/eth.svg' },
        { symbol: 'SOL/USDT', name: 'Solana', icon: '/image/sol.svg' },
        { symbol: 'DOGE/USDT', name: 'Dogecoin', icon: '/image/dogecoin.svg' },
        { symbol: 'BNB/USDT', name: 'BNB', icon: '/image/bnb.svg' },
        { symbol: 'XRP/USDT', name: 'Ripple', icon: '/image/ripple-xrp-crypto.svg' },
    ]

    // Map timeframe to Binance interval and data limit (reduced for faster loading)
    const getInterval = () => {
        const intervalMap = {
            '5m': { interval: '5m', limit: 50 },  // Reduced from 100
            '15m': { interval: '15m', limit: 50 }, // Reduced from 100
            '1h': { interval: '1h', limit: 100 },  // Reduced from 200
            '4h': { interval: '4h', limit: 75 },   // Reduced from 150
            '1d': { interval: '1d', limit: 50 },   // Reduced from 100
            '1w': { interval: '1w', limit: 26 },   // Reduced from 52
        }
        return intervalMap[timeframe] || { interval: '1h', limit: 100 }
    }

    // Real-time price update every 2 seconds (always fetch fresh from Binance)
    useEffect(() => {
        if (!selectedCoin || isUpdating || chartData.length === 0) return // Don't update during loading or if no data

        let isMounted = true
        let updateInterval = null
        const currentCoin = selectedCoin // Capture current coin to prevent stale closures

        const updatePrice = async () => {
            // Only update if still the same coin (prevent mixing data)
            if (!isMounted || currentCoin !== selectedCoin) return

            try {
                // Fetch fresh price from Binance API (no caching for price updates)
                const response = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${selectedCoin.replace('/', '')}`)
                if (!response.ok) throw new Error(`HTTP ${response.status}`)

                const data = await response.json()
                const newPrice = parseFloat(data.price)

                if (!isMounted || currentCoin !== selectedCoin) return

                // Calculate price change percentage
                const oldPrice = currentPrice
                if (oldPrice && oldPrice > 0) {
                    const change = ((newPrice - oldPrice) / oldPrice) * 100
                    setPriceChange(change)
                }

                setCurrentPrice(newPrice)

            } catch (error) {
                if (isMounted) {
                    console.error('Price update failed:', error)
                }
            }
        }

        // Initial price fetch
        updatePrice()

        // Set up interval for real-time updates
        updateInterval = setInterval(updatePrice, 2000) // Update every 2 seconds

        return () => {
            isMounted = false
            if (updateInterval) {
                clearInterval(updateInterval)
            }
        }
    }, [selectedCoin, chartData, isUpdating])

    // Initialize chart - recreate when coin or chartType changes
    useEffect(() => {
        if (!chartContainerRef.current) return

        // Clear all state when recreating chart
        setChartData([])
        setCurrentPrice(null)
        setPriceChange(0)

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'white' },
                textColor: '#333',
            },
            grid: {
                vertLines: { color: '#f5f5f4' },
                horzLines: { color: '#f5f5f4' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
            rightPriceScale: {
                borderColor: '#D6DCDE',
            },
            crosshair: {
                mode: 1, // Normal crosshair
            },
        })

        chartRef.current = chart

        // Create series based on chart type
        let series
        if (chartType === 'area') {
            series = chart.addAreaSeries({
                topColor: 'rgba(37, 99, 235, 0.56)',
                bottomColor: 'rgba(37, 99, 235, 0.04)',
                lineColor: 'rgba(37, 99, 235, 1)',
                lineWidth: 2,
            })
        } else {
            series = chart.addCandlestickSeries({
                upColor: '#16a34a',
                downColor: '#dc2626',
                borderVisible: false,
                wickUpColor: '#16a34a',
                wickDownColor: '#dc2626',
            })
        }
        seriesRef.current = series

        // Handle resize
        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
            }
        }

        window.addEventListener('resize', handleResize)

        // Cleanup function
        return () => {
            window.removeEventListener('resize', handleResize)
            if (chartRef.current) {
                chartRef.current.remove()
                chartRef.current = null
                seriesRef.current = null
            }
        }
    }, [selectedCoin, chartType])

    // Fetch chart data when coin or timeframe changes
    useEffect(() => {
        if (!selectedCoin || !seriesRef.current) return

        const fetchChartData = async () => {
            if (fetchingRef.current) return // Prevent concurrent fetches

            fetchingRef.current = true
            setIsUpdating(true)

            try {
                // Abort any existing request
                if (abortControllerRef.current) {
                    abortControllerRef.current.abort()
                }
                abortControllerRef.current = new AbortController()

                const { interval, limit } = getInterval()

                // Fetch data from Binance API
                const response = await fetch(
                    `https://api.binance.com/api/v3/klines?symbol=${selectedCoin.replace('/', '')}&interval=${interval}&limit=${limit}`,
                    { signal: abortControllerRef.current.signal }
                )

                if (!response.ok) throw new Error(`HTTP ${response.status}`)

                const rawData = await response.json()

                // Transform to lightweight-charts format
                const transformedData = rawData.map(item => ({
                    time: Math.floor(item[0] / 1000), // Convert ms to seconds
                    open: parseFloat(item[1]),
                    high: parseFloat(item[2]),
                    low: parseFloat(item[3]),
                    close: parseFloat(item[4]),
                    volume: parseFloat(item[5])
                }))

                // Update chart data
                if (seriesRef.current && transformedData.length > 0) {
                    if (chartType === 'area') {
                        seriesRef.current.setData(transformedData.map(d => ({
                            time: d.time,
                            value: d.close
                        })))
                    } else {
                        seriesRef.current.setData(transformedData)
                    }

                    setChartData(transformedData)

                    // Fit content to show all data
                    if (chartRef.current) {
                        chartRef.current.timeScale().fitContent()
                    }
                }

            } catch (error) {
                if (error.name !== 'AbortError') {
                    console.error('Chart data fetch failed:', error)
                }
            } finally {
                fetchingRef.current = false
                setIsUpdating(false)
            }
        }

        // Debounce rapid changes (coin/timeframe switches)
        if (debounceTimeoutRef.current) {
            clearTimeout(debounceTimeoutRef.current)
        }

        debounceTimeoutRef.current = setTimeout(fetchChartData, 300) // 300ms debounce

        return () => {
            if (debounceTimeoutRef.current) {
                clearTimeout(debounceTimeoutRef.current)
            }
        }
    }, [selectedCoin, timeframe, chartType])

    // Handle trade markers on chart
    useEffect(() => {
        if (!seriesRef.current || !trades.length) return

        // Add trade markers (buy/sell points)
        const markers = trades.map(trade => ({
            time: trade.timestamp,
            position: trade.side === 'buy' ? 'belowBar' : 'aboveBar',
            color: trade.side === 'buy' ? '#16a34a' : '#dc2626',
            shape: trade.side === 'buy' ? 'arrowUp' : 'arrowDown',
            text: `${trade.side.toUpperCase()} ${trade.size.toFixed(4)}`
        }))

        seriesRef.current.setMarkers(markers)
    }, [trades])

    // Find position for selected coin
    const coinPosition = positions.find(pos => pos.coin === selectedCoin)

    return (
        <div className="chart-container">
            <div className="chart-layout">
                <div className="chart-main">
                    <CoinSelector
                        selectedCoin={selectedCoin}
                        onCoinChange={setSelectedCoin}
                        availableCoins={availableCoins}
                    />

                    <PriceDisplay
                        currentPrice={currentPrice}
                        priceChange={priceChange}
                        symbol={selectedCoin}
                        isUpdating={isUpdating}
                    />

                    <ChartControls
                        timeframe={timeframe}
                        chartType={chartType}
                        onTimeframeChange={setTimeframe}
                        onChartTypeChange={setChartType}
                    />

                    <div className="chart-content">
                        <div className={`chart-wrapper ${isUpdating ? 'updating' : ''}`}>
                            <div ref={chartContainerRef} className="chart-canvas" />
                            {isUpdating && (
                                <div className="chart-loading">
                                    <div className="loading-spinner"></div>
                                    <p>Updating chart data...</p>
                                </div>
                            )}
                        </div>

                        <CoinInfo selectedCoin={selectedCoin} position={coinPosition} />
                    </div>
                </div>
            </div>
        </div>
    )
}

export default Chart