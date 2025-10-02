import os
import tempfile

from src.risk.treasury import set_initial, get_snapshot, allocate_bankroll, lock_profit_to_reserve


def test_treasury_allocate_and_lock(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "treasury.json")
        monkeypatch.setenv("TS_TREASURY_FILE", path)

        set_initial(bankroll_usd=100.0, reserve_usd=900.0)
        s = get_snapshot()
        assert s.bankroll_usd == 100.0
        assert s.reserve_usd == 900.0

        # Move 200 from reserve to bankroll (bounded by reserve)
        s = allocate_bankroll(200.0)
        assert s.bankroll_usd == 300.0
        assert s.reserve_usd == 700.0

        # Lock 100 profit at 50% -> move 50 to reserve
        s = lock_profit_to_reserve(100.0, lock_ratio=0.5)
        assert s.reserve_usd == 750.0
        assert s.bankroll_usd == 250.0


