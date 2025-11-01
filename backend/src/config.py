"""Configuration module for the Autonomous Trading Agent."""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class Config:
    """Configuration for the trading agent loaded from environment variables."""
    
    # Exchange
    exchange_type: str
    symbol: str
    
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
    
    # LLM
    decision_provider: str
    strategy_mode: str  # "hybrid_atr", "hybrid_ema", "ai_only"
    
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
        symbol = os.getenv("SYMBOL")
        exchange_api_key = os.getenv("EXCHANGE_API_KEY")
        exchange_api_secret = os.getenv("EXCHANGE_API_SECRET")
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        run_mode = os.getenv("RUN_MODE")
        decision_provider = os.getenv("DECISION_PROVIDER", "deepseek")
        strategy_mode = os.getenv("STRATEGY_MODE", "hybrid_atr")  # hybrid_atr, hybrid_ema, ai_only
        
        # Validate required fields
        required_fields = {
            "EXCHANGE_TYPE": exchange_type,
            "SYMBOL": symbol,
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
        
        # Validate numeric ranges
        if loop_interval_seconds <= 0:
            raise ValueError("LOOP_INTERVAL_SECONDS must be greater than 0")
        
        if not 0.0 <= max_equity_usage_pct <= 1.0:
            raise ValueError("MAX_EQUITY_USAGE_PCT must be between 0.0 and 1.0")
        
        if max_leverage <= 0:
            raise ValueError("MAX_LEVERAGE must be greater than 0")
        
        if daily_loss_cap_pct is not None and not 0.0 <= daily_loss_cap_pct <= 1.0:
            raise ValueError("DAILY_LOSS_CAP_PCT must be between 0.0 and 1.0")
        
        if cooldown_seconds is not None and cooldown_seconds < 0:
            raise ValueError("COOLDOWN_SECONDS must be non-negative")
        
        # Validate run mode
        if run_mode not in ["testnet", "live"]:
            raise ValueError("RUN_MODE must be either 'testnet' or 'live'")
        
        return cls(
            exchange_type=exchange_type,
            symbol=symbol,
            exchange_api_key=exchange_api_key,
            exchange_api_secret=exchange_api_secret,
            deepseek_api_key=deepseek_api_key,
            loop_interval_seconds=loop_interval_seconds,
            max_equity_usage_pct=max_equity_usage_pct,
            max_leverage=max_leverage,
            run_mode=run_mode,
            daily_loss_cap_pct=daily_loss_cap_pct,
            cooldown_seconds=cooldown_seconds,
            decision_provider=decision_provider,
            strategy_mode=strategy_mode,
        )
