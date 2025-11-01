"""Logging layer for the Autonomous Trading Agent."""

import json
import os
from typing import Optional
from src.models import CycleLog


class Logger:
    """Handles structured logging of agent cycles to JSONL format."""
    
    def __init__(self, log_file: str):
        """
        Initialize logger with output file path.
        
        Args:
            log_file: Path to JSONL log file (will be created if doesn't exist)
        """
        self.log_file = log_file
        
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
    
    def log_cycle(self, cycle_log: CycleLog) -> None:
        """
        Append cycle log to JSONL file.
        
        Writes one JSON object per line in append-only mode.
        Ensures API keys and secrets are never logged.
        Flushes after each write for durability.
        
        Args:
            cycle_log: Complete cycle log record
        """
        # Convert dataclass to dictionary
        log_dict = {
            "timestamp": cycle_log.timestamp,
            "symbol": cycle_log.symbol,
            "market_price": cycle_log.market_price,
            "position_before": cycle_log.position_before,
            "llm_raw_output": cycle_log.llm_raw_output,
            "parsed_action": cycle_log.parsed_action,
            "parsed_size_pct": cycle_log.parsed_size_pct,
            "parsed_reason": cycle_log.parsed_reason,
            "risk_approved": cycle_log.risk_approved,
            "risk_reason": cycle_log.risk_reason,
            "executed": cycle_log.executed,
            "order_id": cycle_log.order_id,
            "filled_size": cycle_log.filled_size,
            "fill_price": cycle_log.fill_price,
            "mode": cycle_log.mode
        }
        
        # Sanitize log to ensure no API keys or secrets are logged
        log_dict = self._sanitize_log(log_dict)
        
        # Write to file in append mode
        with open(self.log_file, 'a') as f:
            json.dump(log_dict, f)
            f.write('\n')
            f.flush()  # Ensure data is written to disk immediately
    
    def _sanitize_log(self, log_dict: dict) -> dict:
        """
        Remove or redact any sensitive information from log.
        
        Ensures API keys, secrets, and other sensitive data are never logged.
        
        Args:
            log_dict: Log dictionary to sanitize
            
        Returns:
            Sanitized log dictionary
        """
        # Check for common patterns that might contain API keys
        sensitive_patterns = [
            'api_key', 'api_secret', 'secret', 'password', 
            'token', 'auth', 'credential'
        ]
        
        # Sanitize string fields that might contain sensitive data
        for key, value in log_dict.items():
            if isinstance(value, str):
                # Check if the value looks like it might contain sensitive data
                lower_value = value.lower()
                for pattern in sensitive_patterns:
                    if pattern in lower_value and len(value) > 20:
                        # If it looks like it might contain a key, redact it
                        # This is a safety measure; in normal operation, 
                        # we shouldn't be logging these fields anyway
                        log_dict[key] = "[REDACTED]"
                        break
        
        return log_dict
