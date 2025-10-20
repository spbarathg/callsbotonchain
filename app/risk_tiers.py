"""
Risk Tier Classification for Moonshot-Optimized Trading

Based on analysis of real 779x moonshot and all historical 10x+ gains.
Uses smart position sizing instead of hard filters to maximize returns.
"""
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class RiskTier:
    """Risk tier classification for a signal"""
    tier_name: str
    tier_level: int  # 1=highest risk/reward, 2=balanced, 3=conservative
    position_size_pct: float  # Recommended position size as % of capital
    stop_loss_pct: float  # Stop loss as % from entry
    take_profit_min_multiplier: float  # Minimum multiplier before taking profit
    rationale: str  # Human-readable explanation


# Tier definitions
TIER_1_MOONSHOT = RiskTier(
    tier_name="MOONSHOT",
    tier_level=1,
    position_size_pct=15.0,  # 15% of capital
    stop_loss_pct=70.0,  # Accept -70% loss for moonshot potential
    take_profit_min_multiplier=5.0,  # Never exit before 5x
    rationale="MICRO CAP GEM - Ultra high risk, 300x-1000x potential. Lottery ticket strategy."
)

TIER_2_AGGRESSIVE = RiskTier(
    tier_name="AGGRESSIVE",
    tier_level=2,
    position_size_pct=20.0,  # 20% of capital
    stop_loss_pct=50.0,  # Standard -50% stop
    take_profit_min_multiplier=2.0,  # Can exit at 2x but aim higher
    rationale="SWEET SPOT - High confidence with proven track record. Main growth engine."
)

TIER_3_CALCULATED = RiskTier(
    tier_name="CALCULATED",
    tier_level=3,
    position_size_pct=10.0,  # 10% of capital
    stop_loss_pct=40.0,  # Tighter stop
    take_profit_min_multiplier=2.0,  # Take profit at 2x-5x
    rationale="SAFER PLAY - Established token with room to grow. Risk management."
)


def classify_signal_risk_tier(
    mcap: Optional[float] = None,
    liquidity: Optional[float] = None,
    score: Optional[int] = None,
    volume_24h: Optional[float] = None,
    conviction_type: str = "High Confidence",
    smart_money_detected: bool = False,
    # Legacy parameter names for backwards compatibility
    market_cap_usd: Optional[float] = None,
    liquidity_usd: Optional[float] = None,
    volume_24h_usd: Optional[float] = None,
) -> Tuple[Optional[RiskTier], str]:
    """
    Classify a signal into a risk tier for position sizing.
    
    Args:
        mcap: Market cap in USD (can be None) - preferred name
        liquidity: Liquidity in USD (can be None) - preferred name
        score: Final score (1-10)
        volume_24h: 24h volume in USD (can be None) - preferred name
        conviction_type: Conviction type from analyzer
        smart_money_detected: Whether smart money was detected
        market_cap_usd: Legacy parameter (use mcap instead)
        liquidity_usd: Legacy parameter (use liquidity instead)
        volume_24h_usd: Legacy parameter (use volume_24h instead)
    
    Returns:
        Tuple of (RiskTier or None, reasoning string)
        Returns (None, reason) if signal should be skipped
    """
    
    # Handle legacy parameter names
    if mcap is None and market_cap_usd is not None:
        mcap = market_cap_usd
    if liquidity is None and liquidity_usd is not None:
        liquidity = liquidity_usd
    if volume_24h is None and volume_24h_usd is not None:
        volume_24h = volume_24h_usd
    
    # Ensure score has a default
    if score is None:
        score = 0
    
    # Basic validation
    if score < 7:
        return None, f"Score {score} below minimum (7)"
    
    # Reject obvious bad signals
    if mcap is not None:
        if mcap < 5000:
            return None, f"MCap ${mcap:,.0f} too low (likely scam)"
        if mcap > 1000000:  # $1M+ is too established
            return None, f"MCap ${mcap:,.0f} too high (limited upside)"
    
    if volume_24h is not None and volume_24h < 5000:
        return None, f"Volume ${volume_24h:,.0f} too low (no activity)"
    
    # Get values (default to 0 if None to allow missing data)
    mcap_val = mcap if mcap is not None else 0
    liq_val = liquidity if liquidity is not None else 0
    
    # ============================================================================
    # TIER 1: MOONSHOT HUNTING (Micro Caps $10k-$50k)
    # ============================================================================
    # Highest risk, highest reward
    # These are the 779x opportunities!
    
    if score >= 8:
        # Check for micro cap characteristics
        is_micro_cap = (10000 <= mcap_val <= 50000) if mcap_val > 0 else False
        
        # High conviction + micro cap = MOONSHOT TIER
        if is_micro_cap and ("High Confidence" in conviction_type or smart_money_detected):
            return TIER_1_MOONSHOT, (
                f"TIER 1: Micro cap ${mcap_val:,.0f} with score {score}/10 and {conviction_type}. "
                f"This is a lottery ticket - small position, huge potential. 15% position, hold for 5x-100x+."
            )
        
        # Also consider micro caps with missing liq data but high score
        if mcap_val == 0 and liq_val == 0 and score >= 9 and "High Confidence" in conviction_type:
            return TIER_1_MOONSHOT, (
                f"TIER 1: Missing MCap/Liq data but score {score}/10 with {conviction_type}. "
                f"Could be early moonshot (like the 779x signal!). 15% position, high risk/reward."
            )
    
    # ============================================================================
    # TIER 2: AGGRESSIVE (Sweet Spot $50k-$150k)
    # ============================================================================
    # Proven range with best historical performance
    # This is the main growth engine
    
    if score >= 8:
        # Sweet spot characteristics
        is_sweet_spot = (50000 <= mcap_val <= 150000) if mcap_val > 0 else False
        has_good_liq = (liq_val >= 25000) if liq_val > 0 else False
        
        # Sweet spot with good metrics = AGGRESSIVE TIER
        if is_sweet_spot or has_good_liq or (mcap_val == 0 and score >= 9):
            return TIER_2_AGGRESSIVE, (
                f"TIER 2: Sweet spot MCap ${mcap_val:,.0f} with score {score}/10. "
                f"Proven range with consistent performance. 20% position, aim for 2x-20x."
            )
        
        # Also include slightly below sweet spot if high conviction
        if (25000 <= mcap_val < 50000) and "High Confidence" in conviction_type:
            return TIER_2_AGGRESSIVE, (
                f"TIER 2: Near-micro cap ${mcap_val:,.0f} with high conviction. "
                f"Bridge between moonshot and sweet spot. 20% position."
            )
    
    # ============================================================================
    # TIER 3: CALCULATED (Established $150k-$500k)
    # ============================================================================
    # Lower risk, lower reward
    # Safety plays for portfolio stability
    
    if score >= 7:
        # Established but still room to grow
        is_established = (150000 <= mcap_val <= 500000) if mcap_val > 0 else False
        has_excellent_liq = (liq_val >= 50000) if liq_val > 0 else False
        
        if is_established and (has_excellent_liq or liq_val == 0):
            return TIER_3_CALCULATED, (
                f"TIER 3: Established MCap ${mcap_val:,.0f} with score {score}/10. "
                f"Safer play with 2x-5x potential. 10% position, tighter stop."
            )
    
    # ============================================================================
    # SKIP: Doesn't fit any tier
    # ============================================================================
    
    # If we get here, signal doesn't fit any tier
    if mcap_val > 0:
        return None, f"MCap ${mcap_val:,.0f} outside optimal ranges or insufficient conviction"
    else:
        return None, f"Insufficient data to classify (score {score}, conviction: {conviction_type})"


