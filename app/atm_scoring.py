"""
ATM Signal Scoring - Pre-filter signals using ATM metadata before queuing.

Evaluates ATM metadata (market cap, holders, liquidity, volume, audit flags)
to produce a score that determines whether a signal should be traded.
"""
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ScoreBreakdown:
    """Detailed scoring breakdown for debugging/logging."""
    mcap_score: float = 0.0
    holders_score: float = 0.0
    liquidity_score: float = 0.0
    volume_score: float = 0.0
    audit_score: float = 0.0
    total: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "mcap_score": self.mcap_score,
            "holders_score": self.holders_score,
            "liquidity_score": self.liquidity_score,
            "volume_score": self.volume_score,
            "audit_score": self.audit_score,
            "total": self.total,
        }


def should_buy_atm_signal(
    atm_meta: Dict[str, Any],
    min_score: float = 3.0,
) -> Tuple[bool, str, Optional[ScoreBreakdown]]:
    """Evaluate ATM metadata and decide whether to buy.

    Args:
        atm_meta: Parsed ATM metadata dict from atm_listener.
        min_score: Minimum score threshold to pass.

    Returns:
        (should_buy, reject_reason, breakdown)
    """
    if not atm_meta:
        return True, "", ScoreBreakdown(total=min_score)

    breakdown = ScoreBreakdown()

    # Market cap scoring
    mcap = atm_meta.get("market_cap_usd", 0) or 0
    if mcap >= 100_000:
        breakdown.mcap_score = 2.0
    elif mcap >= 30_000:
        breakdown.mcap_score = 1.0
    elif mcap > 0 and mcap < 5_000:
        breakdown.mcap_score = -1.0

    # Holder count scoring
    holders = atm_meta.get("holder_count", 0) or 0
    if holders >= 200:
        breakdown.holders_score = 2.0
    elif holders >= 50:
        breakdown.holders_score = 1.0
    elif holders > 0 and holders < 10:
        breakdown.holders_score = -1.0

    # Liquidity scoring
    liq = atm_meta.get("liquidity_usd", 0) or 0
    if liq >= 50_000:
        breakdown.liquidity_score = 2.0
    elif liq >= 15_000:
        breakdown.liquidity_score = 1.0
    elif liq > 0 and liq < 5_000:
        breakdown.liquidity_score = -2.0

    # Volume scoring (5m buy volume)
    vol_buy = atm_meta.get("volume_buy", {})
    vol_5m = vol_buy.get("5m", 0) if isinstance(vol_buy, dict) else 0
    if vol_5m >= 5_000:
        breakdown.volume_score = 1.0
    elif vol_5m >= 1_000:
        breakdown.volume_score = 0.5

    # Audit flags scoring
    audit = atm_meta.get("audit", {})
    if isinstance(audit, dict):
        if audit.get("not_mintable"):
            breakdown.audit_score += 0.5
        if audit.get("not_freezable"):
            breakdown.audit_score += 0.5

    breakdown.total = (
        breakdown.mcap_score
        + breakdown.holders_score
        + breakdown.liquidity_score
        + breakdown.volume_score
        + breakdown.audit_score
    )

    if breakdown.total < min_score:
        return False, f"ATM score {breakdown.total:.1f} < {min_score}", breakdown

    return True, "", breakdown


def get_atm_score_summary(atm_meta: Dict[str, Any]) -> str:
    """Return a one-line human-readable summary of ATM metadata."""
    if not atm_meta:
        return "no ATM data"

    parts = []
    mcap = atm_meta.get("market_cap_usd")
    if mcap:
        parts.append(f"MC=${mcap:,.0f}")
    holders = atm_meta.get("holder_count")
    if holders:
        parts.append(f"Holders={holders}")
    liq = atm_meta.get("liquidity_usd")
    if liq:
        parts.append(f"Liq=${liq:,.0f}")
    top10 = atm_meta.get("top10_percent")
    if top10:
        parts.append(f"Top10={top10:.1f}%")

    return " | ".join(parts) if parts else "partial ATM data"
