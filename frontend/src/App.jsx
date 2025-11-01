import { useState, useEffect } from 'react'
import Header from './components/Header'
import Chart from './components/Chart'
import Sidebar from './components/Sidebar'
import './App.css'

function App() {
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  const [balance, setBalance] = useState({ cash: 0, unrealizedPnL: 0 })
  const [agentMessages, setAgentMessages] = useState([])

  // Fetch data from backend
  useEffect(() => {
    const API_BASE = 'http://localhost:8000/api'
    
    const fetchData = async () => {
      try {
        // Fetch positions
        const positionsRes = await fetch(`${API_BASE}/positions`)
        if (positionsRes.ok) {
          const positionsData = await positionsRes.json()
          setPositions(positionsData)
        }

        // Fetch trades
        const tradesRes = await fetch(`${API_BASE}/trades`)
        if (tradesRes.ok) {
          const tradesData = await tradesRes.json()
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
      } catch (error) {
        console.error('Error fetching data:', error)
        // Keep existing data on error
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000) // Update every 5 seconds
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="app">
      <Header balance={balance} />
      <div className="main-content">
        <Chart symbol="BTC/USDT" trades={trades} />
        <Sidebar 
          positions={positions}
          trades={trades}
          agentMessages={agentMessages}
        />
      </div>
    </div>
  )
}

export default App
