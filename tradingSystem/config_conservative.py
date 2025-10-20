"""
CONSERVATIVE CAPITAL MANAGEMENT CONFIG
Implements the CAPITAL_MANAGEMENT_STRATEGY.md approach

Key Principles:
- SMALL position sizes (5-12% max)
- 50% cash reserve ALWAYS
- Daily/Weekly loss limits (10%/20%)
- Max 4-6 positions
- Risk-tier based sizing
"""
import os
import sys

# Add parent directory to path to import app modules
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
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 150)  # 1.50%
PRIORITY_FEE_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MICROLAMPORTS", 10000)

# Base asset
USDC_MINT = os.getenv("TS_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
BASE_MINT = os.getenv("TS_BASE_MINT", USDC_MINT)

# ==================== CONSERVATIVE RISK MANAGEMENT ====================
# Starting capital (adjustable)
BANKROLL_USD = _get_float("TS_BANKROLL_USD", 1000)

# STRICT LIMITS - Capital Preservation First!
MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 6)  # Max 4-6 positions
MIN_CONCURRENT = _get_int("TS_MIN_CONCURRENT", 4)  # Aim for 4-6 range

# Maximum deployment (CONSERVATIVE!)
MAX_CAPITAL_DEPLOYED_PCT = _get_float("TS_MAX_CAPITAL_DEPLOYED_PCT", 50.0)  # Never exceed 50%!
MIN_CASH_RESERVE_PCT = _get_float("TS_MIN_CASH_RESERVE_PCT", 50.0)  # Always keep 50%

# CONSERVATIVE POSITION SIZING (by Risk Tier)
# These are MAXIMUM percentages - actual size will be calculated per signal

# Tier 1 (Moonshot): $10k-$50k MCap
TIER1_MIN_PCT = _get_float("TS_TIER1_MIN_PCT", 5.0)  # Min 5%
TIER1_MAX_PCT = _get_float("TS_TIER1_MAX_PCT", 8.0)  # Max 8%
TIER1_DEFAULT_PCT = _get_float("TS_TIER1_DEFAULT_PCT", 7.0)  # Default 7%

# Tier 2 (Aggressive): $50k-$150k MCap
TIER2_MIN_PCT = _get_float("TS_TIER2_MIN_PCT", 8.0)  # Min 8%
TIER2_MAX_PCT = _get_float("TS_TIER2_MAX_PCT", 12.0)  # Max 12%
TIER2_DEFAULT_PCT = _get_float("TS_TIER2_DEFAULT_PCT", 10.0)  # Default 10%

# Tier 3 (Calculated): $150k-$500k MCap
TIER3_MIN_PCT = _get_float("TS_TIER3_MIN_PCT", 5.0)  # Min 5%
TIER3_MAX_PCT = _get_float("TS_TIER3_MAX_PCT", 8.0)  # Max 8%
TIER3_DEFAULT_PCT = _get_float("TS_TIER3_DEFAULT_PCT", 6.0)  # Default 6%

# Absolute maximum per position (safety ceiling)
MAX_POSITION_SIZE_PCT = _get_float("TS_MAX_POSITION_SIZE_PCT", 12.0)  # NEVER exceed 12%!

# ==================== STOP LOSSES (by Risk Tier) ====================
# From ENTRY price (not peak)
TIER1_STOP_LOSS_PCT = _get_float("TS_TIER1_STOP_LOSS_PCT", 70.0)  # -70% for moonshots
TIER2_STOP_LOSS_PCT = _get_float("TS_TIER2_STOP_LOSS_PCT", 50.0)  # -50% for aggressive
TIER3_STOP_LOSS_PCT = _get_float("TS_TIER3_STOP_LOSS_PCT", 40.0)  # -40% for calculated

# ==================== TRAILING STOPS (by Risk Tier) ====================
# From PEAK price
TIER1_TRAIL_PCT = _get_float("TS_TIER1_TRAIL_PCT", 50.0)  # Wide for moonshots
TIER2_TRAIL_PCT = _get_float("TS_TIER2_TRAIL_PCT", 35.0)  # Medium
TIER3_TRAIL_PCT = _get_float("TS_TIER3_TRAIL_PCT", 25.0)  # Tighter for quick flips

