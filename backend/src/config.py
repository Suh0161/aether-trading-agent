"""Configuration module for the Autonomous Trading Agent."""

import os
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv


@dataclass
class Config:
    """Configuration for the trading agent loaded from environment variables."""
    
    # Exchange
    exchange_type: str
    symbols: List[str]  # Changed from single symbol to list of symbols
    
    # Credentials
    exchange_api_key: str
    exchange_api_secret: str
    deepseek_api_key: str
    
    # Agent behavior
    loop_interval_seconds: int
    max_equity_usage_pct: float
    max_leverage: float
    
    # Mode
    run_mode: str
    
    # Optional risk
    daily_loss_cap_pct: Optional[float]
    cooldown_seconds: Optional[int]
    # Minimum hold before allowing discretionary closes
    min_hold_seconds_swing: int
    min_hold_seconds_scalp: int
    # Strategy toggles
    scalp_fast_mode: bool
    scalp_autoflip_enabled: bool
    allow_scalp_reversal_bypass: bool
    scalp_action_cooldown_seconds: int
    swing_action_cooldown_seconds: int
    # Portfolio-level controls
    max_open_positions_total: int
    min_global_open_interval_seconds: int
    
    # Demo mode (only used for binance_demo exchange type)
    mock_starting_equity: float  # Starting equity for demo mode (default: 100.0)
    # Position sync behavior and trade logging
    disable_position_sync_in_demo: bool  # If true, skip exchange position sync in demo
    sync_grace_seconds: int              # Seconds to wait before treating missing exchange pos as closed
    sync_confirm_misses: int             # Number of consecutive misses required to confirm external close
    completed_trades_min_abs_pnl: float  # Minimum absolute P&L to log a completed trade to frontend
    
    # Scalp profit threshold (default: 0.3%)
    scalp_profit_threshold_pct: float  # Minimum profit % to keep scalp position open after 5 min
    
    # LLM
    decision_provider: str
    strategy_mode: str  # "hybrid_atr", "hybrid_ema", "ai_only"

    # Portfolio allocator knobs
    swing_target_pct: float  # per-trade ceiling for swing allocations (e.g., 0.25)
    scalp_target_pct: float  # per-trade ceiling for scalp allocations (e.g., 0.15)
    min_allocation_usd: float  # minimum capital to allocate to any trade (e.g., $3)
    
    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables with validation.
        
        Returns:
            Config: Validated configuration object
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Load .env file if it exists
        load_dotenv()
        
        # Load required fields
        exchange_type = os.getenv("EXCHANGE_TYPE")
        symbols_str = os.getenv("SYMBOLS", "BTC/USDT")  # Default to BTC if not set
        exchange_api_key = os.getenv("EXCHANGE_API_KEY")
        exchange_api_secret = os.getenv("EXCHANGE_API_SECRET")
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        run_mode = os.getenv("RUN_MODE")
        decision_provider = os.getenv("DECISION_PROVIDER", "deepseek")
        strategy_mode = os.getenv("STRATEGY_MODE", "hybrid_atr")  # hybrid_atr, hybrid_ema, ai_only
        
        # Parse symbols (comma-separated)
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        if not symbols:
            raise ValueError("SYMBOLS must contain at least one valid symbol")
        
        # Validate required fields
        required_fields = {
            "EXCHANGE_TYPE": exchange_type,
            "SYMBOLS": symbols_str,
            "EXCHANGE_API_KEY": exchange_api_key,
            "EXCHANGE_API_SECRET": exchange_api_secret,
            "DEEPSEEK_API_KEY": deepseek_api_key,
            "RUN_MODE": run_mode,
        }
        
        missing_fields = [name for name, value in required_fields.items() if not value]
        if missing_fields:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_fields)}")
        
        # Load numeric fields with defaults
        try:
            loop_interval_seconds = int(os.getenv("LOOP_INTERVAL_SECONDS", "30"))
        except ValueError:
            raise ValueError("LOOP_INTERVAL_SECONDS must be a valid integer")
        
        try:
            max_equity_usage_pct = float(os.getenv("MAX_EQUITY_USAGE_PCT", "0.10"))
        except ValueError:
            raise ValueError("MAX_EQUITY_USAGE_PCT must be a valid float")
        
        try:
            max_leverage = float(os.getenv("MAX_LEVERAGE", "3.0"))
        except ValueError:
            raise ValueError("MAX_LEVERAGE must be a valid float")

        # Portfolio allocator knobs
        try:
            swing_target_pct = float(os.getenv("SWING_TARGET_PCT", "0.25"))
        except ValueError:
            raise ValueError("SWING_TARGET_PCT must be a valid float")
        try:
            scalp_target_pct = float(os.getenv("SCALP_TARGET_PCT", "0.15"))
        except ValueError:
            raise ValueError("SCALP_TARGET_PCT must be a valid float")
        try:
            min_allocation_usd = float(os.getenv("MIN_ALLOCATION_USD", "3.0"))
        except ValueError:
            raise ValueError("MIN_ALLOCATION_USD must be a valid float")
        
        # Load optional fields
        daily_loss_cap_pct = None
        daily_loss_cap_str = os.getenv("DAILY_LOSS_CAP_PCT")
        if daily_loss_cap_str:
            try:
                daily_loss_cap_pct = float(daily_loss_cap_str)
            except ValueError:
                raise ValueError("DAILY_LOSS_CAP_PCT must be a valid float")
        
        cooldown_seconds = None
        cooldown_str = os.getenv("COOLDOWN_SECONDS")
        if cooldown_str:
            try:
                cooldown_seconds = int(cooldown_str)
            except ValueError:
                raise ValueError("COOLDOWN_SECONDS must be a valid integer")

        # Minimum hold durations (defaults: swing 900s=15m, scalp 300s=5m)
        try:
            # Swing trades should last hours/days, not minutes
            # Minimum 1 hour (3600s) prevents premature exits
            min_hold_seconds_swing = int(os.getenv("MIN_HOLD_SECONDS_SWING", "3600"))
        except ValueError:
            raise ValueError("MIN_HOLD_SECONDS_SWING must be a valid integer")
        try:
            min_hold_seconds_scalp = int(os.getenv("MIN_HOLD_SECONDS_SCALP", "300"))
        except ValueError:
            raise ValueError("MIN_HOLD_SECONDS_SCALP must be a valid integer")
        
        # Validate numeric ranges
        if loop_interval_seconds <= 0:
            raise ValueError("LOOP_INTERVAL_SECONDS must be greater than 0")
        
        if not 0.0 <= max_equity_usage_pct <= 1.0:
            raise ValueError("MAX_EQUITY_USAGE_PCT must be between 0.0 and 1.0")
        
        if max_leverage <= 0:
            raise ValueError("MAX_LEVERAGE must be greater than 0")

        if not 0.0 <= swing_target_pct <= 1.0:
            raise ValueError("SWING_TARGET_PCT must be between 0.0 and 1.0")
        if not 0.0 <= scalp_target_pct <= 1.0:
            raise ValueError("SCALP_TARGET_PCT must be between 0.0 and 1.0")
        if min_allocation_usd < 0.0:
            raise ValueError("MIN_ALLOCATION_USD must be non-negative")
        
        if daily_loss_cap_pct is not None and not 0.0 <= daily_loss_cap_pct <= 1.0:
            raise ValueError("DAILY_LOSS_CAP_PCT must be between 0.0 and 1.0")
        
        if cooldown_seconds is not None and cooldown_seconds < 0:
            raise ValueError("COOLDOWN_SECONDS must be non-negative")
        
        # Load mock starting equity (for demo mode only)
        try:
            mock_starting_equity = float(os.getenv("MOCK_STARTING_EQUITY", "100.0"))
        except ValueError:
            raise ValueError("MOCK_STARTING_EQUITY must be a valid float")
        
        if mock_starting_equity <= 0:
            raise ValueError("MOCK_STARTING_EQUITY must be greater than 0")
        
        # Position sync flags and completed-trade logging threshold
        disable_position_sync_in_demo = os.getenv("DISABLE_POSITION_SYNC_IN_DEMO", "true").strip().lower() in ("1", "true", "yes", "y")
        try:
            sync_grace_seconds = int(os.getenv("SYNC_GRACE_SECONDS", "900"))
        except ValueError:
            raise ValueError("SYNC_GRACE_SECONDS must be a valid integer")
        try:
            sync_confirm_misses = int(os.getenv("SYNC_CONFIRM_MISSES", "3"))
        except ValueError:
            raise ValueError("SYNC_CONFIRM_MISSES must be a valid integer")
        try:
            completed_trades_min_abs_pnl = float(os.getenv("COMPLETED_TRADES_MIN_ABS_PNL", "0.00"))
        except ValueError:
            raise ValueError("COMPLETED_TRADES_MIN_ABS_PNL must be a valid float")

        # Load optional scalp profit threshold (default 0.3%)
        try:
            scalp_profit_threshold_pct = float(os.getenv("SCALP_PROFIT_THRESHOLD_PCT", "0.3"))
        except ValueError:
            raise ValueError("SCALP_PROFIT_THRESHOLD_PCT must be a valid float")
        
        if scalp_profit_threshold_pct < 0:
            raise ValueError("SCALP_PROFIT_THRESHOLD_PCT must be non-negative")

        # Strategy toggles
        scalp_fast_mode = os.getenv("SCALP_FAST_MODE", "false").strip().lower() in ("1", "true", "yes", "y")
        # Accept multiple spellings for safety
        _auto_names = [
            "SCALP_AUTOFLIP_ENABLED",
            "SCALP_AUTOFILP_ENABLED",
            "SCALP_AUTofLIP_ENABLED",
        ]
        scalp_autoflip_enabled = any(
            os.getenv(name, "false").strip().lower() in ("1", "true", "yes", "y") for name in _auto_names
        )
        allow_scalp_reversal_bypass = os.getenv("ALLOW_SCALP_REVERSAL_BYPASS", "false").strip().lower() in ("1", "true", "yes", "y")
        try:
            scalp_action_cooldown_seconds = int(os.getenv("SCALP_ACTION_COOLDOWN_SECONDS", "180"))
        except ValueError:
            raise ValueError("SCALP_ACTION_COOLDOWN_SECONDS must be a valid integer")
        try:
            swing_action_cooldown_seconds = int(os.getenv("SWING_ACTION_COOLDOWN_SECONDS", "300"))
        except ValueError:
            raise ValueError("SWING_ACTION_COOLDOWN_SECONDS must be a valid integer")
        # Portfolio-level controls
        try:
            max_open_positions_total = int(os.getenv("MAX_OPEN_POSITIONS_TOTAL", "2"))
        except ValueError:
            raise ValueError("MAX_OPEN_POSITIONS_TOTAL must be a valid integer")
        try:
            min_global_open_interval_seconds = int(os.getenv("MIN_GLOBAL_OPEN_INTERVAL_SECONDS", "180"))
        except ValueError:
            raise ValueError("MIN_GLOBAL_OPEN_INTERVAL_SECONDS must be a valid integer")
        
        # Validate run mode
        if run_mode not in ["testnet", "live", "demo"]:
            raise ValueError("RUN_MODE must be either 'testnet', 'live', or 'demo'")
        
        return cls(
            exchange_type=exchange_type,
            symbols=symbols,
            exchange_api_key=exchange_api_key,
            exchange_api_secret=exchange_api_secret,
            deepseek_api_key=deepseek_api_key,
            loop_interval_seconds=loop_interval_seconds,
            max_equity_usage_pct=max_equity_usage_pct,
            max_leverage=max_leverage,
            run_mode=run_mode,
            daily_loss_cap_pct=daily_loss_cap_pct,
            cooldown_seconds=cooldown_seconds,
            min_hold_seconds_swing=min_hold_seconds_swing,
            min_hold_seconds_scalp=min_hold_seconds_scalp,
            mock_starting_equity=mock_starting_equity,
            disable_position_sync_in_demo=disable_position_sync_in_demo,
            sync_grace_seconds=sync_grace_seconds,
            sync_confirm_misses=sync_confirm_misses,
            completed_trades_min_abs_pnl=completed_trades_min_abs_pnl,
            decision_provider=decision_provider,
            strategy_mode=strategy_mode,
            scalp_profit_threshold_pct=scalp_profit_threshold_pct,
            swing_target_pct=swing_target_pct,
            scalp_target_pct=scalp_target_pct,
            min_allocation_usd=min_allocation_usd,
            scalp_fast_mode=scalp_fast_mode,
            scalp_autoflip_enabled=scalp_autoflip_enabled,
            allow_scalp_reversal_bypass=allow_scalp_reversal_bypass,
            scalp_action_cooldown_seconds=scalp_action_cooldown_seconds,
            swing_action_cooldown_seconds=swing_action_cooldown_seconds,
            max_open_positions_total=max_open_positions_total,
            min_global_open_interval_seconds=min_global_open_interval_seconds,
        )
