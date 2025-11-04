"""Position management for trading agent."""

import logging
from typing import Dict, Optional

from src.utils.snapshot_utils import get_price_from_snapshot

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages position tracking, entry prices, stop losses, and take profits."""

    def __init__(self, config):
        """
        Initialize position manager.

        Args:
            config: Configuration object with mock_starting_equity
        """
        # Track entry prices and timestamps for P&L calculation and trade logging
        # NEW: Track per position type (swing and scalp can coexist)
        self.position_entry_prices = {}  # {symbol: {'swing': price, 'scalp': price}}
        self.position_entry_timestamps = {}  # {symbol: {'swing': timestamp, 'scalp': timestamp}} - Unix timestamp in seconds

        # Track position sizes internally (for demo mode when exchange doesn't support position queries)
        # NEW: Track swing and scalp positions separately - can coexist!
        self.tracked_position_sizes = {}  # {symbol: {'swing': size, 'scalp': size}} - positive for long, negative for short

        # Track equity dynamically for demo mode (starts at mock equity from config, updates with realized P&L)
        self.tracked_equity = config.mock_starting_equity  # Starting equity for demo mode (will update with realized P&L)
        self.starting_equity = config.mock_starting_equity  # Track starting equity for daily reset
        self.current_equity = config.mock_starting_equity  # Current equity (tracked_equity + unrealized P&L, or real equity from exchange)

        # Track stop loss and take profit for automatic monitoring
        self.position_stop_losses = {}  # {symbol: {'swing': sl, 'scalp': sl}}
        self.position_take_profits = {}  # {symbol: {'swing': tp, 'scalp': tp}}

        # Track leverage and risk/reward for position monitoring
        self.position_leverages = {}  # {symbol: {'swing': leverage, 'scalp': leverage}}
        self.position_risk_amounts = {}  # {symbol: {'swing': risk, 'scalp': risk}}
        self.position_reward_amounts = {}  # {symbol: {'swing': reward, 'scalp': reward}}

        # Track highest/lowest price for trailing stop (swing trades only)
        self.position_highest_prices = {}  # {symbol: {'swing': highest}} for LONG positions
        self.position_lowest_prices = {}  # {symbol: {'swing': lowest}} for SHORT positions
        self.position_initial_sl = {}  # {symbol: {'swing': initial_sl}} to calculate R multiples

        # Track confidence when position was opened (for adaptive trailing stop)
        self.position_confidence = {}  # {symbol: {'swing': confidence, 'scalp': confidence}}

        # Track last scalp close time per symbol to prevent immediate re-entry (cooldown)
        self.last_scalp_close_time = {}  # {symbol: timestamp} - Unix timestamp in seconds

    def get_position_by_type(self, symbol: str, position_type: str) -> float:
        """Helper to get position size by type (swing or scalp). Returns 0 if not found."""
        positions = self.tracked_position_sizes.get(symbol, {})
        if isinstance(positions, dict):
            return positions.get(position_type, 0.0)
        # Backward compatibility: if old format (single value), treat as swing
        return positions if position_type == 'swing' else 0.0

    def set_position_by_type(self, symbol: str, position_type: str, size: float):
        """Helper to set position size by type."""
        if symbol not in self.tracked_position_sizes:
            self.tracked_position_sizes[symbol] = {}
        if not isinstance(self.tracked_position_sizes[symbol], dict):
            # Convert old format to new format
            old_size = self.tracked_position_sizes[symbol]
            self.tracked_position_sizes[symbol] = {'swing': old_size, 'scalp': 0.0}
        self.tracked_position_sizes[symbol][position_type] = size
        # Clean up if both are zero
        if self.tracked_position_sizes[symbol].get('swing', 0.0) == 0.0 and self.tracked_position_sizes[symbol].get('scalp', 0.0) == 0.0:
            self.tracked_position_sizes[symbol] = {}

    def get_total_position(self, symbol: str) -> float:
        """Get total position size (swing + scalp) for backward compatibility."""
        positions = self.tracked_position_sizes.get(symbol, {})
        if isinstance(positions, dict):
            return positions.get('swing', 0.0) + positions.get('scalp', 0.0)
        return positions  # Old format

    def update_trailing_stops(self, symbol: str, position_type: str, position_size: float, current_price: float):
        """
        Update trailing stops based on price movement.

        For swing trades only, implements 10-15% trailing based on confidence.
        Higher confidence = tighter trailing (10%), lower confidence = looser (15%).

        Args:
            symbol: Trading symbol
            position_type: 'swing' or 'scalp' (only swing gets trailing)
            position_size: Position size (positive for long, negative for short)
            current_price: Current market price
        """
        # Only implement trailing stops for swing trades
        if position_type != 'swing':
            return

        # Get confidence for this position
        confidence = 0.5  # Default medium confidence
        if symbol in self.position_confidence:
            conf_dict = self.position_confidence[symbol]
            if isinstance(conf_dict, dict):
                confidence = conf_dict.get(position_type, 0.5)
            else:
                confidence = conf_dict if position_type == 'swing' else 0.5

        # Calculate trailing percentage based on confidence
        # Higher confidence = tighter trailing (10%), lower confidence = looser (15%)
        if confidence >= 0.8:
            trail_pct = 0.10  # 10% trailing for high confidence
        elif confidence >= 0.6:
            trail_pct = 0.12  # 12% trailing for medium-high confidence
        else:
            trail_pct = 0.15  # 15% trailing for lower confidence

        # Update highest/lowest prices and trailing stops
        if position_size > 0:  # LONG position
            # Track highest price reached
            current_highest = self.position_highest_prices.get(symbol, {}).get(position_type, current_price)
            if current_price > current_highest:
                # Price went higher - update highest price
                if symbol not in self.position_highest_prices:
                    self.position_highest_prices[symbol] = {}
                self.position_highest_prices[symbol][position_type] = current_price
                current_highest = current_price

                # Update trailing stop: trail behind highest price
                new_sl = current_highest * (1 - trail_pct)
                if symbol not in self.position_stop_losses:
                    self.position_stop_losses[symbol] = {}
                self.position_stop_losses[symbol][position_type] = new_sl

                logger.info(f"[TRAILING] {symbol} {position_type} LONG: New high ${current_highest:.2f}, SL updated to ${new_sl:.2f} ({trail_pct*100:.0f}% trail, conf: {confidence:.2f})")

        elif position_size < 0:  # SHORT position
            # Track lowest price reached
            current_lowest = self.position_lowest_prices.get(symbol, {}).get(position_type, current_price)
            if current_price < current_lowest:
                # Price went lower - update lowest price
                if symbol not in self.position_lowest_prices:
                    self.position_lowest_prices[symbol] = {}
                self.position_lowest_prices[symbol][position_type] = current_price
                current_lowest = current_price

                # Update trailing stop: trail above lowest price
                new_sl = current_lowest * (1 + trail_pct)
                if symbol not in self.position_stop_losses:
                    self.position_stop_losses[symbol] = {}
                self.position_stop_losses[symbol][position_type] = new_sl

                logger.info(f"[TRAILING] {symbol} {position_type} SHORT: New low ${current_lowest:.2f}, SL updated to ${new_sl:.2f} ({trail_pct*100:.0f}% trail, conf: {confidence:.2f})")

    def check_position_sl_tp(self, symbol: str, snapshot, position_type: str, position_size: float, current_price: float) -> Optional[str]:
        """
        Check stop loss and take profit for a specific position type.

        Args:
            symbol: Trading symbol
            snapshot: Market snapshot
            position_type: 'swing' or 'scalp'
            position_size: Position size (positive for long, negative for short)
            current_price: Current market price

        Returns:
            JSON decision string if SL/TP hit, None otherwise
        """
        # Get stored SL/TP for this position type
        stored_stop_loss = None
        stored_take_profit = None
        entry_price = current_price

        if symbol in self.position_stop_losses:
            sl_dict = self.position_stop_losses[symbol]
            if isinstance(sl_dict, dict):
                stored_stop_loss = sl_dict.get(position_type)
            else:
                # Backward compatibility: if old format, only use for swing
                stored_stop_loss = sl_dict if position_type == 'swing' else None

        if symbol in self.position_take_profits:
            tp_dict = self.position_take_profits[symbol]
            if isinstance(tp_dict, dict):
                stored_take_profit = tp_dict.get(position_type)
            else:
                # Backward compatibility: if old format, only use for swing
                stored_take_profit = tp_dict if position_type == 'swing' else None

        if symbol in self.position_entry_prices:
            entry_dict = self.position_entry_prices[symbol]
            if isinstance(entry_dict, dict):
                entry_price = entry_dict.get(position_type, current_price)
            else:
                # Backward compatibility
                entry_price = entry_dict if position_type == 'swing' else current_price

        # Check stop loss
        if stored_stop_loss is not None:
            if position_size > 0:  # Long position
                if current_price <= stored_stop_loss:
                    logger.info(f"[SL] {symbol} {position_type} LONG SL triggered: ${current_price:.2f} <= ${stored_stop_loss:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} long stop loss triggered: price ${current_price:.2f} <= ${stored_stop_loss:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision
            else:  # Short position
                if current_price >= stored_stop_loss:
                    logger.info(f"[SL] {symbol} {position_type} SHORT SL triggered: ${current_price:.2f} >= ${stored_stop_loss:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} short stop loss triggered: price ${current_price:.2f} >= ${stored_stop_loss:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision

        # Check take profit
        if stored_take_profit is not None:
            if position_size > 0:  # Long position
                if current_price >= stored_take_profit:
                    logger.info(f"[TP] {symbol} {position_type} LONG TP triggered: ${current_price:.2f} >= ${stored_take_profit:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} long take profit triggered: price ${current_price:.2f} >= ${stored_take_profit:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision
            else:  # Short position
                if current_price <= stored_take_profit:
                    logger.info(f"[TP] {symbol} {position_type} SHORT TP triggered: ${current_price:.2f} <= ${stored_take_profit:.2f}")
                    decision = f'{{"action": "close", "size_pct": 1.0, "reason": "{position_type.capitalize()} short take profit triggered: price ${current_price:.2f} <= ${stored_take_profit:.2f}", "position_type": "{position_type}"}}'
                    # Clear stored stop loss/take profit for this type
                    self._clear_position_tracking(symbol, position_type)
                    return decision

        return None  # No SL/TP hit

    def _clear_position_tracking(self, symbol: str, position_type: str):
        """Clear position tracking data for a specific position type."""
        # Clear stop loss/take profit
        if symbol in self.position_stop_losses:
            if isinstance(self.position_stop_losses[symbol], dict):
                if position_type in self.position_stop_losses[symbol]:
                    del self.position_stop_losses[symbol][position_type]
            else:
                # Old format: clear entire entry
                del self.position_stop_losses[symbol]

        if symbol in self.position_take_profits:
            if isinstance(self.position_take_profits[symbol], dict):
                if position_type in self.position_take_profits[symbol]:
                    del self.position_take_profits[symbol][position_type]
            else:
                del self.position_take_profits[symbol]

        # Clear confidence
        if symbol in self.position_confidence:
            if isinstance(self.position_confidence[symbol], dict):
                if position_type in self.position_confidence[symbol]:
                    del self.position_confidence[symbol][position_type]
            else:
                del self.position_confidence[symbol]

        # Clear entry prices and timestamps
        if symbol in self.position_entry_prices:
            if isinstance(self.position_entry_prices[symbol], dict):
                if position_type in self.position_entry_prices[symbol]:
                    del self.position_entry_prices[symbol][position_type]
            else:
                del self.position_entry_prices[symbol]

        if symbol in self.position_entry_timestamps:
            if isinstance(self.position_entry_timestamps[symbol], dict):
                if position_type in self.position_entry_timestamps[symbol]:
                    del self.position_entry_timestamps[symbol][position_type]
            else:
                del self.position_entry_timestamps[symbol]

        # Clear trailing stop tracking (highest/lowest prices)
        if symbol in self.position_highest_prices:
            if isinstance(self.position_highest_prices[symbol], dict):
                if position_type in self.position_highest_prices[symbol]:
                    del self.position_highest_prices[symbol][position_type]
            else:
                del self.position_highest_prices[symbol]

        if symbol in self.position_lowest_prices:
            if isinstance(self.position_lowest_prices[symbol], dict):
                if position_type in self.position_lowest_prices[symbol]:
                    del self.position_lowest_prices[symbol][position_type]
            else:
                del self.position_lowest_prices[symbol]

        # Clear leverage and risk/reward tracking
        if symbol in self.position_leverages:
            if isinstance(self.position_leverages[symbol], dict):
                if position_type in self.position_leverages[symbol]:
                    del self.position_leverages[symbol][position_type]
            else:
                del self.position_leverages[symbol]

        if symbol in self.position_risk_amounts:
            if isinstance(self.position_risk_amounts[symbol], dict):
                if position_type in self.position_risk_amounts[symbol]:
                    del self.position_risk_amounts[symbol][position_type]
            else:
                del self.position_risk_amounts[symbol]

        if symbol in self.position_reward_amounts:
            if isinstance(self.position_reward_amounts[symbol], dict):
                if position_type in self.position_reward_amounts[symbol]:
                    del self.position_reward_amounts[symbol][position_type]
            else:
                del self.position_reward_amounts[symbol]
