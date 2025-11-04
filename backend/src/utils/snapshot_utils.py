"""Utility functions for handling market snapshots."""

from src.tiered_data import EnhancedMarketSnapshot


def get_price_from_snapshot(snapshot) -> float:
    """
    Extract price from MarketSnapshot or EnhancedMarketSnapshot.

    Args:
        snapshot: MarketSnapshot or EnhancedMarketSnapshot

    Returns:
        float: Current price
    """
    if isinstance(snapshot, EnhancedMarketSnapshot):
        return snapshot.tier1.price if snapshot.tier1 else snapshot.original.price
    else:
        return snapshot.price


def get_base_snapshot(snapshot):
    """
    Get base MarketSnapshot from EnhancedMarketSnapshot or return as-is.

    Args:
        snapshot: MarketSnapshot or EnhancedMarketSnapshot

    Returns:
        MarketSnapshot: Base snapshot with indicators, timestamp, symbol
    """
    if isinstance(snapshot, EnhancedMarketSnapshot):
        return snapshot.original
    else:
        return snapshot
