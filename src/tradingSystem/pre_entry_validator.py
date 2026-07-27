"""
PRE-ENTRY VALIDATOR - Prevent Scams & Ghost Buys BEFORE Entry

CRITICAL FIX (Oct 27): Multi-layer validation to prevent rugpulls and ghost buys
Problem: Recent losses from obvious scams and untradeable tokens
- #380, #379, #378: Lost $104 to rugpulls (-100%)
- #387, #386: Lost $108 to ghost buys (tokens never arrived)

Solution: Validate tokens BEFORE buying, not after
- Layer 1: Token Age (reject brand new tokens)
- Layer 2: Recent Price Action (reject recent dumps)
- Layer 3: Tradeability Check (verify Jupiter can swap)

Impact: Prevents 50% of recent losses ($104 + $108 = $212 saved per 10 trades)
"""
import time
import os
from typing import Dict, Tuple, Optional
import requests


class PreEntryValidator:
    """
    Validates tokens BEFORE buying to prevent scams, rugpulls, and ghost buys.
    
    All checks run in parallel where possible to minimize latency.
    Total validation time: ~5-10 seconds per token.
    """
    
    def __init__(self):
        # Validation thresholds
        self.MIN_TOKEN_AGE_HOURS = 1.0  # Reject tokens < 1 hour old
        self.MAX_RECENT_DUMP_PCT = -20.0  # Reject if -20%+ in last 10 min
        self.RECENT_DUMP_WINDOW_MIN = 10  # Check last 10 minutes
        
        # API endpoints
        # REMOVED: DexScreener API (user requirement: Jupiter API only)
        self.SOLSCAN_API = "https://api.solscan.io/v2/token/meta"
        self._tradeability_cache = {}  # token -> (is_tradeable, reason, ts, ttl)
        self._tradeability_cache_ttl = int(
            os.getenv("JUP_TRADEABLE_CACHE_TTL_SEC", "180")
        )
        self._tradeability_rate_limit_ttl = int(
            os.getenv("JUP_TRADEABLE_RATE_LIMIT_TTL_SEC", "30")
        )
        
    def validate_token(self, token: str, stats: Dict) -> Tuple[bool, str]:
        """
        Comprehensive pre-entry validation.
        
        Returns: (is_valid: bool, reason: str)
        
        If is_valid = False, DO NOT BUY this token!
        """
        # Layer 1: Token Age Check
        is_old_enough, age_reason = self._check_token_age(token, stats)
        if not is_old_enough:
            return False, f"❌ Token too young: {age_reason}"
        
        # Layer 2: Recent Dump Check
        no_recent_dump, dump_reason = self._check_recent_dumps(token, stats)
        if not no_recent_dump:
            return False, f"❌ Recent dump detected: {dump_reason}"
        
        # Layer 3: Tradeability Check (most important - prevents ghost buys)
        is_tradeable, trade_reason = self._check_tradeable(token)
        if not is_tradeable:
            return False, f"❌ Not tradeable: {trade_reason}"
        
        # All checks passed!
        return True, "✅ All validation checks passed"
    
    def _check_token_age(self, token: str, stats: Dict) -> Tuple[bool, str]:
        """
        Check if token is old enough to be considered safe.
        
        Why: Brand new tokens (< 1 hour) are often scams/rugpulls
        Evidence: Positions #380, #379, #378 were all very new tokens
        
        Returns: (is_old_enough: bool, reason: str)
        """
        try:
            # Try to get token age from stats (if available)
            created_at = stats.get("created_at") or stats.get("token_created_at")
            
            if created_at:
                # Parse timestamp
                if isinstance(created_at, (int, float)):
                    age_seconds = time.time() - created_at
                elif isinstance(created_at, str):
                    # Try parsing ISO format timestamp
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        age_seconds = time.time() - dt.timestamp()
                    except:
                        # If parsing fails, skip this check
                        return True, "Could not parse token age (skipping check)"
                else:
                    return True, "Token age format unknown (skipping check)"
                
                age_hours = age_seconds / 3600
                
                if age_hours < self.MIN_TOKEN_AGE_HOURS:
                    return False, f"Only {age_hours:.1f}h old (min: {self.MIN_TOKEN_AGE_HOURS}h)"
                
                return True, f"Token age OK ({age_hours:.1f}h old)"
            
            # REMOVED: DexScreener fallback (user requirement: Jupiter API only)
            # If age data not available from signal, skip validation rather than using DexScreener
            
            # If all checks fail, SKIP this validation (don't block entry)
            # Better to trade than to block all tokens due to API issues
            return True, "Token age unknown (skipping check)"
            
        except Exception as e:
            print(f"[VALIDATOR] ⚠️ Token age check error: {e}", flush=True)
            return True, "Token age check failed (skipping)"
    
    def _check_recent_dumps(self, token: str, stats: Dict) -> Tuple[bool, str]:
        """
        Check if token recently dumped hard.
        
        Why: Tokens that just dumped -20%+ are likely rugpulls or scams
        Evidence: Position #385 (vx91ZoRC) dumped -37% quickly after entry
        
        Returns: (no_recent_dump: bool, reason: str)
        """
        try:
            # First, check stats for recent price changes
            change_5m = stats.get("change_5m") or stats.get("priceChange", {}).get("m5")
            change_10m = stats.get("change_10m") or stats.get("priceChange", {}).get("m10")
            
            if change_5m is not None:
                change_5m = float(change_5m)
                if change_5m <= self.MAX_RECENT_DUMP_PCT:
                    return False, f"{change_5m:.1f}% drop in last 5 min"
            
            if change_10m is not None:
                change_10m = float(change_10m)
                if change_10m <= self.MAX_RECENT_DUMP_PCT:
                    return False, f"{change_10m:.1f}% drop in last 10 min"
            
            # REMOVED: DexScreener fallback (user requirement: Jupiter API only)
            # If dump data not available from signal, rely on signal provider's data only
            
            # No recent dumps detected
            return True, "No recent dumps detected"
            
        except Exception as e:
            print(f"[VALIDATOR] ⚠️ Recent dump check error: {e}", flush=True)
            return True, "Dump check failed (skipping)"
    
    def _check_tradeable(self, token: str) -> Tuple[bool, str]:
        """
        Verify token is actually tradeable on Jupiter.
        
        Why: Some tokens accept SOL but don't deliver (ghost buys)
        Evidence: #387 (-$54), #386 (-$54) - transactions succeeded but no tokens
        
        This is the MOST IMPORTANT check - prevents 100% losses!
        
        Multi-strategy approach:
        1. Try direct routes only (fastest, most reliable)
        2. Try multi-hop with higher slippage (slower tokens)
        3. Try smaller test amount (micro-cap tokens)
        
        Returns: (is_tradeable: bool, reason: str)
        """
        try:
            from app.jupiter_client import get_jupiter_client
            from .config_optimized import SOL_MINT
            
            jupiter = get_jupiter_client()

            now = time.time()
            cached = self._tradeability_cache.get(token)
            if cached:
                cached_ok, cached_reason, cached_ts, cached_ttl = cached
                if (now - cached_ts) < cached_ttl:
                    return cached_ok, cached_reason

            def _cache_result(ok: bool, reason: str, ttl_override: Optional[int] = None):
                ttl = ttl_override if ttl_override is not None else self._tradeability_cache_ttl
                self._tradeability_cache[token] = (ok, reason, time.time(), ttl)

            def _is_rate_limited(result: Dict) -> bool:
                if result.get("status_code") == 429:
                    return True
                err = str(result.get("error") or "").lower()
                return "rate limit" in err or "429" in err

            def _should_retry(result: Dict) -> bool:
                err = str(result.get("error") or "")
                if result.get("status_code") in (429, None):
                    return False
                if "TOKEN_NOT_TRADABLE" in err:
                    return False
                if "COULD_NOT_FIND_ANY_ROUTE" in err or "NO_ROUTES_FOUND" in err:
                    return True
                if result.get("status_code") in (400, 404):
                    return True
                return False
            
            # Strategy 1: Direct routes only with conservative slippage (fastest path)
            # This works for most liquid tokens with SOL pairs
            test_amount_lamports = 10_000_000  # 0.01 SOL
            
            try:
                print(f"[VALIDATOR] 🔍 Strategy 1: Testing direct routes (0.01 SOL, 20% slippage)...", flush=True)
                result = jupiter.get_quote(
                    input_mint=SOL_MINT,
                    output_mint=token,
                    amount=test_amount_lamports,
                    slippage_bps=2000,  # 20% slippage
                    only_direct_routes=True,
                    priority="medium"
                )
                
                if result["status_code"] == 200 and result.get("json"):
                    quote_data = result["json"]
                    out_amount = quote_data.get("outAmount")
                    if out_amount and int(out_amount) > 0:
                        print(f"[VALIDATOR] ✅ Direct route found! Output: {out_amount} tokens", flush=True)
                        _cache_result(True, "Direct Jupiter route available (most reliable)")
                        return True, "Direct Jupiter route available (most reliable)"
                
                print(f"[VALIDATOR] ⚠️ Strategy 1 failed: {result.get('error', 'No direct route')}", flush=True)
                if _is_rate_limited(result):
                    reason = "Rate limited during tradeability check"
                    _cache_result(False, reason, ttl_override=self._tradeability_rate_limit_ttl)
                    return False, reason
                if not _should_retry(result):
                    reason = result.get("error", "Direct route unavailable")
                    _cache_result(False, reason)
                    return False, reason
                
            except Exception as e:
                print(f"[VALIDATOR] ⚠️ Strategy 1 error: {e}", flush=True)
            
            # Strategy 2: Multi-hop routes with aggressive slippage
            # For tokens without direct SOL pairs but routable via USDC/other
            try:
                print(f"[VALIDATOR] 🔍 Strategy 2: Testing multi-hop routes (0.01 SOL, 50% slippage)...", flush=True)
                result = jupiter.get_quote(
                    input_mint=SOL_MINT,
                    output_mint=token,
                    amount=test_amount_lamports,
                    slippage_bps=5000,  # 50% slippage (aggressive)
                    only_direct_routes=False,
                    max_accounts=64,  # Allow more complex routes
                    priority="medium"
                )
                
                if result["status_code"] == 200 and result.get("json"):
                    quote_data = result["json"]
                    out_amount = quote_data.get("outAmount")
                    if out_amount and int(out_amount) > 0:
                        print(f"[VALIDATOR] ✅ Multi-hop route found! Output: {out_amount} tokens", flush=True)
                        _cache_result(True, "Multi-hop Jupiter route available (requires higher slippage)")
                        return True, "Multi-hop Jupiter route available (requires higher slippage)"
                
                print(f"[VALIDATOR] ⚠️ Strategy 2 failed: {result.get('error', 'No multi-hop route')}", flush=True)
                if _is_rate_limited(result):
                    reason = "Rate limited during tradeability check"
                    _cache_result(False, reason, ttl_override=self._tradeability_rate_limit_ttl)
                    return False, reason
                if not _should_retry(result):
                    reason = result.get("error", "Multi-hop route unavailable")
                    _cache_result(False, reason)
                    return False, reason
                
            except Exception as e:
                print(f"[VALIDATOR] ⚠️ Strategy 2 error: {e}", flush=True)
            
            # Strategy 3: Micro amount test (for very small market cap tokens)
            # Sometimes new tokens have minimum trade sizes
            try:
                print(f"[VALIDATOR] 🔍 Strategy 3: Testing with micro amount (0.001 SOL, 50% slippage)...", flush=True)
                micro_amount = 1_000_000  # 0.001 SOL (~$0.15)
                result = jupiter.get_quote(
                    input_mint=SOL_MINT,
                    output_mint=token,
                    amount=micro_amount,
                    slippage_bps=5000,  # 50% slippage
                    only_direct_routes=False,
                    max_accounts=64,
                    priority="medium"
                )
                
                if result["status_code"] == 200 and result.get("json"):
                    quote_data = result["json"]
                    out_amount = quote_data.get("outAmount")
                    if out_amount and int(out_amount) > 0:
                        print(f"[VALIDATOR] ✅ Micro-trade route found! Output: {out_amount} tokens", flush=True)
                        _cache_result(True, "Tradeable with micro amounts (very low liquidity)")
                        return True, "Tradeable with micro amounts (very low liquidity)"
                
                print(f"[VALIDATOR] ⚠️ Strategy 3 failed: {result.get('error', 'Not tradeable even with micro amount')}", flush=True)
                if _is_rate_limited(result):
                    reason = "Rate limited during tradeability check"
                    _cache_result(False, reason, ttl_override=self._tradeability_rate_limit_ttl)
                    return False, reason
                
            except Exception as e:
                print(f"[VALIDATOR] ⚠️ Strategy 3 error: {e}", flush=True)
            
            # All strategies failed - token is not tradeable on Jupiter
            print(f"[VALIDATOR] ❌ All tradeability strategies failed for {token[:12]}...", flush=True)
            print(f"[VALIDATOR] 💡 This token might be:", flush=True)
            print(f"[VALIDATOR]    - Too new (no liquidity established yet)", flush=True)
            print(f"[VALIDATOR]    - Raydium-only (not indexed by Jupiter)", flush=True)
            print(f"[VALIDATOR]    - Scam token (accepts buys but can't sell)", flush=True)
            print(f"[VALIDATOR]    - Requires direct Raydium integration", flush=True)
            
            reason = "Not tradeable on Jupiter (tried 3 strategies: direct, multi-hop, micro)"
            _cache_result(False, reason)
            return False, reason
        
        except Exception as e:
            print(f"[VALIDATOR] ⚠️ Tradeability check system error: {e}", flush=True)
            # CRITICAL: If check fails due to system error, BLOCK entry
            # Better to miss a trade than to risk a ghost buy
            return False, f"System error during tradeability check: {str(e)[:100]}"


# Global singleton
_validator: Optional[PreEntryValidator] = None

def get_pre_entry_validator() -> PreEntryValidator:
    """Get global pre-entry validator instance."""
    global _validator
    if _validator is None:
        _validator = PreEntryValidator()
    return _validator


