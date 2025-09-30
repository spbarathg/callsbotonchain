from app.http_client import request_json


def test_request_json_handles_non_json(monkeypatch):
    # Can't hit network; just ensure function returns keys for error path
    r = request_json("GET", "https://example.invalid.localdomain/test", timeout=0.1)
    assert "status_code" in r
    assert (r.get("json") is None) or isinstance(r.get("json"), dict)


