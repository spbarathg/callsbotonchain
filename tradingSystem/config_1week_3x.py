"""
1-WEEK 3X CHALLENGE CONFIG
For flipping $1,000 → $3,000 in 7 days

Key Differences from Conservative:
- Larger position sizes (8-15%)
- Higher deployment (60-70% vs 50%)
- More positions (6-8 vs 4-6)
- Relaxed daily loss limit (15% vs 10%)
- More aggressive Tier 1 exposure
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.risk_tiers import classify_signal_risk_tier, RiskTier


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ==================== WALLET & EXECUTION ====================
RPC_URL = os.getenv("TS_RPC_URL", "https://api.mainnet-beta.solana.com")
WALLET_SECRET = os.getenv("TS_WALLET_SECRET", "")
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 150)
PRIORITY_FEE_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MICROLAMPORTS", 10000)

USDC_MINT = os.getenv("TS_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
BASE_MINT = os.getenv("TS_BASE_MINT", USDC_MINT)

# ==================== AGGRESSIVE RISK MANAGEMENT ====================
BANKROLL_USD = _get_float("TS_BANKROLL_USD", 1000)

# AGGRESSIVE LIMITS - For 1 week challenge
MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 8)  # 6-8 positions
MIN_CONCURRENT = _get_int("TS_MIN_CONCURRENT", 6)

# More aggressive deployment
MAX_CAPITAL_DEPLOYED_PCT = _get_float("TS_MAX_CAPITAL_DEPLOYED_PCT", 70.0)  # Up to 70%!
MIN_CASH_RESERVE_PCT = _get_float("TS_MIN_CASH_RESERVE_PCT", 30.0)  # Minimum 30%

# AGGRESSIVE POSITION SIZING (by Risk Tier)

# Tier 1 (Moonshot): $10k-$50k MCap - INCREASED for moonshot hunting
TIER1_MIN_PCT = _get_float("TS_TIER1_MIN_PCT", 8.0)   # Min 8%
TIER1_MAX_PCT = _get_float("TS_TIER1_MAX_PCT", 12.0)  # Max 12%
TIER1_DEFAULT_PCT = _get_float("TS_TIER1_DEFAULT_PCT", 10.0)  # Default 10%

# Tier 2 (Aggressive): $50k-$150k MCap - INCREASED for reliability
TIER2_MIN_PCT = _get_float("TS_TIER2_MIN_PCT", 10.0)  # Min 10%
TIER2_MAX_PCT = _get_float("TS_TIER2_MAX_PCT", 15.0)  # Max 15%
TIER2_DEFAULT_PCT = _get_float("TS_TIER2_DEFAULT_PCT", 12.0)  # Default 12%

# Tier 3 (Calculated): $150k-$500k MCap - SLIGHTLY increased
TIER3_MIN_PCT = _get_float("TS_TIER3_MIN_PCT", 6.0)   # Min 6%
TIER3_MAX_PCT = _get_float("TS_TIER3_MAX_PCT", 10.0)  # Max 10%
TIER3_DEFAULT_PCT = _get_float("TS_TIER3_DEFAULT_PCT", 8.0)  # Default 8%

# Absolute maximum per position
MAX_POSITION_SIZE_PCT = _get_float("TS_MAX_POSITION_SIZE_PCT", 15.0)  # Max 15% (vs 12% conservative)

# ==================== STOP LOSSES ====================
# Same as conservative - don't relax stop losses
TIER1_STOP_LOSS_PCT = _get_float("TS_TIER1_STOP_LOSS_PCT", 70.0)
TIER2_STOP_LOSS_PCT = _get_float("TS_TIER2_STOP_LOSS_PCT", 50.0)
TIER3_STOP_LOSS_PCT = _get_float("TS_TIER3_STOP_LOSS_PCT", 40.0)

# ==================== TRAILING STOPS ====================
# Same as conservative
TIER1_TRAIL_PCT = _get_float("TS_TIER1_TRAIL_PCT", 50.0)
TIER2_TRAIL_PCT = _get_float("TS_TIER2_TRAIL_PCT", 35.0)
TIER3_TRAIL_PCT = _get_float("TS_TIER3_TRAIL_PCT", 25.0)

# ==================== CIRCUIT BREAKERS (RELAXED) ====================
# Daily loss limit - RELAXED for aggressive trading
MAX_DAILY_LOSS_PCT = _get_float("TS_MAX_DAILY_LOSS_PCT", 15.0)  # -15% (vs -10%)
MAX_DAILY_LOSS_USD = BANKROLL_USD * (MAX_DAILY_LOSS_PCT / 100.0)

# Weekly loss limit - RELAXED
MAX_WEEKLY_LOSS_PCT = _get_float("TS_MAX_WEEKLY_LOSS_PCT", 30.0)  # -30% (vs -20%)
MAX_WEEKLY_LOSS_USD = BANKROLL_USD * (MAX_WEEKLY_LOSS_PCT / 100.0)

# Consecutive losses - RELAXED
MAX_CONSECUTIVE_LOSSES = _get_int("TS_MAX_CONSECUTIVE_LOSSES", 5)  # 5 losses (vs 3)

# Recovery mode - LESS aggressive reduction
RECOVERY_MODE_POSITION_REDUCTION_PCT = _get_float("TS_RECOVERY_POSITION_REDUCTION_PCT", 30.0)  # 30% (vs 50%)

# ==================== ENTRY FILTERS ====================
MIN_LIQUIDITY_USD = _get_float("TS_MIN_LIQUIDITY_USD", 0)
MIN_VOLUME_24H_USD = _get_float("TS_MIN_VOLUME_24H_USD", 10000)

# ==================== PATHS ====================
DB_PATH = os.getenv("TS_DB_PATH", "var/trading_1week_3x.db")
LOG_JSON_PATH = os.getenv("TS_LOG_JSON", "data/logs/trading_1week_3x.jsonl")
LOG_TEXT_PATH = os.getenv("TS_LOG_TEXT", "data/logs/trading_1week_3x.log")

# ==================== MODE ====================
DRY_RUN = _get_bool("TS_DRY_RUN", True)


# ==================== HELPER FUNCTIONS ====================
def get_position_size_aggressive(signal_data: dict, current_capital: float, 
                                 deployed_capital: float, day_num: int = 1) -> tuple[float, RiskTier, str]:
    """
    Calculate AGGRESSIVE position size for 1-week 3x challenge.
    
    Day 1-3: More aggressive (hunt for moonshots)
    Day 4-7: Scale based on progress toward goal
    """
    deployed_pct = (deployed_capital / current_capital) * 100 if current_capital > 0 else 100
    available_deployment_pct = MAX_CAPITAL_DEPLOYED_PCT - deployed_pct
    
    if available_deployment_pct <= 0:
        return 0.0, None, f"Max deployment reached ({deployed_pct:.1f}%, limit: {MAX_CAPITAL_DEPLOYED_PCT}%)"
    
    # Classify signal risk tier
    tier, tier_explanation = classify_signal_risk_tier(
        mcap=signal_data.get('first_market_cap_usd', signal_data.get('market_cap_usd', 0)),
        liquidity=signal_data.get('first_liquidity_usd', signal_data.get('liquidity_usd', 0)),
        score=signal_data.get('final_score', signal_data.get('score', 0)),
        volume_24h=signal_data.get('volume_24h_usd', 0),
        conviction_type=signal_data.get('conviction_type', 'High Confidence')
    )
    
    if tier is None:
        return 0.0, None, "Signal does not meet risk tier criteria"
    
    # Base position size by tier
    score = signal_data.get('final_score', signal_data.get('score', 8))
    
    if tier.tier_name == "MOONSHOT":
        # AGGRESSIVE on Tier 1 - need moonshots!
        if score >= 9:
            base_pct = TIER1_MAX_PCT  # 12%
        elif score >= 8:
            base_pct = TIER1_DEFAULT_PCT  # 10%
        else:
            base_pct = TIER1_MIN_PCT  # 8%
        
        # Days 1-3: Full aggression on Tier 1
        if day_num <= 3:
            base_pct = min(base_pct * 1.1, TIER1_MAX_PCT)  # 10% boost
    
    elif tier.tier_name == "AGGRESSIVE":
        # Core strategy - reliable gains
        if score >= 9:
            base_pct = TIER2_MAX_PCT  # 15%
        elif score >= 8:
            base_pct = TIER2_DEFAULT_PCT  # 12%
        else:
            base_pct = TIER2_MIN_PCT  # 10%
    
    else:  # CALCULATED
        # Quick flips
        if score >= 9:
            base_pct = TIER3_MAX_PCT  # 10%
        elif score >= 8:
            base_pct = TIER3_DEFAULT_PCT  # 8%
        else:
            base_pct = TIER3_MIN_PCT  # 6%
    
    # Calculate USD size
    position_size = current_capital * (base_pct / 100.0)
    
    # Cap at absolute maximum
    max_size = current_capital * (MAX_POSITION_SIZE_PCT / 100.0)
    position_size = min(position_size, max_size)
    
    # Cap at available deployment
    max_available = current_capital * (available_deployment_pct / 100.0)
    position_size = min(position_size, max_available)
    
    # Minimum size check
    if position_size < 20:
        return 0.0, tier, f"Position too small (${position_size:.2f} < $20 minimum)"
    
    explanation = (
        f"Tier: {tier.tier_name}, "
        f"Size: {base_pct:.1f}% (${position_size:.2f}), "
        f"Deployed: {deployed_pct:.1f}%, "
        f"Reserve: {100-deployed_pct:.1f}%"
    )
    
    return position_size, tier, explanation


def get_stop_loss_for_tier(tier: RiskTier) -> float:
    """Get stop loss percentage for risk tier"""
    if tier.tier_name == "MOONSHOT":
        return TIER1_STOP_LOSS_PCT
    elif tier.tier_name == "AGGRESSIVE":
        return TIER2_STOP_LOSS_PCT
    else:
        return TIER3_STOP_LOSS_PCT


def get_trailing_stop_for_tier(tier: RiskTier) -> float:
    """Get trailing stop percentage for risk tier"""
    if tier.tier_name == "MOONSHOT":
        return TIER1_TRAIL_PCT
    elif tier.tier_name == "AGGRESSIVE":
        return TIER2_TRAIL_PCT
    else:
        return TIER3_TRAIL_PCT


def get_profit_target_for_tier(tier: RiskTier) -> float:
    """Get minimum profit target multiplier for tier"""
    return tier.take_profit_min_multiplier


def check_can_trade(daily_pnl: float, weekly_pnl: float, consecutive_losses: int) -> tuple[bool, str]:
    """Check if trading is allowed based on loss limits"""
    if daily_pnl <= -MAX_DAILY_LOSS_USD:
        return False, f"Daily loss limit hit: ${abs(daily_pnl):.2f} / ${MAX_DAILY_LOSS_USD:.2f}"
    
    if weekly_pnl <= -MAX_WEEKLY_LOSS_USD:
        return False, f"Weekly loss limit hit: ${abs(weekly_pnl):.2f} / ${MAX_WEEKLY_LOSS_USD:.2f}"
    
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return False, f"Consecutive losses limit: {consecutive_losses} / {MAX_CONSECUTIVE_LOSSES}"
    
    return True, ""


def should_scale_back(current_capital: float, starting_capital: float) -> tuple[bool, str]:
    """
    Check if should scale back risk after hitting goal.
    If capital >= 2.5x starting, recommend scaling back.
    """
    multiplier = current_capital / starting_capital
    
    if multiplier >= 3.0:
        return True, f"🎉 GOAL HIT! ({multiplier:.1f}x) - LOCK IN GAINS, reduce risk!"
    elif multiplier >= 2.5:
        return True, f"⚠️  Close to goal ({multiplier:.1f}x) - Consider scaling back risk"
    
    return False, ""


# ==================== CONFIGURATION SUMMARY ====================
AGGRESSIVE_CONFIG_SUMMARY = f"""
╔═══════════════════════════════════════════════════════════════╗
║         1-WEEK 3X CHALLENGE CONFIG (AGGRESSIVE!)              ║
║              $1,000 → $3,000 in 7 Days                        ║
╚═══════════════════════════════════════════════════════════════╝