# ==================== CIRCUIT BREAKERS (STRICT!) ====================
# Daily loss limit
MAX_DAILY_LOSS_PCT = _get_float("TS_MAX_DAILY_LOSS_PCT", 10.0)  # Stop trading at -10% day!
MAX_DAILY_LOSS_USD = BANKROLL_USD * (MAX_DAILY_LOSS_PCT / 100.0)

# Weekly loss limit
MAX_WEEKLY_LOSS_PCT = _get_float("TS_MAX_WEEKLY_LOSS_PCT", 20.0)  # Stop trading at -20% week!
MAX_WEEKLY_LOSS_USD = BANKROLL_USD * (MAX_WEEKLY_LOSS_PCT / 100.0)

# Consecutive losses
MAX_CONSECUTIVE_LOSSES = _get_int("TS_MAX_CONSECUTIVE_LOSSES", 3)  # Stop after 3 losses!

# Recovery mode (after hitting limits)
RECOVERY_MODE_POSITION_REDUCTION_PCT = _get_float("TS_RECOVERY_POSITION_REDUCTION_PCT", 50.0)  # Cut positions by 50%

# ==================== ENTRY FILTERS ====================
MIN_LIQUIDITY_USD = _get_float("TS_MIN_LIQUIDITY_USD", 0)  # No minimum (moonshot optimized)
MIN_VOLUME_24H_USD = _get_float("TS_MIN_VOLUME_24H_USD", 10000)  # Activity check

# ==================== PATHS ====================
DB_PATH = os.getenv("TS_DB_PATH", "var/trading_conservative.db")
LOG_JSON_PATH = os.getenv("TS_LOG_JSON", "data/logs/trading_conservative.jsonl")
LOG_TEXT_PATH = os.getenv("TS_LOG_TEXT", "data/logs/trading_conservative.log")

# ==================== MODE ====================
DRY_RUN = _get_bool("TS_DRY_RUN", True)  # Default to paper trading for safety!


# ==================== HELPER FUNCTIONS ====================
def get_position_size_conservative(signal_data: dict, current_capital: float, 
                                   deployed_capital: float) -> tuple[float, RiskTier, str]:
    """
    Calculate CONSERVATIVE position size based on risk tier classification.
    
    Returns: (position_size_usd, risk_tier, explanation)
    """
    # Check if we have room for new position
    deployed_pct = (deployed_capital / current_capital) * 100 if current_capital > 0 else 100
    available_deployment_pct = MAX_CAPITAL_DEPLOYED_PCT - deployed_pct
    
    if available_deployment_pct <= 0:
        return 0.0, None, f"Max deployment reached ({deployed_pct:.1f}% deployed, limit: {MAX_CAPITAL_DEPLOYED_PCT}%)"
    
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
    
    # Get position size percentage based on tier
    if tier.tier_name == "MOONSHOT":
        base_pct = TIER1_DEFAULT_PCT
        # Scale based on score (higher score = slightly larger position within range)
        score = signal_data.get('final_score', signal_data.get('score', 8))
        if score >= 9:
            base_pct = TIER1_MAX_PCT
        elif score <= 7:
            base_pct = TIER1_MIN_PCT
    elif tier.tier_name == "AGGRESSIVE":
        base_pct = TIER2_DEFAULT_PCT
        score = signal_data.get('final_score', signal_data.get('score', 8))
        if score >= 9:
            base_pct = TIER2_MAX_PCT
        elif score <= 7:
            base_pct = TIER2_MIN_PCT
    else:  # CALCULATED
        base_pct = TIER3_DEFAULT_PCT
        score = signal_data.get('final_score', signal_data.get('score', 8))
        if score >= 9:
            base_pct = TIER3_MAX_PCT
        elif score <= 7:
            base_pct = TIER3_MIN_PCT
    
    # Calculate USD size
    position_size = current_capital * (base_pct / 100.0)
    
    # Cap at absolute maximum
    max_size = current_capital * (MAX_POSITION_SIZE_PCT / 100.0)
    position_size = min(position_size, max_size)
    
    # Cap at available deployment room
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
    else:  # CALCULATED
        return TIER3_STOP_LOSS_PCT


def get_trailing_stop_for_tier(tier: RiskTier) -> float:
    """Get trailing stop percentage for risk tier"""
    if tier.tier_name == "MOONSHOT":
        return TIER1_TRAIL_PCT
    elif tier.tier_name == "AGGRESSIVE":
        return TIER2_TRAIL_PCT
    else:  # CALCULATED
        return TIER3_TRAIL_PCT


