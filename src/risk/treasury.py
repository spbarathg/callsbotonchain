import json
import os
from dataclasses import dataclass
from typing import Dict


_DEFAULT_PATH = os.getenv("TS_TREASURY_FILE", os.path.join("var", "treasury.json"))
os.makedirs(os.path.dirname(_DEFAULT_PATH), exist_ok=True)


@dataclass
class TreasurySnapshot:
    bankroll_usd: float
    reserve_usd: float

    def total(self) -> float:
        return float(self.bankroll_usd + self.reserve_usd)

    def to_dict(self) -> Dict[str, float]:
        return {"bankroll_usd": float(self.bankroll_usd), "reserve_usd": float(self.reserve_usd)}


def _read(path: str = _DEFAULT_PATH) -> TreasurySnapshot:
    try:
        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)
            return TreasurySnapshot(float(j.get("bankroll_usd", 0.0)), float(j.get("reserve_usd", 0.0)))
    except Exception:
        return TreasurySnapshot(0.0, 0.0)


def _write(s: TreasurySnapshot, path: str = _DEFAULT_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s.to_dict(), f)
    os.replace(tmp, path)


def get_snapshot() -> TreasurySnapshot:
    return _read()


def allocate_bankroll(from_reserve_usd: float) -> TreasurySnapshot:
    """Move funds from reserve into bankroll."""
    s = _read()
    amount = max(0.0, float(from_reserve_usd))
    move = min(amount, s.reserve_usd)
    s.reserve_usd -= move
    s.bankroll_usd += move
    _write(s)
    return s


def lock_profit_to_reserve(profit_usd: float, lock_ratio: float = 0.5) -> TreasurySnapshot:
    """After profitable periods, lock a portion of profits into reserve to mitigate drawdowns."""
    s = _read()
    p = max(0.0, float(profit_usd))
    r = max(0.0, min(1.0, float(lock_ratio)))
    lock = p * r
    s.bankroll_usd = max(0.0, s.bankroll_usd - lock)
    s.reserve_usd += lock
    _write(s)
    return s


def set_initial(bankroll_usd: float, reserve_usd: float) -> TreasurySnapshot:
    s = TreasurySnapshot(bankroll_usd=float(max(0.0, bankroll_usd)), reserve_usd=float(max(0.0, reserve_usd)))
    _write(s)
    return s


