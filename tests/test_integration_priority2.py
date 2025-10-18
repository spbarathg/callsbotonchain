
from app.analyze_token import _normalize_stats_schema


def test_normalize_unknown_flags():
    data = {"market_cap_usd": None, "price_usd": None, "volume": {"24h": {}}}
    out = _normalize_stats_schema(data)
    assert "market_cap_unknown" in out and out["market_cap_unknown"] is True
    assert "price_unknown" in out and out["price_unknown"] is True
    assert out["volume"]["24h"]["volume_usd_unknown"] is True



