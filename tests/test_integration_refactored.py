"""
Integration Tests for Refactored Architecture

Tests the new modular components:
- Domain models
- Signal processor
- Repositories
- Container/DI
- Circuit breakers
"""
import pytest
import os
import tempfile
from datetime import datetime, timedelta


# ============================================================================
# DOMAIN MODELS TESTS
# ============================================================================

def test_token_stats_validation():
    """Test TokenStats model validates numeric fields"""
    from app.models import TokenStats
    
    # Test NaN/Infinity handling
    stats = TokenStats(
        token_address="test123",
        price_usd=float('nan'),
        liquidity_usd=float('inf'),
        market_cap_usd=100000.0
    )
    
    # NaN and Infinity should be filtered out
    assert stats.price_usd is None
    assert stats.liquidity_usd is None
    assert stats.market_cap_usd == 100000.0


def test_token_stats_from_api_response():
    """Test TokenStats can parse various API response shapes"""
    from app.models import TokenStats
    
    # Cielo-style response
    cielo_data = {
        "token_address": "abc123",
        "price_usd": 0.001,
        "market_cap_usd": 50000,
        "liquidity": {"usd": 25000},
        "security": {"is_mint_revoked": True},
        "holders": {"top_10_concentration_percent": 15.5},
    }
    
    stats = TokenStats.from_api_response(cielo_data, source="cielo")
    
    assert stats is not None
    assert stats.token_address == "abc123"
    assert stats.price_usd == 0.001
    assert stats.liquidity_usd == 25000
    assert stats.is_mint_revoked is True
    assert stats.top_10_concentration_percent == 15.5


def test_feed_transaction_model():
    """Test FeedTransaction model handles various inputs"""
    from app.models import FeedTransaction
    
    tx = FeedTransaction(
        token0_address="So11111111111111111111111111111111111111112",  # SOL
        token1_address="xyz789",
        token0_amount_usd=100.0,
        token1_amount_usd=95.0,
        smart_money=True
    )
    
    # Should identify non-SOL token
    candidate = tx.get_candidate_token()
    assert candidate == "xyz789"
    
    # Should compute USD value
    assert tx.usd_value == 100.0


def test_process_result_model():
    """Test ProcessResult provides clear status"""
    from app.models import ProcessResult
    
    result = ProcessResult(
        status="alert_sent",
        token_address="test",
        final_score=8
    )
    
    assert result.is_alert is True
    assert result.is_error is False


# ============================================================================
# REPOSITORY TESTS
# ============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def test_alert_repository_basic_operations(temp_db):
    """Test AlertRepository CRUD operations"""
    from app.repositories import DatabaseConnection, AlertRepository, initialize_schema
    
    db_conn = DatabaseConnection(temp_db)
    initialize_schema(db_conn)
    
    repo = AlertRepository(db_conn)
    
    # Initially not alerted
    assert repo.has_been_alerted("token123") is False
    
    # Mark as alerted
    repo.mark_alerted("token123", score=8, smart_money_detected=True, conviction_type="High")
    
    # Should now be alerted (checks cache)
    assert repo.has_been_alerted("token123") is True
    
    # Should persist across new instance
    repo2 = AlertRepository(db_conn)
    assert repo2.has_been_alerted("token123") is True


