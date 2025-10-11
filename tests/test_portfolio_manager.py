"""
Tests for Portfolio Manager - Circle Strategy

Test coverage:
- Position adding/removal
- Momentum ranking
- Rebalancing logic
- Cooldown enforcement
- Position age requirements
"""

import pytest
import time
from tradingSystem.portfolio_manager import PortfolioManager, Position


class TestPosition:
    """Test Position dataclass"""
    
    def test_pnl_calculation(self):
        """Test PnL percentage calculation"""
        pos = Position(
            token_address="ABC",
            entry_price=1.0,
            current_price=1.5,
            quantity=100,
            entry_time=time.time(),
            conviction_score=5,
            signal_score=8,
        )
        assert pos.pnl_percent == 50.0  # +50%
    
    def test_negative_pnl(self):
        """Test negative PnL"""
        pos = Position(
            token_address="ABC",
            entry_price=1.0,
            current_price=0.8,
            quantity=100,
            entry_time=time.time(),
            conviction_score=5,
            signal_score=8,
        )
        assert pos.pnl_percent == pytest.approx(-20.0, rel=1e-6)  # -20%
    
    def test_momentum_score_components(self):
        """Test momentum score calculation"""
        pos = Position(
            token_address="ABC",
            entry_price=1.0,
            current_price=1.5,
            quantity=100,
            entry_time=time.time() - 1800,  # 30 min ago
            conviction_score=5,
            signal_score=8,
        )
        
        momentum = pos.momentum_score
        
        # Should be positive (50% gain)
        assert momentum > 0
        
        # Should include signal bonus
        # Signal score 8 -> (8-5)*4 = 12 bonus
        assert momentum > 50  # PnL + signal bonus
    
    def test_time_decay(self):
        """Test time decay penalty"""
        # Recent position
        pos_new = Position(
            token_address="ABC",
            entry_price=1.0,
            current_price=1.5,
            quantity=100,
            entry_time=time.time() - 600,  # 10 min ago
            conviction_score=5,
            signal_score=8,
        )
        
        # Old position
        pos_old = Position(
            token_address="ABC",
            entry_price=1.0,
            current_price=1.5,
            quantity=100,
            entry_time=time.time() - 7200,  # 2 hours ago
            conviction_score=5,
            signal_score=8,
        )
        
        # Newer position should have higher momentum
        assert pos_new.momentum_score > pos_old.momentum_score


