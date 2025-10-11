"""
Tests for Momentum Ranker

Test coverage:
- Momentum calculation
- PnL velocity
- Time decay
- Conviction bonuses
- Position ranking
- Opportunity comparison
"""

import pytest
import time
from tradingSystem.momentum_ranker import MomentumRanker, MomentumMetrics


class TestMomentumCalculation:
    """Test momentum metric calculations"""
    
    def test_positive_pnl(self):
        """Test positive PnL momentum"""
        ranker = MomentumRanker()
        
        entry_time = time.time() - 3600  # 1 hour ago
        
        metrics = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.5,
            entry_time=entry_time,
            signal_score=8,
            conviction_type="General",
        )
        
        assert metrics.pnl_percent == 50.0
        assert metrics.pnl_velocity == pytest.approx(50.0, rel=0.1)  # 50% per hour
        assert metrics.momentum_score > 0
    
    def test_negative_pnl(self):
        """Test negative PnL momentum"""
        ranker = MomentumRanker()
        
        entry_time = time.time() - 3600  # 1 hour ago
        
        metrics = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=0.8,
            entry_time=entry_time,
            signal_score=8,
            conviction_type="General",
        )
        
        assert metrics.pnl_percent == pytest.approx(-20.0, rel=1e-6)
        assert metrics.pnl_velocity == pytest.approx(-20.0, rel=0.1)
        assert metrics.momentum_score < metrics.rank_score  # Negative impact
    
    def test_pnl_velocity(self):
        """Test velocity calculation"""
        ranker = MomentumRanker()
        
        # Fast mover (1 hour, +50%)
        metrics_fast = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.5,
            entry_time=time.time() - 3600,
            signal_score=8,
        )
        
        # Slow mover (4 hours, +50%)
        metrics_slow = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.5,
            entry_time=time.time() - 14400,
            signal_score=8,
        )
        
        # Fast mover should have higher velocity
        assert metrics_fast.pnl_velocity > metrics_slow.pnl_velocity
        
        # Fast mover should have higher momentum
        assert metrics_fast.momentum_score > metrics_slow.momentum_score
    
    def test_signal_score_impact(self):
        """Test signal quality impact"""
        ranker = MomentumRanker()
        
        entry_time = time.time() - 3600
        
        # High score
        metrics_high = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=entry_time,
            signal_score=10,
        )
        
        # Low score
        metrics_low = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=entry_time,
            signal_score=6,
        )
        
        # Higher signal score should boost momentum
        assert metrics_high.momentum_score > metrics_low.momentum_score
    
    def test_conviction_bonuses(self):
        """Test conviction type bonuses"""
        ranker = MomentumRanker()
        
        entry_time = time.time() - 3600
        
        # Smart Money
        metrics_smart = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=entry_time,
            signal_score=8,
            conviction_type="Smart Money",
        )
        
        # High Conviction
        metrics_high = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=entry_time,
            signal_score=8,
            conviction_type="High Conviction",
        )
        
        # General
        metrics_general = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=entry_time,
            signal_score=8,
            conviction_type="General",
        )
        
        # Smart Money best, then High, then General
        assert metrics_smart.momentum_score > metrics_high.momentum_score
        assert metrics_high.momentum_score > metrics_general.momentum_score
    
    def test_time_decay_progression(self):
        """Test time decay over different ages"""
        ranker = MomentumRanker()
        
        current = time.time()
        
        # Recent (30 min)
        metrics_30m = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=current - 1800,
            signal_score=8,
        )
        
        # 1 hour
        metrics_1h = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=current - 3600,
            signal_score=8,
        )
        
        # 3 hours
        metrics_3h = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=current - 10800,
            signal_score=8,
        )
        
        # 6 hours
        metrics_6h = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.2,
            entry_time=current - 21600,
            signal_score=8,
        )
        
        # Older positions should have lower momentum
        assert metrics_30m.momentum_score > metrics_1h.momentum_score
        assert metrics_1h.momentum_score > metrics_3h.momentum_score
        assert metrics_3h.momentum_score > metrics_6h.momentum_score
        
        # Time penalties should increase
        assert metrics_30m.time_penalty < metrics_1h.time_penalty
        assert metrics_1h.time_penalty < metrics_3h.time_penalty
        assert metrics_3h.time_penalty < metrics_6h.time_penalty


