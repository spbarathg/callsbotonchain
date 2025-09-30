import json
import os
import time
from typing import Dict, Optional
from contextlib import contextmanager


class BudgetManager:
    """
    Simple credits budget manager with per-minute and per-day caps.
    Persists counters to var/credits_budget.json to survive restarts.
    """

    def __init__(self,
                 storage_path: str,
                 per_minute_max: int,
                 per_day_max: int,
                 feed_cost: int = 1,
                 stats_cost: int = 1,
                 hard_block: bool = True) -> None:
        self.storage_path = storage_path
        self.per_minute_max = max(0, int(per_minute_max or 0))
        self.per_day_max = max(0, int(per_day_max or 0))
        self.feed_cost = max(0, int(feed_cost or 0))
        self.stats_cost = max(0, int(stats_cost or 0))
        self.hard_block = bool(hard_block)
        self._state: Dict[str, int] = {
            "minute_epoch": 0,
            "minute_count": 0,
            "day_utc": 0,
            "day_count": 0,
        }
        self._load()

    # ---------- cross-process file lock ----------
    @staticmethod
    @contextmanager
    def _lock_file(path: str):
        """Best-effort cross-process advisory lock using a sidecar .lock file.
        Works on POSIX (fcntl) and Windows (msvcrt)."""
        lock_path = f"{path}.lock"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        f = open(lock_path, "a+b")
        locked = False
        try:
            try:
                import fcntl  # type: ignore
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    locked = True
                except Exception:
                    locked = False
            except ImportError:
                try:
                    import msvcrt  # type: ignore
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    locked = True
                except Exception:
                    locked = False
            yield
        finally:
            try:
                if locked:
                    try:
                        import fcntl  # type: ignore
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        try:
                            import msvcrt  # type: ignore
                            f.seek(0)
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                f.close()
            except Exception:
                pass

    # ---------- persistence ----------
    def _ensure_dir(self) -> None:
        d = os.path.dirname(self.storage_path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

    def _load_unlocked(self) -> None:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._state.update({k: int(v) for k, v in data.items() if k in self._state})
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _load(self) -> None:
        try:
            with self._lock_file(self.storage_path):
                self._load_unlocked()
        except Exception:
            pass

    def _save_unlocked(self) -> None:
        try:
            self._ensure_dir()
            tmp = self.storage_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False)
            os.replace(tmp, self.storage_path)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            with self._lock_file(self.storage_path):
                self._save_unlocked()
        except Exception:
            pass

    # ---------- windows & counters ----------
    @staticmethod
    def _utc_day(ts: Optional[float] = None) -> int:
        t = int(ts or time.time())
        return int(t // 86400)  # days since epoch (UTC)

    @staticmethod
    def _minute_epoch(ts: Optional[float] = None) -> int:
        t = int(ts or time.time())
        return int(t // 60)

    def _roll_windows(self) -> None:
        now = time.time()
        m = self._minute_epoch(now)
        d = self._utc_day(now)
        if self._state["minute_epoch"] != m:
            self._state["minute_epoch"] = m
            self._state["minute_count"] = 0
        if self._state["day_utc"] != d:
            self._state["day_utc"] = d
            self._state["day_count"] = 0

    # ---------- API ----------
    def remaining_minute(self) -> int:
        # Reload under lock to reflect external updates
        with self._lock_file(self.storage_path):
            self._load_unlocked()
            self._roll_windows()
        if self.per_minute_max <= 0:
            return 1_000_000_000
        return max(0, self.per_minute_max - self._state["minute_count"])

    def remaining_day(self) -> int:
        with self._lock_file(self.storage_path):
            self._load_unlocked()
            self._roll_windows()
        if self.per_day_max <= 0:
            return 1_000_000_000
        return max(0, self.per_day_max - self._state["day_count"])

    def _cost_for_kind(self, kind: str) -> int:
        if kind == "feed":
            return self.feed_cost
        if kind == "stats":
            return self.stats_cost
        return 1

    def can_spend(self, kind: str = "stats", cost: Optional[int] = None) -> bool:
        c = int(cost if cost is not None else self._cost_for_kind(kind))
        with self._lock_file(self.storage_path):
            self._load_unlocked()
            self._roll_windows()
            min_left = self.per_minute_max if self.per_minute_max <= 0 else max(0, self.per_minute_max - self._state["minute_count"])
            day_left = self.per_day_max if self.per_day_max <= 0 else max(0, self.per_day_max - self._state["day_count"])
            return (min_left >= c) and (day_left >= c)

    def spend(self, kind: str = "stats", cost: Optional[int] = None) -> None:
        c = int(cost if cost is not None else self._cost_for_kind(kind))
        with self._lock_file(self.storage_path):
            # Refresh state to avoid lost updates without nesting locks
            self._load_unlocked()
            self._roll_windows()
            self._state["minute_count"] += c
            self._state["day_count"] += c
            self._save_unlocked()


_budget_singleton: Optional[BudgetManager] = None


def get_budget() -> BudgetManager:
    global _budget_singleton
    if _budget_singleton is not None:
        return _budget_singleton
    from config import (
        BUDGET_ENABLED,
        BUDGET_PER_MINUTE_MAX,
        BUDGET_PER_DAY_MAX,
        BUDGET_FEED_COST,
        BUDGET_STATS_COST,
        BUDGET_HARD_BLOCK,
        CALLSBOT_BUDGET_FILE,
    )
    # When budget is disabled, return a permissive manager with no persistence
    if not BUDGET_ENABLED:
        _budget_singleton = BudgetManager(
            storage_path=CALLSBOT_BUDGET_FILE,
            per_minute_max=0,
            per_day_max=0,
            feed_cost=0,
            stats_cost=0,
            hard_block=False,
        )
        return _budget_singleton
    _budget_singleton = BudgetManager(
        storage_path=CALLSBOT_BUDGET_FILE,
        per_minute_max=BUDGET_PER_MINUTE_MAX,
        per_day_max=BUDGET_PER_DAY_MAX,
        feed_cost=BUDGET_FEED_COST,
        stats_cost=BUDGET_STATS_COST,
        hard_block=BUDGET_HARD_BLOCK,
    )
    return _budget_singleton