def get_profit_target_for_tier(tier: RiskTier) -> float:
    """Get minimum profit target multiplier for tier"""
    return tier.take_profit_min_multiplier


def check_can_trade(daily_pnl: float, weekly_pnl: float, consecutive_losses: int) -> tuple[bool, str]:
    """
    Check if trading is allowed based on loss limits.
    
    Returns: (can_trade, reason)
    """
    # Check daily loss limit
    if daily_pnl <= -MAX_DAILY_LOSS_USD:
        return False, f"Daily loss limit hit: ${abs(daily_pnl):.2f} / ${MAX_DAILY_LOSS_USD:.2f}"
    
    # Check weekly loss limit
    if weekly_pnl <= -MAX_WEEKLY_LOSS_USD:
        return False, f"Weekly loss limit hit: ${abs(weekly_pnl):.2f} / ${MAX_WEEKLY_LOSS_USD:.2f}"
    
    # Check consecutive losses
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return False, f"Consecutive losses limit: {consecutive_losses} / {MAX_CONSECUTIVE_LOSSES}"
    
    return True, ""


# ==================== CONFIGURATION SUMMARY ====================
CONSERVATIVE_CONFIG_SUMMARY = f"""
╔═══════════════════════════════════════════════════════════════╗
║         CONSERVATIVE CAPITAL MANAGEMENT CONFIG                ║
║              Capital Preservation First!                      ║
╚═══════════════════════════════════════════════════════════════╝

Starting Bankroll: ${BANKROLL_USD:,.2f}

POSITION SIZING:
├─ TIER 1 (Moonshot):   {TIER1_MIN_PCT}%-{TIER1_MAX_PCT}% (default {TIER1_DEFAULT_PCT}%)
├─ TIER 2 (Aggressive): {TIER2_MIN_PCT}%-{TIER2_MAX_PCT}% (default {TIER2_DEFAULT_PCT}%)
├─ TIER 3 (Calculated): {TIER3_MIN_PCT}%-{TIER3_MAX_PCT}% (default {TIER3_DEFAULT_PCT}%)
└─ ABSOLUTE MAX:        {MAX_POSITION_SIZE_PCT}% per position

PORTFOLIO LIMITS:
├─ Max Positions:       {MAX_CONCURRENT} simultaneous
├─ Max Deployed:        {MAX_CAPITAL_DEPLOYED_PCT}% of capital
└─ Min Cash Reserve:    {MIN_CASH_RESERVE_PCT}% always

STOP LOSSES (from entry):
├─ TIER 1:  -{TIER1_STOP_LOSS_PCT}% (wide, for moonshots)
├─ TIER 2:  -{TIER2_STOP_LOSS_PCT}% (medium)
└─ TIER 3:  -{TIER3_STOP_LOSS_PCT}% (tight)

TRAILING STOPS (from peak):
├─ TIER 1:  -{TIER1_TRAIL_PCT}% (let moonshots run)
├─ TIER 2:  -{TIER2_TRAIL_PCT}% (standard)
└─ TIER 3:  -{TIER3_TRAIL_PCT}% (lock profits fast)

CIRCUIT BREAKERS:
├─ Daily Loss Limit:    -{MAX_DAILY_LOSS_PCT}% (${MAX_DAILY_LOSS_USD:.2f})
├─ Weekly Loss Limit:   -{MAX_WEEKLY_LOSS_PCT}% (${MAX_WEEKLY_LOSS_USD:.2f})
└─ Consecutive Losses:  {MAX_CONSECUTIVE_LOSSES} trades

RECOVERY MODE:
└─ After hitting limits: Reduce position sizes by {RECOVERY_MODE_POSITION_REDUCTION_PCT}%

═══════════════════════════════════════════════════════════════
Example: Starting with $1,000
- TIER 1 position: $70 (7%)
- TIER 2 position: $100 (10%)
- TIER 3 position: $60 (6%)
- Max deployed: $500 (50%)
- Cash reserve: $500 (50%)
═══════════════════════════════════════════════════════════════
"""

def print_config_summary():
    """Print configuration summary"""
    print(CONSERVATIVE_CONFIG_SUMMARY)


if __name__ == "__main__":
    print_config_summary()




