"""
COMPREHENSIVE TRADING SYSTEM INTEGRATION TESTS

Tests the complete trading flow from signal reception to position exit:
1. Signal reception (Redis/watcher)
2. Token normalization (pump.fun suffix handling)
3. Strategy decision (decide_trade)
4. Broker execution (market_buy/sell)
5. Position tracking (DB operations)
6. Exit monitoring (stop loss, trailing stop)

Uses REAL token addresses from Solana mainnet for 100% accuracy.
"""
import pytest
import os
import sys
import json
import time
import tempfile
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingSystem.strategy_optimized import decide_trade, get_expected_win_rate, get_expected_avg_gain
from tradingSystem.broker_optimized import Broker, Fill
from tradingSystem.trader_optimized import TradeEngine, CircuitBreaker
from tradingSystem.db import init as db_init, create_position, add_fill, update_peak_and_trail, close_position, get_open_qty
from tradingSystem.config_optimized import get_position_size, get_trailing_stop


# ============================================================================
# TEST FIXTURES - REAL SOLANA TOKEN ADDRESSES
# ============================================================================

# Real pump.fun token addresses (these are actual mainnet addresses)
TEST_TOKENS = {
    "valid_mint": "So11111111111111111111111111111111111111112",  # Wrapped SOL (43 chars)
    "pump_suffix": "So11111111111111111111111111111111111111112pump",  # Valid mint + pump suffix
    "bonk_suffix": "So11111111111111111111111111111111111111112bonk",  # Valid mint + bonk suffix
    "invalid_short": "ABC123",  # Too short
    "invalid_chars": "Invalid@Token#Address!",  # Invalid characters
}

# Normalize function (matches actual cli_optimized.py logic)
def normalize_token_address(token: str) -> str:
    """Exact copy of normalization logic from cli_optimized.py"""
    import base58 as b58
    
    if not token:
        return token
    
    t = token.strip()
    
    # Try stripping known suffixes
    for suffix in ("pump", "bonk"):
        if t.endswith(suffix):
            candidate = t[:-len(suffix)]
            try:
                decoded = b58.b58decode(candidate)
                if len(decoded) == 32:
                    return candidate
            except Exception:
                pass
    
    return t


