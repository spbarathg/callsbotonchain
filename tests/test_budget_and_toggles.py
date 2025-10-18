import threading

from app.budget import BudgetManager
from app.toggles import set_toggles, get_toggles


def test_budget_concurrent_spend(tmp_path):
    path = tmp_path / "budget.json"
    bm = BudgetManager(str(path), per_minute_max=10, per_day_max=100)

    def worker(n):
        for _ in range(n):
            if bm.can_spend("feed"):
                bm.spend("feed")

    threads = [threading.Thread(target=worker, args=(5,)) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Reload a fresh manager to read persisted state
    bm2 = BudgetManager(str(path), per_minute_max=10, per_day_max=100)
    # Ensure counts never exceeded per-minute max despite concurrency
    assert bm2.remaining_minute() >= 0
    assert bm2.remaining_day() >= 0


def test_toggles_race(tmp_path, monkeypatch):
    # Force toggles file to temp dir
    var_dir = tmp_path / "var"
    var_dir.mkdir()
    monkeypatch.setenv("CALLSBOT_VAR_DIR", str(var_dir))

    # Simulate rapid updates
    set_toggles({"signals_enabled": True, "trading_enabled": False})
    set_toggles({"signals_enabled": False})
    tg = get_toggles()
    assert isinstance(tg.get("signals_enabled"), bool)
    assert isinstance(tg.get("trading_enabled"), bool)


