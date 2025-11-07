import { createContext, useContext, useState, useEffect } from 'react'

const PriceContext = createContext(null)

export function PriceProvider({ children }) {
  const [coinPrices, setCoinPrices] = useState({})
  const [priceTimestamps, setPriceTimestamps] = useState({}) // Track when prices were last updated

  // Update price with timestamp
  const updatePrice = (symbol, price) => {
    if (price && !isNaN(price) && price > 0) {
      setCoinPrices(prev => ({ ...prev, [symbol]: price }))
      setPriceTimestamps(prev => ({ ...prev, [symbol]: Date.now() }))
    }
  }

  // Get price for a symbol
  const getPrice = (symbol) => {
    return coinPrices[symbol] || null
  }

  // Check if price is stale (> 5 seconds old)
  const isPriceStale = (symbol) => {
    const timestamp = priceTimestamps[symbol]
    if (!timestamp) return true
    return Date.now() - timestamp > 5000 // 5 seconds
  }

  return (
    <PriceContext.Provider value={{ coinPrices, updatePrice, getPrice, isPriceStale }}>
      {children}
    </PriceContext.Provider>
  )
}

export function usePriceContext() {
  const context = useContext(PriceContext)
  if (!context) {
    // Return fallback if context not available
    return {
      coinPrices: {},
      updatePrice: () => {},
      getPrice: () => null,
      isPriceStale: () => true
    }
  }
  return context
}