Starting Bankroll: ${BANKROLL_USD:,.2f}
Goal: ${BANKROLL_USD * 3:,.2f} (3x in 1 week)

POSITION SIZING (AGGRESSIVE!):
├─ TIER 1 (Moonshot):   {TIER1_MIN_PCT}%-{TIER1_MAX_PCT}% (default {TIER1_DEFAULT_PCT}%)
├─ TIER 2 (Aggressive): {TIER2_MIN_PCT}%-{TIER2_MAX_PCT}% (default {TIER2_DEFAULT_PCT}%)
├─ TIER 3 (Calculated): {TIER3_MIN_PCT}%-{TIER3_MAX_PCT}% (default {TIER3_DEFAULT_PCT}%)
└─ ABSOLUTE MAX:        {MAX_POSITION_SIZE_PCT}% per position

PORTFOLIO LIMITS (RELAXED):
├─ Max Positions:       {MAX_CONCURRENT} simultaneous
├─ Max Deployed:        {MAX_CAPITAL_DEPLOYED_PCT}% of capital
└─ Min Cash Reserve:    {MIN_CASH_RESERVE_PCT}% minimum

STOP LOSSES (from entry):
├─ TIER 1:  -{TIER1_STOP_LOSS_PCT}% (wide)
├─ TIER 2:  -{TIER2_STOP_LOSS_PCT}% (medium)
└─ TIER 3:  -{TIER3_STOP_LOSS_PCT}% (tight)