def get_position_recommendation(
    tier: RiskTier,
    capital_available: float,
    current_price: float
) -> Dict[str, float]:
    """
    Calculate recommended position details.
    
    Args:
        tier: RiskTier classification
        capital_available: Total capital available for trading
        current_price: Current price per token
    
    Returns:
        Dict with position details
    """
    position_usd = capital_available * (tier.position_size_pct / 100)
    stop_loss_price = current_price * (1 - tier.stop_loss_pct / 100)
    take_profit_min_price = current_price * tier.take_profit_min_multiplier
    
    return {
        "position_size_usd": position_usd,
        "position_size_pct": tier.position_size_pct,
        "quantity": position_usd / current_price if current_price > 0 else 0,
        "entry_price": current_price,
        "stop_loss_price": stop_loss_price,
        "stop_loss_pct": tier.stop_loss_pct,
        "take_profit_min_price": take_profit_min_price,
        "take_profit_min_multiplier": tier.take_profit_min_multiplier,
        "max_loss_usd": position_usd * (tier.stop_loss_pct / 100),
        "tier_name": tier.tier_name,
        "rationale": tier.rationale
    }


def format_tier_alert_message(tier: RiskTier, reasoning: str) -> str:
    """
    Format a user-friendly alert message including tier information.
    
    Args:
        tier: RiskTier classification
        reasoning: Reasoning string from classification
    
    Returns:
        Formatted message string
    """
    tier_emoji = {
        "MOONSHOT": "🚀",
        "AGGRESSIVE": "⚡",
        "CALCULATED": "🎯"
    }
    
    emoji = tier_emoji.get(tier.tier_name, "📊")
    
    message = f"""
{emoji} RISK TIER: {tier.tier_name}
━━━━━━━━━━━━━━━
Position Size: {tier.position_size_pct:.0f}% of capital
Stop Loss: -{tier.stop_loss_pct:.0f}%
Min Take Profit: {tier.take_profit_min_multiplier:.0f}x
━━━━━━━━━━━━━━━
Strategy: {tier.rationale}

{reasoning}
"""
    return message


# ============================================================================
# SMART PROFIT-TAKING SYSTEM
# ============================================================================
# Multi-level profit taking to capture gains at every milestone
# Format: (multiplier, pct_to_sell)
# Example: (2.0, 0.10) = At 2x, sell 10% of original position

