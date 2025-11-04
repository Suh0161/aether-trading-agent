import { useState, useRef, useEffect } from 'react'
import '../../CoinSelector.css'

function CoinSelector({ selectedCoin, onCoinChange, availableCoins }) {
    const [showDropdown, setShowDropdown] = useState(false)
    const dropdownRef = useRef(null)

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setShowDropdown(false)
            }
        }

        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    const handleCoinSelect = (coin) => {
        onCoinChange(coin.symbol)
        setShowDropdown(false)
    }

    const currentCoin = availableCoins.find(coin => coin.symbol === selectedCoin) || availableCoins[0]

    return (
        <div className="coin-selector" ref={dropdownRef}>
            <button
                className={`chart-title clickable ${showDropdown ? 'open' : ''}`}
                onClick={() => setShowDropdown(!showDropdown)}
                aria-expanded={showDropdown}
                aria-haspopup="listbox"
            >
                <div className="chart-title-content">
                    <img
                        src={currentCoin.icon}
                        alt={currentCoin.name}
                        className="chart-title-icon"
                    />
                    <span className="chart-title-text">{currentCoin.name}</span>
                    <svg
                        className={`dropdown-arrow ${showDropdown ? 'open' : ''}`}
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                    >
                        <path d="m6 9 6 6 6-6"/>
                    </svg>
                </div>
            </button>

            {showDropdown && (
                <div className="coin-dropdown" role="listbox">
                    {availableCoins.map((coin) => (
                        <button
                            key={coin.symbol}
                            className={`coin-option ${coin.symbol === selectedCoin ? 'selected' : ''}`}
                            onClick={() => handleCoinSelect(coin)}
                            role="option"
                            aria-selected={coin.symbol === selectedCoin}
                        >
                            <img
                                src={coin.icon}
                                alt={coin.name}
                                className="coin-option-icon"
                            />
                            <div className="coin-option-info">
                                <span className="coin-option-name">{coin.name}</span>
                                <span className="coin-option-symbol">{coin.symbol}</span>
                            </div>
                            {coin.symbol === selectedCoin && (
                                <svg
                                    className="coin-option-check"
                                    width="16"
                                    height="16"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                >
                                    <path d="m20 6-10.5 10.5L4 12"/>
                                </svg>
                            )}
                        </button>
                    ))}
                </div>
            )}
        </div>
    )
}

export default CoinSelector
