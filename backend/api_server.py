#!/usr/bin/env python3
"""
FastAPI server to expose trading data to the frontend.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Trading Agent API")

# Initialize logger BEFORE exception handler
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return 500 with error details"""
    logger.error(f"Unhandled exception in {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "detail": str(exc),
            "path": str(request.url.path)
        }
    )

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# In-memory storage (replace with database later)
positions_data = []
trades_data = []  # Empty - will be populated by actual trades from the trading loop
agent_messages_data = []
balance_data = {"cash": 0.00, "unrealizedPnL": 0.00}

# Global reference to loop controller for interactive chat
loop_controller_instance: Optional[Any] = None

# Pydantic models
class ChatRequest(BaseModel):
    message: str


@app.get("/")
async def root():
    return {"message": "Trading Agent API", "status": "running"}


@app.get("/api/balance")
async def get_balance():
    """Get current account balance"""
    try:
        # Ensure balance_data exists and has correct structure
        if not isinstance(balance_data, dict):
            return {"cash": 0.00, "unrealizedPnL": 0.00}
        
        # CRITICAL: If we have positions but balance_data is stale/default, calculate from position manager
        # This ensures balance and positions are always consistent
        if loop_controller_instance and hasattr(loop_controller_instance, 'position_manager'):
            try:
                position_manager = loop_controller_instance.position_manager
                tracked_equity = getattr(position_manager, 'tracked_equity', None)
                
                if tracked_equity is not None and len(positions_data) > 0:
                    # We have positions - calculate balance from them to ensure consistency
                    # Calculate total unrealized P&L from LIVE prices every request
                    total_unrealized_pnl = 0.0
                    # Resolve exchange handle for live ticker
                    exchange = None
                    try:
                        cc = getattr(loop_controller_instance, 'cycle_controller', None)
                        if cc and hasattr(cc, 'exchange_adapter'):
                            exchange_adapter = getattr(cc, 'exchange_adapter')
                            exchange = getattr(exchange_adapter, 'exchange', None)
                    except Exception:
                        exchange = None
                    
                    # Calculate total margin used from positions
                    # CRITICAL: Use stored capital_amount for accurate margin calculation (same as frontend_manager)
                    # This ensures smart money management works correctly
                    total_margin_used = 0.0
                    config = loop_controller_instance.config if hasattr(loop_controller_instance, 'config') else None
                    
                    for pos in positions_data:
                        if not isinstance(pos, dict):
                            continue
                        
                        coin = pos.get('coin', 'UNKNOWN')
                        pos_type = pos.get('positionType', 'swing')
                        
                        # Get symbol from coin name
                        symbol_for_pos = None
                        if config and hasattr(config, 'symbols'):
                            for sym in config.symbols:
                                if sym.split('/')[0] == coin:
                                    symbol_for_pos = sym
                                    break
                        # Compute LIVE unrealized P&L using PositionManager size + live ticker price
                        try:
                            entry_price = None
                            if symbol_for_pos and symbol_for_pos in position_manager.position_entry_prices:
                                ep_dict = position_manager.position_entry_prices[symbol_for_pos]
                                if isinstance(ep_dict, dict):
                                    entry_price = ep_dict.get(pos_type)
                                else:
                                    entry_price = ep_dict if pos_type == 'swing' else None
                            if entry_price is None:
                                entry_price = pos.get('entryPrice')

                            size = 0.0
                            if symbol_for_pos:
                                size = position_manager.get_position_by_type(symbol_for_pos, pos_type)

                            current_price = pos.get('currentPrice', entry_price)
                            if exchange and symbol_for_pos:
                                sym_ccxt = symbol_for_pos.replace('/', '')
                                try:
                                    if hasattr(exchange, 'fapiPublicGetTickerPrice'):
                                        res = exchange.fapiPublicGetTickerPrice({'symbol': sym_ccxt})
                                        p = float(res['price']) if isinstance(res, dict) and 'price' in res else float(res)
                                        if p > 0:
                                            current_price = p
                                    elif hasattr(exchange, 'fetch_ticker'):
                                        t = exchange.fetch_ticker(symbol_for_pos)
                                        p = float(t.get('last', current_price))
                                        if p > 0:
                                            current_price = p
                                except Exception:
                                    pass

                            if entry_price and current_price and abs(size) > 0:
                                if size > 0:
                                    total_unrealized_pnl += size * (current_price - entry_price)
                                else:
                                    total_unrealized_pnl += abs(size) * (entry_price - current_price)
                        except Exception:
                            pass
                        
                        # Try to get actual capital used from PositionManager (if available)
                        # This is the actual capital allocated, not the inflated notional value
                        actual_capital_used = None
                        if symbol_for_pos and hasattr(position_manager, 'position_capital_used'):
                            if symbol_for_pos in position_manager.position_capital_used:
                                capital_dict = position_manager.position_capital_used[symbol_for_pos]
                                if isinstance(capital_dict, dict):
                                    actual_capital_used = capital_dict.get(pos_type)
                                else:
                                    actual_capital_used = capital_dict if pos_type == 'swing' else None
                        
                        if actual_capital_used is not None and actual_capital_used > 0:
                            # Use stored actual capital - this is the correct margin!
                            margin_for_position = actual_capital_used
                            total_margin_used += margin_for_position
                            logger.debug(f"Balance calc: {coin} ({pos_type}) using stored capital=${actual_capital_used:.2f}")
                        else:
                            # Fallback: Calculate from notional/leverage if capital not stored
                            # This shouldn't happen for new positions, but handles old positions gracefully
                            entry_price = pos.get('entryPrice')
                            current_price = pos.get('currentPrice', entry_price)
                            leverage_str = pos.get('leverage', '1.0X')
                            notional = pos.get('notional', 0.0)
                            
                            if entry_price and current_price and notional > 0:
                                try:
                                    # Calculate position size from current notional
                                    position_size = notional / current_price if current_price > 0 else 0.0
                                    if position_size > 0 and entry_price > 0:
                                        # Try to get actual leverage from stored position_leverages
                                        actual_leverage = None
                                        if symbol_for_pos and hasattr(position_manager, 'position_leverages'):
                                            if symbol_for_pos in position_manager.position_leverages:
                                                lev_dict = position_manager.position_leverages[symbol_for_pos]
                                                if isinstance(lev_dict, dict):
                                                    actual_leverage = lev_dict.get(pos_type)
                                                else:
                                                    actual_leverage = lev_dict if pos_type == 'swing' else 1.0
                                        
                                        leverage = 1.0
                                        if actual_leverage is not None and actual_leverage > 0:
                                            leverage = actual_leverage
                                        else:
                                            leverage = float(leverage_str.replace('X', '').replace('x', ''))
                                        
                                        entry_notional = position_size * entry_price
                                        margin_for_position = entry_notional / leverage
                                        
                                        # VALIDATION: Skip positions with invalid sizes
                                        if margin_for_position > tracked_equity * 2.0:
                                            logger.debug(f"Skipping invalid position {coin} ({pos_type}) in balance calc: margin ${margin_for_position:.2f} > 2x equity ${tracked_equity:.2f}")
                                            continue
                                        
                                        total_margin_used += margin_for_position
                                        logger.debug(f"Balance calc: {coin} ({pos_type}) FALLBACK using notional/leverage=${margin_for_position:.2f} (stored capital not available)")
                                except (ValueError, AttributeError, ZeroDivisionError, TypeError) as e:
                                    logger.debug(f"Error calculating margin for {coin} ({pos_type}): {e}")
                                    pass
                    
                    # Calculate available cash
                    total_equity = tracked_equity + total_unrealized_pnl
                    
                    # CRITICAL SAFEGUARD: Cap margin_used at total_equity to prevent negative cash
                    # This can happen due to rounding errors in position size or margin calculation
                    if total_margin_used > total_equity:
                        logger.warning(f"OVER-LEVERAGE DETECTED in balance endpoint: Margin (${total_margin_used:.2f}) > Equity (${total_equity:.2f})")
                        logger.warning(f"  Clamping margin to equity to prevent negative cash display.")
                        total_margin_used = total_equity
                    
                    # SMART MONEY MANAGEMENT: Cap margin at configured percentage of equity
                    try:
                        from src.config import Config
                        cfg = Config.load()
                        limit_pct = getattr(cfg, 'max_equity_usage_pct', 0.10)
                    except Exception:
                        limit_pct = 0.10
                    max_allowed_margin = total_equity * limit_pct
                    if total_margin_used > max_allowed_margin:
                        logger.debug(f"SMART MONEY: Margin usage (${total_margin_used:.2f}) > {int(limit_pct*100)}% limit (${max_allowed_margin:.2f}), clamping to limit")
                        total_margin_used = max_allowed_margin
                    
                    available_cash = max(0.0, total_equity - total_margin_used)
                    
                    logger.debug(f"Balance calculated from positions: equity=${tracked_equity:.2f}, pnl=${total_unrealized_pnl:.2f}, margin=${total_margin_used:.2f}, cash=${available_cash:.2f}")
                    
                    return {
                        "cash": float(available_cash),
                        "unrealizedPnL": float(total_unrealized_pnl)
                    }
                elif tracked_equity is not None and len(positions_data) == 0:
                    # No positions - return tracked equity as cash
                    return {
                        "cash": float(tracked_equity),
                        "unrealizedPnL": float(balance_data.get("unrealizedPnL", 0.00))
                    }
            except Exception as e:
                logger.debug(f"Could not calculate balance from position manager: {e}")
        
        # Fallback to stored balance_data
        return {
            "cash": float(balance_data.get("cash", 0.00)),
            "unrealizedPnL": float(balance_data.get("unrealizedPnL", 0.00))
        }
    except Exception as e:
        logger.error(f"Error getting balance: {e}", exc_info=True)
        return {"cash": 0.00, "unrealizedPnL": 0.00}