class TestPortfolioManager:
    """Test Portfolio Manager"""
    
    def test_initialization(self):
        """Test manager initialization"""
        pm = PortfolioManager(max_positions=5)
        assert pm.max_positions == 5
        assert pm.get_position_count() == 0
        assert not pm.is_full()
    
    def test_add_position(self):
        """Test adding positions"""
        pm = PortfolioManager(max_positions=3)
        
        # Add first position
        success = pm.add_position(
            token_address="TOKEN1",
            entry_price=1.0,
            quantity=100,
            signal_score=8,
            conviction_score=5,
        )
        
        assert success
        assert pm.get_position_count() == 1
        assert pm.has_position("TOKEN1")
    
    def test_cannot_add_duplicate(self):
        """Test duplicate prevention"""
        pm = PortfolioManager(max_positions=3)
        
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        
        # Try to add same token again
        success = pm.add_position("TOKEN1", 1.5, 100, 9, 6)
        
        assert not success
        assert pm.get_position_count() == 1
    
    def test_portfolio_capacity(self):
        """Test max positions limit"""
        pm = PortfolioManager(max_positions=3)
        
        # Fill portfolio
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        pm.add_position("TOKEN2", 1.0, 100, 8, 5)
        pm.add_position("TOKEN3", 1.0, 100, 8, 5)
        
        assert pm.is_full()
        assert pm.get_position_count() == 3
        
        # Try to add 4th (should fail if not rebalancing)
        success = pm.add_position("TOKEN4", 1.0, 100, 8, 5)
        assert not success
    
    def test_remove_position(self):
        """Test position removal"""
        pm = PortfolioManager(max_positions=3)
        
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        pm.add_position("TOKEN2", 1.0, 100, 8, 5)
        
        # Remove TOKEN1
        success = pm.remove_position("TOKEN1")
        
        assert success
        assert pm.get_position_count() == 1
        assert not pm.has_position("TOKEN1")
        assert pm.has_position("TOKEN2")
    
    def test_update_prices(self):
        """Test price updates"""
        pm = PortfolioManager(max_positions=3)
        
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        pm.add_position("TOKEN2", 1.0, 100, 8, 5)
        
        # Update prices
        pm.update_prices({
            "TOKEN1": 1.5,
            "TOKEN2": 0.8,
        })
        
        # Verify updates
        positions = pm.get_ranked_positions()
        token1 = next(p for p, _ in positions if p.token_address == "TOKEN1")
        token2 = next(p for p, _ in positions if p.token_address == "TOKEN2")
        
        assert token1.current_price == 1.5
        assert token2.current_price == 0.8
        assert token1.pnl_percent == 50.0
        assert token2.pnl_percent == pytest.approx(-20.0, rel=1e-6)
    
    def test_ranking_by_momentum(self):
        """Test position ranking"""
        pm = PortfolioManager(max_positions=5)
        
        current_time = time.time()
        # Add positions with different performance
        pm.add_position("BEST", 1.0, 100, 9, 5, name="Best")  # High score
        pm.add_position("WORST", 1.0, 100, 6, 5, name="Worst")  # Low score  
        pm.add_position("MIDDLE", 1.0, 100, 7, 5, name="Middle")  # Mid score
        
        # Update prices
        pm.update_prices({
            "BEST": 1.8,    # +80%
            "WORST": 0.95,  # -5%
            "MIDDLE": 1.2,  # +20%
        })
        
        # Get ranked
        ranked = pm.get_ranked_positions()
        
        # BEST should be first
        assert ranked[0][0].token_address == "BEST"
        
        # WORST should be last
        assert ranked[-1][0].token_address == "WORST"
        
        # MIDDLE in between
        assert ranked[1][0].token_address == "MIDDLE"
    
    def test_get_weakest_position(self):
        """Test finding weakest position"""
        pm = PortfolioManager(max_positions=3, min_position_age=0.1)  # 0.1 sec age (fast)
        
        # Add positions
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        pm.add_position("TOKEN2", 1.0, 100, 6, 5)
        
        # Update prices
        pm.update_prices({
            "TOKEN1": 1.5,  # +50%
            "TOKEN2": 0.9,  # -10%
        })
        
        weakest = pm.get_weakest_position()
        
        # Should be TOKEN1 (oldest eligible) or None if ages not met
        assert weakest is None or weakest.token_address == "TOKEN1"
    
    def test_evaluate_rebalance_not_full(self):
        """Test rebalance evaluation when not full"""
        pm = PortfolioManager(max_positions=5)
        
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        
        # New signal
        new_signal = {
            "token": "TOKEN2",
            "price": 1.0,
            "score": 9,
            "conviction_type": "High",
        }
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should not rebalance (not full)
        assert not should_rebalance
        assert reason == "portfolio_not_full"
    
    def test_evaluate_rebalance_cooldown(self):
        """Test rebalance cooldown enforcement"""
        pm = PortfolioManager(
            max_positions=2,
            rebalance_cooldown=10,  # 10 sec cooldown
            min_position_age=0.1,  # Fast for testing
        )
        
        # Fill portfolio
        pm.add_position("TOKEN1", 1.0, 100, 6, 5)
        pm.add_position("TOKEN2", 1.0, 100, 6, 5)
        
        # First rebalance evaluation
        new_signal = {
            "token": "TOKEN3",
            "price": 1.0,
            "score": 10,
            "conviction_type": "Smart Money",
        }
        
        pm._last_rebalance_time = time.time()  # Simulate recent rebalance
        
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should be blocked by cooldown
        assert not should_rebalance
        assert "cooldown" in reason
    
    def test_rebalance_statistics(self):
        """Test portfolio statistics"""
        pm = PortfolioManager(max_positions=3)
        
        pm.add_position("TOKEN1", 1.0, 100, 8, 5)
        pm.add_position("TOKEN2", 1.0, 100, 7, 5)
        
        # Update prices
        pm.update_prices({
            "TOKEN1": 1.5,
            "TOKEN2": 1.2,
        })
        
        stats = pm.get_statistics()
        
        assert stats["position_count"] == 2
        assert stats["max_positions"] == 3
        assert stats["capacity_used"] == 2/3
        assert stats["avg_pnl_percent"] == pytest.approx(35.0, rel=1)  # (50 + 20) / 2


class TestRebalancingLogic:
    """Test complete rebalancing scenarios"""
    
    def test_rebalance_execution(self):
        """Test full rebalance execution"""
        pm = PortfolioManager(
            max_positions=2,
            min_momentum_advantage=10.0,
            rebalance_cooldown=0.0,  # No cooldown for testing
            min_position_age=0.0,  # No minimum age for testing
        )
        
        # Add initial positions
        pm.add_position("WEAK", 1.0, 100, 3, 5, name="Weak Token")  # Very low score
        pm.add_position("STRONG", 1.0, 100, 8, 5, name="Strong Token")
        
        # Update prices - make WEAK perform badly
        pm.update_prices({
            "WEAK": 0.7,   # -30%
            "STRONG": 1.4,  # +40%
        })
        
        # New high-quality signal
        new_signal = {
            "token": "MOON",
            "price": 1.0,
            "score": 10,
            "conviction_type": "Smart Money",
            "quantity": 100,
            "prelim_score": 10,
            "name": "Moon Token",
            "symbol": "MOON",
        }
        
        # Evaluate
        should_rebalance, token_to_replace, reason = pm.evaluate_rebalance(new_signal)
        
        # Should want to rebalance
        assert should_rebalance
        assert token_to_replace == "WEAK"
        
        # Execute
        success = pm.execute_rebalance("WEAK", new_signal)
        
        assert success
        assert not pm.has_position("WEAK")
        assert pm.has_position("MOON")
        assert pm.has_position("STRONG")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

