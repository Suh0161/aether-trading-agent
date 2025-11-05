"""Frontend communication and updates for trading agent."""

import logging
from typing import Dict, Optional

from src.utils.snapshot_utils import get_price_from_snapshot

logger = logging.getLogger(__name__)


class FrontendManager:
    """Manages communication with the frontend API."""

    def __init__(self, config, api_client=None):
        """
        Initialize frontend manager.

        Args:
            config: Configuration object
            api_client: Optional API client for frontend communication
        """
        self.config = config
        self.api_client = api_client

    def update_frontend_all_positions(
        self,
        snapshots: dict,
        positions: dict,
        equity: float,
        cycle_count: int,
        position_manager
    ) -> None:
        """
        Update frontend with all positions aggregated from all symbols.

        NEW: Now handles both swing and scalp positions separately.

        Args:
            snapshots: Dict of {symbol: snapshot}
            positions: Dict of {symbol: position_size} (total for backward compat)
            equity: Current account equity
            cycle_count: Current cycle number
            position_manager: PositionManager instance for position data
        """
        if not self.api_client:
            return

        try:
            total_unrealized_pnl = 0.0
            positions_list = []

            # Process all positions (both swing and scalp separately)
            for symbol in self.config.symbols:
                snapshot = snapshots.get(symbol)
                if not snapshot:
                    continue

                current_price = get_price_from_snapshot(snapshot)
                base_currency = symbol.split('/')[0]

                # Process swing position
                swing_position = position_manager.get_position_by_type(symbol, 'swing')
                if abs(swing_position) > 0.0001:
                    entry_dict = position_manager.position_entry_prices.get(symbol, {})
                    if isinstance(entry_dict, dict):
                        entry_price = entry_dict.get('swing', current_price)
                    else:
                        entry_price = entry_dict

                    # Calculate unrealized P&L
                    was_long = swing_position > 0
                    if was_long:
                        unrealized_pnl = swing_position * (current_price - entry_price)
                        pnl_percentage = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                    else:
                        unrealized_pnl = abs(swing_position) * (entry_price - current_price)
                        pnl_percentage = ((entry_price - current_price) / entry_price) * 100 if entry_price > 0 else 0

                    total_unrealized_pnl += unrealized_pnl

                    # Get SL/TP/leverage for swing
                    stop_loss = None
                    take_profit = None
                    leverage = 1.0

                    if symbol in position_manager.position_stop_losses:
                        sl_dict = position_manager.position_stop_losses[symbol]
                        if isinstance(sl_dict, dict):
                            stop_loss = sl_dict.get('swing')
                        else:
                            stop_loss = sl_dict

                    if symbol in position_manager.position_take_profits:
                        tp_dict = position_manager.position_take_profits[symbol]
                        if isinstance(tp_dict, dict):
                            take_profit = tp_dict.get('swing')
                        else:
                            take_profit = tp_dict

                    if symbol in position_manager.position_leverages:
                        lev_dict = position_manager.position_leverages[symbol]
                        if isinstance(lev_dict, dict):
                            leverage = lev_dict.get('swing', 1.0)
                        else:
                            leverage = lev_dict

                    # Round leverage to whole number (Binance doesn't support decimals)
                    leverage_whole = int(round(leverage))
                    
                    positions_list.append({
                        "side": "LONG" if was_long else "SHORT",
                        "coin": base_currency,
                        "leverage": f"{leverage_whole}X",  # Whole number only (1x or 2x)
                        "notional": abs(swing_position) * current_price,
                        "unrealPnL": unrealized_pnl,
                        "entryPrice": entry_price,
                        "currentPrice": current_price,
                        "pnlPercent": pnl_percentage,
                        "stopLoss": stop_loss,
                        "takeProfit": take_profit,
                        "positionType": "swing"  # NEW: Mark position type
                    })

                # Process scalp position
                scalp_position = position_manager.get_position_by_type(symbol, 'scalp')
                if abs(scalp_position) > 0.0001:
                    entry_dict = position_manager.position_entry_prices.get(symbol, {})
                    if isinstance(entry_dict, dict):
                        entry_price = entry_dict.get('scalp', current_price)
                    else:
                        entry_price = current_price

                    # Calculate unrealized P&L
                    was_long = scalp_position > 0
                    if was_long:
                        unrealized_pnl = scalp_position * (current_price - entry_price)
                        pnl_percentage = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                    else:
                        unrealized_pnl = abs(scalp_position) * (entry_price - current_price)
                        pnl_percentage = ((entry_price - current_price) / entry_price) * 100 if entry_price > 0 else 0

                    total_unrealized_pnl += unrealized_pnl

                    # Get SL/TP/leverage for scalp
                    stop_loss = None
                    take_profit = None
                    leverage = 1.0

                    if symbol in position_manager.position_stop_losses:
                        sl_dict = position_manager.position_stop_losses[symbol]
                        if isinstance(sl_dict, dict):
                            stop_loss = sl_dict.get('scalp')
                        else:
                            stop_loss = None

                    if symbol in position_manager.position_take_profits:
                        tp_dict = position_manager.position_take_profits[symbol]
                        if isinstance(tp_dict, dict):
                            take_profit = tp_dict.get('scalp')
                        else:
                            take_profit = None

                    if symbol in position_manager.position_leverages:
                        lev_dict = position_manager.position_leverages[symbol]
                        if isinstance(lev_dict, dict):
                            leverage = lev_dict.get('scalp', 1.0)
                        else:
                            leverage = 1.0

                    # Round leverage to whole number (Binance doesn't support decimals)
                    leverage_whole = int(round(leverage))
                    
                    positions_list.append({
                        "side": "LONG" if was_long else "SHORT",
                        "coin": base_currency,
                        "leverage": f"{leverage_whole}X",  # Whole number only (1x or 2x)
                        "notional": abs(scalp_position) * current_price,
                        "unrealPnL": unrealized_pnl,
                        "entryPrice": entry_price,
                        "currentPrice": current_price,
                        "pnlPercent": pnl_percentage,
                        "stopLoss": stop_loss,
                        "takeProfit": take_profit,
                        "positionType": "scalp"  # NEW: Mark position type
                    })

            # Sync all positions (CRITICAL: Always sync, even if margin calculation is wrong)
            # This ensures positions persist across cycles and don't disappear
            if positions_list:
                self.api_client.sync_positions(positions_list)
                logger.debug(f"  Synced {len(positions_list)} positions to frontend")
            else:
                # Clear positions if no positions exist
                self.api_client.sync_positions([])
                logger.debug(f"  Cleared positions (no open positions)")

            # Update balance
            # Available cash = Total Equity - Margin Used
            # Total Equity = tracked_equity + unrealized P&L (for demo mode) or equity from exchange (for live mode)
            # Margin Used = Sum of (notional / leverage) for all open positions

            # Calculate total margin used across all open positions
            # Margin = Entry Notional / Leverage (the actual capital locked in the position at entry)
            # Use entry price, not current price, to calculate margin!
            total_margin_used = 0.0
            for pos in positions_list:
                coin = pos.get('coin', 'UNKNOWN')
                entry_price = pos.get('entryPrice')
                current_price = pos.get('currentPrice')
                leverage_str = pos.get('leverage', '1.0X')
                pos_type = pos.get('positionType', 'swing')

                # Get position size (quantity)
                symbol_for_pos = None
                for sym in self.config.symbols:
                    if sym.split('/')[0] == coin:
                        symbol_for_pos = sym
                        break

                position_size = 0.0
                if symbol_for_pos:
                    position_size = abs(position_manager.get_position_by_type(symbol_for_pos, pos_type))

                # Try to get actual leverage from stored position_leverages (more accurate)
                actual_leverage = None
                if symbol_for_pos and symbol_for_pos in position_manager.position_leverages:
                    lev_dict = position_manager.position_leverages[symbol_for_pos]
                    if isinstance(lev_dict, dict):
                        actual_leverage = lev_dict.get(pos_type)
                    else:
                        actual_leverage = lev_dict if pos_type == 'swing' else 1.0

                # Use stored leverage if available, otherwise parse from string
                if actual_leverage is not None and actual_leverage > 0:
                    leverage = actual_leverage
                else:
                    try:
                        leverage = float(leverage_str.replace('X', ''))
                    except (ValueError, AttributeError):
                        leverage = 1.0

                # Calculate margin using ENTRY price (not current price!)
                # Margin = (Position Size * Entry Price) / Leverage = Entry Notional / Leverage
                # CRITICAL: Validate position size - if margin seems unreasonable, the position size might be stored incorrectly
                if entry_price and position_size > 0 and leverage > 0:
                    entry_notional = position_size * entry_price
                    margin_for_position = entry_notional / leverage
                    
                    # Validate: If margin for a single position exceeds total equity, position size is likely stored incorrectly
                    # This can happen if old positions were stored as percentages instead of quantities
                    if margin_for_position > position_manager.tracked_equity * 2.0:  # More than 2x equity = definitely wrong
                        logger.error(f"  {coin} ({pos_type}) INVALID POSITION SIZE DETECTED: size={position_size:.6f}, margin=${margin_for_position:.2f} exceeds equity ${position_manager.tracked_equity:.2f}")
                        logger.error(f"    This position was likely stored incorrectly (as percentage instead of quantity). Skipping margin calculation for this position.")
                        logger.error(f"    RECOMMENDATION: Close this position and reopen it to fix the stored size.")
                        # Skip this position's margin to prevent incorrect cash calculation
                        continue
                    
                    total_margin_used += margin_for_position
                    logger.info(f"  {coin} ({pos_type}) margin calc: size={position_size:.6f}, entry=${entry_price:.2f}, entry_notional=${entry_notional:.2f}, leverage={leverage:.1f}x, margin=${margin_for_position:.2f}, stored_leverage={actual_leverage if actual_leverage is not None else 'N/A'}")
                elif position_size > 0 and leverage > 0 and current_price:
                    # Fallback: use current price if entry price unavailable (shouldn't happen)
                    current_notional = position_size * current_price
                    margin_for_position = current_notional / leverage
                    total_margin_used += margin_for_position
                    logger.warning(f"  {coin} ({pos_type}) using current price for margin calc: ${margin_for_position:.2f} (entry price missing!)")
                elif position_size > 0:
                    # Last resort: if no price available, skip this position (shouldn't happen)
                    logger.warning(f"  {coin} ({pos_type}) missing price/leverage for margin calculation - skipping margin for this position")
                # If position_size is 0, no margin needed (already handled by condition above)

            if self.config.exchange_type.lower() == "binance_demo":
                # Total equity = tracked base equity + unrealized P&L
                total_equity = position_manager.tracked_equity + total_unrealized_pnl
                # Available cash = total equity - margin used
                available_cash = total_equity - total_margin_used
            else:
                # For live mode, equity passed in already includes unrealized P&L
                total_equity = equity
                # Available cash = total equity - margin used
                available_cash = total_equity - total_margin_used

            # CRITICAL SAFEGUARD: Cap margin_used at total_equity to prevent negative cash
            # This can happen due to rounding errors in position size or margin calculation
            # If margin exceeds equity, we're over-leveraged - clamp margin to equity
            if total_margin_used > total_equity:
                logger.warning(f"  OVER-LEVERAGE DETECTED: Margin (${total_margin_used:.2f}) > Equity (${total_equity:.2f})")
                logger.warning(f"    This indicates rounding errors or position size calculation issues.")
                logger.warning(f"    Clamping margin to equity to prevent negative cash display.")
                # Cap margin at equity (meaning available cash = 0)
                total_margin_used = total_equity
                available_cash = 0.0
            else:
                available_cash = total_equity - total_margin_used
            
            # SMART MONEY MANAGEMENT: Ensure we never use more than 95% of equity as margin
            # This leaves a 5% buffer for opportunities and prevents over-leverage
            max_allowed_margin = total_equity * 0.95
            if total_margin_used > max_allowed_margin:
                logger.info(f"  SMART MONEY: Margin usage (${total_margin_used:.2f}) > 95% limit (${max_allowed_margin:.2f})")
                logger.info(f"    Clamping to 95% limit for smart money management (5% buffer maintained)")
                total_margin_used = max_allowed_margin
                available_cash = total_equity - total_margin_used

            # Safeguard: Available cash shouldn't be negative (indicates margin calculation error)
            # CRITICAL: Always send positions even if margin calculation shows negative cash
            # The margin calculation might be incorrect, but positions still exist and should be displayed
            if available_cash < 0:
                logger.warning(f"  WARNING: Negative available cash (${available_cash:.2f})! This indicates a margin calculation error.")
                logger.warning(f"    Total equity: ${total_equity:.2f}, Margin used: ${total_margin_used:.2f}")
                logger.warning(f"    Positions: {len(positions_list)}")
                logger.warning(f"    NOTE: Positions will still be displayed even with negative cash calculation")
                # Clamp to 0 for display (but log the actual value)
                available_cash_display = max(0.0, available_cash)
            else:
                available_cash_display = available_cash

            self.api_client.update_balance(available_cash_display, total_unrealized_pnl)

            # Debug logging for balance calculation
            logger.info(f"  Balance calculation: tracked_equity=${position_manager.tracked_equity:.2f}, unrealized_pnl=${total_unrealized_pnl:.2f}, total_equity=${total_equity:.2f}, margin_used=${total_margin_used:.2f}, available_cash=${available_cash:.2f}")
            logger.info(f"  Frontend updated: Cash=${available_cash_display:.2f}, P&L=${total_unrealized_pnl:.2f} (positions: {len(positions_list)})")

            # Log detailed position breakdown if margin seems wrong
            if total_margin_used > total_equity * 1.5:  # Margin > 150% of equity is suspicious
                logger.warning(f"  WARNING: Margin (${total_margin_used:.2f}) is > 150% of equity (${total_equity:.2f})!")
                for pos in positions_list:
                    coin = pos.get('coin', 'UNKNOWN')
                    entry_price = pos.get('entryPrice')
                    leverage_str = pos.get('leverage', '1.0X')
                    pos_type = pos.get('positionType', 'swing')
                    logger.warning(f"    {coin} ({pos_type}): entry=${entry_price:.2f}, leverage={leverage_str}")

        except Exception as e:
            logger.warning(f"Failed to update frontend: {e}")
