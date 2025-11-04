"""Exchange adapter for connecting to different cryptocurrency exchanges."""

import ccxt
import logging
from src.config import Config

logger = logging.getLogger(__name__)


class ExchangeAdapter:
    """Handles exchange connections and configurations."""

    def __init__(self, config: Config):
        """
        Initialize exchange adapter.

        Args:
            config: Configuration object with exchange settings
        """
        self.config = config
        self.exchange = self._init_exchange(config)

    def _init_exchange(self, config: Config) -> ccxt.Exchange:
        """
        Initialize ccxt exchange client with proper configuration.

        Args:
            config: Configuration object

        Returns:
            Configured ccxt exchange instance
        """
        exchange_type = config.exchange_type.lower()

        # Map exchange types to ccxt classes
        if exchange_type == "binance_demo":
            # Binance Demo Trading uses demo.binance.com URLs
            # Demo trading is DIFFERENT from testnet - do NOT use set_sandbox_mode
            # Just override URLs directly to point to demo.binance.com
            logger.info("DEMO TRADING MODE: Using Binance Demo Trading environment.")
            logger.info("Using demo API keys from demo.binance.com")
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                    'adjustForTimeDifference': True,
                }
            })
            # Override URLs for demo trading - use live public endpoints for market data,
            # but demo endpoints for trading and balance operations
            # DO NOT use set_sandbox_mode because ccxt will block Futures in sandbox mode
            exchange.urls['api'].update({
                # Keep public endpoints pointing to live API (for market data like exchangeInfo)
                # Demo trading doesn't have all public endpoints, so use live API for market data
                'public': 'https://api.binance.com/api',  # Live public API for spot market data
                'private': 'https://api.binance.com/api',  # Live private API (not used for demo trading)
                # Use demo endpoints for Futures trading operations
                'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',  # Demo Futures public (for ticker/klines)
                'fapiPrivate': 'https://demo-fapi.binance.com/fapi/v1',  # Demo Futures private (for trading)
                # Use demo endpoints for balance/account operations
                'sapi': 'https://demo.binance.com/sapi/v1',  # SAPI endpoint for balance/account info
                'sapiPublic': 'https://demo.binance.com/sapi/v1',  # SAPI public endpoint
                'sapiPrivate': 'https://demo.binance.com/sapi/v1',  # SAPI private endpoint
            })
            
            # Override fetch_markets to use Futures endpoints directly
            # This prevents ccxt from trying to call publicGetExchangeInfo on spot API
            original_fetch_markets = exchange.fetch_markets
            
            def fetch_markets_demo_only(params=None):
                """Fetch only Futures markets for demo trading using Futures endpoints."""
                # For demo mode, only fetch Futures markets using Futures API
                # This avoids the spot API exchangeInfo endpoint which doesn't support ?type=future
                if params is None:
                    params = {}
                merged_params = params.copy() if isinstance(params, dict) else {}
                
                # Force Futures type and use Futures endpoints
                merged_params['type'] = 'future'
                
                # Use Futures-specific market loading
                # ccxt will use fapiPublicGetExchangeInfo for Futures markets
                try:
                    return original_fetch_markets(merged_params)
                except Exception as e:
                    # If Futures market loading fails, return empty markets dict
                    # Markets will be loaded on-demand during trading
                    logger.warning(f"Failed to load Futures markets for demo mode: {e}")
                    logger.warning("Markets will be loaded on-demand during trading")
                    return {}
            
            exchange.fetch_markets = fetch_markets_demo_only
        elif exchange_type == "binance_testnet":
            # NOTE: Binance Futures does not support testnet/sandbox mode anymore
            # We'll use live Futures API endpoints (user should use small amounts for testing)
            logger.warning("TESTNET MODE: Binance Futures testnet is deprecated. Using live Futures API.")
            logger.warning("IMPORTANT: You MUST use LIVE API keys (not testnet keys) for Futures trading.")
            logger.warning("IMPORTANT: Ensure your API key has 'Enable Futures' enabled in Binance API Management.")
            logger.warning("IMPORTANT: Use small amounts for testing. Switch to RUN_MODE=live for Futures trading.")
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                }
            })
            # DO NOT call set_sandbox_mode(True) for Futures - it's not supported
        elif exchange_type == "binance":
            exchange = ccxt.binance({
                'apiKey': config.exchange_api_key,
                'secret': config.exchange_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # Use USD-M Futures
                }
            })
        elif exchange_type == "hyperliquid":
            # Placeholder for future Hyperliquid support
            raise NotImplementedError("Hyperliquid exchange not yet implemented")
        else:
            raise ValueError(f"Unsupported exchange type: {exchange_type}")

        return exchange

    def fetch_futures_klines(self, symbol: str, timeframe: str, limit: int) -> list:
        """
        Fetch OHLCV data using Futures klines endpoint for demo trading.
        This ensures we use demo-fapi.binance.com instead of live endpoints.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")
            timeframe: Timeframe string (e.g., "1d", "1h", "15m")
            limit: Number of candles to fetch

        Returns:
            List of OHLCV candles in ccxt format [[timestamp, open, high, low, close, volume], ...]
        """
        # Convert symbol format (BTC/USDT -> BTCUSDT)
        futures_symbol = symbol.replace('/', '')

        # Map timeframe to Binance format
        tf_map = {
            '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
            '1d': '1d', '3d': '3d', '1w': '1w', '1M': '1M'
        }
        binance_tf = tf_map.get(timeframe, timeframe)

        # Call Futures klines endpoint (uses demo-fapi.binance.com for demo trading)
        # ccxt method: fapiPublicGetKlines for /fapi/v1/klines
        klines = self.exchange.fapiPublicGetKlines({
            'symbol': futures_symbol,
            'interval': binance_tf,
            'limit': limit
        })

        # Convert to ccxt format: [[timestamp, open, high, low, close, volume], ...]
        return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in klines]