@app.get("/api/positions")
async def get_positions():
    """Get current open positions"""
    try:
        # Ensure positions_data is a list
        if not isinstance(positions_data, list):
            return []
        return positions_data
    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        return []


@app.get("/api/trades")
async def get_trades():
    """Get completed trades history"""
    try:
        # Ensure trades_data is a list
        if not isinstance(trades_data, list):
            return []
        return trades_data
    except Exception as e:
        logger.error(f"Error getting trades: {e}", exc_info=True)
        return []


@app.get("/api/agent-messages")
async def get_agent_messages():
    """Get agent chat messages"""
    try:
        # Ensure agent_messages_data is a list
        if not isinstance(agent_messages_data, list):
            return []
        return agent_messages_data
    except Exception as e:
        logger.error(f"Error getting agent messages: {e}", exc_info=True)
        return []


@app.post("/api/positions")
async def add_position(position: Dict[str, Any]):
    """Add a new position"""
    try:
        global positions_data
        if not isinstance(positions_data, list):
            positions_data = []
        positions_data.append(position)
        return {"status": "success", "position": position}
    except Exception as e:
        logger.error(f"Error adding position: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.delete("/api/positions")
async def clear_positions():
    """Clear all positions"""
    global positions_data
    positions_data = []
    return {"status": "success", "message": "Positions cleared"}


@app.put("/api/positions")
async def sync_positions(positions: List[Dict[str, Any]]):
    """Replace all positions with new data"""
    try:
        global positions_data
        if not isinstance(positions, list):
            return {"status": "error", "message": "Invalid positions data: must be a list"}
        positions_data = positions
        return {"status": "success", "count": len(positions)}
    except Exception as e:
        logger.error(f"Error syncing positions: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.post("/api/trades")
async def add_trade(trade: Dict[str, Any]):
    """Add a completed trade"""
    try:
        global trades_data
        if not isinstance(trades_data, list):
            trades_data = []
        trades_data.append(trade)
        return {"status": "success", "trade": trade}
    except Exception as e:
        logger.error(f"Error adding trade: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.delete("/api/trades")
async def clear_trades():
    """Clear all completed trades"""
    global trades_data
    trades_data = []
    return {"status": "success", "message": "All trades cleared"}


@app.post("/api/agent-messages")
async def add_agent_message(message: Dict[str, Any]):
    """Add an agent message"""
    try:
        global agent_messages_data
        if not isinstance(agent_messages_data, list):
            agent_messages_data = []
        if not isinstance(message, dict):
            return {"status": "error", "message": "Invalid message format"}
        message["timestamp"] = datetime.now().strftime("%d/%m %H:%M")
        agent_messages_data.append(message)
        return {"status": "success", "message": message}
    except Exception as e:
        logger.error(f"Error adding agent message: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.put("/api/balance")
async def update_balance(balance: Dict[str, float]):
    """Update account balance"""
    try:
        global balance_data
        if not isinstance(balance, dict):
            return {"status": "error", "message": "Invalid balance data: must be a dictionary"}
        # Ensure float values
        balance_data = {
            "cash": float(balance.get("cash", 0.00)),
            "unrealizedPnL": float(balance.get("unrealizedPnL", 0.00))
        }
        return {"status": "success", "balance": balance_data}
    except Exception as e:
        logger.error(f"Error updating balance: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/api/chart/{symbol}")
async def get_chart_data(symbol: str, timeframe: str = "1h", limit: int = 100):
    """
    Get chart data for a symbol.
    This should fetch from your exchange API (CCXT).
    For now, returns empty array - implement with real exchange data.
    """
    try:
        # TODO: Implement with CCXT
        # import ccxt
        # exchange = ccxt.binance()
        # ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        # return ohlcv
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "data": []
        }
    except Exception as e:
        logger.error(f"Error fetching chart data: {e}")
        return {"error": str(e)}


@app.post("/api/emergency-close")
async def emergency_close():
    """Emergency close all positions"""
    try:
        import os
        flag_path = os.path.join(os.path.dirname(__file__), "emergency_close.flag")
        with open(flag_path, "w") as f:
            f.write("1")
        logger.info(f"Emergency close flag created at: {flag_path}")
        return {"status": "success", "message": "Emergency close triggered - will execute on next cycle"}
    except Exception as e:
        logger.error(f"Error triggering emergency close: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/agent/pause")
async def pause_agent():
    """Pause the trading agent"""
    try:
        import os
        flag_path = os.path.join(os.path.dirname(__file__), "agent_paused.flag")
        with open(flag_path, "w") as f:
            f.write("1")
        logger.info(f"Agent paused flag created at: {flag_path}")
        return {"status": "success", "message": "Agent paused"}
    except Exception as e:
        logger.error(f"Error pausing agent: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/agent/resume")
async def resume_agent():
    """Resume the trading agent"""
    try:
        import os
        flag_path = os.path.join(os.path.dirname(__file__), "agent_paused.flag")
        if os.path.exists(flag_path):
            os.remove(flag_path)
        logger.info("Agent resumed")
        return {"status": "success", "message": "Agent resumed"}
    except Exception as e:
        logger.error(f"Error resuming agent: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/agent/status")
async def get_agent_status():
    """Get agent status"""
    try:
        import os
        flag_path = os.path.join(os.path.dirname(__file__), "agent_paused.flag")
        is_paused = os.path.exists(flag_path)
        return {"paused": is_paused}
    except Exception as e:
        logger.error(f"Error getting agent status: {e}", exc_info=True)
        return {"paused": False}


def _process_position_for_chat(
    loop_controller_instance, symbol, base_currency, position_size,
    abs_position_size, is_long, position_direction, position_type,
    all_snapshots, snapshot, price, all_positions_info, total_unrealized_pnl
):
    """Helper method to process a single position (swing or scalp) for chat context."""
    # Get position details for this symbol and type
    entry_price = None
    stop_loss = None
    take_profit = None
    leverage = 1.0
    risk_amount = None
    reward_amount = None
    
    # Get entry price (per-type)
    # In new architecture, positions are in cycle_controller.position_manager
    if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
        entry_dict = loop_controller_instance.cycle_controller.position_manager.position_entry_prices.get(symbol, {})
        if isinstance(entry_dict, dict):
            entry_price = entry_dict.get(position_type)
        else:
            # Backward compatibility
            entry_price = entry_dict if position_type == 'swing' else None
    # Fallback for old architecture
    elif hasattr(loop_controller_instance, 'position_entry_prices'):
        entry_dict = loop_controller_instance.position_entry_prices.get(symbol, {})
        if isinstance(entry_dict, dict):
            entry_price = entry_dict.get(position_type)
        else:
            # Backward compatibility
            entry_price = entry_dict if position_type == 'swing' else None
    
    # Get stop loss (per-type)
    # In new architecture, positions are in cycle_controller.position_manager
    if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
        sl_dict = loop_controller_instance.cycle_controller.position_manager.position_stop_losses.get(symbol, {})
        if isinstance(sl_dict, dict):
            stop_loss = sl_dict.get(position_type)
        else:
            # Backward compatibility
            stop_loss = sl_dict if position_type == 'swing' else None
    # Fallback for old architecture
    elif hasattr(loop_controller_instance, 'position_stop_losses'):
        sl_dict = loop_controller_instance.position_stop_losses.get(symbol, {})
        if isinstance(sl_dict, dict):
            stop_loss = sl_dict.get(position_type)
        else:
            # Backward compatibility
            stop_loss = sl_dict if position_type == 'swing' else None
    
    # Get take profit (per-type)
    if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
        tp_dict = loop_controller_instance.cycle_controller.position_manager.position_take_profits.get(symbol, {})
        if isinstance(tp_dict, dict):
            take_profit = tp_dict.get(position_type)
        else:
            # Backward compatibility
            take_profit = tp_dict if position_type == 'swing' else None
    elif hasattr(loop_controller_instance, 'position_take_profits'):
        tp_dict = loop_controller_instance.position_take_profits.get(symbol, {})
        if isinstance(tp_dict, dict):
            take_profit = tp_dict.get(position_type)
        else:
            # Backward compatibility
            take_profit = tp_dict if position_type == 'swing' else None
    
    # Get leverage (per-type)
    if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
        lev_dict = loop_controller_instance.cycle_controller.position_manager.position_leverages.get(symbol, {})
        if isinstance(lev_dict, dict):
            leverage = lev_dict.get(position_type, 1.0)
        else:
            # Backward compatibility
            leverage = lev_dict if position_type == 'swing' else 1.0
    elif hasattr(loop_controller_instance, 'position_leverages'):
        lev_dict = loop_controller_instance.position_leverages.get(symbol, {})
        if isinstance(lev_dict, dict):
            leverage = lev_dict.get(position_type, 1.0)
        else:
            # Backward compatibility
            leverage = lev_dict if position_type == 'swing' else 1.0
    
    # Get risk/reward (per-type)
    if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
        risk_dict = loop_controller_instance.cycle_controller.position_manager.position_risk_amounts.get(symbol, {})
        if isinstance(risk_dict, dict):
            risk_amount = risk_dict.get(position_type)
        else:
            risk_amount = risk_dict if position_type == 'swing' else None
    elif hasattr(loop_controller_instance, 'position_risk_amounts'):
        risk_dict = loop_controller_instance.position_risk_amounts.get(symbol, {})
        if isinstance(risk_dict, dict):
            risk_amount = risk_dict.get(position_type)
        else:
            risk_amount = risk_dict if position_type == 'swing' else None
    
    if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
        reward_dict = loop_controller_instance.cycle_controller.position_manager.position_reward_amounts.get(symbol, {})
        if isinstance(reward_dict, dict):
            reward_amount = reward_dict.get(position_type)
        else:
            reward_amount = reward_dict if position_type == 'swing' else None
    elif hasattr(loop_controller_instance, 'position_reward_amounts'):
        reward_dict = loop_controller_instance.position_reward_amounts.get(symbol, {})
        if isinstance(reward_dict, dict):
            reward_amount = reward_dict.get(position_type)
        else:
            reward_amount = reward_dict if position_type == 'swing' else None
    
    # Get current price for this symbol
    current_price = price  # Default to snapshot price
    if all_snapshots and symbol in all_snapshots:
        current_price = all_snapshots[symbol].price
    elif snapshot and snapshot.symbol == symbol:
        current_price = snapshot.price
    
    # Calculate unrealized P&L
    unrealized_pnl = 0.0
    if entry_price and entry_price > 0:
        if is_long:  # LONG
            unrealized_pnl = (current_price - entry_price) * abs_position_size
        else:  # SHORT
            unrealized_pnl = (entry_price - current_price) * abs_position_size
        total_unrealized_pnl[0] += unrealized_pnl  # Use list to modify in place
    
    # Calculate risk/reward
    actual_risk = risk_amount
    actual_reward = reward_amount
    if not actual_risk and stop_loss and entry_price:
        if is_long:
            actual_risk = abs((entry_price - stop_loss) * abs_position_size)
        else:
            actual_risk = abs((stop_loss - entry_price) * abs_position_size)
    if not actual_reward and take_profit and entry_price:
        if is_long:
            actual_reward = abs((take_profit - entry_price) * abs_position_size)
        else:
            actual_reward = abs((entry_price - take_profit) * abs_position_size)
    
    # Calculate notional value
    notional_value = abs_position_size * current_price
    
    # Calculate P&L percentage
    pnl_pct = (unrealized_pnl / (abs_position_size * entry_price) * 100) if entry_price and entry_price > 0 else 0
    
    # Format strings
    entry_str = f"${entry_price:,.2f}" if entry_price else "N/A"
    sl_str = f"${stop_loss:,.2f} (risk: ${actual_risk:.2f} if hit)" if stop_loss and actual_risk else ("Not set" if not stop_loss else f"${stop_loss:,.2f}")
    tp_str = f"${take_profit:,.2f} (reward: ${actual_reward:.2f} if hit)" if take_profit and actual_reward else ("Not set" if not take_profit else f"${take_profit:,.2f}")
    rr_str = f"1:{(actual_reward / actual_risk):.2f}" if actual_risk and actual_risk > 0 else "N/A"
    
    # Format position size based on magnitude
    if abs_position_size >= 1:
        size_str = f"{abs_position_size:.2f}"
    elif abs_position_size >= 0.01:
        size_str = f"{abs_position_size:.4f}"
    else:
        size_str = f"{abs_position_size:.8f}"
    
    # Build position info for this symbol
    pos_info = f"""
{symbol} - {position_direction} POSITION ({position_type.upper()}):
- Size: {size_str} {base_currency} (${notional_value:,.2f} notional)
- Direction: {position_direction}
- Leverage: {leverage:.1f}x
- Entry Price: {entry_str}
- Current Price: ${current_price:,.2f}
- Unrealized P&L: ${unrealized_pnl:+,.2f} ({pnl_pct:+.2f}%)
- Stop Loss: {sl_str}
- Take Profit: {tp_str}
- Risk:Reward Ratio: {rr_str}"""
    
    all_positions_info.append(pos_info)


@app.post("/api/agent-chat")
async def agent_chat(request: ChatRequest):
    """
    Handle user questions about the market and trading decisions.
    Uses the AI to provide intelligent, context-aware responses.
    """
    try:
        user_question = request.message.strip()
        if not user_question:
            return {"status": "error", "detail": "Message cannot be empty"}
        
        # Add user message to chat history
        user_msg = {
            "sender": "USER",
            "text": user_question,
            "timestamp": datetime.now().strftime("%d/%m %H:%M"),
            "id": f"user_{len(agent_messages_data)}"
        }
        agent_messages_data.append(user_msg)
        
        # Get current market snapshots (all 6 coins) if available
        snapshot = None
        all_snapshots = {}
        if loop_controller_instance:
            # Access snapshots through cycle_controller
            cycle_controller = loop_controller_instance.cycle_controller
            if cycle_controller:
                # Get ALL snapshots for multi-coin context
                if hasattr(cycle_controller, 'all_snapshots'):
                    all_snapshots = cycle_controller.all_snapshots or {}
                    logger.debug(f"Loaded {len(all_snapshots)} market snapshots for chat AI")
                # Get first snapshot for backward compatibility (BTC)
                if hasattr(cycle_controller, 'last_snapshot'):
                    snapshot = cycle_controller.last_snapshot
                    if snapshot:
                        logger.debug(f"Primary snapshot: {snapshot.symbol} @ ${snapshot.price:,.2f}")
            else:
                logger.warning("cycle_controller is None - chat AI may not have market data")
        else:
            logger.warning("loop_controller_instance is None - API server not connected to trading loop")
        
        # Build COMPREHENSIVE context for AI (with ALL 6 COINS data)
        if snapshot or all_snapshots:
            # Use first snapshot if available, otherwise use first from all_snapshots
            if not snapshot and all_snapshots:
                snapshot = list(all_snapshots.values())[0]
            price = snapshot.price
            indicators = snapshot.indicators
            
            # Multi-timeframe trends (flat structure)
            trend_1d = indicators.get('trend_1d', 'unknown')
            trend_4h = indicators.get('trend_4h', 'unknown')
            trend_1h = 'bullish' if price > indicators.get('ema_50', 0) else 'bearish'  # 1h trend
            trend_15m = indicators.get('trend_15m', 'unknown')
            trend_5m = indicators.get('trend_5m', 'unknown')
            trend_1m = indicators.get('trend_1m', 'unknown')
            
            # Key indicators across timeframes
            ema_50_1h = indicators.get('ema_50', 0)  # Primary 1h
            rsi_1h = indicators.get('rsi_14', 50)
            atr_1h = indicators.get('atr_14', 0)
            vwap_1h = indicators.get('vwap_1h', 0)
            vwap_5m = indicators.get('vwap_5m', 0)
            
            # Keltner Channels
            keltner_upper_1h = indicators.get('keltner_upper', 0)  # Primary 1h
            keltner_lower_1h = indicators.get('keltner_lower', 0)
            keltner_upper_5m = indicators.get('keltner_upper_5m', 0)
            keltner_lower_5m = indicators.get('keltner_lower_5m', 0)
            
            # Support/Resistance levels
            r1 = indicators.get('resistance_1', 0)
            r2 = indicators.get('resistance_2', 0)
            r3 = indicators.get('resistance_3', 0)
            s1 = indicators.get('support_1', 0)
            s2 = indicators.get('support_2', 0)
            s3 = indicators.get('support_3', 0)
            
            # Swing highs/lows
            swing_high_1h = indicators.get('swing_high', 0)
            swing_low_1h = indicators.get('swing_low', 0)
            
            # Volume analysis
            volume_ratio_1h = indicators.get('volume_ratio_1h', 1.0)
            volume_ratio_5m = indicators.get('volume_ratio_5m', 1.0)
            obv_trend_1h = indicators.get('obv_trend_1h', 'neutral')
            obv_trend_5m = indicators.get('obv_trend_5m', 'neutral')
            
            # Get ALL positions from loop controller (not just snapshot symbol)
            all_positions_info = []
            # Default to MOCK_STARTING_EQUITY from env or 100.0 if not available
            import os
            default_equity = float(os.getenv("MOCK_STARTING_EQUITY", "100.0"))
            current_equity = default_equity
            total_unrealized_pnl = 0.0
            
            if loop_controller_instance:
                # Get ALL positions across all symbols
                # In new architecture, positions are in cycle_controller.position_manager
                if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
                    tracked_positions = loop_controller_instance.cycle_controller.position_manager.tracked_position_sizes
                # Fallback for old architecture
                elif hasattr(loop_controller_instance, 'tracked_position_sizes'):
                    tracked_positions = loop_controller_instance.tracked_position_sizes
                    
                    # Build info for EACH position (handle both swing and scalp separately)
                    for symbol, position_data in tracked_positions.items():
                        # Handle new dictionary format: {symbol: {'swing': size, 'scalp': size}}
                        if isinstance(position_data, dict):
                            # Process swing and scalp positions separately
                            for position_type in ['swing', 'scalp']:
                                position_size = position_data.get(position_type, 0.0)
                                if abs(position_size) < 0.0001:  # Skip zero positions
                                    continue
                                
                                # Get base currency
                                base_currency = symbol.split('/')[0]
                                
                                # Determine direction (positive = LONG, negative = SHORT)
                                is_long = position_size > 0
                                position_direction = "LONG" if is_long else "SHORT"
                                abs_position_size = abs(position_size)
                                
                                # Process this position (swing or scalp)
                                pnl_list = [total_unrealized_pnl]  # Use list for in-place modification
                                _process_position_for_chat(
                                    loop_controller_instance, symbol, base_currency, position_size,
                                    abs_position_size, is_long, position_direction, position_type,
                                    all_snapshots, snapshot, price, all_positions_info, pnl_list
                                )
                                total_unrealized_pnl = pnl_list[0]  # Update after processing
                        else:
                            # Backward compatibility: old format (single float value)
                            position_size = position_data
                            if abs(position_size) < 0.0001:
                                continue
                            
                            # Get base currency
                            base_currency = symbol.split('/')[0]
                            
                            # Determine direction (positive = LONG, negative = SHORT)
                            is_long = position_size > 0
                            position_direction = "LONG" if is_long else "SHORT"
                            abs_position_size = abs(position_size)
                            
                            # Process as swing position (default for old format)
                            pnl_list = [total_unrealized_pnl]  # Use list for in-place modification
                            _process_position_for_chat(
                                loop_controller_instance, symbol, base_currency, position_size,
                                abs_position_size, is_long, position_direction, 'swing',
                                all_snapshots, snapshot, price, all_positions_info, pnl_list
                            )
                            total_unrealized_pnl = pnl_list[0]  # Update after processing
                
                # Get current equity from loop controller
                if hasattr(loop_controller_instance, 'cycle_controller') and loop_controller_instance.cycle_controller:
                    # Use position_manager equity in new architecture
                    position_manager = loop_controller_instance.cycle_controller.position_manager
                    if hasattr(position_manager, 'current_equity'):
                        current_equity = position_manager.current_equity
                    elif hasattr(position_manager, 'tracked_equity'):
                        # Calculate equity for demo mode: tracked_equity + unrealized P&L
                        tracked_equity = position_manager.tracked_equity
                        current_equity = tracked_equity + total_unrealized_pnl
                    else:
                        current_equity = default_equity
                elif hasattr(loop_controller_instance, 'current_equity'):
                    # Use stored current equity if available (old architecture)
                    current_equity = loop_controller_instance.current_equity
                elif hasattr(loop_controller_instance, 'tracked_equity'):
                    # Calculate equity for demo mode: tracked_equity + unrealized P&L (old architecture)
                    # For live mode, this should come from exchange balance
                    tracked_equity = loop_controller_instance.tracked_equity
                    current_equity = tracked_equity + total_unrealized_pnl
                else:
                    # Fallback to default
                    current_equity = default_equity
            
            # Get completed trades summary
            total_trades = len(trades_data)
            winning_trades = sum(1 for t in trades_data if t.get('pnl', 0) > 0)
            losing_trades = sum(1 for t in trades_data if t.get('pnl', 0) < 0)
            total_pnl = sum(t.get('pnl', 0) for t in trades_data)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Strategy mode
            strategy_mode = "HYBRID (ATR Breakout + AI Filter)"  # Default, can be read from config if needed
            
            # Build position info string (ALL positions)
            if all_positions_info:
                position_info = f"\nALL OPEN POSITIONS ({len(all_positions_info)}):" + "".join(all_positions_info)
            else:
                position_info = "\nCURRENT POSITION: NO OPEN POSITIONS"
            
            context = f"""=== FULL TRADING AGENT STATUS ===

MARKET DATA:
- {snapshot.symbol} Price: ${price:,.2f}
- Multi-Timeframe Trends: 1D={trend_1d}, 4H={trend_4h}, 1H={trend_1h}, 15m={trend_15m}, 5m={trend_5m}, 1m={trend_1m}

INDICATORS:
- 1h EMA(50): ${ema_50_1h:,.2f} | RSI: {rsi_1h:.1f} | ATR: ${atr_1h:.2f}
- 1h VWAP: ${vwap_1h:,.2f} | 5m VWAP: ${vwap_5m:,.2f}
- 1h Keltner: Upper ${keltner_upper_1h:,.2f}, Lower ${keltner_lower_1h:,.2f}
- 5m Keltner: Upper ${keltner_upper_5m:,.2f}, Lower ${keltner_lower_5m:,.2f}

SUPPORT/RESISTANCE:
- Resistances: R1=${r1:,.2f}, R2=${r2:,.2f}, R3=${r3:,.2f}
- Supports: S1=${s1:,.2f}, S2=${s2:,.2f}, S3=${s3:,.2f}
- Swing High: ${swing_high_1h:,.2f} | Swing Low: ${swing_low_1h:,.2f}

VOLUME:
- 1h: {volume_ratio_1h:.2f}x average (OBV: {obv_trend_1h})
- 5m: {volume_ratio_5m:.2f}x average (OBV: {obv_trend_5m})
{position_info}

TRADING PERFORMANCE:
- Total Completed Trades: {total_trades}
- Winning Trades: {winning_trades} | Losing Trades: {losing_trades}
- Win Rate: {win_rate:.1f}%
- Total Realized P&L: ${total_pnl:+,.2f}
- Current Virtual Equity: ${current_equity:.2f}

AGENT CAPABILITIES:
- Strategy Mode: {strategy_mode}
- Decision Cycle: Every 30 seconds
- Features: Multi-timeframe analysis, VWAP filtering, volume confirmation, support/resistance detection, swing/scalp adaptive strategy, automatic stop-loss/take-profit"""
            # Append AgentMemory summary (recent closed trades and reasons)
            try:
                from src.memory.agent_memory import get_memory
                mem = get_memory()
                mem_sum = mem.summarize_recent_closes(limit=20)
                recent = mem_sum.get("trades", [])
                lines = []
                for t in recent[-12:][::-1]:
                    sym = t.get("symbol")
                    ptype = (t.get("position_type") or '').upper()
                    side = (t.get("side") or '').upper()
                    pnl = t.get("pnl")
                    dur = t.get("duration_secs")
                    rsn = (t.get("reason") or '').strip()
                    if len(rsn) > 120:
                        rsn = rsn[:117] + "..."
                    pnl_str = f"${pnl:+.2f}" if pnl is not None else "n/a"
                    dur_str = f"{int(dur)}s" if isinstance(dur, (int, float)) else "n/a"
                    lines.append(f"- {sym} {ptype} {side}: PnL {pnl_str}, duration {dur_str}, reason: {rsn}")
                mem_context = f"\nRECENT CLOSED TRADES (last {mem_sum.get('count',0)}):\n" \
                              f"- Win rate: {mem_sum.get('win_rate',0.0)*100:.1f}% | Total PnL: ${mem_sum.get('pnl_sum',0.0):+.2f} | Avg duration: {int(mem_sum.get('avg_duration_secs') or 0)}s\n" \
                              + ("\n".join(lines) if lines else "- none yet")
            except Exception:
                mem_context = "\nRECENT CLOSED TRADES: unavailable"

            context += mem_context
            
            # Build ALL 6 COINS market overview (COMPREHENSIVE - ALL INDICATORS)
            all_coins_context = ""
            if all_snapshots:
                all_coins_context = "\n\nALL 6 COINS MARKET OVERVIEW (COMPLETE DATA):\n"
                for coin_symbol, coin_snap in all_snapshots.items():
                    coin_name = coin_symbol.split('/')[0]
                    coin_price = coin_snap.price
                    coin_ind = coin_snap.indicators
                    
                    # Multi-timeframe trends
                    coin_trend_1d = coin_ind.get('trend_1d', 'unknown')
                    coin_trend_4h = coin_ind.get('trend_4h', 'unknown')
                    coin_trend_1h = 'bullish' if coin_price > coin_ind.get('ema_50', 0) else 'bearish'
                    coin_trend_15m = coin_ind.get('trend_15m', 'unknown')
                    coin_trend_5m = coin_ind.get('trend_5m', 'unknown')
                    coin_trend_1m = coin_ind.get('trend_1m', 'unknown')
                    
                    # Key indicators
                    coin_ema_50 = coin_ind.get('ema_50', 0)
                    coin_rsi = coin_ind.get('rsi_14', 50)
                    coin_atr = coin_ind.get('atr_14', 0)
                    coin_vwap_1h = coin_ind.get('vwap_1h', coin_price)
                    coin_vwap_5m = coin_ind.get('vwap_5m', coin_price)
                    vwap_pos_1h = 'above' if coin_price > coin_vwap_1h else 'below'
                    vwap_pos_5m = 'above' if coin_price > coin_vwap_5m else 'below'
                    
                    # Keltner Channels
                    coin_keltner_upper_1h = coin_ind.get('keltner_upper', 0)
                    coin_keltner_lower_1h = coin_ind.get('keltner_lower', 0)
                    coin_keltner_upper_5m = coin_ind.get('keltner_upper_5m', 0)
                    coin_keltner_lower_5m = coin_ind.get('keltner_lower_5m', 0)
                    
                    # Support/Resistance
                    coin_r1 = coin_ind.get('resistance_1', 0)
                    coin_r2 = coin_ind.get('resistance_2', 0)
                    coin_r3 = coin_ind.get('resistance_3', 0)
                    coin_s1 = coin_ind.get('support_1', 0)
                    coin_s2 = coin_ind.get('support_2', 0)
                    coin_s3 = coin_ind.get('support_3', 0)
                    coin_swing_high = coin_ind.get('swing_high', 0)
                    coin_swing_low = coin_ind.get('swing_low', 0)
                    
                    # Volume analysis
                    coin_vol_1h = coin_ind.get('volume_ratio_1h', 1.0)
                    coin_vol_5m = coin_ind.get('volume_ratio_5m', 1.0)
                    coin_obv_1h = coin_ind.get('obv_trend_1h', 'neutral')
                    coin_obv_5m = coin_ind.get('obv_trend_5m', 'neutral')
                    vol_str_1h = 'STRONG' if coin_vol_1h >= 1.5 else 'MODERATE' if coin_vol_1h >= 1.2 else 'WEAK'
                    vol_str_5m = 'STRONG' if coin_vol_5m >= 1.5 else 'MODERATE' if coin_vol_5m >= 1.2 else 'WEAK'
                    
                    # Format price based on magnitude
                    if coin_price >= 1000:
                        price_str = f"${coin_price:,.2f}"
                    elif coin_price >= 1:
                        price_str = f"${coin_price:,.2f}"
                    else:
                        price_str = f"${coin_price:.4f}"
                    
                    all_coins_context += f"""
{coin_name}/{coin_symbol.split('/')[1]}:
  Price: {price_str}
  Trends: 1D={coin_trend_1d}, 4H={coin_trend_4h}, 1H={coin_trend_1h}, 15m={coin_trend_15m}, 5m={coin_trend_5m}, 1m={coin_trend_1m}
  Indicators: EMA50=${coin_ema_50:,.2f}, RSI={coin_rsi:.1f}, ATR=${coin_atr:.2f}
  VWAP: 1h=${coin_vwap_1h:,.2f} ({vwap_pos_1h}), 5m=${coin_vwap_5m:,.2f} ({vwap_pos_5m})
  Keltner 1h: Upper=${coin_keltner_upper_1h:,.2f}, Lower=${coin_keltner_lower_1h:,.2f}
  Keltner 5m: Upper=${coin_keltner_upper_5m:,.2f}, Lower=${coin_keltner_lower_5m:,.2f}
  S/R: R1=${coin_r1:,.2f}, R2=${coin_r2:,.2f}, R3=${coin_r3:,.2f} | S1=${coin_s1:,.2f}, S2=${coin_s2:,.2f}, S3=${coin_s3:,.2f}
  Swing: High=${coin_swing_high:,.2f}, Low=${coin_swing_low:,.2f}
  Volume: 1h={coin_vol_1h:.2f}x ({vol_str_1h}, OBV={coin_obv_1h}), 5m={coin_vol_5m:.2f}x ({vol_str_5m}, OBV={coin_obv_5m})
"""
                
                context += all_coins_context
        else:
            context = "Market data is currently unavailable."
        
        # Call DeepSeek AI for response
        try:
            from openai import OpenAI
            import os
            
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY not found in environment variables")
            
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            
            prompt = f"""You are Aether, an autonomous trading assistant. You're fully aware of your capabilities:

YOUR CAPABILITIES:
- You monitor 6 cryptocurrencies (BTC, ETH, SOL, DOGE, BNB, XRP) every 30 seconds
- You can hold SIMULTANEOUS swing AND scalp positions on the same coin (even opposite directions!)
- For example: You can hold a swing LONG position while scalping SHORT on the same coin
- You use ATR Breakout Strategy + AI filter for swing trades, and Scalping Strategy for quick trades
- When your confidence is high (>=0.7), you can adjust TP/SL to hit S/R levels instead of default strategy values
- You use critical thinking: question opposite direction, explain reasoning, identify concerns before deciding
- You evaluate all 6 coins each cycle and trade the one with the best opportunity
- You make decisions every 30 seconds in a continuous loop

You're monitoring and trading these 6 cryptocurrencies in real-time, making decisions every 30 seconds by evaluating all coins and trading the one with the best opportunity.

{context}

IMPORTANT GUIDELINES:
1. Use ONLY the data shown in the context above - don't make up or estimate numbers
2. Use exact prices and levels from the context
3. If "NO OPEN POSITIONS" is shown, don't mention any positions, P&L, or gains/losses
4. You're a multi-coin trader - you evaluate BTC, ETH, SOL, DOGE, BNB, and XRP every cycle and trade the best opportunity
5. When listing positions, mention ALL positions from the "ALL OPEN POSITIONS" section, not just BTC
6. Position sizes are positive numbers with direction (LONG/SHORT). For example, "Size: 0.001 BTC" with "Direction: SHORT" means shorting 0.001 BTC
7. Positions show their TYPE (SWING or SCALP) - you can have both types on the same coin simultaneously
8. When asked about specific coins, provide exact prices from the "ALL 6 COINS MARKET OVERVIEW" section
9. You have access to all 6 coins data - reference that section when users ask about other coins

TONE & STYLE:
- Be friendly, conversational, and natural - like chatting with a friend
- Avoid robotic phrases like "based on", "according to", "data indicates"
- Instead, say things naturally: "I'm seeing...", "It looks like...", "Right now...", "I notice..."
- Be confident but not arrogant
- Explain things simply without jargon overload
- Show personality - you're Aether, not a robot

User Question: {user_question}

Answer naturally and conversationally using ONLY the data from the context above. Use exact numbers when available. If asked about specific coins (XRP, DOGE, ETH, etc.), use the exact prices from the overview section. When listing positions, mention ALL open positions (not just BTC). Position sizes should be positive numbers with direction (LONG/SHORT). If there's no open position, don't mention position details or P&L. Be friendly and natural - like you're explaining to a friend. Keep it under 150 words."""
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are Aether, a friendly and intelligent trading assistant. You use only the data provided in the user's message. You never make up numbers or recall prices from training data. You speak naturally and conversationally, avoiding robotic phrases like 'based on' or 'according to'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            ai_response = response.choices[0].message.content.strip()
            
        except ValueError as e:
            logger.error(f"API key error: {e}")
            ai_response = "[WARNING] Configuration Error: DEEPSEEK_API_KEY is not set in the .env file. Please add it to enable chat responses."
        except Exception as e:
            logger.error(f"Error calling DeepSeek API: {e}")
            # Provide agent-aware fallback responses
            if all_snapshots or snapshot:
                # If we have all snapshots, build multi-coin response
                if all_snapshots:
                    coins_info = []
                    for coin_symbol, coin_snap in all_snapshots.items():
                        coin_name = coin_symbol.split('/')[0]
                        coins_info.append(f"{coin_name} at ${coin_snap.price:,.2f}")
                    coins_str = ", ".join(coins_info)
                    
                    # Check if user asked about specific coins
                    user_lower = user_question.lower()
                    if "xrp" in user_lower:
                        xrp_snap = all_snapshots.get("XRP/USDT")
                        if xrp_snap:
                            ai_response = f"XRP is at ${xrp_snap.price:,.2f} right now. I'm watching all 6 coins (BTC, ETH, SOL, DOGE, BNB, XRP) every cycle and I'll trade whichever one has the best setup. Still waiting for clearer signals across all coins - I'll keep you updated!"
                    elif "doge" in user_lower:
                        doge_snap = all_snapshots.get("DOGE/USDT")
                        if doge_snap:
                            ai_response = f"DOGE is sitting at ${doge_snap.price:,.4f}. I'm monitoring all 6 coins every cycle and I'll trade whichever shows the strongest setup. Right now I'm waiting for clearer signals - I'll let you know when I see something interesting!"
                    else:
                        ai_response = f"I'm watching all 6 coins: {coins_str}. I check them every 30 seconds and trade whichever one has the best opportunity. Still waiting for clearer signals across all coins - I'll keep you posted when I see something worth trading!"
                elif snapshot:
                    price = snapshot.price
                    indicators = snapshot.indicators
                    rsi_1h = indicators.get('rsi_14', 50)
                    r1 = indicators.get('resistance_1', 0)
                    s1 = indicators.get('support_1', 0)
                    volume_ratio_1h = indicators.get('volume_ratio_1h', 1.0)
                    
                    if "when" in user_question.lower() and "trade" in user_question.lower():
                        ai_response = f"Hey! I'm Aether, and I'm watching BTC right now at ${price:,.2f}. I'm waiting for a clear breakout above ${r1:,.2f} resistance or a bounce off ${s1:,.2f} support with strong volume - need more than 1.2x average, currently at {volume_ratio_1h:.2f}x. I'll let you know when I see something worth trading!"
                    elif "why" in user_question.lower() and ("not" in user_question.lower() or "no" in user_question.lower()):
                        ai_response = f"Right now at ${price:,.2f}, I'm seeing mixed signals - RSI at {rsi_1h:.1f}, volume at {volume_ratio_1h:.2f}x average. I need clearer confirmation before jumping in. I'm watching for breakouts, strong volume, and multi-timeframe alignment. I'll keep you posted!"
                    else:
                        ai_response = f"Hi! I'm Aether, your trading assistant. I'm monitoring BTC/USDT 24/7, and right now it's at ${price:,.2f}. I analyze multi-timeframe trends, volume, VWAP, and support/resistance to find the best setups. Check my updates above to see what I'm thinking!"
            else:
                ai_response = "Hey, I'm having trouble accessing market data right now. Give me a moment and try again, or check my updates above!"
        
        # Add AI response to chat history
        ai_msg = {
            "sender": "AETHER",
            "text": ai_response,
            "timestamp": datetime.now().strftime("%d/%m %H:%M"),
            "id": f"ai_{len(agent_messages_data)}"
        }
        agent_messages_data.append(ai_msg)
        
        return {
            "status": "success",
            "user_message": user_msg,
            "ai_response": ai_msg
        }
        
    except Exception as e:
        logger.error(f"Error in agent chat: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
