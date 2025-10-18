"""
Portfolio Manager - "Circle Strategy" Implementation

Manages a fixed-size portfolio of highest-momentum assets.
Continuously rebalances by replacing weak positions with stronger opportunities.

Ideology:
- Portfolio as a "circle" of best N assets
- New signals compete against weakest current holding
- Capital always allocated to highest-momentum opportunities
- Manages opportunity cost actively

Author: Cielo Signal Optimizer Team
Date: October 10, 2025
"""

import time
import threading
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Position:
    """Represents a position in the portfolio"""
    token_address: str
    entry_price: float
    current_price: float
    quantity: float
    entry_time: float
    conviction_score: int
    signal_score: int
    name: str = ""
    symbol: str = ""
    
    @property
    def pnl_percent(self) -> float:
        """Current profit/loss percentage"""
        if self.entry_price <= 0:
            return 0.0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100
    
    @property
    def momentum_score(self) -> float:
        """
        Momentum score for ranking positions.
        
        Combines:
        - Recent PnL (current price action)
        - Original signal quality
        - Time decay (older positions lose priority)
        """
        # Base score from PnL
        pnl_score = self.pnl_percent
        
        # Bonus for original signal quality (normalized to -20 to +20)
        signal_bonus = (self.signal_score - 5) * 4  # Score of 5 = neutral
        
        # Time decay: positions older than 1 hour lose momentum
        age_hours = (time.time() - self.entry_time) / 3600
        time_penalty = min(age_hours * 2, 10)  # Cap at -10
        
        return pnl_score + signal_bonus - time_penalty
    
    @property
    def age_minutes(self) -> float:
        """Age of position in minutes"""
        return (time.time() - self.entry_time) / 60
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "token": self.token_address,
            "name": self.name,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "quantity": self.quantity,
            "pnl_percent": self.pnl_percent,
            "momentum_score": self.momentum_score,
            "age_minutes": self.age_minutes,
            "conviction_score": self.conviction_score,
        }


