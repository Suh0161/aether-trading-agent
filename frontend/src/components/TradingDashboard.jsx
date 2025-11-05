import Chart from './Chart'
import './TradingDashboard.css'

function TradingDashboard({ positions = [], trades = [] }) {
    return (
        <div className="trading-dashboard">
            <div className="dashboard-content">
                <Chart positions={positions} trades={trades} />
            </div>
        </div>
    )
}

export default TradingDashboard

