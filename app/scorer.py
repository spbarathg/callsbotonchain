from typing import Any, Dict, List
import os


def score_token(data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute 0-10 confidence score from on-chain and enrichment metrics."""
    score = 0.0
    reasons: List[str] = []

    lp_sol = float(data.get("lp_sol") or 0.0)
    top1 = float(data.get("top1_pct") or 1.0)
    top10 = float(data.get("top10_pct") or 1.0)
    enrichment = int(data.get("enrichment_score") or 0)
    creator_hist = int(data.get("creator_score") or 0)

    # New features
    transfer_fee_bps = int(data.get("transfer_fee_bps") or 0)
    freeze_null = bool(data.get("freeze_authority_null"))
    mint_null = bool(data.get("mint_authority_null"))
    momentum = int(data.get("momentum_score") or 0)

    # LP size sweet spot for 50%+ potential (max 4)
    # Add minimum LP check to prevent over-scoring extremely low LP tokens
    if lp_sol < 1.0:
        score += 0.5
        reasons.append("LP very low (risky)")
    elif 15 <= lp_sol <= 45:
        score += 4
        reasons.append("LP perfect (15-45 SOL)")
    elif 8 <= lp_sol <= 65:
        score += 3.5
        reasons.append("LP excellent (8-65 SOL)")
    elif 5 <= lp_sol <= 85:
        score += 3
        reasons.append("LP good (5-85 SOL)")
    elif lp_sol <= 120:
        score += 2
        reasons.append("LP adequate")
    else:
        # LP > 120 SOL likely means established token with lower upside
        score += 0.5
        reasons.append("LP very high (established)")

    # Holder concentration - critical for 50%+ (max 4)  
    # Top1 holder concentration
    if top1 <= 0.12:
        score += 3
        reasons.append("Top1 <= 12% (excellent)")
    elif top1 <= 0.20:
        score += 2
        reasons.append("Top1 <= 20% (good)")
    elif top1 <= 0.30:
        score += 1
        reasons.append("Top1 <= 30% (fair)")

    # Top10 distribution bonus
    if top10 <= 0.45:
        score += 1
        reasons.append("Top10 <= 45% (distributed)")

    # Momentum (max 4) - Critical for 50%+ pumps
    if momentum >= 4:
        score += 4
        reasons.append(f"Viral momentum ({momentum})")
    elif momentum >= 3:
        score += 3
        reasons.append(f"Strong momentum ({momentum})")
    elif momentum >= 2:
        score += 2
        reasons.append(f"Good momentum ({momentum})")
    elif momentum >= 1:
        score += 1
        reasons.append(f"Some momentum ({momentum})")

    # Smart wallets involvement (max 3)
    if enrichment > 0:
        score += min(enrichment, 3)
        reasons.append(f"Smart wallets+whales score {enrichment}")

    # Creator history (max 1)
    if creator_hist > 0:
        score += 1
        reasons.append("Positive creator history")

    # Safety penalties
    # Freeze authority present is a hard red flag: block signal regardless
    if not freeze_null:
        reasons.append("Freeze authority set")
        return {"score": 0.0, "reasons": reasons, "signal": False}

    # Mint authority present early can be risky; only a soft penalty
    if not mint_null:
        score -= 1
        reasons.append("Mint authority not renounced")
    
    # Additional safety check for extremely low LP with high concentration
    if lp_sol < 2.0 and top1 > 0.5:
        score -= 2
        reasons.append("Very low LP with high concentration (high risk)")

    # Transfer fees (tax) penalty
    max_tax_pct = float(os.getenv("MAX_TRANSFER_TAX_PCT", "6"))
    tax_pct = transfer_fee_bps / 100.0
    if tax_pct > 0:
        reasons.append(f"Transfer fee {tax_pct:.2f}%")
    if tax_pct > max_tax_pct:
        score -= 2
        reasons.append("Transfer tax above threshold")

    # Penalties for centralization (reduces 50%+ potential) - more balanced
    if top1 >= 0.70:
        score -= 3
        reasons.append("Top1 > 70% (extreme whale risk)")
    elif top1 >= 0.50:
        score -= 2
        reasons.append("Top1 > 50% (high centralization)")
    elif top1 >= 0.40:
        score -= 1
        reasons.append("Top1 > 40% (concerning)")
    
    if top10 >= 0.85:
        score -= 2
        reasons.append("Top10 > 85% (very centralized)")
    elif top10 >= 0.70:
        score -= 1
        reasons.append("Top10 > 70% (centralized)")

    # Clamp and finalize
    score = min(max(score, 0.0), 10.0)
    threshold = float(os.getenv("SCORE_THRESHOLD", "6"))
    is_signal = score >= threshold
    return {"score": score, "reasons": reasons, "signal": is_signal}


__all__ = ["score_token"]


