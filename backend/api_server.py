#!/usr/bin/env python3
"""
FastAPI server to expose trading data to the frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Trading Agent API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# In-memory storage (replace with database later)
positions_data = []
trades_data = []
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
    return balance_data


@app.get("/api/positions")
async def get_positions():
    """Get current open positions"""
    return positions_data


@app.get("/api/trades")
async def get_trades():
    """Get completed trades history"""
    return trades_data


@app.get("/api/agent-messages")
async def get_agent_messages():
    """Get agent chat messages"""
    return agent_messages_data


@app.post("/api/positions")
async def add_position(position: Dict[str, Any]):
    """Add a new position"""
    positions_data.append(position)
    return {"status": "success", "position": position}


@app.delete("/api/positions")
async def clear_positions():
    """Clear all positions"""
    global positions_data
    positions_data = []
    return {"status": "success", "message": "Positions cleared"}


@app.put("/api/positions")
async def sync_positions(positions: List[Dict[str, Any]]):
    """Replace all positions with new data"""
    global positions_data
    positions_data = positions
    return {"status": "success", "count": len(positions)}


@app.post("/api/trades")
async def add_trade(trade: Dict[str, Any]):
    """Add a completed trade"""
    trades_data.append(trade)
    return {"status": "success", "trade": trade}


@app.delete("/api/trades")
async def clear_trades():
    """Clear all completed trades"""
    global trades_data
    trades_data = []
    return {"status": "success", "message": "All trades cleared"}


@app.post("/api/agent-messages")
async def add_agent_message(message: Dict[str, Any]):
    """Add an agent message"""
    message["timestamp"] = datetime.now().strftime("%d/%m %H:%M")
    agent_messages_data.append(message)
    return {"status": "success", "message": message}


@app.put("/api/balance")
async def update_balance(balance: Dict[str, float]):
    """Update account balance"""
    global balance_data
    balance_data = balance
    return {"status": "success", "balance": balance_data}


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
    import os
    flag_path = os.path.join(os.path.dirname(__file__), "agent_paused.flag")
    is_paused = os.path.exists(flag_path)
    return {"paused": is_paused}


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
        
        # Get current market snapshot if available
        snapshot = None
        if loop_controller_instance:
            logger.info(f"[DEBUG] loop_controller_instance exists: {loop_controller_instance is not None}")
            if hasattr(loop_controller_instance, 'last_snapshot'):
                snapshot = loop_controller_instance.last_snapshot
                logger.info(f"[DEBUG] last_snapshot exists: {snapshot is not None}")
                if snapshot:
                    logger.info(f"[DEBUG] snapshot price: {snapshot.price}")
            else:
                logger.warning("[DEBUG] loop_controller_instance has no 'last_snapshot' attribute")
        else:
            logger.error("[DEBUG] loop_controller_instance is None! API server not connected to trading loop.")
        
        # Build COMPREHENSIVE context for AI
        if snapshot:
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
            
            # Get current position and equity from loop controller
            current_position = 0.0
            current_equity = 100.0
            position_type = None
            entry_price = None
            stop_loss = None
            take_profit = None
            leverage = 1.0
            risk_amount = None
            reward_amount = None
            unrealized_pnl = 0.0
            
            if loop_controller_instance:
                current_position = getattr(loop_controller_instance, 'current_position_size', 0.0)
                current_equity = getattr(loop_controller_instance, 'virtual_equity', 100.0)
                
                # Get position type
                if hasattr(loop_controller_instance, 'position_types') and loop_controller_instance.position_types:
                    position_type = list(loop_controller_instance.position_types.values())[0] if loop_controller_instance.position_types else None
                
                # Get entry price, stop loss, take profit, leverage, risk, reward
                symbol = snapshot.symbol
                if hasattr(loop_controller_instance, 'position_entry_prices'):
                    entry_price = loop_controller_instance.position_entry_prices.get(symbol)
                if hasattr(loop_controller_instance, 'position_stop_losses'):
                    stop_loss = loop_controller_instance.position_stop_losses.get(symbol)
                if hasattr(loop_controller_instance, 'position_take_profits'):
                    take_profit = loop_controller_instance.position_take_profits.get(symbol)
                if hasattr(loop_controller_instance, 'position_leverages'):
                    leverage = loop_controller_instance.position_leverages.get(symbol, 1.0)
                if hasattr(loop_controller_instance, 'position_risk_amounts'):
                    risk_amount = loop_controller_instance.position_risk_amounts.get(symbol)
                if hasattr(loop_controller_instance, 'position_reward_amounts'):
                    reward_amount = loop_controller_instance.position_reward_amounts.get(symbol)
                
                # Calculate unrealized P&L if we have a position
                if current_position != 0 and entry_price:
                    if current_position > 0:  # LONG
                        unrealized_pnl = (price - entry_price) * current_position
                    else:  # SHORT
                        unrealized_pnl = (entry_price - price) * abs(current_position)
            
            # Get completed trades summary
            total_trades = len(trades_data)
            winning_trades = sum(1 for t in trades_data if t.get('pnl', 0) > 0)
            losing_trades = sum(1 for t in trades_data if t.get('pnl', 0) < 0)
            total_pnl = sum(t.get('pnl', 0) for t in trades_data)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Strategy mode
            strategy_mode = "HYBRID (ATR Breakout + AI Filter)"  # Default, can be read from config if needed
            
            # Build position info string
            if current_position != 0:
                # Calculate actual risk/reward if not provided
                actual_risk = risk_amount if risk_amount else (abs((entry_price - stop_loss) * current_position) if stop_loss and entry_price else 0)
                actual_reward = reward_amount if reward_amount else (abs((take_profit - entry_price) * current_position) if take_profit and entry_price else 0)
                
                position_info = f"""