TRAILING STOPS (from peak):
├─ TIER 1:  -{TIER1_TRAIL_PCT}% (let moonshots run!)
├─ TIER 2:  -{TIER2_TRAIL_PCT}% (standard)
└─ TIER 3:  -{TIER3_TRAIL_PCT}% (lock profits fast)

CIRCUIT BREAKERS (RELAXED):
├─ Daily Loss Limit:    -{MAX_DAILY_LOSS_PCT}% (${MAX_DAILY_LOSS_USD:.2f})
├─ Weekly Loss Limit:   -{MAX_WEEKLY_LOSS_PCT}% (${MAX_WEEKLY_LOSS_USD:.2f})
└─ Consecutive Losses:  {MAX_CONSECUTIVE_LOSSES} trades

RECOVERY MODE:
└─ After hitting limits: Reduce position sizes by {RECOVERY_MODE_POSITION_REDUCTION_PCT}%

═══════════════════════════════════════════════════════════════
Example: Starting with $1,000 (Day 1)
- TIER 1 position: $100 (10%) - Hunt for 20x moonshot!
- TIER 2 position: $120 (12%) - Reliable 5x gains
- TIER 3 position: $80 (8%)   - Quick 2-3x flips
- Max deployed: $700 (70%)
- Cash reserve: $300 (30%)

After 2x ($2,000 capital):
- TIER 1: $200, TIER 2: $240, TIER 3: $160
Your positions DOUBLE in size! (compounding)

After 3x ($3,000 capital):
- SCALE BACK! Reduce to conservative mode
- Lock in your gains!
═══════════════════════════════════════════════════════════════

⚠️  WARNING: This is AGGRESSIVE! Only for 1-week challenge.
    After hitting 3x, switch to conservative config!
"""

def print_config_summary():
    """Print configuration summary"""
    print(AGGRESSIVE_CONFIG_SUMMARY)


if __name__ == "__main__":
    print_config_summary()




