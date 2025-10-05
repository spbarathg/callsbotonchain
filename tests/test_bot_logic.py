from app.analyze_token import calculate_preliminary_score


def test_tx_has_smart_money_hints():
    from scripts.bot import tx_has_smart_money

    tx = {"smart_money": True}
    assert tx_has_smart_money(tx) is True

    tx = {"is_smart": True}
    assert tx_has_smart_money(tx) is True

    tx = {"top_wallets": ["w1", "w2"]}
    assert tx_has_smart_money(tx) is True

    tx = {"wallet_pnl": 1500}
    assert tx_has_smart_money(tx) is True

    tx = {"labels": ["alpha-hunter", "scout"]}
    assert tx_has_smart_money(tx) is True

    tx = {"labels": "elite sniper"}
    assert tx_has_smart_money(tx) is True

    # Negative cases
    tx = {"labels": ["random"], "wallet_pnl": 100}
    assert tx_has_smart_money(tx) is False


def test_preliminary_score_downweights_synthetic():
    base = {"usd_value": 1200}
    non_syn = calculate_preliminary_score(dict(base), smart_money_detected=False)
    syn = calculate_preliminary_score({**base, "is_synthetic": True}, smart_money_detected=False)
    assert syn <= non_syn


# Removed test_should_fetch_detailed_stats_raises_threshold_for_synthetic
# This test was using a non-existent function should_fetch_detailed_stats


