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

    def _try_get_live_price(self, symbol: str, fallback_price: float) -> float:
        """Fetch latest ticker price using the active exchange if available.

        This avoids showing 0.00 P&L right after fills by using a fresh price
        instead of the snapshot captured at the start of the cycle.
        """
        try:
            import api_server  # late import to avoid circulars during app startup
            if getattr(api_server, 'loop_controller_instance', None):
                loop_controller = api_server.loop_controller_instance
                if hasattr(loop_controller, 'cycle_controller') and loop_controller.cycle_controller:
                    exchange_adapter = getattr(loop_controller.cycle_controller, 'exchange_adapter', None)
                    exchange = getattr(exchange_adapter, 'exchange', None)
                    if exchange is None:
                        return fallback_price
                    # Prefer Futures public ticker if present (works in demo)
                    sym = symbol.replace('/', '')
                    if hasattr(exchange, 'fapiPublicGetTickerPrice'):
                        res = exchange.fapiPublicGetTickerPrice({'symbol': sym})
                        price = float(res['price']) if isinstance(res, dict) and 'price' in res else float(res)
                        return price if price > 0 else fallback_price
                    # Fallback to generic fetch_ticker
                    if hasattr(exchange, 'fetch_ticker'):
                        t = exchange.fetch_ticker(symbol)
                        price = float(t.get('last', fallback_price))
                        return price if price > 0 else fallback_price
        except Exception as e:
            logger.debug(f"Live price fetch failed for {symbol}: {e}")
        return fallback_price

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
                # Try to refresh to a live ticker so unrealized P&L moves immediately after fills
                current_price = self._try_get_live_price(symbol, current_price)
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

                    # Sanitize TP/SL if missing or nonsensical
                    if entry_price and isinstance(entry_price, (int, float)):
                        if was_long:
                            # For a valid long: tp > entry, sl < entry
                            if not isinstance(take_profit, (int, float)) or take_profit <= entry_price:
                                # Fallback: 2% target
                                take_profit = entry_price * 1.02
                            if not isinstance(stop_loss, (int, float)) or stop_loss >= entry_price or stop_loss <= 0:
                                # Fallback: 2% stop
                                stop_loss = entry_price * 0.98
                        else:
                            # For a valid short: tp < entry, sl > entry
                            if not isinstance(take_profit, (int, float)) or take_profit >= entry_price or take_profit <= 0:
                                # Fallback: 2% target below
                                take_profit = entry_price * 0.98
                            if not isinstance(stop_loss, (int, float)) or stop_loss <= entry_price:
                                # Fallback: 2% stop above
                                stop_loss = entry_price * 1.02

                    # Round leverage to whole number (Binance doesn't support decimals)
                    leverage_whole = int(round(leverage))

                    # Compute display notional consistent with sizing/risk manager
                    # Prefer actual capital used × leverage; fallback to qty × entry price
                    display_notional = abs(swing_position) * entry_price
                    try:
                        capital_used = None
                        if symbol in position_manager.position_capital_used:
                            cap_dict = position_manager.position_capital_used[symbol]
                            if isinstance(cap_dict, dict):
                                capital_used = cap_dict.get('swing')
                            else:
                                capital_used = cap_dict
                        if capital_used and capital_used > 0:
                            display_notional = capital_used * leverage_whole
                    except Exception:
                        pass
                    
                    positions_list.append({
                        "side": "LONG" if was_long else "SHORT",
                        "coin": base_currency,
                        "leverage": f"{leverage_whole}X",  # Whole number only (1x or 2x)
                        "notional": display_notional,
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

                    # Sanitize TP/SL for scalp if missing or nonsensical (use small 0.5%/0.3% defaults)
                    if entry_price and isinstance(entry_price, (int, float)):
                        if was_long:
                            if not isinstance(take_profit, (int, float)) or take_profit <= entry_price:
                                take_profit = entry_price * 1.005  # +0.5%
                            if not isinstance(stop_loss, (int, float)) or stop_loss >= entry_price or stop_loss <= 0:
                                stop_loss = entry_price * 0.997  # -0.3%
                        else:
                            if not isinstance(take_profit, (int, float)) or take_profit >= entry_price or take_profit <= 0:
                                take_profit = entry_price * 0.995  # -0.5%
                            if not isinstance(stop_loss, (int, float)) or stop_loss <= entry_price:
                                stop_loss = entry_price * 1.003  # +0.3%

                    # Round leverage to whole number (Binance doesn't support decimals)
                    leverage_whole = int(round(leverage))

                    # Compute display notional consistent with sizing/risk manager
                    # Prefer actual capital used × leverage; fallback to qty × entry price
                    display_notional = abs(scalp_position) * entry_price
                    try:
                        capital_used = None
                        if symbol in position_manager.position_capital_used:
                            cap_dict = position_manager.position_capital_used[symbol]
                            if isinstance(cap_dict, dict):
                                capital_used = cap_dict.get('scalp')
                            else:
                                # when not typed dict, assume swing-only old data
                                capital_used = None
                        if capital_used and capital_used > 0:
                            display_notional = capital_used * leverage_whole
                    except Exception:
                        pass
                    
                    positions_list.append({
                        "side": "LONG" if was_long else "SHORT",
                        "coin": base_currency,
                        "leverage": f"{leverage_whole}X",  # Whole number only (1x or 2x)
                        "notional": display_notional,
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
            # Margin Used = Sum of actual capital allocated for all open positions (not inflated notional / leverage)
            # CRITICAL: We use stored capital_amount to ensure smart money management works correctly

            # Calculate total margin used across all open positions
            # Margin = Actual Capital Used (not inflated notional / leverage)
            # CRITICAL: Use stored capital_amount for accurate margin calculation
            # This ensures smart money management works correctly
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

                # Get actual capital used from PositionManager (if available)
                # This is the actual capital allocated, not the inflated notional value
                actual_capital_used = None
                if symbol_for_pos and symbol_for_pos in position_manager.position_capital_used:
                    capital_dict = position_manager.position_capital_used[symbol_for_pos]
                    if isinstance(capital_dict, dict):
                        actual_capital_used = capital_dict.get(pos_type)
                    else:
                        actual_capital_used = capital_dict if pos_type == 'swing' else None

                if actual_capital_used is not None and actual_capital_used > 0:
                    # Use stored actual capital - this is the correct margin!
                    margin_for_position = actual_capital_used
                    total_margin_used += margin_for_position
                    entry_str = f"${entry_price:.2f}" if entry_price else 'N/A'
                    logger.info(f"  {coin} ({pos_type}) margin calc: using stored capital=${actual_capital_used:.2f} (position size={position_size:.6f}, entry={entry_str})")
                elif entry_price and position_size > 0:
                    # Fallback: Calculate from notional/leverage if capital not stored
                    # This shouldn't happen for new positions, but handles old positions gracefully
                    # Try to get actual leverage from stored position_leverages (more accurate)
                    actual_leverage = None
                    if symbol_for_pos and symbol_for_pos in position_manager.position_leverages:
                        lev_dict = position_manager.position_leverages[symbol_for_pos]
                        if isinstance(lev_dict, dict):
                            actual_leverage = lev_dict.get(pos_type)
                        else:
                            actual_leverage = lev_dict if pos_type == 'swing' else 1.0

                    # Use stored leverage if available, otherwise parse from string
                    leverage = 1.0
                    if actual_leverage is not None and actual_leverage > 0:
                        leverage = actual_leverage
                    else:
                        try:
                            leverage = float(leverage_str.replace('X', ''))
                        except (ValueError, AttributeError):
                            leverage = 1.0
                    
                    entry_notional = position_size * entry_price
                    margin_for_position = entry_notional / leverage
                    
                    # Validate: If margin for a single position exceeds total equity, position size is likely stored incorrectly
                    if margin_for_position > position_manager.tracked_equity * 2.0:
                        logger.error(f"  {coin} ({pos_type}) INVALID POSITION SIZE DETECTED: size={position_size:.6f}, margin=${margin_for_position:.2f} exceeds equity ${position_manager.tracked_equity:.2f}")
                        logger.error(f"    This position was likely stored incorrectly (as percentage instead of quantity). Skipping margin calculation for this position.")
                        continue
                    
                    total_margin_used += margin_for_position
                    logger.warning(f"  {coin} ({pos_type}) margin calc: FALLBACK using notional/leverage=${margin_for_position:.2f} (stored capital not available - old position?)")
                elif position_size > 0:
                    # Last resort: if no price available, skip this position (shouldn't happen)
                    logger.warning(f"  {coin} ({pos_type}) missing price/leverage for margin calculation - skipping margin for this position")

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
            
            # SMART MONEY MANAGEMENT: Cap margin usage based on config (MAX_EQUITY_USAGE_PCT)
            # Default in config is conservative (e.g., 10%). This prevents capital from being fully locked.
            limit_pct = getattr(self.config, 'max_equity_usage_pct', 0.10)
            max_allowed_margin = total_equity * limit_pct
            if total_margin_used > max_allowed_margin:
                logger.info(f"  SMART MONEY: Margin usage (${total_margin_used:.2f}) > {int(limit_pct*100)}% limit (${max_allowed_margin:.2f})")
                logger.info(f"    Clamping to {int(limit_pct*100)}% limit for smart money management")
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
