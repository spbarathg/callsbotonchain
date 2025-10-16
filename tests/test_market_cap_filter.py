"""
Test to verify that NO tokens with market cap > $1M can pass through the filter.

This test verifies the critical user requirement:
"no token with market cap > 1million gets past through and sent as a signal"
"""
import pytest
from app.analyze_token import check_junior_strict, check_junior_nuanced


def make_token_stats(market_cap_usd: float, liquidity_usd: float = 28000.0, volume_24h: float = None):
    """Helper to create token stats with specified market cap
    
    Updated for 50%+ hit rate optimization:
    - Liquidity: $25k+ required (was $18k)
    - Volume: $10k+ required (was $5k)
    - Vol/MCap ratio: 25%+ required (was 15%)
    """
    # Auto-calculate volume to meet 25% vol/mcap ratio AND $10k minimum
    if volume_24h is None:
        volume_24h = max(market_cap_usd * 0.30, 10000.0)  # 30% of mcap or $10k minimum
    
    return {
        "market_cap_usd": market_cap_usd,
        "liquidity_usd": liquidity_usd,  # Default $28k (above $25k requirement)
        "volume": {
            "24h": {
                "volume_usd": volume_24h
            }
        },
        "change": {
            "1h": 10.0,  # Positive momentum to test bypass
            "24h": 50.0
        },
        "security": {},
        "liquidity": {},
        "holders": {}
    }


class TestMarketCapFilter:
    """Test suite for market cap filtering"""
    
    def test_under_1m_passes_strict(self):
        """Tokens under $1M should pass strict check"""
        # Test various values under $1M
        for mcap in [100_000, 500_000, 999_999]:
            stats = make_token_stats(mcap)
            score = 8  # High score
            assert check_junior_strict(stats, score), f"Token with ${mcap:,} should pass strict check"
    
    def test_exactly_1m_passes_strict(self):
        """Token at exactly $1M should pass strict check"""
        stats = make_token_stats(1_000_000)
        score = 8
        assert check_junior_strict(stats, score), "Token at exactly $1M should pass"
    
    def test_over_1m_rejected_strict(self):
        """Tokens over $1M should be REJECTED by strict check"""
        # Test various values over $1M
        for mcap in [1_000_001, 1_500_000, 5_000_000, 50_000_000]:
            stats = make_token_stats(mcap)
            score = 10  # Even with max score
            assert not check_junior_strict(stats, score), \
                f"Token with ${mcap:,} should be REJECTED by strict check"
    
    def test_over_1m_rejected_with_momentum(self):
        """
        CRITICAL: Tokens over $1M should be rejected EVEN with high momentum.
        
        This tests the fix for the momentum bypass vulnerability.
        """
        for mcap in [2_000_000, 10_000_000]:
            stats = make_token_stats(mcap)
            # Add very high momentum to try to trigger bypass
            stats["change"]["1h"] = 100.0  # 100% momentum
            stats["change"]["24h"] = 200.0  # 200% momentum
            score = 10  # Max score
            
            assert not check_junior_strict(stats, score), \
                f"Token with ${mcap:,} and high momentum should STILL be REJECTED"
    
    def test_under_1m_passes_nuanced(self):
        """Tokens under $1M should pass nuanced check"""
        for mcap in [100_000, 500_000, 999_999]:
            stats = make_token_stats(mcap)
            score = 7
            assert check_junior_nuanced(stats, score), f"Token with ${mcap:,} should pass nuanced check"
    
    def test_over_1m_rejected_nuanced(self):
        """
        CRITICAL: Nuanced mode should NOT allow tokens > $1M.
        
        This tests the fix for NUANCED_MCAP_FACTOR = 1.0 (was 1.5).
        """
        # Test that nuanced mode does NOT multiply the limit by 1.5
        for mcap in [1_000_001, 1_200_000, 1_500_000, 5_000_000]:
            stats = make_token_stats(mcap)
            score = 10  # Max score
            assert not check_junior_nuanced(stats, score), \
                f"Token with ${mcap:,} should be REJECTED by nuanced check (no 1.5x multiplier)"
    
    def test_edge_cases(self):
        """Test edge cases for market cap filtering"""
        # Zero market cap (passes because mcap <= 1M)
        stats = make_token_stats(0, volume_24h=5000)
        score = 8
        # Note: Zero mcap will fail vol/mcap ratio (5000/0 = inf or division error)
        # But that's a different check, not the market cap limit check
        
        # Very small market cap
        stats = make_token_stats(10_000)  # $10k mcap with auto volume
        score = 8
        assert check_junior_strict(stats, score), "Very small market cap should pass"
        
        # Just over the limit
        stats = make_token_stats(1_000_001)
        score = 10
        assert not check_junior_strict(stats, score), "Market cap just over $1M should be rejected"
    
    def test_perfect_score_doesnt_bypass(self):
        """
        CRITICAL: Even perfect 10/10 score should not bypass market cap filter.
        """
        stats = make_token_stats(2_000_000)
        score = 10  # Perfect score
        
        # Add all the "good" signals
        stats["liquidity_usd"] = 100_000  # Excellent liquidity
        stats["volume"]["24h"]["volume_usd"] = 200_000  # High volume
        stats["change"]["1h"] = 50.0  # Strong momentum
        stats["change"]["24h"] = 100.0  # Strong trend
        
        assert not check_junior_strict(stats, score), \
            "Perfect 10/10 score should NOT bypass market cap filter"
        assert not check_junior_nuanced(stats, score), \
            "Perfect 10/10 score should NOT bypass market cap filter in nuanced mode"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

