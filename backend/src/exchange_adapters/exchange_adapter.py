"""Exchange adapter for connecting to different cryptocurrency exchanges."""

try:
    import ccxt
except ImportError:
    ccxt = None
import logging
import time
from src.config import Config
from typing import Optional

logger = logging.getLogger(__name__)


class MockExchange:
    """Mock exchange object for when CCXT is not available."""
    def __init__(self):
        self.id = 'mock'
        self.urls = {'api': {}}
        self.options = {}

    def loadMarkets(self):
        pass

    def setSandboxMode(self, enabled):
        pass

    def fetch_futures_klines(self, symbol: str, timeframe: str, limit: int, params=None):
        """Mock klines fetch - returns empty list."""
        logger.warning("MockExchange: fetch_futures_klines called - returning empty data (CCXT not available)")
        return []

    # The following methods emulate a tiny subset of ccxt/binance endpoints that
    # our data fetchers may call during startup checks. They return minimal
    # placeholder data so the agent can boot in environments without CCXT.

    def fapiPublicGetKlines(self, params=None):
        """Mock Futures klines endpoint - returns a tiny synthetic series."""
        logger.warning("MockExchange: fapiPublicGetKlines called - returning mock klines (CCXT not available)")
        if params is None:
            params = {}
        import time
        now = int(time.time() * 1000)
        # Generate 50 flat candles at $100 with small random noise
        candles = []
        price = 100.0
        for i in range(50):
            ts = now - (50 - i) * 60_000
            open_p = price
            high_p = price * 1.0005
            low_p = price * 0.9995
            close_p = price
            vol = 1.0
            candles.append([ts, str(open_p), str(high_p), str(low_p), str(close_p), str(vol)])
        return candles

    def fapiPublicGetTickerPrice(self, params=None):
        """Mock Futures ticker price - returns a constant price string."""
        logger.warning("MockExchange: fapiPublicGetTickerPrice called - returning mock price (CCXT not available)")
        symbol = "BTCUSDT"
        if isinstance(params, dict) and 'symbol' in params:
            symbol = params['symbol']
        return {'symbol': symbol, 'price': '100.00'}

    def fapiPrivatePostOrder(self, params=None):
        """Mock order placement - always fails."""
        logger.error("MockExchange: Order placement attempted but CCXT not available - order will fail")
        raise Exception("MockExchange: Trading not available - CCXT library not installed")

    def fapiPrivateGetOrder(self, params=None):
        """Mock order status check - always fails."""
        logger.error("MockExchange: Order status check attempted but CCXT not available")
        raise Exception("MockExchange: Trading not available - CCXT library not installed")

    def fapiPrivateGetBalance(self, params=None):
        """Mock balance fetch - returns empty balance."""
        logger.warning("MockExchange: Balance fetch attempted but CCXT not available - returning mock balance")
        return {'assets': []}


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

    def _init_exchange(self, config: Config):
        """
        Initialize ccxt exchange client with proper configuration.

        Args:
            config: Configuration object

        Returns:
            Configured ccxt exchange instance
        """
        if ccxt is None:
            # Use HTTP-based fallback to fetch real market data without CCXT
            logger.warning("CCXT not available. Using HTTP fallback for real Binance Futures market data (trading disabled).")

            class HttpExchange:
                def __init__(self, base_url: str):
                    self.base_url = base_url.rstrip('/')
                    self.id = 'http'
                    self.urls = {'api': {'fapiPublic': self.base_url}}
                    self.options = {}

                def fapiPublicGetKlines(self, params=None):
                    if params is None:
                        params = {}
                    symbol = params.get('symbol')
                    interval = params.get('interval', '5m')
                    limit = params.get('limit', 150)
                    # Try httpx first; if unavailable, fallback to urllib
                    try:
                        import httpx  # lazy import to avoid global dependency
                        url = f"{self.base_url}/klines"
                        query = {'symbol': symbol, 'interval': interval, 'limit': limit}
                        with httpx.Client(timeout=10.0) as client:
                            r = client.get(url, params=query)
                            r.raise_for_status()
                            return r.json()
                    except Exception as e:
                        logger.error(f"HTTP klines fetch failed: {e}")
                        try:
                            from urllib.parse import urlencode
                            from urllib.request import urlopen
                            import json, ssl
                            url = f"{self.base_url}/klines?" + urlencode({'symbol': symbol, 'interval': interval, 'limit': limit})
                            ctx = ssl.create_default_context()
                            with urlopen(url, context=ctx, timeout=10) as resp:
                                data = resp.read().decode('utf-8')
                                return json.loads(data)
                        except Exception as e2:
                            logger.error(f"URllib klines fetch failed: {e2}")
                            # Return minimal synthetic candles so the pipeline keeps running
                            import time
                            now = int(time.time() * 1000)
                            return [[now, '100', '100', '100', '100', '1'] for _ in range(10)]

                def fapiPublicGetTickerPrice(self, params=None):
                    symbol = 'BTCUSDT'
                    if isinstance(params, dict) and 'symbol' in params:
                        symbol = params['symbol']
                    # Try httpx first; fallback to urllib
                    try:
                        import httpx  # lazy import
                        url = f"{self.base_url}/ticker/price"
                        with httpx.Client(timeout=5.0) as client:
                            r = client.get(url, params={'symbol': symbol})
                            r.raise_for_status()
                            return r.json()
                    except Exception as e:
                        logger.error(f"HTTP ticker fetch failed: {e}")
                        try:
                            from urllib.parse import urlencode
                            from urllib.request import urlopen
                            import json, ssl
                            url = f"{self.base_url}/ticker/price?" + urlencode({'symbol': symbol})
                            ctx = ssl.create_default_context()
                            with urlopen(url, context=ctx, timeout=5) as resp:
                                data = resp.read().decode('utf-8')
                                return json.loads(data)
                        except Exception as e2:
                            logger.error(f"URllib ticker fetch failed: {e2}")
                            return {'symbol': symbol, 'price': '100.00'}

                def fapiPublicGetExchangeInfo(self, params=None):
                    """Stub method - trading requires CCXT."""
                    logger.error("HttpExchange: fapiPublicGetExchangeInfo called but CCXT not available")
                    raise AttributeError("'HttpExchange' object has no attribute 'fapiPublicGetExchangeInfo' - CCXT required for trading")

                def fapiPrivatePostOrder(self, params=None):
                    """Stub method - trading requires CCXT."""
                    logger.error("HttpExchange: fapiPrivatePostOrder called but CCXT not available")
                    raise AttributeError("'HttpExchange' object has no attribute 'fapiPrivatePostOrder' - CCXT required for trading")

                def load_time_difference(self):
                    """Stub method - time sync requires CCXT."""
                    pass

            # Choose base URL depending on configured exchange_type
            et = config.exchange_type.lower()
            if et == 'binance_demo':
                base = 'https://demo-fapi.binance.com/fapi/v1'
            else:
                # Use live public Futures endpoints for market data
                base = 'https://fapi.binance.com/fapi/v1'
            return HttpExchange(base)

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
                    'recvWindow': 5000,  # 5 second window for timestamp tolerance
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
            
            # Override fetch_markets to skip market loading for demo mode
            # Markets will be loaded on-demand during trading when needed
            def fetch_markets_demo_only(params=None):
                """Skip market loading for demo mode (markets load on-demand)."""
                logger.debug("Skipping market loading for demo mode (markets load on-demand)")
                return {}
            
            exchange.fetch_markets = fetch_markets_demo_only
            
            # Sync time with Binance server to prevent timestamp errors
            try:
                logger.info("Synchronizing time with Binance server...")
                # Use ccxt's built-in time difference loader
                try:
                    if hasattr(exchange, 'load_time_difference'):
                        exchange.load_time_difference()
                except Exception as e:
                    logger.debug(f"load_time_difference() failed (will fallback to manual sync): {e}")
                # Skip load_markets() for demo mode (it fails with 404, markets load on-demand)
                # Force time sync by fetching server time directly
                try:
                    server_time = exchange.fapiPublicGetTime()
                    if isinstance(server_time, dict) and 'serverTime' in server_time:
                        server_time_ms = server_time['serverTime']
                        # Convert to int if it's a string
                        if isinstance(server_time_ms, str):
                            server_time_ms = int(server_time_ms)
                        elif not isinstance(server_time_ms, (int, float)):
                            server_time_ms = int(time.time() * 1000)  # Fallback to local time
                        
                        local_time_ms = int(time.time() * 1000)
                        time_diff_ms = local_time_ms - server_time_ms
                        logger.info(f"Time sync: Local={local_time_ms}, Server={server_time_ms}, Diff={time_diff_ms}ms")
                        if abs(time_diff_ms) > 1000:
                            logger.warning(f"Large time difference detected: {time_diff_ms}ms - CCXT will auto-adjust")
                except Exception as e:
                    logger.debug(f"Could not fetch server time for sync: {e} - CCXT will handle time adjustment automatically")
            except Exception as e:
                logger.debug(f"Time sync warning: {e} - CCXT will handle time adjustment automatically")
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

    def fetch_futures_positions(self) -> dict:
        """
        Fetch current open positions from Binance Futures.
        
        Returns:
            Dictionary mapping symbols to position info:
            {
                'BTC/USDT': {'side': 'long', 'size': 0.001, 'entry_price': 102641.0, 'unrealized_pnl': -0.94},
                'ETH/USDT': {'side': 'short', 'size': 0.008, 'entry_price': 3325.91, 'unrealized_pnl': 0.08}
            }
        """
        try:
            # Try using account endpoint first (works for both demo and live)
            # Endpoint: GET /fapi/v2/account
            account_data = self.exchange.fapiPrivateGetAccount()
            
            positions = {}
            
            # Extract positions from account data
            if 'positions' in account_data:
                for pos in account_data['positions']:
                    symbol_raw = pos.get('symbol', '')  # e.g., "BTCUSDT"
                    position_amt = float(pos.get('positionAmt', 0))
                    
                    # Skip positions with zero size
                    if abs(position_amt) < 0.0001:
                        continue
                    
                    # Convert symbol format (BTCUSDT -> BTC/USDT)
                    if symbol_raw.endswith('USDT'):
                        symbol = symbol_raw[:-4] + '/USDT'
                    else:
                        symbol = symbol_raw  # Fallback
                    
                    entry_price = float(pos.get('entryPrice', 0))
                    unrealized_pnl = float(pos.get('unrealizedProfit', 0))
                    
                    positions[symbol] = {
                        'side': 'long' if position_amt > 0 else 'short',
                        'size': abs(position_amt),
                        'entry_price': entry_price,
                        'unrealized_pnl': unrealized_pnl
                    }
            
            return positions
            
        except Exception as e:
            logger.debug(f"Position sync skipped: {e}")
            # Return empty dict - sync will be skipped this cycle
            return {}
