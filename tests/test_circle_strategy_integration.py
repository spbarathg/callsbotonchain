"""
Integration test for Circle Strategy

Tests the full flow:
1. Portfolio manager initialization
2. Trader integration
3. Rebalancing decision logic
"""

import pytest
import time
from unittest.mock import Mock, patch
from tradingSystem.portfolio_manager import PortfolioManager, get_portfolio_manager
from tradingSystem.config_optimized import MAX_CONCURRENT


class TestCircleStrategyIntegration:
    """Test complete Circle Strategy integration"""
    
    def test_portfolio_manager_initialization(self):
        """Test portfolio manager can be initialized with config"""
        pm = PortfolioManager(
            max_positions=MAX_CONCURRENT,
            min_momentum_advantage=15.0,
            rebalance_cooldown=300,
            min_position_age=600,
        )
        
        assert pm.max_positions == MAX_CONCURRENT
        assert pm.min_momentum_advantage == 15.0
        assert pm.get_position_count() == 0
        assert not pm.is_full()
    
    def test_portfolio_fills_then_evaluates_rebalancing(self):
        """Test portfolio fills normally, then evaluates rebalancing"""
        pm = PortfolioManager(
            max_positions=3,
            min_momentum_advantage=10.0,
            rebalance_cooldown=0,  # No cooldown for testing
            min_position_age=0,    # No minimum age for testing
        )
        
        # Phase 1: Fill portfolio
        for i in range(3):
            success = pm.add_position(
                token_address=f"TOKEN{i}",
                entry_price=1.0,
                quantity=100,
                signal_score=7,
                conviction_score=5,
            )
            assert success
        
        assert pm.is_full()
        assert pm.get_position_count() == 3
        
        # Phase 2: Try to add 4th position (should fail - portfolio full)
        success = pm.add_position(
            token_address="TOKEN3",
            entry_price=1.0,
            quantity=100,
            signal_score=8,
            conviction_score=5,
        )
        assert not success  # Portfolio full, add fails
        
        # Phase 3: Evaluate rebalancing with weak current positions
        pm.update_prices({
            "TOKEN0": 0.8,  # -20%
            "TOKEN1": 1.1,  # +10%
            "TOKEN2": 1.2,  # +20%
        })
        
        # New strong signal
        new_signal = {
            "token": "STRONG_TOKEN",
            "score": 10,
            "conviction_type": "Smart Money",
            "price": 1.0,
            "quantity": 100,
            "prelim_score": 10,
            "name": "Strong Token",
            "symbol": "STRONG",
        }
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should want to rebalance (strong signal vs weak positions)
        assert should_rebalance
        assert token_to_replace == "TOKEN0"  # Weakest position
        assert "advantage" in reason
    
    def test_rebalancing_respects_cooldown(self):
        """Test cooldown prevents rapid rebalancing"""
        pm = PortfolioManager(
            max_positions=2,
            min_momentum_advantage=10.0,
            rebalance_cooldown=10,  # 10 second cooldown
            min_position_age=0,
        )
        
        # Fill portfolio
        pm.add_position("TOKEN0", 1.0, 100, 6, 5)
        pm.add_position("TOKEN1", 1.0, 100, 6, 5)
        
        # Simulate recent rebalance
        pm._last_rebalance_time = time.time()
        
        # Try to rebalance again
        new_signal = {
            "token": "TOKEN2",
            "score": 10,
            "conviction_type": "Smart Money",
            "price": 1.0,
        }
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should be blocked by cooldown
        assert not should_rebalance
        assert "cooldown" in reason
    
    def test_rebalancing_respects_minimum_position_age(self):
        """Test positions must be old enough to be replaced"""
        pm = PortfolioManager(
            max_positions=2,
            min_momentum_advantage=5.0,  # Very low threshold
            rebalance_cooldown=0,
            min_position_age=3600,  # 1 hour minimum age
        )
        
        # Add new positions (will be < 1 hour old)
        pm.add_position("TOKEN0", 1.0, 100, 5, 5)
        pm.add_position("TOKEN1", 1.0, 100, 5, 5)
        
        # Try to rebalance with much better signal
        new_signal = {
            "token": "TOKEN2",
            "score": 10,
            "conviction_type": "Smart Money",
            "price": 1.0,
        }
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should be blocked (no positions old enough)
        assert not should_rebalance
        assert "no_eligible_positions" in reason
    
    def test_momentum_ranking_affects_replacement_choice(self):
        """Test that weakest momentum position is chosen for replacement"""
        pm = PortfolioManager(
            max_positions=3,
            min_momentum_advantage=5.0,
            rebalance_cooldown=0,
            min_position_age=0,
        )
        
        # Add positions with different performance
        pm.add_position("BEST", 1.0, 100, 10, 5)
        pm.add_position("MIDDLE", 1.0, 100, 7, 5)
        pm.add_position("WORST", 1.0, 100, 5, 5)
        
        # Update prices to create clear winner/loser
        pm.update_prices({
            "BEST": 2.0,    # +100%
            "MIDDLE": 1.3,  # +30%
            "WORST": 0.7,   # -30%
        })
        
        # Evaluate rebalancing
        new_signal = {
            "token": "NEW",
            "score": 9,
            "conviction_type": "High",
            "price": 1.0,
        }
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should choose WORST position for replacement
        assert token_to_replace == "WORST"
    
    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly"""
        pm = PortfolioManager(max_positions=3)
        
        # Add positions
        pm.add_position("TOKEN0", 1.0, 100, 8, 5)
        pm.add_position("TOKEN1", 1.0, 100, 9, 5)
        
        # Update prices
        pm.update_prices({
            "TOKEN0": 1.5,  # +50%
            "TOKEN1": 1.2,  # +20%
        })
        
        # Get statistics
        stats = pm.get_statistics()
        
        assert stats["position_count"] == 2
        assert stats["max_positions"] == 3
        assert stats["capacity_used"] == 2/3
        assert stats["avg_pnl_percent"] == pytest.approx(35.0, rel=1)  # (50+20)/2
        assert "avg_momentum_score" in stats
        assert stats["rebalance_count"] == 0  # No rebalances yet
    
    def test_complete_rebalancing_flow(self):
        """Test complete rebalancing flow from evaluation to execution"""
        pm = PortfolioManager(
            max_positions=2,
            min_momentum_advantage=10.0,
            rebalance_cooldown=0,
            min_position_age=0,
        )
        
        # Phase 1: Fill portfolio
        pm.add_position("WEAK", 1.0, 100, 5, 5, name="Weak Token")
        pm.add_position("STRONG", 1.0, 100, 8, 5, name="Strong Token")
        
        # Phase 2: Update prices (make WEAK perform badly)
        pm.update_prices({
            "WEAK": 0.6,    # -40%
            "STRONG": 1.5,  # +50%
        })
        
        # Phase 3: Evaluate new signal
        new_signal = {
            "token": "MOON",
            "score": 10,
            "conviction_type": "Smart Money",
            "price": 1.0,
            "quantity": 100,
            "prelim_score": 10,
            "name": "Moon Token",
            "symbol": "MOON",
        }
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        assert should_rebalance
        assert token_to_replace == "WEAK"
        
        # Phase 4: Execute rebalance
        success = pm.execute_rebalance(token_to_replace, new_signal)
        
        assert success
        assert not pm.has_position("WEAK")
        assert pm.has_position("MOON")
        assert pm.has_position("STRONG")
        
        # Phase 5: Verify statistics updated
        stats = pm.get_statistics()
        assert stats["rebalance_count"] == 1
        assert stats["position_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