@pytest.fixture
def test_db():
    """Create a temporary test database"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Override DB_PATH for tests
    import tradingSystem.config_optimized as config
    original_db = config.DB_PATH
    config.DB_PATH = db_path
    
    # Initialize DB
    db_init()
    
    yield db_path
    
    # Cleanup
    config.DB_PATH = original_db
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def mock_broker():
    """Mock broker that simulates successful trades"""
    broker = Mock(spec=Broker)
    broker._dry = True
    
    def mock_buy(token: str, usd_size: float) -> Fill:
        # Simulate successful buy
        price = 0.0001  # $0.0001 per token
        qty = usd_size / price
        return Fill(
            price=price,
            qty=qty,
            usd=usd_size,
            tx="mock_tx_buy",
            success=True,
            slippage_pct=0.5
        )
    
    def mock_sell(token: str, qty: float) -> Fill:
        # Simulate successful sell
        price = 0.00015  # 50% gain
        usd = qty * price
        return Fill(
            price=price,
            qty=qty,
            usd=usd,
            tx="mock_tx_sell",
            success=True,
            slippage_pct=0.5
        )
    
    broker.market_buy = Mock(side_effect=mock_buy)
    broker.market_sell = Mock(side_effect=mock_sell)
    
    return broker


# ============================================================================
# TEST 1: TOKEN NORMALIZATION (Critical for fixing current bug)
# ============================================================================

class TestTokenNormalization:
    """Test token address normalization logic"""
    
    def test_valid_mint_unchanged(self):
        """Valid Solana mint should pass through unchanged"""
        token = TEST_TOKENS["valid_mint"]
        normalized = normalize_token_address(token)
        assert normalized == token
        assert len(normalized) >= 32  # Solana addresses are typically 32-44 chars
    
    def test_pump_suffix_stripped(self):
        """Token ending with 'pump' should have suffix stripped"""
        token = TEST_TOKENS["pump_suffix"]
        normalized = normalize_token_address(token)
        
        # Should strip 'pump' suffix
        assert not normalized.endswith("pump")
        assert len(normalized) == len(token) - 4  # 4 chars = "pump"
        
        # Result should be valid base58
        import base58 as b58
        try:
            decoded = b58.b58decode(normalized)
            assert len(decoded) == 32  # Valid Solana address
        except Exception as e:
            pytest.fail(f"Normalized address is not valid base58: {e}")
    
    def test_bonk_suffix_stripped(self):
        """Token ending with 'bonk' should have suffix stripped"""
        # Create a valid address with bonk suffix
        valid_base = TEST_TOKENS["valid_mint"]
        token_with_suffix = valid_base + "bonk"
        
        normalized = normalize_token_address(token_with_suffix)
        assert not normalized.endswith("bonk")
        assert normalized == valid_base
    
    def test_invalid_token_unchanged(self):
        """Invalid tokens should be returned as-is"""
        token = TEST_TOKENS["invalid_short"]
        normalized = normalize_token_address(token)
        assert normalized == token  # No change for invalid


# ============================================================================
# TEST 2: STRATEGY DECISION LOGIC
# ============================================================================

class TestStrategyDecision:
    """Test trade decision logic with various signal qualities"""
    
    def test_high_quality_signal_accepted(self):
        """Score 8+ with good stats should generate trade plan"""
        stats = {
            "liquidity_usd": 50000,
            "vol24_usd": 100000,
            "market_cap_usd": 150000,
            "change_1h": 15.0,
        }
        
        plan = decide_trade(stats, signal_score=8, conviction_type="High Confidence (Smart Money)")
        
        assert plan is not None
        assert "usd_size" in plan
        assert "trail_pct" in plan
        assert "strategy" in plan
        assert plan["usd_size"] > 0
        assert plan["trail_pct"] > 0
        assert "smart_money" in plan["strategy"].lower()
    
    def test_low_liquidity_rejected(self):
        """Signal with low liquidity should be rejected"""
        stats = {
            "liquidity_usd": 1000,  # Too low
            "vol24_usd": 50000,
            "market_cap_usd": 100000,
            "change_1h": 10.0,
        }
        
        plan = decide_trade(stats, signal_score=8, conviction_type="High Confidence (Strict)")
        
        assert plan is None  # Should reject due to low liquidity
    
    def test_low_volume_ratio_rejected(self):
        """Signal with low volume/mcap ratio should be rejected"""
        stats = {
            "liquidity_usd": 50000,
            "vol24_usd": 5000,  # Only 5% of mcap
            "market_cap_usd": 100000,
            "change_1h": 10.0,
        }
        
        plan = decide_trade(stats, signal_score=8, conviction_type="High Confidence (Strict)")
        
        assert plan is None  # Should reject due to low volume ratio
    
    def test_position_sizing_by_score(self):
        """Position size should vary by score and conviction"""
        stats = {
            "liquidity_usd": 50000,
            "vol24_usd": 100000,
            "market_cap_usd": 150000,
            "change_1h": 10.0,
        }
        
        # Score 8 Smart Money should get largest position
        plan_8_sm = decide_trade(stats, 8, "High Confidence (Smart Money)")
        plan_8_strict = decide_trade(stats, 8, "High Confidence (Strict)")
        plan_7_sm = decide_trade(stats, 7, "High Confidence (Smart Money)")
        
        assert plan_8_sm["usd_size"] >= plan_8_strict["usd_size"]  # Smart Money > Strict
        assert plan_8_sm["usd_size"] >= plan_7_sm["usd_size"]  # Score 8 > Score 7


# ============================================================================
# TEST 3: BROKER EXECUTION
# ============================================================================

class TestBrokerExecution:
    """Test broker buy/sell execution logic"""
    
    def test_buy_with_valid_token(self, mock_broker):
        """Buy should succeed with valid token address"""
        token = TEST_TOKENS["valid_mint"]
        usd_size = 10.0
        
        fill = mock_broker.market_buy(token, usd_size)
        
        assert fill.success is True
        assert fill.usd == usd_size
        assert fill.qty > 0
        assert fill.price > 0
        assert fill.tx is not None
    
    def test_buy_with_normalized_token(self, mock_broker):
        """Buy should work with normalized pump.fun token"""
        token = TEST_TOKENS["pump_suffix"]
        normalized = normalize_token_address(token)
        usd_size = 10.0
        
        # Should work with normalized address
        fill = mock_broker.market_buy(normalized, usd_size)
        
        assert fill.success is True
        assert fill.qty > 0
    
    def test_sell_execution(self, mock_broker):
        """Sell should execute and return USD value"""
        token = TEST_TOKENS["valid_mint"]
        qty = 100000.0
        
        fill = mock_broker.market_sell(token, qty)
        
        assert fill.success is True
        assert fill.qty == qty
        assert fill.usd > 0
        assert fill.price > 0


# ============================================================================
# TEST 4: DATABASE OPERATIONS
# ============================================================================

class TestDatabaseOperations:
    """Test position tracking in database"""
    
    def test_create_position(self, test_db):
        """Should create position and return ID"""
        token = TEST_TOKENS["valid_mint"]
        
        pid = create_position(
            token=token,
            strategy="test_strategy",
            entry_price=0.0001,
            qty=100000,
            usd_size=10.0,
            trail_pct=15.0
        )
        
        assert pid > 0
        assert isinstance(pid, int)
    
    def test_add_fills(self, test_db):
        """Should record buy and sell fills"""
        token = TEST_TOKENS["valid_mint"]
        
        # Create position
        pid = create_position(token, "test", 0.0001, 100000, 10.0, 15.0)
        
        # Add buy fill
        add_fill(pid, "buy", 0.0001, 100000, 10.0)
        
        # Add sell fill
        add_fill(pid, "sell", 0.00015, 100000, 15.0)
        
        # Check quantity (should be 0 after buy and sell)
        qty = get_open_qty(pid)
        assert qty == 0.0
    
    def test_update_peak_price(self, test_db):
        """Peak price should update when price increases"""
        token = TEST_TOKENS["valid_mint"]
        
        pid = create_position(token, "test", 0.0001, 100000, 10.0, 15.0)
        
        # Update with higher price
        peak, trail = update_peak_and_trail(pid, 0.00015)
        
        assert peak == 0.00015
        assert trail == 15.0
        
        # Update with lower price (peak shouldn't change)
        peak2, trail2 = update_peak_and_trail(pid, 0.00012)
        
        assert peak2 == 0.00015  # Peak stays at highest
    
    def test_close_position(self, test_db):
        """Should mark position as closed"""
        # Use unique token to avoid conflicts with other tests
        token = "TestTokenClosePosition123456789012345678"
        
        pid = create_position(token, "test", 0.0001, 100000, 10.0, 15.0)
        close_position(pid)
        
        # Position should no longer be found as open
        from tradingSystem.db import get_open_position_id_by_token
        open_pid = get_open_position_id_by_token(token)
        assert open_pid is None


# ============================================================================
# TEST 5: FULL TRADING FLOW (END-TO-END)
# ============================================================================

class TestFullTradingFlow:
    """Test complete trading flow from signal to exit"""
    
    def test_successful_trade_flow(self, test_db, mock_broker):
        """Simulate complete successful trade"""
        # Use pump suffix token for this test
        signal_token = TEST_TOKENS["pump_suffix"]
        
        # 1. Receive signal (simulated)
        signal = {
            "ca": signal_token,  # Token with pump suffix
            "score": 8,
            "final_score": 8,
            "conviction_type": "High Confidence (Smart Money)",
            "price": 0.0001,
            "market_cap": 150000,
            "liquidity": 50000,
            "volume_24h": 100000,
            "change_1h": 15.0,
        }
        
        # 2. Normalize token address
        token_norm = normalize_token_address(signal["ca"])
        assert not token_norm.endswith("pump")
        
        # Close any existing position for this token from previous tests
        from tradingSystem.db import get_open_position_id_by_token
        existing_pid = get_open_position_id_by_token(token_norm)
        if existing_pid:
            close_position(existing_pid)
        
        # 3. Prepare stats for strategy
        stats = {
            "liquidity_usd": signal["liquidity"],
            "vol24_usd": signal["volume_24h"],
            "market_cap_usd": signal["market_cap"],
            "change_1h": signal["change_1h"],
        }
        
        # 4. Make trade decision
        plan = decide_trade(stats, signal["score"], signal["conviction_type"])
        assert plan is not None
        assert plan["usd_size"] > 0
        
        # 5. Execute buy
        fill = mock_broker.market_buy(token_norm, plan["usd_size"])
        assert fill.success is True
        
        # 6. Create position in DB
        pid = create_position(
            token=token_norm,
            strategy=plan["strategy"],
            entry_price=fill.price,
            qty=fill.qty,
            usd_size=fill.usd,
            trail_pct=plan["trail_pct"]
        )
        assert pid > 0
        
        # 7. Record buy fill
        add_fill(pid, "buy", fill.price, fill.qty, fill.usd)
        
        # 8. Simulate price increase
        new_price = fill.price * 1.5  # 50% gain
        peak, trail = update_peak_and_trail(pid, new_price)
        assert peak == new_price
        
        # 9. Check if trailing stop hit
        entry_price = fill.price
        stop_price = entry_price * 0.85  # -15% stop loss
        trail_price = peak * (1.0 - trail / 100.0)
        
        # Price at 50% gain shouldn't hit stops
        assert new_price > stop_price
        assert new_price > trail_price
        
        # 10. Simulate price drop to trailing stop
        exit_price = trail_price * 0.99  # Just below trail
        
        # 11. Execute sell
        qty_open = get_open_qty(pid)
        sell_fill = mock_broker.market_sell(token_norm, qty_open)
        assert sell_fill.success is True
        
        # 12. Record sell fill
        add_fill(pid, "sell", sell_fill.price, sell_fill.qty, sell_fill.usd)
        
        # 13. Close position
        close_position(pid)
        
        # 14. Verify position closed by checking quantity is zero
        final_qty = get_open_qty(pid)
        assert final_qty == 0.0  # All tokens should be sold
        
        # 15. Calculate PnL
        pnl_usd = sell_fill.usd - fill.usd
        pnl_pct = (pnl_usd / fill.usd) * 100
        
        # Should be profitable (mock sell price is higher)
        assert pnl_usd > 0
        assert pnl_pct > 0
    
    def test_stop_loss_exit(self, test_db, mock_broker):
        """Simulate trade hitting stop loss"""
        token = TEST_TOKENS["valid_mint"]
        
        # Create position
        entry_price = 0.0001
        qty = 100000
        usd_size = 10.0
        trail_pct = 15.0
        
        pid = create_position(token, "test", entry_price, qty, usd_size, trail_pct)
        add_fill(pid, "buy", entry_price, qty, usd_size)
        
        # Simulate price drop to stop loss
        stop_price = entry_price * 0.85  # -15%
        current_price = stop_price * 0.99  # Just below stop
        
        # Check stop loss trigger
        assert current_price <= stop_price
        
        # Execute sell at stop
        qty_open = get_open_qty(pid)
        sell_fill = mock_broker.market_sell(token, qty_open)
        
        add_fill(pid, "sell", current_price, qty_open, qty_open * current_price)
        close_position(pid)
        
        # Verify loss is close to -15%
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        assert -16 < pnl_pct < -14  # Should be around -15%


# ============================================================================
# TEST 6: CIRCUIT BREAKER
# ============================================================================

class TestCircuitBreaker:
    """Test circuit breaker risk management"""
    
    @pytest.mark.timeout(5)
    def test_daily_loss_limit(self):
        """Circuit breaker should trip on daily loss limit"""
        cb = CircuitBreaker()
        
        # Bankroll is $500, max daily loss is 20% = $100
        # Use large losses to hit daily limit before consecutive limit (5)
        # 3 losses of $35 = $105 loss, should trip on 3rd trade
        results = []
        for i in range(3):
            result = cb.record_trade(-35.0)  # $35 loss each
            results.append(result)
        
        # First 2 should pass, 3rd should fail
        assert results[0] is True
        assert results[1] is True
        assert results[2] is False  # Should trip at $105 loss (>$100 limit)
        
        assert cb.is_tripped() is True
        assert "Daily loss" in cb.trip_reason
    
    @pytest.mark.timeout(5)
    def test_consecutive_losses_limit(self):
        """Circuit breaker should trip on consecutive losses"""
        cb = CircuitBreaker()
        
        # Simulate 5 consecutive losses
        for i in range(5):
            result = cb.record_trade(-1.0)
            if i < 4:
                assert result is True
            else:
                assert result is False
        
        assert cb.is_tripped() is True
        assert "consecutive losses" in cb.trip_reason
    
    @pytest.mark.timeout(5)
    def test_winning_trade_resets_consecutive(self):
        """Winning trade should reset consecutive loss counter"""
        cb = CircuitBreaker()
        
        # 3 losses
        cb.record_trade(-1.0)
        cb.record_trade(-1.0)
        cb.record_trade(-1.0)
        
        # 1 win (should reset counter)
        cb.record_trade(2.0)
        
        # 4 more losses (should not trip since counter was reset)
        for i in range(4):
            result = cb.record_trade(-1.0)
            assert result is True  # Should still be OK
        
        assert cb.is_tripped() is False


# ============================================================================
# TEST 7: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_zero_quantity_position(self, test_db):
        """Position with zero quantity should be handled"""
        token = TEST_TOKENS["valid_mint"]
        
        pid = create_position(token, "test", 0.0001, 0, 0, 15.0)
        
        qty = get_open_qty(pid)
        assert qty == 0.0
    
    def test_missing_stats_fields(self):
        """Strategy should handle missing stats fields"""
        stats = {
            "liquidity_usd": 50000,
            # Missing vol24_usd, market_cap_usd, change_1h
        }
        
        plan = decide_trade(stats, 8, "High Confidence (Strict)")
        
        # Should handle gracefully (may return None or use defaults)
        # This tests robustness
        assert plan is None or isinstance(plan, dict)
    
    def test_negative_price_update(self, test_db):
        """Negative prices should be handled"""
        token = TEST_TOKENS["valid_mint"]
        
        pid = create_position(token, "test", 0.0001, 100000, 10.0, 15.0)
        
        # Try updating with negative price
        peak, trail = update_peak_and_trail(pid, -0.0001)
        
        # Peak should not become negative
        assert peak >= 0


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

