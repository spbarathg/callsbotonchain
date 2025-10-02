from tradingSystem.strategy import decide_runner, decide_scout


def test_decide_runner_requires_smart_and_gates_pass():
    stats = {
        "liquidity_usd": 25000,
        "ratio": 0.7,
        "market_cap_usd": 900000,
        "change_1h": 25.0,
    }
    plan = decide_runner(stats, is_smart=True)
    assert plan is not None
    assert plan["strategy"] == "runner"
    assert plan["usd_size"] > 0
    assert plan["trail_pct"] > 0


def test_decide_runner_rejects_not_smart():
    stats = {
        "liquidity_usd": 25000,
        "ratio": 0.7,
        "market_cap_usd": 900000,
        "change_1h": 25.0,
    }
    assert decide_runner(stats, is_smart=False) is None


