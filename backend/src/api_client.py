"""
API Client for sending trading data to the frontend API server.
"""

import requests
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class APIClient:
    """Client for communicating with the frontend API server."""
    
    def __init__(self, base_url: str = "http://localhost:8000/api"):
        """
        Initialize API client.
        
        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def _post(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """
        Send POST request to API.
        
        Args:
            endpoint: API endpoint
            data: Data to send
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.session.post(f"{self.base_url}/{endpoint}", json=data, timeout=5)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to send data to API: {e}")
            return False
    
    def _put(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """
        Send PUT request to API.
        
        Args:
            endpoint: API endpoint
            data: Data to send
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.session.put(f"{self.base_url}/{endpoint}", json=data, timeout=5)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to update data via API: {e}")
            return False
    
    def update_balance(self, cash: float, unrealized_pnl: float) -> bool:
        """
        Update account balance.
        
        Args:
            cash: Available cash
            unrealized_pnl: Total unrealized P&L
            
        Returns:
            True if successful
        """
        return self._put("balance", {
            "cash": cash,
            "unrealizedPnL": unrealized_pnl
        })
    
    def add_position(self, side: str, coin: str, leverage: str, 
                    notional: float, unreal_pnl: float) -> bool:
        """
        Add or update a position.
        
        Args:
            side: 'LONG' or 'SHORT'
            coin: Coin symbol (e.g., 'BTC')
            leverage: Leverage string (e.g., '10X')
            notional: Position notional value
            unreal_pnl: Unrealized P&L
            
        Returns:
            True if successful
        """
        return self._post("positions", {
            "side": side,
            "coin": coin,
            "leverage": leverage,
            "notional": notional,
            "unrealPnL": unreal_pnl
        })
    
    def add_trade(self, coin: str, side: str, entry_price: float, 
                 exit_price: float, quantity: float, entry_notional: float,
                 exit_notional: float, holding_time: str, pnl: float,
                 entry_timestamp: int = None, exit_timestamp: int = None) -> bool:
        """
        Add a completed trade.
        
        Args:
            coin: Coin symbol
            side: 'LONG' or 'SHORT'
            entry_price: Entry price
            exit_price: Exit price
            quantity: Trade quantity
            entry_notional: Entry notional value
            exit_notional: Exit notional value
            holding_time: Holding time string (e.g., '4H 53M')
            pnl: Profit/Loss
            entry_timestamp: Unix timestamp (seconds) when position was opened
            exit_timestamp: Unix timestamp (seconds) when position was closed
            
        Returns:
            True if successful
        """
        # Use current time if timestamps not provided (for backwards compatibility)
        if exit_timestamp is None:
            exit_timestamp = int(datetime.now().timestamp())
        if entry_timestamp is None:
            entry_timestamp = exit_timestamp  # Fallback if not provided
        
        timestamp = datetime.fromtimestamp(exit_timestamp).strftime("%d/%m %H:%M")
        
        return self._post("trades", {
            "id": exit_timestamp,  # Use exit timestamp as ID
            "coin": coin,
            "side": side,
            "entryPrice": entry_price,
            "exitPrice": exit_price,
            "quantity": quantity,
            "entryNotional": entry_notional,
            "exitNotional": exit_notional,
            "holdingTime": holding_time,
            "pnl": pnl,
            "timestamp": timestamp,
            "entryTimestamp": entry_timestamp,
            "exitTimestamp": exit_timestamp
        })
    
    def add_agent_message(self, text: str) -> bool:
        """
        Add an agent chat message.
        
        Args:
            text: Message text
            
        Returns:
            True if successful
        """
        return self._post("agent-messages", {
            "id": int(datetime.now().timestamp()),
            "text": text
        })
    
    def sync_positions(self, positions: List[Dict[str, Any]]) -> bool:
        """
        Sync all positions at once using PUT endpoint.
        
        Args:
            positions: List of position dictionaries
            
        Returns:
            True if successful
        """
        try:
            response = self.session.put(f"{self.base_url}/positions", json=positions, timeout=5)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to sync positions via API: {e}")
            return False
