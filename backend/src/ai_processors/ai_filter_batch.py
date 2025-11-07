"""Batching system for AI filter calls to reduce API costs."""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class BatchRequest:
    """Request to be batched for AI filter."""
    symbol: str
    snapshot: Any
    signal: Any
    position_size: float
    equity: float
    total_margin_used: float
    all_symbols: List[str]
    request_id: str
    timestamp: float


@dataclass
class BatchResponse:
    """Response from batched AI filter call."""
    approved: bool
    suggested_leverage: Optional[float]
    ai_confidence: Optional[float]
    request_id: str


class AIFilterBatcher:
    """Batches AI filter requests to reduce API calls."""
    
    def __init__(self, ai_filter, batch_window_seconds: float = 2.0, max_batch_size: int = 6):
        """
        Initialize AI filter batcher.
        
        Args:
            ai_filter: AIFilter instance to use for actual API calls
            batch_window_seconds: Maximum time to wait before processing batch (default: 2.0s)
            max_batch_size: Maximum number of requests per batch (default: 6)
        """
        self.ai_filter = ai_filter
        self.batch_window_seconds = batch_window_seconds
        self.max_batch_size = max_batch_size
        
        # Pending requests by action type
        self.pending_requests: Dict[str, List[BatchRequest]] = defaultdict(list)
        self.pending_responses: Dict[str, BatchResponse] = {}
        self.last_batch_time: Dict[str, float] = defaultdict(float)
        self.request_counter = 0
        
        # Statistics
        self.batches_processed = 0
        self.requests_batched = 0
        self.requests_immediate = 0
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        self.request_counter += 1
        return f"req_{int(time.time() * 1000)}_{self.request_counter}"
    
    def _should_batch(self, action: str, position_type: str) -> bool:
        """
        Determine if request should be batched.
        
        Only batch HOLD decisions - trades (long/short/close) are always immediate.
        
        Args:
            action: Decision action (long/short/hold/close)
            position_type: Position type (swing/scalp)
            
        Returns:
            True if should batch (only for HOLD), False for immediate processing
        """
        # Only batch HOLD decisions (most common, can wait)
        # Trades (long/short/close) should always be immediate for safety
        if action == 'hold':
            return True
        
        # Never batch trades - they need immediate processing
        return False
    
    def filter_signal(
        self,
        snapshot: Any,
        signal: Any,
        position_size: float,
        equity: float,
        total_margin_used: float = 0.0,
        all_symbols: List[str] = None,
        force_immediate: bool = False
    ) -> Tuple[bool, Optional[float], Optional[float]]:
        """
        Filter signal with batching support.
        
        Args:
            snapshot: Market snapshot
            signal: Strategy signal
            position_size: Current position size
            equity: Account equity
            total_margin_used: Total margin used
            all_symbols: List of all symbols
            force_immediate: Force immediate processing (skip batching)
            
        Returns:
            Tuple of (approved, suggested_leverage, ai_confidence)
        """
        action = signal.action
        position_type = getattr(signal, 'position_type', 'swing')
        symbol = snapshot.symbol if hasattr(snapshot, 'symbol') else 'UNKNOWN'
        
        # Force immediate for high-priority actions or if explicitly requested
        # Check this FIRST before batching logic
        if force_immediate or action in ['close', 'long', 'short']:
            self.requests_immediate += 1
            logger.debug(f"Immediate AI filter call for {symbol} {action} {position_type}")
            return self.ai_filter.filter_signal(
                snapshot, signal, position_size, equity, total_margin_used, all_symbols, symbol=symbol
            )
        
        # Check if should batch (only HOLD decisions)
        if not self._should_batch(action, position_type):
            # Process immediately for trades or if forced
            self.requests_immediate += 1
            logger.debug(f"Immediate AI filter call for {symbol} {action} {position_type}")
            return self.ai_filter.filter_signal(
                snapshot, signal, position_size, equity, total_margin_used, all_symbols, symbol=symbol
            )
        
        # Add HOLD decisions to batch
        request_id = self._generate_request_id()
        batch_key = f"{action}_{position_type}"  # For HOLD, this will be "hold_swing" or "hold_scalp"
        
        request = BatchRequest(
            symbol=symbol,
            snapshot=snapshot,
            signal=signal,
            position_size=position_size,
            equity=equity,
            total_margin_used=total_margin_used,
            all_symbols=all_symbols or [],
            request_id=request_id,
            timestamp=time.time()
        )
        
        self.pending_requests[batch_key].append(request)
        self.requests_batched += 1
        
        logger.debug(
            f"Batched AI filter request for {symbol} {action} {position_type} "
            f"(batch size: {len(self.pending_requests[batch_key])})"
        )
        
        # Check if batch is ready to process
        if len(self.pending_requests[batch_key]) >= self.max_batch_size:
            self._process_batch(batch_key)
        else:
            # Schedule batch processing after window
            self._schedule_batch_processing(batch_key)
        
        # Wait for response (with timeout) - for HOLD decisions, short timeout is OK
        return self._wait_for_response(request_id, timeout=3.0)
    
    def _schedule_batch_processing(self, batch_key: str) -> None:
        """Schedule batch processing after window expires."""
        # This will be called by the cycle controller to process pending batches
        # For now, we'll process immediately if window expired
        last_batch = self.last_batch_time.get(batch_key, 0)
        time_since_last = time.time() - last_batch
        
        if time_since_last >= self.batch_window_seconds:
            self._process_batch(batch_key)
    
    def _process_batch(self, batch_key: str) -> None:
        """
        Process a batch of requests.
        
        Args:
            batch_key: Batch key (action_position_type)
        """
        requests = self.pending_requests.get(batch_key, [])
        if not requests:
            return
        
        logger.info(
            f"Processing AI filter batch: {batch_key} ({len(requests)} requests)"
        )
        
        # Process each request in the batch
        for request in requests:
            try:
                approved, suggested_leverage, ai_confidence = self.ai_filter.filter_signal(
                    request.snapshot,
                    request.signal,
                    request.position_size,
                    request.equity,
                    request.total_margin_used,
                    request.all_symbols,
                    symbol=request.symbol  # Pass symbol for caching
                )
                
                response = BatchResponse(
                    approved=approved,
                    suggested_leverage=suggested_leverage,
                    ai_confidence=ai_confidence,
                    request_id=request.request_id
                )
                
                self.pending_responses[request.request_id] = response
                
            except Exception as e:
                logger.error(f"Error processing batched request {request.request_id}: {e}")
                # Return default response on error
                response = BatchResponse(
                    approved=True,  # Default to approve on error
                    suggested_leverage=None,
                    ai_confidence=None,
                    request_id=request.request_id
                )
                self.pending_responses[request.request_id] = response
        
        # Clear processed requests
        self.pending_requests[batch_key] = []
        self.last_batch_time[batch_key] = time.time()
        self.batches_processed += 1
    
    def _wait_for_response(self, request_id: str, timeout: float = 5.0) -> Tuple[bool, Optional[float], Optional[float]]:
        """
        Wait for batched response.
        
        Args:
            request_id: Request ID
            timeout: Maximum time to wait
            
        Returns:
            Tuple of (approved, suggested_leverage, ai_confidence)
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if request_id in self.pending_responses:
                response = self.pending_responses.pop(request_id)
                return (response.approved, response.suggested_leverage, response.ai_confidence)
            
            time.sleep(0.1)  # Small sleep to avoid busy waiting
        
        # Timeout - return default (approve)
        logger.warning(f"Timeout waiting for batched response {request_id}, defaulting to approve")
        return (True, None, None)
    
    def process_pending_batches(self) -> None:
        """Process all pending batches that have exceeded their window."""
        now = time.time()
        
        for batch_key, requests in list(self.pending_requests.items()):
            if not requests:
                continue
            
            last_batch = self.last_batch_time.get(batch_key, 0)
            time_since_last = now - last_batch
            
            # Process if window expired or batch is full
            if time_since_last >= self.batch_window_seconds or len(requests) >= self.max_batch_size:
                self._process_batch(batch_key)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get batching statistics."""
        total_requests = self.requests_batched + self.requests_immediate
        batching_rate = (self.requests_batched / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            'batches_processed': self.batches_processed,
            'requests_batched': self.requests_batched,
            'requests_immediate': self.requests_immediate,
            'batching_rate_pct': batching_rate,
            'pending_requests': sum(len(reqs) for reqs in self.pending_requests.values())
        }

