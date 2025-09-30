import time

from app.analyze_token import (
    calculate_preliminary_score,
    score_token,
    check_senior_strict,
    check_junior_strict,
    check_senior_nuanced,
    check_junior_nuanced,
    _normalize_stats_schema,
)


def test_calculate_preliminary_score_bounds():
    tx = {"usd_value": 0}
    assert calculate_preliminary_score(tx) == 0
    tx = {"usd_value": 10_000_000}
    s = calculate_preliminary_score(tx, smart_money_detected=True)
    assert 0 <= s <= 10


def test_score_token_returns_details_and_bounds():
    stats = {
        "market_cap_usd": 50_000,
        "volume": {"24h": {"volume_usd": 60_000, "unique_buyers": 10, "unique_sellers": 5}},
        "change": {"1h": 10, "24h": 5},
    }
    score, details = score_token(stats, smart_money_detected=True, token_address="X")
    assert isinstance(score, int)
    assert 0 <= score <= 10
    assert isinstance(details, list)


def _base_stats():
    return _normalize_stats_schema({
        "market_cap_usd": 100_000,
        "liquidity_usd": 20_000,
        "volume": {"24h": {"volume_usd": 60_000}},
        "change": {"1h": 10, "24h": 5},
        "security": {"is_honeypot": False, "is_mint_revoked": True},
        "liquidity": {"is_lp_locked": True},
        "holders": {"top_10_concentration_percent": 30},
        "symbol": "TKN",
        "name": "Token",
    })


def test_senior_and_junior_checks_strict():
    stats = _base_stats()
    assert check_senior_strict(stats, token_address="abc") is True
    # Use a high score to satisfy junior gate
    assert check_junior_strict(stats, final_score=10) is True


def test_senior_and_junior_checks_nuanced():
    stats = _base_stats()
    # Slightly relax holders and liquidity in nuanced; still should pass
    assert check_senior_nuanced(stats, token_address="abc") is True
    assert check_junior_nuanced(stats, final_score=9) is True


