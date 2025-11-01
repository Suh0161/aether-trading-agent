"""
Example integration showing how to send data from your trading agent to the frontend.

Add this code to your loop_controller.py or wherever you execute trades.
"""

from src.api_client import APIClient
import logging

logger = logging.getLogger(__name__)


class TradingAgentWithAPI:
    """Example of integrating API client with your trading agent."""
    
    def __init__(self):
        # Initialize API client
        self.api = APIClient()
        logger.info("API client initialized")
    
    def update_frontend_balance(self, cash: float, unrealized_pnl: float):
        """Update balance in frontend."""
        self.api.update_balance(cash, unrealized_pnl)
    
    def sync_positions_to_frontend(self, positions_from_exchange):
        """
        Sync positions from exchange to frontend.
        
        Args:
            positions_from_exchange: List of positions from your exchange
        """
        # Clear old positions first
        import requests
        try:
            requests.delete("http://localhost:8000/api/positions", timeout=5)
        except:
            pass
        
        # Add current positions
        for position in positions_from_exchange:
            self.api.add_position(
                side=position['side'],  # 'LONG' or 'SHORT'
                coin=position['symbol'].replace('/USDT', ''),  # e.g., 'BTC'
                leverage=f"{position.get('leverage', 10)}X",
                notional=abs(position['notional']),
                unreal_pnl=position.get('unrealizedPnl', 0)
            )
    
    def log_trade_to_frontend(self, trade_info):
        """
        Log a completed trade to frontend.
        
        Args:
            trade_info: Dictionary with trade information
        """
        self.api.add_trade(
            coin=trade_info['symbol'].replace('/USDT', ''),
            side=trade_info['side'],
            entry_price=trade_info['entry_price'],
            exit_price=trade_info['exit_price'],
            quantity=trade_info['quantity'],
            entry_notional=trade_info['entry_notional'],
            exit_notional=trade_info['exit_notional'],
            holding_time=trade_info['holding_time'],  # e.g., "4H 53M"
            pnl=trade_info['pnl']
        )
    
    def send_agent_message(self, message: str):
        """Send agent reasoning/message to frontend chat."""
        self.api.add_agent_message(message)


# Example usage in your loop_controller.py:
"""
from src.api_client import APIClient

class LoopController:
    def __init__(self, config):
        # ... your existing code ...
        self.api = APIClient()
    
    def run(self):
        while self.running:
            # ... your trading logic ...
            
            # Update balance
            balance = self.get_account_balance()
            self.api.update_balance(
                cash=balance['free'],
                unrealized_pnl=balance['unrealizedPnl']
            )
            
            # Sync positions
            positions = self.get_open_positions()
            for pos in positions:
                self.api.add_position(
                    side='LONG' if pos['side'] == 'buy' else 'SHORT',
                    coin=pos['symbol'].replace('/USDT', ''),
                    leverage=f"{pos['leverage']}X",
                    notional=abs(pos['notional']),
                    unreal_pnl=pos['unrealizedPnl']
                )
            
            # When you close a trade
            if trade_closed:
                self.api.add_trade(
                    coin=trade['symbol'].replace('/USDT', ''),
                    side='LONG' if trade['side'] == 'buy' else 'SHORT',
                    entry_price=trade['entry_price'],
                    exit_price=trade['exit_price'],
                    quantity=trade['amount'],
                    entry_notional=trade['entry_notional'],
                    exit_notional=trade['exit_notional'],
                    holding_time=self.calculate_holding_time(trade),
                    pnl=trade['pnl']
                )
            
            # Send agent reasoning
            if agent_decision:
                self.api.add_agent_message(agent_decision['reasoning'])
            
            time.sleep(60)  # Wait before next iteration
"""
