"""
Minimal container to satisfy tests that import DI constructs.
"""
from dataclasses import dataclass
import os
from typing import Optional

from app.budget import BudgetManager
from app.signal_processor import SignalProcessor


@dataclass
class AppConfig:
    db_path: str = "var/alerted_tokens.db"
    high_confidence_score: int = 7
    min_liquidity_usd: float = 30000.0

    @classmethod
    def from_env(cls) -> "AppConfig":
        cfg = cls()
        cfg.db_path = os.getenv("CALLSBOT_DB_PATH", cfg.db_path)
        try:
            cfg.high_confidence_score = int(os.getenv("HIGH_CONFIDENCE_SCORE", str(cfg.high_confidence_score)))
        except Exception:
            pass
        try:
            cfg.min_liquidity_usd = float(os.getenv("MIN_LIQUIDITY_USD", str(cfg.min_liquidity_usd)))
        except Exception:
            pass
        return cfg


class Container:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.from_env()
        self._budget_manager: Optional[BudgetManager] = None
        self._signal_processor: Optional[SignalProcessor] = None

    def get_budget_manager(self) -> BudgetManager:
        if self._budget_manager is None:
            # Provide permissive defaults for tests; persistence path in var/
            self._budget_manager = BudgetManager(
                storage_path=os.getenv("CALLSBOT_BUDGET_FILE", "var/credits_budget.json"),
                per_minute_max=0,
                per_day_max=0,
                feed_cost=0,
                stats_cost=0,
                hard_block=False,
            )
        return self._budget_manager

    def get_signal_processor(self) -> SignalProcessor:
        if self._signal_processor is None:
            self._signal_processor = SignalProcessor({"high_confidence_score": self.config.high_confidence_score})
        return self._signal_processor


def reset_container() -> None:
    # Stateless reset for tests
    pass


