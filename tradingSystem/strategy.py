from typing import Optional, Dict
from .config import (
	CORE_SIZE_USD, SCOUT_SIZE_USD,
	MIN_LP_USD, RATIO_MIN, MCAP_MAX, MOMENTUM_1H_GATE,
	TRAIL_DEFAULT_PCT, TRAIL_TIGHT_PCT, TRAIL_WIDE_PCT,
)


def decide_runner(stats: Dict[str, float], is_smart: bool) -> Optional[Dict]:
	"""Strict + Smart path; returns a trade plan dict or None.

	Expected stats keys: liquidity_usd, vol24_usd, market_cap_usd, change_1h, ratio
	"""
	if not is_smart:
		return None
	liq = float(stats.get("liquidity_usd") or 0)
	ratio = float(stats.get("ratio") or 0)
	mcap = float(stats.get("market_cap_usd") or 0)
	ch1 = float(stats.get("change_1h") or 0)
	if liq < MIN_LP_USD:
		return None
	if ratio < RATIO_MIN:
		return None
	if not (mcap <= MCAP_MAX or ch1 >= MOMENTUM_1H_GATE):
		return None
	trail = TRAIL_DEFAULT_PCT
	if ch1 >= 35.0 and ratio >= 0.7:
		trail = TRAIL_TIGHT_PCT
	elif ratio >= 1.0 and -5.0 <= ch1 <= 10.0:
		trail = TRAIL_WIDE_PCT
	return {
		"strategy": "runner",
		"usd_size": CORE_SIZE_USD,
		"trail_pct": trail,
	}


def decide_scout(stats: Dict[str, float]) -> Optional[Dict]:
	"""Nuanced high-velocity path (no smart required)."""
	liq = float(stats.get("liquidity_usd") or 0)
	ratio = float(stats.get("ratio") or 0)
	mcap = float(stats.get("market_cap_usd") or 0)
	ch1 = float(stats.get("change_1h") or 0)
	vel = float(stats.get("vel_score") or 0)
	unique = float(stats.get("unique_traders_15m") or 0)
	if liq < MIN_LP_USD:
		return None
	# Velocity route
	if (vel >= 8 and unique >= 25 and ratio >= 0.8 and mcap <= 1_200_000) or (
		ch1 >= 25 and ratio >= 0.7 and mcap <= 1_000_000
	):
		return {
			"strategy": "scout",
			"usd_size": SCOUT_SIZE_USD,
			"trail_pct": TRAIL_TIGHT_PCT,
		}
	return None


