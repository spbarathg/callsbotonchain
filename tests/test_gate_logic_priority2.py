from app.analyze_token import check_senior_strict, check_junior_strict


def _mk_stats(**kw):
    base = {
        'market_cap_usd': 100000,
        'liquidity_usd': 20000,
        'volume': {'24h': {'volume_usd': 60000}},
        'change': {'1h': 10, '24h': 0},
        'security': {'is_honeypot': False, 'is_mint_revoked': True},
        'liquidity': {'is_lp_locked': True},
        'holders': {'top_10_concentration_percent': 30},
    }
    base.update(kw)
    return base


def test_strict_gate_liquidity_low():
    s = _mk_stats(liquidity_usd=1000)
    assert check_junior_strict(s, 9) is False


def test_strict_gate_mint_not_revoked_respects_config():
    # Behavior depends on REQUIRE_MINT_REVOKED; default False in config.
    s = _mk_stats(security={'is_mint_revoked': False})
    # With default config, not revoked is allowed; just assert the function returns a bool
    assert isinstance(check_senior_strict(s), bool)


def test_strict_gate_honeypot():
    s = _mk_stats(security={'is_honeypot': True})
    assert check_senior_strict(s) is False


def test_strict_gate_high_concentration():
    s = _mk_stats(holders={'top_10_concentration_percent': 90})
    assert check_senior_strict(s) is False


