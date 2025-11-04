import './PriceDisplay.css'

function PriceDisplay({ currentPrice, priceChange, symbol, isUpdating }) {
    const formatPrice = (price) => {
        if (price === null || price === undefined) return '--'

        // Format based on price magnitude
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

    const formatChange = (change) => {
        if (change === null || change === undefined) return '--'

        const sign = change >= 0 ? '+' : ''
        const color = change >= 0 ? 'positive' : 'negative'

        return {
            value: `${sign}${change.toFixed(2)}%`,
            color
        }
    }

    const changeData = formatChange(priceChange)

    return (
        <div className="price-display">
            <div className="price-main">
                <div className="price-symbol">{symbol}</div>
                <div className={`price-value ${isUpdating ? 'updating' : ''}`}>
                    ${formatPrice(currentPrice)}
                </div>
            </div>

            <div className={`price-change ${changeData.color}`}>
                <span className="price-change-value">
                    {changeData.value}
                </span>
                <div className={`price-change-indicator ${changeData.color}`}>
                    {priceChange > 0 && '↗'}
                    {priceChange < 0 && '↘'}
                    {priceChange === 0 && '→'}
                </div>
            </div>
        </div>
    )
}

export default PriceDisplay