class PortfolioManager:
    """
    Manages a fixed-size portfolio with dynamic rebalancing.
    
    "Circle Strategy" implementation:
    - Maintains N best positions (the "circle")
    - Ranks positions by momentum
    - Replaces weakest position when better signal appears
    """
    
    def __init__(
        self,
        max_positions: int = 5,
        min_momentum_advantage: float = 15.0,
        rebalance_cooldown: int = 300,  # 5 minutes
        min_position_age: int = 600,    # 10 minutes before can be replaced
    ):
        """
        Args:
            max_positions: Maximum number of concurrent positions (circle size)
            min_momentum_advantage: Minimum momentum advantage required to rebalance
            rebalance_cooldown: Seconds between rebalance operations
            min_position_age: Minimum age before position can be replaced
        """
        self.max_positions = max_positions
        self.min_momentum_advantage = min_momentum_advantage
        self.rebalance_cooldown = rebalance_cooldown
        self.min_position_age = min_position_age
        
        # Portfolio state
        self._positions: Dict[str, Position] = {}
        self._lock = threading.Lock()
        
        # Rebalancing state
        self._last_rebalance_time = 0.0
        self._rebalance_count = 0
        self._rejected_signals_count = 0
        
        # Performance tracking
        self._rebalance_history: List[Dict[str, Any]] = []
    
    def get_positions(self) -> List[Position]:
        """Get all current positions"""
        with self._lock:
            return list(self._positions.values())
    
    def get_position_count(self) -> int:
        """Get number of current positions"""
        with self._lock:
            return len(self._positions)
    
    def is_full(self) -> bool:
        """Check if portfolio is at max capacity"""
        return self.get_position_count() >= self.max_positions
    
    def has_position(self, token_address: str) -> bool:
        """Check if token already in portfolio"""
        with self._lock:
            return token_address in self._positions
    
    def _add_position_unsafe(
        self,
        token_address: str,
        entry_price: float,
        quantity: float,
        signal_score: int,
        conviction_score: int,
        name: str = "",
        symbol: str = "",
    ) -> bool:
        """
        Internal: Add a position (no locking - caller must hold lock).
        
        Returns:
            True if position added
        """
        # Check if already holding this token
        if token_address in self._positions:
            return False
        
        # If not full, add directly
        if len(self._positions) < self.max_positions:
            position = Position(
                token_address=token_address,
                entry_price=entry_price,
                current_price=entry_price,
                quantity=quantity,
                entry_time=time.time(),
                conviction_score=conviction_score,
                signal_score=signal_score,
                name=name,
                symbol=symbol,
            )
            self._positions[token_address] = position
            self._log_event("position_added", position.to_dict())
            return True
        
        return False
    
    def add_position(
        self,
        token_address: str,
        entry_price: float,
        quantity: float,
        signal_score: int,
        conviction_score: int,
        name: str = "",
        symbol: str = "",
    ) -> bool:
        """
        Add a new position to portfolio.
        
        Only succeeds if:
        1. Portfolio not full, OR
        2. New signal is better than weakest current position
        
        Returns:
            True if position added (may trigger rebalance)
        """
        with self._lock:
            return self._add_position_unsafe(
                token_address=token_address,
                entry_price=entry_price,
                quantity=quantity,
                signal_score=signal_score,
                conviction_score=conviction_score,
                name=name,
                symbol=symbol,
            )
    
    def update_prices(self, price_updates: Dict[str, float]) -> None:
        """
        Update current prices for positions.
        
        Args:
            price_updates: Dict mapping token_address -> current_price
        """
        with self._lock:
            for token, price in price_updates.items():
                if token in self._positions:
                    self._positions[token].current_price = price
    
    def _remove_position_unsafe(self, token_address: str, reason: str = "manual") -> bool:
        """
        Internal: Remove a position (no locking - caller must hold lock).
        
        Returns:
            True if position was removed
        """
        if token_address in self._positions:
            position = self._positions.pop(token_address)
            self._log_event("position_removed", {
                **position.to_dict(),
                "reason": reason,
            })
            return True
        return False
    
    def remove_position(self, token_address: str, reason: str = "manual") -> bool:
        """
        Remove a position from portfolio.
        
        Returns:
            True if position was removed
        """
        with self._lock:
            return self._remove_position_unsafe(token_address, reason)
    
    def _rank_positions_unsafe(self, positions: List[Position]) -> List[Tuple[Position, float]]:
        """
        Internal: Rank positions by momentum (no locking).
        
        Args:
            positions: List of positions to rank
            
        Returns:
            List of (Position, momentum_score) tuples sorted by momentum
        """
        ranked = [(pos, pos.momentum_score) for pos in positions]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
    
    def get_ranked_positions(self) -> List[Tuple[Position, float]]:
        """
        Get positions ranked by momentum score (best to worst).
        
        Returns:
            List of (Position, momentum_score) tuples
        """
        with self._lock:
            positions = list(self._positions.values())
        
        return self._rank_positions_unsafe(positions)
    
    def _get_weakest_position_unsafe(self, positions: List[Position]) -> Optional[Position]:
        """
        Internal: Get weakest position (no locking).
        
        Args:
            positions: List of positions to check
            
        Returns:
            Weakest position or None if no eligible positions
        """
        if not positions:
            return None
        
        ranked = self._rank_positions_unsafe(positions)
        
        # Find weakest position that is old enough to replace
        now = time.time()
        for position, score in reversed(ranked):
            age = now - position.entry_time
            if age >= self.min_position_age:
                return position
        
        # No eligible positions
        return None
    
    def get_weakest_position(self) -> Optional[Position]:
        """
        Get the weakest position (lowest momentum).
        
        Only considers positions older than min_position_age.
        
        Returns:
            Weakest position or None if no eligible positions
        """
        with self._lock:
            positions = list(self._positions.values())
        
        return self._get_weakest_position_unsafe(positions)
    
    def evaluate_rebalance(
        self,
        new_signal: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], str]:
        """
        Evaluate whether to rebalance portfolio for new signal.
        
        Args:
            new_signal: Dict with token info and scores
        
        Returns:
            Tuple of (should_rebalance, token_to_replace, reason)
        """
        with self._lock:
            # Can't rebalance if not full
            if len(self._positions) < self.max_positions:
                return (False, None, "portfolio_not_full")
            
            # Check cooldown
            time_since_last = time.time() - self._last_rebalance_time
            if time_since_last < self.rebalance_cooldown:
                self._rejected_signals_count += 1
                return (False, None, f"cooldown_{int(self.rebalance_cooldown - time_since_last)}s")
            
            # Get weakest position (use internal method to avoid deadlock)
            positions = list(self._positions.values())
            weakest = self._get_weakest_position_unsafe(positions)
            if not weakest:
                self._rejected_signals_count += 1
                return (False, None, "no_eligible_positions")
            
            # Calculate new signal's momentum score
            # For new signals, we only have the signal score (no price action yet)
            new_signal_score = new_signal.get("score", 0)
            new_momentum = (new_signal_score - 5) * 4  # Normalize to same scale
            
            # Add bonus for high conviction
            conviction = new_signal.get("conviction_type", "")
            if "High" in conviction or "Smart Money" in conviction:
                new_momentum += 10
            
            # Compare
            momentum_advantage = new_momentum - weakest.momentum_score
            
            if momentum_advantage >= self.min_momentum_advantage:
                return (True, weakest.token_address, f"advantage_{momentum_advantage:.1f}")
            else:
                self._rejected_signals_count += 1
                return (False, None, f"insufficient_advantage_{momentum_advantage:.1f}")
    
    def execute_rebalance(
        self,
        token_to_remove: str,
        new_signal: Dict[str, Any],
    ) -> bool:
        """
        Execute rebalance: remove weak position, add new signal.
        
        This should be called AFTER the trader has executed the swap.
        
        Args:
            token_to_remove: Token address to remove
            new_signal: New signal to add
        
        Returns:
            True if rebalance successful
        """
        with self._lock:
            # Remove old position
            old_position = self._positions.get(token_to_remove)
            if not old_position:
                return False
            
            # Use internal unsafe version since we already hold the lock
            self._remove_position_unsafe(token_to_remove, reason="rebalanced")
            
            # Add new position - use internal unsafe version to avoid deadlock
            success = self._add_position_unsafe(
                token_address=new_signal["token"],
                entry_price=new_signal["price"],
                quantity=new_signal.get("quantity", 0),
                signal_score=new_signal["score"],
                conviction_score=new_signal.get("prelim_score", 0),
                name=new_signal.get("name", ""),
                symbol=new_signal.get("symbol", ""),
            )
            
            if success:
                self._last_rebalance_time = time.time()
                self._rebalance_count += 1
                
                # Record rebalance
                self._rebalance_history.append({
                    "timestamp": time.time(),
                    "removed": old_position.to_dict(),
                    "added": new_signal,
                    "momentum_advantage": new_signal["score"] - old_position.momentum_score,
                })
                
                self._log_event("rebalance_executed", {
                    "removed_token": token_to_remove,
                    "removed_pnl": old_position.pnl_percent,
                    "added_token": new_signal["token"],
                    "added_score": new_signal["score"],
                })
            
            return success
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get portfolio statistics"""
        with self._lock:
            positions = list(self._positions.values())
            
            if not positions:
                return {
                    "position_count": 0,
                    "capacity_used": 0.0,
                    "rebalance_count": self._rebalance_count,
                    "rejected_signals": self._rejected_signals_count,
                }
            
            total_pnl = sum(p.pnl_percent for p in positions)
            avg_momentum = sum(p.momentum_score for p in positions) / len(positions)
            
            # Calculate ranked positions inline to avoid deadlock (don't call get_ranked_positions while holding lock)
            ranked = [(pos, pos.momentum_score) for pos in positions]
            ranked.sort(key=lambda x: x[1], reverse=True)
            
            return {
                "position_count": len(positions),
                "max_positions": self.max_positions,
                "capacity_used": len(positions) / self.max_positions,
                "avg_pnl_percent": total_pnl / len(positions),
                "avg_momentum_score": avg_momentum,
                "rebalance_count": self._rebalance_count,
                "rejected_signals": self._rejected_signals_count,
                "rebalance_efficiency": self._rebalance_count / max(1, self._rebalance_count + self._rejected_signals_count),
                "positions": [p.to_dict() for p, _ in ranked],
            }
    
    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """Get detailed portfolio snapshot for monitoring"""
        ranked = self.get_ranked_positions()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "position_count": len(ranked),
            "capacity": f"{len(ranked)}/{self.max_positions}",
            "is_full": self.is_full(),
            "positions": [
                {
                    "rank": i + 1,
                    "token": pos.token_address[:8],
                    "symbol": pos.symbol,
                    "momentum": f"{score:.1f}",
                    "pnl": f"{pos.pnl_percent:+.1f}%",
                    "age_min": f"{pos.age_minutes:.0f}",
                    "score": pos.signal_score,
                }
                for i, (pos, score) in enumerate(ranked)
            ],
            "stats": self.get_statistics(),
        }
    
    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log portfolio events"""
        try:
            from app.logger_utils import log_process
            log_process({
                "type": f"portfolio_{event_type}",
                "timestamp": time.time(),
                **data,
            })
        except Exception:
            pass


# Global singleton
_portfolio_manager: Optional[PortfolioManager] = None


def get_portfolio_manager(
    max_positions: int = 5,
    min_momentum_advantage: float = 15.0,
) -> PortfolioManager:
    """Get or create global portfolio manager instance"""
    global _portfolio_manager
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioManager(
            max_positions=max_positions,
            min_momentum_advantage=min_momentum_advantage,
        )
    return _portfolio_manager


def should_use_portfolio_manager() -> bool:
    """Check if portfolio manager is enabled via config"""
    import os
    return os.getenv("PORTFOLIO_REBALANCING_ENABLED", "false").lower() == "true"

