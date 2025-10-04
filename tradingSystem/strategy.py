from typing import Optional, Dict
from .config import (
	CORE_SIZE_USD, SCOUT_SIZE_USD, STRICT_SIZE_USD, NUANCED_SIZE_USD,
	MIN_LP_USD, RATIO_MIN, MCAP_MAX, MOMENTUM_1H_GATE,
	TRAIL_DEFAULT_PCT, TRAIL_TIGHT_PCT, TRAIL_WIDE_PCT,
	STRICT_MIN_LP_USD, STRICT_RATIO_MIN, STRICT_MCAP_MAX,
	NUANCED_MIN_LP_USD, NUANCED_RATIO_MIN, NUANCED_MCAP_MAX,
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
	"""High-velocity scout path (original nuanced logic)."""
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


def decide_strict(stats: Dict[str, float]) -> Optional[Dict]:
	"""High Confidence (Strict) - no smart money, but high conviction.
	
	Uses slightly relaxed gates vs runner, smaller size, tighter trails.
	"""
	liq = float(stats.get("liquidity_usd") or 0)
	ratio = float(stats.get("ratio") or 0)
	mcap = float(stats.get("market_cap_usd") or 0)
	ch1 = float(stats.get("change_1h") or 0)
	final_score = int(stats.get("final_score", 0))
	
	# Entry gates (slightly relaxed)
	if liq < STRICT_MIN_LP_USD:
		return None
	if ratio < STRICT_RATIO_MIN:
		return None
	if mcap > STRICT_MCAP_MAX and ch1 < MOMENTUM_1H_GATE:
		return None
	
	# Score-based sizing: higher scores get more allocation
	size = STRICT_SIZE_USD
	if final_score >= 8:
		size = STRICT_SIZE_USD * 1.5  # 150% for excellent signals
	elif final_score <= 5:
		size = STRICT_SIZE_USD * 0.75  # 75% for marginal signals
	
	# Dynamic trailing based on momentum
	trail = TRAIL_DEFAULT_PCT
	if ch1 >= 30.0 and ratio >= 0.6:
		trail = TRAIL_TIGHT_PCT  # Lock gains on hot movers
	elif ratio >= 0.8 and 0 <= ch1 <= 15.0:
		trail = TRAIL_WIDE_PCT  # Give room for consolidation
	
	return {
		"strategy": "strict",
		"usd_size": size,
		"trail_pct": trail,
	}


def decide_nuanced(stats: Dict[str, float]) -> Optional[Dict]:
	"""Nuanced Conviction - lower confidence, requires exceptional stats.
	
	Smallest position sizes, tightest stops, only for screaming momentum.
	"""
	liq = float(stats.get("liquidity_usd") or 0)
	ratio = float(stats.get("ratio") or 0)
	mcap = float(stats.get("market_cap_usd") or 0)
	ch1 = float(stats.get("change_1h") or 0)
	vel = float(stats.get("vel_score") or 0)
	unique = float(stats.get("unique_traders_15m") or 0)
	
	# Stricter gates for nuanced signals
	if liq < NUANCED_MIN_LP_USD:
		return None
	if ratio < NUANCED_RATIO_MIN:
		return None
	if mcap > NUANCED_MCAP_MAX:
		return None
	
	# Only take nuanced if velocity OR momentum is exceptional
	has_velocity = vel >= 9 and unique >= 30
	has_momentum = ch1 >= 35 and ratio >= 0.8
	
	if not (has_velocity or has_momentum):
		return None
	
	return {
		"strategy": "nuanced",
		"usd_size": NUANCED_SIZE_USD,
		"trail_pct": TRAIL_TIGHT_PCT,  # Always tight for risky plays
	}


