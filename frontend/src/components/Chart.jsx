import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import './Chart.css'

function Chart({ symbol, trades = [] }) {
    const chartContainerRef = useRef()
    const chartRef = useRef()
    const seriesRef = useRef()
    const [currentPrice, setCurrentPrice] = useState(0)
    const [priceChange, setPriceChange] = useState(0)
    const [chartType, setChartType] = useState('candlestick') // 'candlestick' or 'area'
    const [timeframe, setTimeframe] = useState('1D') // Selected timeframe
    const [isUpdating, setIsUpdating] = useState(false)

    // Create chart once
    useEffect(() => {
        if (!chartContainerRef.current) return

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { color: '#fafaf9' },
                textColor: '#78716c',
            },
            grid: {
                vertLines: { color: '#f5f5f4' },
                horzLines: { color: '#f5f5f4' },
            },
            crosshair: {
                mode: 1,
            },
            rightPriceScale: {
                borderColor: '#e7e5e4',
            },
            timeScale: {
                borderColor: '#e7e5e4',
                timeVisible: true,
                secondsVisible: false,
            },
        })

        chartRef.current = chart

        // Create series based on chart type
        let series
        if (chartType === 'candlestick') {
            series = chart.addCandlestickSeries({
                upColor: '#16a34a',
                downColor: '#dc2626',
                borderVisible: false,
                wickUpColor: '#16a34a',
                wickDownColor: '#dc2626',
            })
        } else {
            series = chart.addAreaSeries({
                lineColor: '#2563eb',
                topColor: 'rgba(37, 99, 235, 0.4)',
                bottomColor: 'rgba(37, 99, 235, 0.0)',
                lineWidth: 2,
            })
        }

        seriesRef.current = series

        // Map timeframe to Binance interval
        const getInterval = () => {
            const intervalMap = {
                '1D': { interval: '5m', limit: 288 },
                '5D': { interval: '15m', limit: 480 },
                '1M': { interval: '1h', limit: 720 },
                '3M': { interval: '4h', limit: 540 },
                '6M': { interval: '1d', limit: 180 },
                '1Y': { interval: '1d', limit: 365 },
            }
            return intervalMap[timeframe] || { interval: '5m', limit: 200 }
        }

        // Fetch real data from Binance
        const fetchChartData = async () => {
            try {
                const symbolFormatted = symbol.replace('/', '')
                const { interval, limit } = getInterval()
                const response = await fetch(
                    `https://api.binance.com/api/v3/klines?symbol=${symbolFormatted}&interval=${interval}&limit=${limit}`
                )
                const data = await response.json()

                if (chartType === 'candlestick') {
                    const chartData = data.map(candle => ({
                        time: candle[0] / 1000,
                        open: parseFloat(candle[1]),
                        high: parseFloat(candle[2]),
                        low: parseFloat(candle[3]),
                        close: parseFloat(candle[4]),
                    }))
                    series.setData(chartData)

                    if (chartData.length > 0) {
                        const latest = chartData[chartData.length - 1]
                        const first = chartData[0]
                        setCurrentPrice(latest.close)
                        const change = ((latest.close - first.open) / first.open) * 100
                        setPriceChange(change)
                    }
                } else {
                    // Area chart uses close prices
                    const chartData = data.map(candle => ({
                        time: candle[0] / 1000,
                        value: parseFloat(candle[4]),
                    }))
                    series.setData(chartData)

                    if (chartData.length > 0) {
                        const latest = chartData[chartData.length - 1]
                        const first = chartData[0]
                        setCurrentPrice(latest.value)
                        const change = ((latest.value - first.value) / first.value) * 100
                        setPriceChange(change)
                    }
                }

                // Add trade markers
                addTradeMarkers(series, data)
            } catch (error) {
                console.error('Error fetching chart data:', error)
            }
        }

        // Function to add trade markers
        const addTradeMarkers = (series, chartData) => {
            if (!trades || trades.length === 0) return

            const markers = []
            const chartStartTime = chartData[0]?.[0] / 1000 || 0
            const chartEndTime = chartData[chartData.length - 1]?.[0] / 1000 || 0

            trades
                .filter(trade => trade.coin === symbol.split('/')[0])
                .forEach((trade) => {
                    // Use actual timestamps if available, otherwise fallback to estimated positions
                    let entryTime, exitTime

                    if (trade.entryTimestamp && trade.exitTimestamp) {
                        // Use real timestamps from trade data
                        entryTime = trade.entryTimestamp
                        exitTime = trade.exitTimestamp
                    } else {
                        // Fallback: estimate position on chart (for backwards compatibility)
                        const timeRange = chartEndTime - chartStartTime
                        exitTime = chartEndTime - (timeRange * 0.2)
                        entryTime = exitTime - (timeRange * 0.05)
                    }

                    // Only show markers if they're within the chart's time range
                    if (entryTime >= chartStartTime && entryTime <= chartEndTime) {
                        // Entry marker (BUY)
                        markers.push({
                            time: entryTime,
                            position: trade.side === 'LONG' ? 'belowBar' : 'aboveBar',
                            color: trade.side === 'LONG' ? '#16a34a' : '#dc2626',
                            shape: trade.side === 'LONG' ? 'arrowUp' : 'arrowDown',
                            text: `${trade.side === 'LONG' ? '↑' : '↓'} $${trade.entryPrice.toFixed(2)}`,
                            size: 1,
                        })
                    }

                    if (exitTime >= chartStartTime && exitTime <= chartEndTime) {
                        // Exit marker (SELL)
                        markers.push({
                            time: exitTime,
                            position: trade.side === 'LONG' ? 'aboveBar' : 'belowBar',
                            color: trade.pnl >= 0 ? '#16a34a' : '#dc2626',
                            shape: 'circle',
                            text: `$${trade.exitPrice.toFixed(2)} ${trade.pnl >= 0 ? '✅' : '❌'}`,
                            size: 1,
                        })
                    }
                })

            if (markers.length > 0) {
                series.setMarkers(markers)
            }
        }

        fetchChartData()
        const interval = setInterval(fetchChartData, 30000)

        const handleResize = () => {
            chart.applyOptions({
                width: chartContainerRef.current.clientWidth,
                height: chartContainerRef.current.clientHeight,
            })
        }

        window.addEventListener('resize', handleResize)
        handleResize()

        return () => {
            window.removeEventListener('resize', handleResize)
            chart.remove()
        }
    }, [chartType])

    // Update data when dependencies change
    useEffect(() => {
        if (!chartRef.current || !seriesRef.current) return

        const series = seriesRef.current

        // Map timeframe to Binance interval
        const getInterval = () => {
            const intervalMap = {
                '1D': { interval: '5m', limit: 288 },
                '5D': { interval: '15m', limit: 480 },
                '1M': { interval: '1h', limit: 720 },
                '3M': { interval: '4h', limit: 540 },
                '6M': { interval: '1d', limit: 180 },
                '1Y': { interval: '1d', limit: 365 },
            }
            return intervalMap[timeframe] || { interval: '5m', limit: 200 }
        }

        // Fetch real data from Binance
        const fetchChartData = async () => {
            try {
                const symbolFormatted = symbol.replace('/', '')
                const { interval, limit } = getInterval()
                const response = await fetch(
                    `https://api.binance.com/api/v3/klines?symbol=${symbolFormatted}&interval=${interval}&limit=${limit}`
                )
                const data = await response.json()

                if (chartType === 'candlestick') {
                    const chartData = data.map(candle => ({
                        time: candle[0] / 1000,
                        open: parseFloat(candle[1]),
                        high: parseFloat(candle[2]),
                        low: parseFloat(candle[3]),
                        close: parseFloat(candle[4]),
                    }))
                    series.setData(chartData)

                    if (chartData.length > 0) {
                        const latest = chartData[chartData.length - 1]
                        const first = chartData[0]
                        setCurrentPrice(latest.close)
                        const change = ((latest.close - first.open) / first.open) * 100
                        setPriceChange(change)
                    }
                } else {
                    // Area chart uses close prices
                    const chartData = data.map(candle => ({
                        time: candle[0] / 1000,
                        value: parseFloat(candle[4]),
                    }))
                    series.setData(chartData)

                    if (chartData.length > 0) {
                        const latest = chartData[chartData.length - 1]
                        const first = chartData[0]
                        setCurrentPrice(latest.value)
                        const change = ((latest.value - first.value) / first.value) * 100
                        setPriceChange(change)
                    }
                }

                // Add trade markers
                addTradeMarkers(series, data)
            } catch (error) {
                console.error('Error fetching chart data:', error)
            }
        }

        // Function to add trade markers
        const addTradeMarkers = (series, chartData) => {
            if (!trades || trades.length === 0) return

            const markers = []
            const chartStartTime = chartData[0]?.[0] / 1000 || 0
            const chartEndTime = chartData[chartData.length - 1]?.[0] / 1000 || 0

            trades
                .filter(trade => trade.coin === symbol.split('/')[0])
                .forEach((trade) => {
                    // Use actual timestamps if available, otherwise fallback to estimated positions
                    let entryTime, exitTime

                    if (trade.entryTimestamp && trade.exitTimestamp) {
                        // Use real timestamps from trade data
                        entryTime = trade.entryTimestamp
                        exitTime = trade.exitTimestamp
                    } else {
                        // Fallback: estimate position on chart (for backwards compatibility)
                        const timeRange = chartEndTime - chartStartTime
                        exitTime = chartEndTime - (timeRange * 0.2)
                        entryTime = exitTime - (timeRange * 0.05)
                    }

                    // Only show markers if they're within the chart's time range
                    if (entryTime >= chartStartTime && entryTime <= chartEndTime) {
                        // Entry marker (BUY)
                        markers.push({
                            time: entryTime,
                            position: trade.side === 'LONG' ? 'belowBar' : 'aboveBar',
                            color: trade.side === 'LONG' ? '#16a34a' : '#dc2626',
                            shape: trade.side === 'LONG' ? 'arrowUp' : 'arrowDown',
                            text: `${trade.side === 'LONG' ? '↑' : '↓'} $${trade.entryPrice.toFixed(2)}`,
                            size: 1,
                        })
                    }

                    if (exitTime >= chartStartTime && exitTime <= chartEndTime) {
                        // Exit marker (SELL)
                        markers.push({
                            time: exitTime,
                            position: trade.side === 'LONG' ? 'aboveBar' : 'belowBar',
                            color: trade.pnl >= 0 ? '#16a34a' : '#dc2626',
                            shape: 'circle',
                            text: `$${trade.exitPrice.toFixed(2)} ${trade.pnl >= 0 ? '✅' : '❌'}`,
                            size: 1,
                        })
                    }
                })

            if (markers.length > 0) {
                series.setMarkers(markers)
            }
        }

        fetchChartData()
        const interval = setInterval(fetchChartData, 30000)

        return () => {
            clearInterval(interval)
        }
    }, [symbol, trades, chartType, timeframe])

    const timeframes = ['1D', '5D', '1M', '3M', '6M', '1Y']

    return (
        <div className="chart-container">
            <div className="chart-header">
                <h2 className="chart-title">{symbol}</h2>
                <div className="chart-controls">
                    <div className="chart-type-toggle">
                        <button
                            className={`chart-type-btn ${chartType === 'candlestick' ? 'active' : ''}`}
                            onClick={() => setChartType('candlestick')}
                        >
                            Candles
                        </button>
                        <button
                            className={`chart-type-btn ${chartType === 'area' ? 'active' : ''}`}
                            onClick={() => setChartType('area')}
                        >
                            Area
                        </button>
                    </div>
                    <div className="chart-info">
                        <span className="chart-price">
                            ${currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                        <span className={`chart-change ${priceChange >= 0 ? 'positive' : 'negative'}`}>
                            {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                        </span>
                    </div>
                </div>
            </div>

            <div className="timeframe-selector">
                {timeframes.map(tf => (
                    <button
                        key={tf}
                        className={`timeframe-btn ${timeframe === tf ? 'active' : ''}`}
                        onClick={() => setTimeframe(tf)}
                    >
                        {tf}
                    </button>
                ))}
            </div>

            <div ref={chartContainerRef} className={`chart ${isUpdating ? 'updating' : ''}`} />
        </div>
    )
}

export default Chart
