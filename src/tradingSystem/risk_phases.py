"""
Risk Phase System - Phased stop-loss for memecoin volatility.

PROBLEM: Hard stop-loss fires during normal entry noise (first 1-3 minutes),
         killing 76% of trades. The stop ignores MIN_HOLD_SECONDS.

SOLUTION: Three risk phases with different stop-loss thresholds:
  EARLY (0-3min): Very loose stop (or disabled). Let entry noise pass.
  MID (3-15min):  Normal stop + trailing enabled.
  LATE (15min+):  Trailing-stop dominant, tighter hard stop.

Forensic evidence:
  - 52/73 trades exit in <5min (71%), net -$73.11
  - 16/73 trades exit in 5-15min (22%), net -$2.75 (near breakeven)
  - 5/73 trades exit >15min (7%), net +$35.92 (all profit is here)
"""

import os
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Tuple


class RiskPhase(Enum):
    """Risk management phases based on position age."""
    EARLY = "early"   # 0 -> early_end_sec
    MID = "mid"       # early_end_sec -> mid_end_sec
    LATE = "late"     # mid_end_sec -> inf


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class PhaseConfig:
    """Configuration for the phased risk system.

    All values can be overridden via environment variables.
    """
    # Phase boundaries (seconds)
    early_end_sec: int = 180       # 3 minutes
    mid_end_sec: int = 900         # 15 minutes

    # Stop-loss thresholds per phase (% from entry)
    early_stop_pct: float = 50.0   # Very loose - only emergency exits
    mid_stop_pct: float = 25.0     # Normal stop
    late_stop_pct: float = 20.0    # Tighter when trail is dominant

    # Trail enablement per phase
    early_trail_enabled: bool = False   # No trail in early (let it breathe)
    mid_trail_enabled: bool = True
    late_trail_enabled: bool = True

    @classmethod
    def from_env(cls) -> "PhaseConfig":
        """Load configuration from environment variables."""
        return cls(
            early_end_sec=_env_int("RISK_EARLY_END_SEC", 180),
            mid_end_sec=_env_int("RISK_MID_END_SEC", 900),
            early_stop_pct=_env_float("RISK_EARLY_STOP_PCT", 50.0),
            mid_stop_pct=_env_float("RISK_MID_STOP_PCT", 25.0),
            late_stop_pct=_env_float("RISK_LATE_STOP_PCT", 20.0),
            early_trail_enabled=os.getenv("RISK_EARLY_TRAIL", "false").strip().lower() in ("1", "true"),
            mid_trail_enabled=os.getenv("RISK_MID_TRAIL", "true").strip().lower() in ("1", "true"),
            late_trail_enabled=os.getenv("RISK_LATE_TRAIL", "true").strip().lower() in ("1", "true"),
        )


class RiskManager:
    """Phased risk manager that replaces the monolithic stop-loss.

    Usage::

        rm = get_risk_manager()
        should_exit, reason = rm.should_exit(
            hold_seconds=elapsed,
            current_pnl_pct=pnl,
            peak_pnl_pct=peak_profit,
            trail_pct=configured_trail,
        )
    """

    def __init__(self, config: Optional[PhaseConfig] = None):
        self.config = config or PhaseConfig.from_env()
        print(
            f"[RISK] Phases: EARLY(0-{self.config.early_end_sec}s, stop={self.config.early_stop_pct}%) "
            f"-> MID({self.config.early_end_sec}-{self.config.mid_end_sec}s, stop={self.config.mid_stop_pct}%) "
            f"-> LATE(>{self.config.mid_end_sec}s, stop={self.config.late_stop_pct}%)",
            flush=True,
        )

    def get_phase(self, hold_seconds: float) -> RiskPhase:
        """Determine the current risk phase based on hold time."""
        if hold_seconds < self.config.early_end_sec:
            return RiskPhase.EARLY
        elif hold_seconds < self.config.mid_end_sec:
            return RiskPhase.MID
        return RiskPhase.LATE

    def get_stop_loss_pct(self, phase: RiskPhase) -> float:
        """Get the stop-loss threshold for a given phase."""
        return {
            RiskPhase.EARLY: self.config.early_stop_pct,
            RiskPhase.MID: self.config.mid_stop_pct,
            RiskPhase.LATE: self.config.late_stop_pct,
        }[phase]

    def is_trail_enabled(self, phase: RiskPhase) -> bool:
        """Check if trailing stop is enabled in the given phase."""
        return {
            RiskPhase.EARLY: self.config.early_trail_enabled,
            RiskPhase.MID: self.config.mid_trail_enabled,
            RiskPhase.LATE: self.config.late_trail_enabled,
        }[phase]

    def should_exit(
        self,
        hold_seconds: float,
        current_pnl_pct: float,
        peak_pnl_pct: float,
        trail_pct: float,
    ) -> Tuple[bool, str]:
        """Determine if the position should be exited.

        Args:
            hold_seconds: Time since position was opened.
            current_pnl_pct: Current P&L as percentage (e.g., -15.0 for -15%).
            peak_pnl_pct: Peak P&L reached as percentage.
            trail_pct: Trailing stop distance as percentage.

        Returns:
            (should_exit, reason) tuple.
        """
        phase = self.get_phase(hold_seconds)
        stop_pct = self.get_stop_loss_pct(phase)

        # --- STOP LOSS CHECK (phase-aware) ---
        if current_pnl_pct <= -stop_pct:
            return True, (
                f"{phase.value}_stop_loss: {current_pnl_pct:.1f}% "
                f"(threshold: -{stop_pct:.0f}%, held {hold_seconds:.0f}s)"
            )

        # --- TRAILING STOP CHECK (only if enabled for this phase) ---
        if self.is_trail_enabled(phase) and peak_pnl_pct > 0 and trail_pct > 0:
            drawdown_from_peak = peak_pnl_pct - current_pnl_pct
            if drawdown_from_peak >= trail_pct:
                return True, (
                    f"{phase.value}_trail: drawdown {drawdown_from_peak:.1f}% "
                    f"from peak +{peak_pnl_pct:.1f}% (trail: {trail_pct:.0f}%)"
                )

        # --- HOLDING ---
        return False, (
            f"{phase.value}_phase: holding "
            f"(pnl={current_pnl_pct:+.1f}%, peak={peak_pnl_pct:+.1f}%, "
            f"held {hold_seconds:.0f}s)"
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """Get or create the global risk manager instance."""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
