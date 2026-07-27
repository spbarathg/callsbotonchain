"""
Portfolio Manager - ARCHIVED (2026-05-17)

The "Circle Strategy" rebalancing system has been archived as it was disabled in
production (PORTFOLIO_REBALANCING_ENABLED=false) and added complexity without
proven value. The original implementation is preserved at:
    _archive/unused/portfolio_manager.py

This stub preserves the public API so existing imports don't break.
All functions are safe no-ops.
"""
from typing import Dict, Any, Optional, List, Tuple


class PortfolioManager:
    """Stub portfolio manager. All operations are no-ops."""

    def __init__(self, **kwargs):
        pass

    def get_positions(self) -> list:
        return []

    def get_position_count(self) -> int:
        return 0

    def is_full(self) -> bool:
        return False

    def has_position(self, token_address: str) -> bool:
        return False

    def add_position(self, **kwargs) -> bool:
        return False

    def remove_position(self, token_address: str, reason: str = "manual") -> bool:
        return False

    def update_prices(self, price_updates: Dict[str, float]) -> None:
        pass

    def get_ranked_positions(self) -> list:
        return []

    def get_weakest_position(self) -> None:
        return None

    def evaluate_rebalance(self, new_signal: Dict[str, Any]) -> Tuple[bool, Optional[str], str]:
        return (False, None, "portfolio_manager_archived")

    def execute_rebalance(self, token_to_remove: str, new_signal: Dict[str, Any]) -> bool:
        return False

    def get_statistics(self) -> Dict[str, Any]:
        return {"archived": True, "position_count": 0}

    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        return {"archived": True}


_portfolio_manager: Optional[PortfolioManager] = None


def get_portfolio_manager(**kwargs) -> PortfolioManager:
    """Get stub portfolio manager instance."""
    global _portfolio_manager
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioManager()
    return _portfolio_manager


def should_use_portfolio_manager() -> bool:
    """Always returns False — portfolio manager is archived."""
    return False
