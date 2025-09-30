from app.fetch_feed import _parse_retry_after_seconds


class FakeResp:
    def __init__(self, headers):
        self.headers = headers


def test_parse_retry_after_seconds_numeric():
    r = FakeResp({"Retry-After": "3"})
    assert _parse_retry_after_seconds(r) == 3


def test_parse_retry_after_seconds_epoch_headers(monkeypatch):
    now = 1_700_000_000
    monkeypatch.setattr("time.time", lambda: now)
    r = FakeResp({"X-RateLimit-Reset": str(now + 5)})
    assert _parse_retry_after_seconds(r) == 5


