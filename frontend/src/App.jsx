import { useState, useEffect, useRef } from 'react'
import Header from './components/Header'
import TradingDashboard from './components/TradingDashboard'
import Sidebar from './components/Sidebar'
import Toast from './components/Toast'
import PerformanceCard from './components/PerformanceCard'
import './App.css'

function App() {
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  const [balance, setBalance] = useState({ cash: 0, unrealizedPnL: 0 })
  const [agentMessages, setAgentMessages] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [toasts, setToasts] = useState([])
  const [showPerformance, setShowPerformance] = useState(false)

  // Use refs to store previous values for comparison without causing re-renders
  const prevPositionsRef = useRef([])
  const prevTradesRef = useRef([])

  // Toast notification system
  const addToast = (message, type = 'info') => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }

  // Fetch data from backend
  useEffect(() => {
    const API_BASE = '/api'

    const fetchData = async () => {
      try {
        // Fetch positions
        const positionsRes = await fetch(`${API_BASE}/positions`)
        if (positionsRes.ok) {
          const positionsData = await positionsRes.json()

          // Check for significant P&L changes using ref
          if (prevPositionsRef.current.length > 0) {
            positionsData.forEach((newPos, idx) => {
              const oldPos = prevPositionsRef.current[idx]
              if (oldPos && Math.abs(newPos.unrealPnL - oldPos.unrealPnL) > 50) {
                const change = newPos.unrealPnL - oldPos.unrealPnL
                addToast(
                  `${newPos.coin} P&L ${change > 0 ? '+' : ''}$${change.toFixed(2)}`,
                  change > 0 ? 'success' : 'error'
                )
              }
            })
          }

          // Update ref and state
          prevPositionsRef.current = positionsData
          setPositions(positionsData)
        }

        // Fetch trades
        const tradesRes = await fetch(`${API_BASE}/trades`)
        if (tradesRes.ok) {
          const tradesData = await tradesRes.json()

          // Notify on new trades using ref
          if (prevTradesRef.current.length > 0 && tradesData.length > prevTradesRef.current.length) {
            const newTrade = tradesData[tradesData.length - 1]
            addToast(
              `Trade closed: ${newTrade.coin} ${newTrade.pnl >= 0 ? '+' : ''}$${newTrade.pnl.toFixed(2)}`,
              newTrade.pnl >= 0 ? 'success' : 'error'
            )
          }

          // Update ref and state
          prevTradesRef.current = tradesData
          setTrades(tradesData)
        }

        // Fetch agent messages
        const messagesRes = await fetch(`${API_BASE}/agent-messages`)
        if (messagesRes.ok) {
          const messagesData = await messagesRes.json()
          setAgentMessages(messagesData)
        }

        // Fetch balance
        const balanceRes = await fetch(`${API_BASE}/balance`)
        if (balanceRes.ok) {
          const balanceData = await balanceRes.json()
          setBalance(balanceData)
        }

        setIsLoading(false)
      } catch (error) {
        console.error('Error fetching data:', error)
        if (isLoading) setIsLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [isLoading])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.key === 'p' && e.ctrlKey) {
        e.preventDefault()
        setShowPerformance(prev => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [])

  return (
    <div className="app">
      <Header
        balance={balance}
        showPerformance={showPerformance}
        setShowPerformance={setShowPerformance}
      />
      <div className="main-content">
        <TradingDashboard positions={positions} />
        <Sidebar
          positions={positions}
          trades={trades}
          agentMessages={agentMessages}
          isLoading={isLoading}
        />
      </div>

      {showPerformance && (
        <PerformanceCard
          trades={trades}
          balance={balance}
          onClose={() => setShowPerformance(false)}
        />
      )}

      {toasts.map(toast => (
        <Toast key={toast.id} message={toast.message} type={toast.type} />
      ))}
    </div>
  )
}

export default App
