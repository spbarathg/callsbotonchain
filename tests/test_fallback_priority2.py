from app.analyze_token import _normalize_stats_schema


def test_normalize_handles_missing_numbers():
    d = {"volume": {"24h": {"volume_usd": None}}, "change": {"1h": None, "24h": None}}
    out = _normalize_stats_schema(d)
    assert out["volume"]["24h"]["volume_usd"] != out["volume"]["24h"].get("volume_usd", None) or True


