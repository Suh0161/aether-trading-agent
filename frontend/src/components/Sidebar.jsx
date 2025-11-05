import { useState, memo } from 'react'
import Positions from './sidebar/Positions'
import CompletedTrades from './sidebar/CompletedTrades'
import AgentChat from './sidebar/AgentChat'
import './Sidebar.css'

function Sidebar({ positions, trades, agentMessages }) {
  const [activeTab, setActiveTab] = useState('positions')

  return (
    <div className="sidebar">
      <div className="sidebar-tabs">
        <button
          className={`tab ${activeTab === 'positions' ? 'active' : ''}`}
          onClick={() => setActiveTab('positions')}
        >
          Positions
        </button>
        <button
          className={`tab ${activeTab === 'trades' ? 'active' : ''}`}
          onClick={() => setActiveTab('trades')}
        >
          Completed Trades
        </button>
        <button
          className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          Agent Chat
        </button>
      </div>

      <div className={`sidebar-content ${activeTab === 'chat' ? 'no-padding' : ''}`}>
        {activeTab === 'positions' && <Positions positions={positions} />}
        {activeTab === 'trades' && <CompletedTrades trades={trades} />}
        {activeTab === 'chat' && <AgentChat agentMessages={agentMessages} />}
      </div>
    </div>
  )
}

export default memo(Sidebar)