TIER1_PROFIT_LEVELS = [
    (1.30, 0.00),  # +30%: HOLD (too early for moonshots)
    (1.50, 0.00),  # +50%: HOLD (still building)
    (2.00, 0.10),  # 2x: Take 10% (recover 20% of capital)
    (3.00, 0.15),  # 3x: Take 15% (lock in 45% of position)
    (5.00, 0.20),  # 5x: Take 20% (lock in 100% of position value)
    (10.0, 0.25),  # 10x: Take 25% (lock in 250% gain)
    (20.0, 0.20),  # 20x: Take 20% (lock in 400% gain)
    (50.0, 0.10),  # 50x: Take 10% (let the rest run!)
]

TIER2_PROFIT_LEVELS = [
    (1.30, 0.00),  # +30%: HOLD (still early)
    (1.50, 0.20),  # +50%: Take 20% (lock in first profit!)
    (1.75, 0.20),  # +75%: Take 20% (capture the "almost 2x")
    (2.00, 0.30),  # 2x: Take 30% (secure 2x gain)
    (3.00, 0.20),  # 3x: Take 20% (lock in more)
    (5.00, 0.10),  # 5x: Take 10% (keep some for moonshot)
]

TIER3_PROFIT_LEVELS = [
    (1.25, 0.30),  # +25%: Take 30% (start profit taking)
    (1.50, 0.40),  # +50%: Take 40% (lock majority)
    (1.75, 0.20),  # +75%: Take 20% (secure more)
    (2.00, 0.10),  # 2x: Exit rest (don't be greedy)
]


def get_profit_levels_for_tier(tier: RiskTier) -> List[Tuple[float, float]]:
    """
    Get profit-taking levels for a specific tier.
    
    Args:
        tier: RiskTier classification
    
    Returns:
        List of (multiplier, pct_to_sell) tuples
    """
    if tier.tier_name == "MOONSHOT":
        return TIER1_PROFIT_LEVELS
    elif tier.tier_name == "AGGRESSIVE":
        return TIER2_PROFIT_LEVELS
    elif tier.tier_name == "CALCULATED":
        return TIER3_PROFIT_LEVELS
    else:
        return []


def get_dynamic_trailing_stop(tier: RiskTier, current_gain_pct: float) -> float:
    """
    Get trailing stop that tightens as profit grows.
    Captures 50-85% gains before reversal!
    
    Args:
        tier: RiskTier classification
        current_gain_pct: Current unrealized gain as percentage (e.g., 75.0 for +75%)
    
    Returns:
        Trailing stop percentage from peak (e.g., 40.0 for -40% from peak)
    """
    if tier.tier_name == "MOONSHOT":
        # Wide initially, tightens as moonshot develops
        if current_gain_pct < 100:
            return 70.0  # Wide initially (allow volatility)
        elif current_gain_pct < 300:
            return 60.0  # Tightening
        elif current_gain_pct < 500:
            return 50.0  # Lock in some gain
        elif current_gain_pct < 1000:
            return 45.0  # Securing profit
        else:
            return 40.0  # Let moonshot run but protect gains
    
    elif tier.tier_name == "AGGRESSIVE":
        # CRITICAL: Tighter stops at +30-50% to capture "almost winners"!
        if current_gain_pct < 30:
            return 50.0  # Initial stop loss
        elif current_gain_pct < 50:
            return 40.0  # TIGHTEN - capture 50-85% gains!
        elif current_gain_pct < 100:
            return 35.0  # Securing gain
        elif current_gain_pct < 300:
            return 30.0  # Lock profit
        else:
            return 35.0  # Let it run but protect
    
    else:  # CALCULATED
        # Tight stops - quick exits
        if current_gain_pct < 25:
            return 40.0  # Initial
        elif current_gain_pct < 50:
            return 30.0  # TIGHT - lock early gains!
        else:
            return 25.0  # Very tight (don't give back)


def calculate_next_profit_target(
    tier: RiskTier,
    entry_price: float,
    highest_price: float,
    already_taken: List[float]
) -> Optional[Tuple[float, float, float]]:
    """
    Calculate the next profit-taking target for a position.
    
    Args:
        tier: RiskTier classification
        entry_price: Original entry price
        highest_price: Highest price seen (peak)
        already_taken: List of multipliers where profit was already taken
    
    Returns:
        Tuple of (target_price, multiplier, pct_to_sell) or None if no more targets
    """
    profit_levels = get_profit_levels_for_tier(tier)
    
    for multiplier, pct_to_sell in profit_levels:
        if multiplier not in already_taken and pct_to_sell > 0:
            target_price = entry_price * multiplier
            # Only return if we haven't hit this level yet
            if highest_price >= target_price:
                return (target_price, multiplier, pct_to_sell)
    
    return None


# Export all tier definitions for use in other modules
__all__ = [
    'RiskTier',
    'TIER_1_MOONSHOT',
    'TIER_2_AGGRESSIVE',
    'TIER_3_CALCULATED',
    'classify_signal_risk_tier',
    'get_position_recommendation',
    'format_tier_alert_message',
    # Smart profit-taking
    'TIER1_PROFIT_LEVELS',
    'TIER2_PROFIT_LEVELS',
    'TIER3_PROFIT_LEVELS',
    'get_profit_levels_for_tier',
    'get_dynamic_trailing_stop',
    'calculate_next_profit_target',
]

