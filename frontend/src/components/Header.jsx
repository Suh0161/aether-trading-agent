import { useState, useEffect } from 'react'
import './Header.css'

function Header({ balance }) {
  const totalUnrealizedPnL = balance.unrealizedPnL || 0
  const [agentPaused, setAgentPaused] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [modalConfig, setModalConfig] = useState({ title: '', message: '', onConfirm: null })

  useEffect(() => {
    // Check agent status on mount
    fetch('http://localhost:8000/api/agent/status')
      .then(res => res.json())
      .then(data => setAgentPaused(data.paused))
      .catch(err => console.error('Failed to get agent status:', err))
  }, [])

  const showConfirmModal = (title, message, onConfirm) => {
    setModalConfig({ title, message, onConfirm })
    setShowModal(true)
  }

  const handleEmergencyClose = () => {
    showConfirmModal(
      'Close All Positions',
      'This will close all open positions at market price on the next cycle. The AI will continue running normally and can resume trading in subsequent cycles.',
      async () => {
        setLoading(true)
        try {
          const res = await fetch('http://localhost:8000/api/emergency-close', { method: 'POST' })
          const data = await res.json()
          console.log(data.message)
        } catch (err) {
          console.error('Failed to trigger emergency close:', err)
        }
        setLoading(false)
      }
    )
  }

  const handleToggleAgent = async () => {
    setLoading(true)
    try {
      const endpoint = agentPaused ? '/api/agent/resume' : '/api/agent/pause'
      const res = await fetch(`http://localhost:8000${endpoint}`, { method: 'POST' })
      const data = await res.json()
      setAgentPaused(!agentPaused)
      console.log(data.message)
    } catch (err) {
      console.error('Failed to toggle agent:', err)
    }
    setLoading(false)
  }

  return (
    <>
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <img src="/aether.png" alt="AETHER" className="logo-image" draggable="false" />
          </div>
          
          <div className="control-buttons">
            <button 
              className={`control-btn ${agentPaused ? 'start' : 'pause'}`}
              onClick={handleToggleAgent}
              disabled={loading}
            >
              {agentPaused ? 'START AI' : 'PAUSE AI'}
            </button>
            <button 
              className="control-btn emergency"
              onClick={handleEmergencyClose}
              disabled={loading}
            >
              CLOSE ALL
            </button>
          </div>
        </div>

        <div className="header-right">
          <div className="balance-item">
            <span className="balance-label">AVAILABLE CASH:</span>
            <span className="balance-value">${balance.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>
          <div className="balance-item">
            <span className="balance-label">TOTAL UNREALIZED P&L:</span>
            <span className={`balance-value ${totalUnrealizedPnL >= 0 ? 'positive' : 'negative'}`}>
              ${totalUnrealizedPnL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </header>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{modalConfig.title}</h3>
            </div>
            <div className="modal-body">
              <p>{modalConfig.message}</p>
            </div>
            <div className="modal-footer">
              <button 
                className="modal-btn cancel"
                onClick={() => setShowModal(false)}
              >
                Cancel
              </button>
              <button 
                className="modal-btn confirm"
                onClick={() => {
                  setShowModal(false)
                  modalConfig.onConfirm()
                }}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default Header
