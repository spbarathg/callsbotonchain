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

    # LP size (max 4)
    if lp_sol >= 20:
        score += 4
        reasons.append("LP >= 20 SOL")
    elif lp_sol >= 10:
        score += 3
        reasons.append("LP >= 10 SOL")
    elif lp_sol >= 5:
        score += 2
        reasons.append("LP >= 5 SOL")

    # Holder concentration (max 5)
    # Top1
    if top1 <= 0.10:
        score += 3
        reasons.append("Top1 <= 10%")
    elif top1 <= 0.20:
        score += 2
        reasons.append("Top1 <= 20%")
    elif top1 <= 0.30:
        score += 1
        reasons.append("Top1 <= 30%")

    # Top10
    if top10 <= 0.40:
        score += 2
        reasons.append("Top10 <= 40%")
    elif top10 <= 0.60:
        score += 1
        reasons.append("Top10 <= 60%")

    # Momentum (max 3)
    if momentum > 0:
        score += min(momentum, 3)
        reasons.append(f"Momentum score {momentum}")

    # Smart wallets involvement (max 3)
    if enrichment > 0:
        score += min(enrichment, 3)
        reasons.append(f"Smart wallets+whales score {enrichment}")

    # Creator history (max 1)
    if creator_hist > 0:
        score += 1
        reasons.append("Positive creator history")

    # Safety penalties
    # Freeze authority present is a hard red flag
    if not freeze_null:
        score -= 3
        reasons.append("Freeze authority set")

    # Mint authority present early can be risky; only a soft penalty
    if not mint_null:
        score -= 1
        reasons.append("Mint authority not renounced")

    # Transfer fees (tax) penalty
    max_tax_pct = float(os.getenv("MAX_TRANSFER_TAX_PCT", "6"))
    tax_pct = transfer_fee_bps / 100.0
    if tax_pct > 0:
        reasons.append(f"Transfer fee {tax_pct:.2f}%")
    if tax_pct > max_tax_pct:
        score -= 2
        reasons.append("Transfer tax above threshold")

    # Clamp and finalize
    score = min(max(score, 0.0), 10.0)
    threshold = float(os.getenv("SCORE_THRESHOLD", "6"))
    is_signal = score >= threshold
    return {"score": score, "reasons": reasons, "signal": is_signal}


__all__ = ["score_token"]