class TestPositionRanking:
    """Test position ranking"""
    
    def test_rank_positions(self):
        """Test ranking multiple positions"""
        ranker = MomentumRanker()
        
        current = time.time()
        
        positions = [
            {
                "token": "WINNER",
                "entry_price": 1.0,
                "current_price": 2.0,  # +100%
                "entry_time": current - 3600,
                "signal_score": 9,
                "conviction_type": "Smart Money",
            },
            {
                "token": "LOSER",
                "entry_price": 1.0,
                "current_price": 0.8,  # -20%
                "entry_time": current - 7200,  # Old
                "signal_score": 6,
                "conviction_type": "General",
            },
            {
                "token": "MODERATE",
                "entry_price": 1.0,
                "current_price": 1.3,  # +30%
                "entry_time": current - 1800,
                "signal_score": 8,
                "conviction_type": "High Conviction",
            },
        ]
        
        ranked = ranker.rank_positions(positions)
        
        # Should be ranked best to worst
        assert ranked[0]["token"] == "WINNER"
        assert ranked[-1]["token"] == "LOSER"
        assert ranked[1]["token"] == "MODERATE"
    
    def test_rank_score_normalization(self):
        """Test rank scores are normalized 0-100"""
        ranker = MomentumRanker()
        
        positions = [
            {
                "entry_price": 1.0,
                "current_price": 3.0,  # Extreme gain
                "entry_time": time.time() - 3600,
                "signal_score": 10,
                "conviction_type": "Smart Money",
            },
            {
                "entry_price": 1.0,
                "current_price": 0.5,  # Extreme loss
                "entry_time": time.time() - 3600,
                "signal_score": 5,
                "conviction_type": "General",
            },
        ]
        
        ranked = ranker.rank_positions(positions)
        
        for pos in ranked:
            rank_score = pos["rank_score"]
            assert 0 <= rank_score <= 100


class TestOpportunityComparison:
    """Test opportunity comparison logic"""
    
    def test_compare_strong_new_vs_weak_current(self):
        """Test strong new signal vs weak current position"""
        ranker = MomentumRanker()
        
        current_position = {
            "entry_price": 1.0,
            "current_price": 0.9,  # -10%
            "entry_time": time.time() - 7200,  # Old
            "signal_score": 6,
            "conviction_type": "General",
        }
        
        new_signal = {
            "score": 10,
            "conviction_type": "Smart Money",
        }
        
        result = ranker.compare_opportunity(current_position, new_signal)
        
        assert result["should_rebalance"] is True
        assert result["momentum_advantage"] > 15
        assert result["confidence"] in ["high", "medium"]
    
    def test_compare_weak_new_vs_strong_current(self):
        """Test weak new signal vs strong current position"""
        ranker = MomentumRanker()
        
        current_position = {
            "entry_price": 1.0,
            "current_price": 1.8,  # +80%
            "entry_time": time.time() - 1800,  # Recent
            "signal_score": 9,
            "conviction_type": "Smart Money",
        }
        
        new_signal = {
            "score": 7,
            "conviction_type": "General",
        }
        
        result = ranker.compare_opportunity(current_position, new_signal)
        
        assert result["should_rebalance"] is False
        assert result["momentum_advantage"] < 15
    
    def test_compare_similar_quality(self):
        """Test similar quality signals (lateral move)"""
        ranker = MomentumRanker()
        
        current_position = {
            "entry_price": 1.0,
            "current_price": 1.2,  # +20%
            "entry_time": time.time() - 3600,
            "signal_score": 8,
            "conviction_type": "High Conviction",
        }
        
        new_signal = {
            "score": 8,
            "conviction_type": "High Conviction",
        }
        
        result = ranker.compare_opportunity(current_position, new_signal)
        
        # Should not rebalance (insufficient advantage)
        assert result["should_rebalance"] is False


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_zero_entry_price(self):
        """Test handling of zero entry price"""
        ranker = MomentumRanker()
        
        metrics = ranker.calculate_momentum(
            entry_price=0.0,
            current_price=1.0,
            entry_time=time.time() - 3600,
            signal_score=8,
        )
        
        # Should handle gracefully
        assert metrics.pnl_percent == 0.0
        assert metrics.momentum_score >= 0
    
    def test_very_recent_position(self):
        """Test position opened seconds ago"""
        ranker = MomentumRanker()
        
        metrics = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.5,
            entry_time=time.time() - 10,  # 10 seconds ago
            signal_score=8,
        )
        
        # Should have very high velocity
        assert metrics.pnl_velocity > 100  # 50% in 10 sec = 18000% per hour
        
        # Should have no time penalty
        assert metrics.time_penalty == 0.0
    
    def test_extreme_age(self):
        """Test very old position"""
        ranker = MomentumRanker()
        
        metrics = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.5,
            entry_time=time.time() - 86400,  # 24 hours ago
            signal_score=8,
        )
        
        # Should have maximum time penalty (capped at 50)
        assert metrics.time_penalty == pytest.approx(50.0, rel=0.1)
    
    def test_custom_weights(self):
        """Test custom weight configuration"""
        ranker = MomentumRanker(
            pnl_weight=0.5,
            velocity_weight=0.2,
            signal_weight=0.2,
            time_weight=0.1,
        )
        
        metrics = ranker.calculate_momentum(
            entry_price=1.0,
            current_price=1.5,
            entry_time=time.time() - 3600,
            signal_score=8,
        )
        
        # Should calculate successfully with custom weights
        assert metrics.momentum_score is not None
        assert 0 <= metrics.rank_score <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