CURRENT POSITION:
- Type: {position_type.upper() if position_type else 'UNKNOWN'}
- Size: {current_position:.8f} BTC (${abs(current_position) * price:,.2f} notional)
- Direction: {'LONG' if current_position > 0 else 'SHORT'}
- Leverage: {leverage:.1f}x
- Entry Price: ${entry_price:,.2f} {f'(entered at ${entry_price:,.2f})' if entry_price else ''}
- Current Price: ${price:,.2f}
- Unrealized P&L: ${unrealized_pnl:+,.2f} ({(unrealized_pnl / (abs(current_position) * entry_price) * 100):+.2f}% if entry_price else 0)
- Stop Loss: ${stop_loss:,.2f} (risk: ${actual_risk:.2f} if hit)
- Take Profit: ${take_profit:,.2f} (reward: ${actual_reward:.2f} if hit)
- Risk:Reward Ratio: 1:{(actual_reward / actual_risk):.2f} if actual_risk > 0 else 'N/A'"""
            else:
                position_info = "\nCURRENT POSITION: NO OPEN POSITION"
            
            context = f"""=== FULL TRADING AGENT STATUS ===

MARKET DATA:
- BTC/USDT Price: ${price:,.2f}
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
            
            prompt = f"""You are an AUTONOMOUS TRADING AGENT actively monitoring and trading BTC/USDT in REAL-TIME. You make decisions every 30 seconds based on the data below.

{context}

CRITICAL INSTRUCTIONS - FOLLOW EXACTLY:
1. You MUST use ONLY the data shown in the context above
2. The CURRENT PRICE is explicitly stated in the context - use that exact number
3. ALL resistance/support levels are provided - use those exact numbers
4. DO NOT make up, estimate, or recall any prices from memory
5. If a number is in the context, copy it exactly (with proper formatting)
6. NEVER reference prices, levels, or data not shown in the context above
7. **CRITICAL**: If "NO OPEN POSITION" is shown, DO NOT mention any position, entry price, P&L, or gains/losses
8. **CRITICAL**: If "CURRENT POSITION" shows 0.0 BTC, DO NOT calculate or mention any profit/loss

User Question: {user_question}

Answer using ONLY the data from the context above. Quote the exact numbers provided. If there's no open position, do NOT mention position details, P&L, or gains. Be conversational but factually accurate. Under 150 words."""
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a factual trading agent. You ONLY use data provided in the user's message. You NEVER make up numbers or recall prices from training data. You copy numbers exactly as shown in the context."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            ai_response = response.choices[0].message.content.strip()
            
        except ValueError as e:
            logger.error(f"API key error: {e}")
            ai_response = "[WARNING] Configuration Error: DEEPSEEK_API_KEY is not set in the .env file. Please add it to enable chat responses."
        except Exception as e:
            logger.error(f"Error calling DeepSeek API: {e}")
            # Provide agent-aware fallback responses
            if snapshot:
                price = snapshot.price
                indicators = snapshot.indicators
                rsi_1h = indicators.get('rsi_14', 50)
                r1 = indicators.get('resistance_1', 0)
                s1 = indicators.get('support_1', 0)
                volume_ratio_1h = indicators.get('volume_ratio_1h', 1.0)
                
                if "when" in user_question.lower() and "trade" in user_question.lower():
                    ai_response = f"I'm actively monitoring BTC/USDT at ${price:,.2f}. Currently waiting for a clear breakout above ${r1:,.2f} resistance or a bounce off ${s1:,.2f} support with strong volume (need >1.2x avg, currently {volume_ratio_1h:.2f}x). Check my automatic updates above for real-time reasoning."
                elif "why" in user_question.lower() and ("not" in user_question.lower() or "no" in user_question.lower()):
                    ai_response = f"Right now at ${price:,.2f}, I'm seeing mixed signals - RSI at {rsi_1h:.1f}, volume at {volume_ratio_1h:.2f}x average. I need clearer confirmation before entering. I'm watching for breakouts, strong volume, and multi-timeframe alignment. Stay tuned!"
                else:
                    ai_response = f"I'm your autonomous trading agent, actively monitoring BTC/USDT 24/7. Current price: ${price:,.2f}. I analyze multi-timeframe trends, volume, VWAP, and support/resistance to find high-probability setups. Check my automatic updates above for my latest analysis!"
            else:
                ai_response = "I'm having trouble accessing market data right now. Please try again in a moment or check my automatic updates above."
        
        # Add AI response to chat history
        ai_msg = {
            "sender": "DEEPSEEK",
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
