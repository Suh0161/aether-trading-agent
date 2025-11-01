"""Decision parsing and validation layer."""

import json
import logging
from typing import Any, Dict

from src.models import DecisionObject


logger = logging.getLogger(__name__)


class DecisionParser:
    """Parses and validates LLM output into structured DecisionObject."""
    
    ALLOWED_ACTIONS = {"long", "short", "close", "hold"}
    
    def parse(self, raw_response: str) -> DecisionObject:
        """
        Parse LLM response into DecisionObject.
        
        Forces action to "hold" if any validation fails.
        Logs all parsing and validation errors.
        
        Args:
            raw_response: Raw string response from LLM
            
        Returns:
            DecisionObject with validated fields (or forced hold on error)
        """
        # Strip markdown code blocks if present
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            # Remove opening ```json or ```
            lines = cleaned_response.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_response = '\n'.join(lines).strip()
        
        # Try to parse JSON
        try:
            data = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}. Raw response: {raw_response}")
            return DecisionObject(action="hold", size_pct=0.0, reason="JSON parsing error")
        
        # Validate that data is a dictionary
        if not isinstance(data, dict):
            logger.error(f"Parsed JSON is not a dictionary. Type: {type(data)}. Raw response: {raw_response}")
            return DecisionObject(action="hold", size_pct=0.0, reason="Invalid JSON structure")
        
        # Extract and validate action field
        action = data.get("action")
        if action not in self.ALLOWED_ACTIONS:
            logger.error(f"Invalid action '{action}'. Must be one of {self.ALLOWED_ACTIONS}. Raw response: {raw_response}")
            return DecisionObject(action="hold", size_pct=0.0, reason="Invalid action")
        
        # Extract and validate size_pct field
        size_pct = data.get("size_pct")
        if not isinstance(size_pct, (int, float)):
            logger.error(f"Invalid size_pct type: {type(size_pct)}. Must be numeric. Raw response: {raw_response}")
            return DecisionObject(action="hold", size_pct=0.0, reason="Invalid size_pct type")
        
        if not (0.0 <= size_pct <= 1.0):
            logger.error(f"size_pct {size_pct} out of range [0.0, 1.0]. Raw response: {raw_response}")
            return DecisionObject(action="hold", size_pct=0.0, reason="size_pct out of range")
        
        # Extract reason field (default to empty string if missing)
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            logger.warning(f"Reason field is not a string, converting. Raw response: {raw_response}")
            reason = str(reason)
        
        # Extract stop_loss and take_profit (optional fields)
        stop_loss = data.get("stop_loss")
        if stop_loss is not None:
            try:
                stop_loss = float(stop_loss)
            except (ValueError, TypeError):
                logger.warning(f"Invalid stop_loss type, ignoring. Raw response: {raw_response}")
                stop_loss = None
        
        take_profit = data.get("take_profit")
        if take_profit is not None:
            try:
                take_profit = float(take_profit)
            except (ValueError, TypeError):
                logger.warning(f"Invalid take_profit type, ignoring. Raw response: {raw_response}")
                take_profit = None
        
        # All validations passed
        return DecisionObject(
            action=action,
            size_pct=float(size_pct),
            reason=reason,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