def test_alert_repository_metadata(temp_db):
    """Test AlertRepository stores comprehensive metadata"""
    from app.repositories import DatabaseConnection, AlertRepository, initialize_schema
    
    db_conn = DatabaseConnection(temp_db)
    initialize_schema(db_conn)
    
    repo = AlertRepository(db_conn)
    
    stats = {
        "name": "TestToken",
        "symbol": "TEST",
        "price_usd": 0.01,
        "market_cap_usd": 100000,
        "liquidity_usd": 30000,
        "security": {"is_mint_revoked": True, "is_lp_locked": True},
        "holders": {"top_10_concentration_percent": 12.5, "holder_count": 500},
    }
    
    metadata = {
        "token_age_minutes": 60,
        "smart_money_involved": True,
        "passed_junior_strict": True,
        "passed_senior_strict": True,
        "passed_debate": False,
    }
    
    repo.record_alert_with_metadata(
        token_address="token456",
        preliminary_score=7,
        final_score=8,
        conviction_type="High Confidence (Strict)",
        stats=stats,
        alert_metadata=metadata
    )
    
    # Verify it was stored
    with db_conn.get_connection() as conn:
        cursor = conn.execute(
            "SELECT name, symbol, final_score, conviction_type FROM alerted_token_stats WHERE token_address = ?",
            ("token456",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "TestToken"
        assert row[1] == "TEST"
        assert row[2] == 8
        assert row[3] == "High Confidence (Strict)"


def test_performance_repository(temp_db):
    """Test PerformanceRepository tracks token performance"""
    from app.repositories import DatabaseConnection, AlertRepository, PerformanceRepository, initialize_schema
    
    db_conn = DatabaseConnection(temp_db)
    initialize_schema(db_conn)
    
    # First, create an alert (required for performance tracking)
    alert_repo = AlertRepository(db_conn)
    stats = {"price_usd": 0.01, "market_cap_usd": 100000}
    alert_repo.record_alert_with_metadata(
        token_address="token789",
        preliminary_score=7,
        final_score=8,
        conviction_type="High",
        stats=stats,
        alert_metadata={}
    )
    
    # Now track performance
    perf_repo = PerformanceRepository(db_conn)
    
    # Record price snapshot
    perf_repo.record_price_snapshot("token789", price=0.015, liquidity=35000)
    
    # Update performance (50% gain from 0.01 to 0.015)
    perf_repo.update_token_performance("token789", current_price=0.015, liquidity=35000)
    
    # Verify performance was calculated
    snapshot = perf_repo.get_tracking_snapshot("token789")
    assert snapshot is not None
    assert snapshot["current_pnl_pct"] == pytest.approx(50.0, rel=1e-2)
    assert snapshot["max_gain_pct"] == pytest.approx(50.0, rel=1e-2)


def test_activity_repository(temp_db):
    """Test ActivityRepository tracks token activity"""
    from app.repositories import DatabaseConnection, ActivityRepository, initialize_schema
    
    db_conn = DatabaseConnection(temp_db)
    initialize_schema(db_conn)
    
    repo = ActivityRepository(db_conn)
    
    # Record activity
    repo.record_token_activity(
        token_address="tokenABC",
        usd_value=5000.0,
        tx_count=1,
        smart_money=True,
        preliminary_score=7,
        trader="wallet123"
    )
    
    # Should retrieve recent signals
    signals = repo.get_recent_token_signals("tokenABC", window_seconds=3600)
    assert len(signals) == 1
    
    # Cleanup old activity
    repo.cleanup_old_activity(days_back=0)  # Delete everything
    signals_after = repo.get_recent_token_signals("tokenABC", window_seconds=3600)
    assert len(signals_after) == 0


# ============================================================================
# SIGNAL PROCESSOR TESTS
# ============================================================================

def test_signal_processor_validation():
    """Test SignalProcessor validates feed items"""
    from app.signal_processor import SignalProcessor
    
    config = {"high_confidence_score": 7}
    processor = SignalProcessor(config)
    
    # Test with invalid transaction (no token)
    tx = {"tx_type": "buy", "usd_value": 0}
    result = processor.process_feed_item(tx, is_smart_cycle=False)
    
    assert result.status == "skipped"
    assert "No valid token" in result.error_message or "zero value" in result.error_message


def test_signal_processor_native_sol_filter():
    """Test SignalProcessor filters native SOL"""
    from app.signal_processor import SignalProcessor
    
    config = {"high_confidence_score": 7}
    processor = SignalProcessor(config)
    
    # Native SOL should be skipped
    tx = {
        "token0_address": "So11111111111111111111111111111111111111112",
        "token1_address": "So11111111111111111111111111111111111111112",
        "usd_value": 1000
    }
    result = processor.process_feed_item(tx, is_smart_cycle=False)
    
    assert result.status == "skipped"


# ============================================================================
# CONTAINER/DI TESTS
# ============================================================================

def test_container_provides_singletons():
    """Test Container provides singleton instances"""
    from app.container import Container, AppConfig, reset_container
    
    # Reset first to ensure clean state
    reset_container()
    
    config = AppConfig.from_env()
    container = Container(config)
    
    # Budget manager should be singleton
    budget1 = container.get_budget_manager()
    budget2 = container.get_budget_manager()
    assert budget1 is budget2
    
    # Signal processor should be singleton
    processor1 = container.get_signal_processor()
    processor2 = container.get_signal_processor()
    assert processor1 is processor2


def test_container_config():
    """Test Container loads configuration correctly"""
    from app.container import AppConfig
    
    config = AppConfig.from_env()
    
    # Should have loaded from environment
    assert isinstance(config.high_confidence_score, int)
    assert isinstance(config.min_liquidity_usd, float)


# ============================================================================
# CIRCUIT BREAKER TESTS
# ============================================================================

def test_circuit_breaker_opens_on_failures():
    """Test CircuitBreaker opens after threshold failures"""
    from app.http_client import CircuitBreaker
    
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
    
    # Initially closed
    assert cb.state == "CLOSED"
    
    # Simulate failures
    cb.on_failure()
    assert cb.state == "CLOSED"  # Below threshold
    
    cb.on_failure()
    assert cb.state == "CLOSED"
    
    cb.on_failure()
    assert cb.state == "OPEN"  # Hit threshold
    
    # Should reject requests
    with pytest.raises(Exception, match="Circuit breaker OPEN"):
        cb.before_request()


def test_circuit_breaker_recovers():
    """Test CircuitBreaker attempts recovery after timeout"""
    from app.http_client import CircuitBreaker
    import time
    
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
    
    # Open the circuit
    cb.on_failure()
    cb.on_failure()
    assert cb.state == "OPEN"
    
    # Wait for recovery timeout
    time.sleep(1.1)
    
    # Should transition to HALF_OPEN
    cb.before_request()
    assert cb.state == "HALF_OPEN"
    
    # Success should close it
    cb.on_success()
    assert cb.state == "CLOSED"


def test_circuit_breaker_status():
    """Test circuit breaker status reporting"""
    from app.http_client import _get_circuit_breaker, get_circuit_breaker_status, reset_circuit_breakers
    
    # Reset first
    reset_circuit_breakers()
    
    # Create a circuit breaker
    cb = _get_circuit_breaker("test.example.com")
    cb.on_failure()
    
    # Get status
    status = get_circuit_breaker_status()
    assert "test.example.com" in status
    assert status["test.example.com"]["failure_count"] == 1


# ============================================================================
# END-TO-END INTEGRATION TEST
# ============================================================================

def test_end_to_end_alert_flow(temp_db):
    """
    Test complete alert flow:
    1. Process feed item
    2. Store alert
    3. Track performance
    4. Retrieve data
    """
    from app.repositories import DatabaseConnection, AlertRepository, PerformanceRepository, initialize_schema
    from app.models import TokenStats
    
    db_conn = DatabaseConnection(temp_db)
    initialize_schema(db_conn)
    
    alert_repo = AlertRepository(db_conn)
    perf_repo = PerformanceRepository(db_conn)
    
    # Simulate an alert
    token = "endtoend123"
    stats_dict = {
        "name": "EndToEndToken",
        "symbol": "E2E",
        "price_usd": 0.005,
        "market_cap_usd": 250000,
        "liquidity_usd": 40000,
        "volume_24h_usd": 80000,
        "security": {"is_mint_revoked": True, "is_lp_locked": True},
        "holders": {"top_10_concentration_percent": 14.0},
    }
    
    # Record alert
    alert_repo.record_alert_with_metadata(
        token_address=token,
        preliminary_score=7,
        final_score=8,
        conviction_type="High Confidence (Strict)",
        stats=stats_dict,
        alert_metadata={"smart_money_involved": True}
    )
    
    # Verify it's marked as alerted
    assert alert_repo.has_been_alerted(token) is True
    
    # Simulate price increase (100% gain)
    perf_repo.update_token_performance(
        token_address=token,
        current_price=0.010,
        liquidity=45000
    )
    
    # Retrieve performance
    snapshot = perf_repo.get_tracking_snapshot(token)
    assert snapshot is not None
    assert snapshot["current_pnl_pct"] == pytest.approx(100.0, rel=1e-2)
    assert snapshot["name"] == "EndToEndToken"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

