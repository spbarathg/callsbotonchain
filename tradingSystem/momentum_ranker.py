"""
Momentum Ranker - Advanced Position Ranking

Provides sophisticated momentum calculations for portfolio positions.
Used by Portfolio Manager to determine which positions to keep/replace.

Author: Cielo Signal Optimizer Team
Date: October 10, 2025
"""

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class MomentumMetrics:
    """Comprehensive momentum metrics for a position"""
    
    # Price action
    pnl_percent: float
    pnl_velocity: float  # % gain per hour
    
    # Signal quality
    original_score: int
    conviction_type: str
    
    # Time factors
    age_hours: float
    time_penalty: float
    
    # Combined
    momentum_score: float
    rank_score: float  # Final ranking score
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pnl_percent": round(self.pnl_percent, 2),
            "pnl_velocity": round(self.pnl_velocity, 2),
            "original_score": self.original_score,
            "conviction": self.conviction_type,
            "age_hours": round(self.age_hours, 2),
            "momentum": round(self.momentum_score, 2),
            "rank": round(self.rank_score, 2),
        }


class MomentumRanker:
    """
    Advanced momentum ranking system.
    
    Considers multiple factors:
    - Recent price performance
    - Rate of change (velocity)
    - Original signal quality
    - Time decay
    - Market conditions
    """
    
    def __init__(
        self,
        pnl_weight: float = 0.4,
        velocity_weight: float = 0.3,
        signal_weight: float = 0.2,
        time_weight: float = 0.1,
    ):
        """
        Args:
            pnl_weight: Weight for current PnL
            velocity_weight: Weight for gain velocity
            signal_weight: Weight for original signal quality
            time_weight: Weight for time factors
        """
        self.pnl_weight = pnl_weight
        self.velocity_weight = velocity_weight
        self.signal_weight = signal_weight
        self.time_weight = time_weight
    
    def calculate_momentum(
        self,
        entry_price: float,
        current_price: float,
        entry_time: float,
        signal_score: int,
        conviction_type: str = "General",
        market_momentum: float = 0.0,  # Overall market trend
    ) -> MomentumMetrics:
        """
        Calculate comprehensive momentum metrics.
        
        Args:
            entry_price: Entry price
            current_price: Current price
            entry_time: Entry timestamp
            signal_score: Original signal score (0-10)
            conviction_type: Signal conviction type
            market_momentum: Overall market momentum (-100 to +100)
        
        Returns:
            MomentumMetrics object
        """
        # Calculate PnL
        pnl_percent = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        
        # Calculate velocity (% gain per hour)
        age_seconds = time.time() - entry_time
        age_hours = max(age_seconds / 3600, 0.01)  # Minimum 0.01 to avoid division by zero
        pnl_velocity = pnl_percent / age_hours
        
        # Signal quality score (normalize to 0-100)
        signal_quality = (signal_score / 10) * 100
        
        # Conviction bonus
        conviction_bonus = 0
        if "Smart Money" in conviction_type:
            conviction_bonus = 20
        elif "High" in conviction_type:
            conviction_bonus = 10
        elif "Strict" in conviction_type:
            conviction_bonus = 5
        
        # Time decay
        # Positions lose momentum over time, but not linearly
        if age_hours < 1:
            time_penalty = 0  # First hour: no penalty
        elif age_hours < 3:
            time_penalty = (age_hours - 1) * 5  # Hours 1-3: gradual penalty
        else:
            time_penalty = 10 + ((age_hours - 3) * 3)  # After 3h: accelerated penalty
        
        time_penalty = min(time_penalty, 50)  # Cap at 50
        
        # Calculate base momentum score
        momentum_score = (
            (pnl_percent * self.pnl_weight) +
            (pnl_velocity * self.velocity_weight) +
            ((signal_quality + conviction_bonus) * self.signal_weight) -
            (time_penalty * self.time_weight)
        )
        
        # Adjust for market conditions
        market_adjustment = market_momentum * 0.1  # Small influence
        momentum_score += market_adjustment
        
        # Final rank score (normalized to 0-100 range)
        rank_score = max(0, min(100, 50 + momentum_score))
        
        return MomentumMetrics(
            pnl_percent=pnl_percent,
            pnl_velocity=pnl_velocity,
            original_score=signal_score,
            conviction_type=conviction_type,
            age_hours=age_hours,
            time_penalty=time_penalty,
            momentum_score=momentum_score,
            rank_score=rank_score,
        )
    
    def rank_positions(
        self,
        positions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Rank a list of positions by momentum.
        
        Args:
            positions: List of position dicts with required fields
        
        Returns:
            Sorted list (best to worst) with momentum metrics added
        """
        ranked = []
        
        for pos in positions:
            metrics = self.calculate_momentum(
                entry_price=pos.get("entry_price", 0),
                current_price=pos.get("current_price", 0),
                entry_time=pos.get("entry_time", time.time()),
                signal_score=pos.get("signal_score", 5),
                conviction_type=pos.get("conviction_type", "General"),
                market_momentum=pos.get("market_momentum", 0),
            )
            
            ranked.append({
                **pos,
                "momentum_metrics": metrics.to_dict(),
                "rank_score": metrics.rank_score,
            })
        
        # Sort by rank score (descending)
        ranked.sort(key=lambda x: x["rank_score"], reverse=True)
        
        return ranked
    
    def compare_opportunity(
        self,
        current_position: Dict[str, Any],
        new_signal: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare a current position against a new signal.
        
        Args:
            current_position: Existing position data
            new_signal: New signal data
        
        Returns:
            Comparison result with recommendation
        """
        # Calculate momentum for current position
        current_metrics = self.calculate_momentum(
            entry_price=current_position.get("entry_price", 0),
            current_price=current_position.get("current_price", 0),
            entry_time=current_position.get("entry_time", time.time()),
            signal_score=current_position.get("signal_score", 5),
            conviction_type=current_position.get("conviction_type", "General"),
        )
        
        # Estimate momentum for new signal
        # New signals have no price action yet, so we estimate based on signal quality
        new_signal_score = new_signal.get("score", 5)
        new_conviction = new_signal.get("conviction_type", "General")
        
        # Estimate new signal momentum (optimistic but realistic)
        new_signal_quality = (new_signal_score / 10) * 100
        new_conviction_bonus = 20 if "Smart Money" in new_conviction else 10 if "High" in new_conviction else 0
        estimated_new_momentum = (new_signal_quality + new_conviction_bonus) * 0.7  # Conservative estimate
        
        # Compare
        momentum_advantage = estimated_new_momentum - current_metrics.rank_score
        
        # Decision threshold
        min_advantage = 15  # Require 15+ point advantage to swap
        should_rebalance = momentum_advantage >= min_advantage
        
        return {
            "should_rebalance": should_rebalance,
            "momentum_advantage": momentum_advantage,
            "current_momentum": current_metrics.rank_score,
            "estimated_new_momentum": estimated_new_momentum,
            "current_metrics": current_metrics.to_dict(),
            "confidence": "high" if momentum_advantage >= 25 else "medium" if momentum_advantage >= 15 else "low",
            "reason": f"Momentum advantage: {momentum_advantage:+.1f} points" if should_rebalance else f"Insufficient advantage: {momentum_advantage:+.1f} points (need +{min_advantage})",
        }


# Global singleton
_momentum_ranker: Optional[MomentumRanker] = None


def get_momentum_ranker() -> MomentumRanker:
    """Get or create global momentum ranker instance"""
    global _momentum_ranker
    if _momentum_ranker is None:
        _momentum_ranker = MomentumRanker()
    return _momentum_ranker

