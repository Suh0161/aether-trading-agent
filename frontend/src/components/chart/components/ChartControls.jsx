import '../../ChartControls.css'

function ChartControls({ timeframe, chartType, onTimeframeChange, onChartTypeChange }) {
    const timeframes = [
        { value: '5m', label: '5M' },
        { value: '15m', label: '15M' },
        { value: '1h', label: '1H' },
        { value: '4h', label: '4H' },
        { value: '1d', label: '1D' },
        { value: '1w', label: '1W' }
    ]

    const chartTypes = [
        { value: 'candlestick', label: 'Candlestick', icon: null },
        { value: 'area', label: 'Area', icon: null }
    ]

    return (
        <div className="chart-controls">
            <div className="timeframe-controls">
                <span className="control-label">Timeframe:</span>
                <div className="timeframe-buttons">
                    {timeframes.map((tf) => (
                        <button
                            key={tf.value}
                            className={`timeframe-btn ${timeframe === tf.value ? 'active' : ''}`}
                            onClick={() => onTimeframeChange(tf.value)}
                        >
                            {tf.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="chart-type-controls">
                <span className="control-label">Chart:</span>
                <div className="chart-type-buttons">
                    {chartTypes.map((type) => (
                        <button
                            key={type.value}
                            className={`chart-type-btn ${chartType === type.value ? 'active' : ''}`}
                            onClick={() => onChartTypeChange(type.value)}
                        >
                            {type.icon && <span className="chart-type-icon">{type.icon}</span>}
                            <span className="chart-type-label">{type.label}</span>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default ChartControls
