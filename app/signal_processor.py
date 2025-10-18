"""
Signal Processor - Core signal analysis and alerting logic

Extracted from bot.py to improve testability and maintainability.
Processes feed items and decides whether to send alerts.
"""
import time
import html
from typing import Optional, Dict, Any
from datetime import datetime

from app.models import FeedTransaction, TokenStats, ProcessResult
from app.analyze_token import (
    get_token_stats,
    score_token,
    calculate_preliminary_score,
    check_senior_strict,
    check_junior_strict,
    check_junior_nuanced,
)
from app.storage import (
    has_been_alerted,
    mark_alerted,
    record_alert_with_metadata,
    record_token_activity,
    get_recent_token_signals,
)
from app.notify import send_telegram_alert, push_signal_to_redis
from app.telethon_notifier import send_group_message
from app.logger_utils import log_alert, log_process


class SignalProcessor:
    """
    Processes feed transactions and generates trading signals.
    
    Responsibilities:
    - Validate feed items
    - Calculate preliminary scores
    - Fetch detailed token statistics
    - Apply gating logic
    - Generate and send alerts
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize signal processor with configuration.
        
        Args:
            config: Dictionary containing configuration values
        """
        self.config = config
        self._session_alerted_tokens = set()
        self._last_alert_time = 0.0
        self._api_calls_saved = 0
    
    def process_feed_item(
        self,
        tx: Dict[str, Any],
        is_smart_cycle: bool
    ) -> ProcessResult:
        """
        Process a single feed item and determine if it should generate an alert.
        
        Args:
            tx: Transaction data from feed
            is_smart_cycle: Whether this is from the smart money feed cycle
        
        Returns:
            ProcessResult with status and metadata
        """
        # Import config values (could be passed in constructor instead)
        from app.config_unified import (
            DEBUG_PRELIM,
            REQUIRE_SMART_MONEY_FOR_ALERT,
            PRELIM_DETAILED_MIN,
            GENERAL_CYCLE_MIN_SCORE,
            MIN_LIQUIDITY_USD,
            USE_LIQUIDITY_FILTER,
            EXCELLENT_LIQUIDITY_USD,
            REQUIRE_LP_LOCKED,
            REQUIRE_MINT_REVOKED,
            ALLOW_UNKNOWN_SECURITY,
        )
        
        # Parse transaction into model
        feed_tx = FeedTransaction(
            token0_address=tx.get("token0_address"),
            token1_address=tx.get("token1_address"),
            token0_amount_usd=tx.get("token0_amount_usd"),
            token1_amount_usd=tx.get("token1_amount_usd"),
            usd_value=tx.get("usd_value"),
            tx_type=tx.get("tx_type"),
            dex=tx.get("dex"),
            smart_money=is_smart_cycle or self._tx_has_smart_money(tx),
            is_synthetic=bool(tx.get('is_synthetic')) or str(tx.get('tx_type', '')).endswith('_fallback'),
            raw_data=tx
        )
        
        token_address = feed_tx.get_candidate_token()
        usd_value = feed_tx.usd_value or 0
        
        # Early validation
        if not token_address or usd_value == 0:
            return ProcessResult(status="skipped", error_message="No valid token or zero value")
        
        # Skip native SOL
        if token_address in ("native", "So11111111111111111111111111111111111111112"):
            return ProcessResult(status="skipped", error_message="Native SOL token")
        
        # Check if already alerted (EARLY GATE: Skip before any processing)
        if token_address in self._session_alerted_tokens or has_been_alerted(token_address):
            return ProcessResult(status="skipped", error_message="Already alerted")
        
        # Calculate preliminary score (EARLY GATE: Skip expensive operations)
        preliminary_score = calculate_preliminary_score(tx, smart_money_detected=feed_tx.smart_money)
        
        if DEBUG_PRELIM:
            self._log_prelim_debug(tx)
        
        # Preliminary score gating (BEFORE recording activity - no DB writes for rejected signals)
        if preliminary_score < PRELIM_DETAILED_MIN:
            self._log(f"Token {token_address} prelim: {preliminary_score}/10 (skipped detailed analysis)")
            self._api_calls_saved += 1
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                api_calls_saved=1,
                error_message="Preliminary score too low"
            )
        
        # OPTIMIZED: Record activity ONLY for signals that pass preliminary score check
        # This avoids writing thousands of rejected transactions to the database
        trader = tx.get('from') or tx.get('wallet')
        record_token_activity(
            token_address,
            usd_value,
            1,
            feed_tx.smart_money,
            preliminary_score,
            trader
        )
        
        # Fetch detailed stats
        self._log(f"FETCHING DETAILED STATS for {token_address[:8]} (prelim: {preliminary_score}/10)")
        stats_raw = get_token_stats(token_address)
        if not stats_raw:
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                error_message="Failed to fetch stats"
            )
        
        # Parse stats into model
        stats = TokenStats.from_api_response(stats_raw, source=stats_raw.get("_source", "unknown"))
        if not stats:
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                error_message="Failed to parse stats"
            )
        
        # EARLY GATE: Liquidity pre-filter (fast rejection before expensive scoring)
        # NOTE: Also checked in junior_strict/nuanced for nuanced liquidity_factor support
        if USE_LIQUIDITY_FILTER:
            if not self._check_liquidity(stats, MIN_LIQUIDITY_USD, EXCELLENT_LIQUIDITY_USD):
                return ProcessResult(
                    status="skipped",
                    token_address=token_address,
                    preliminary_score=preliminary_score,
                    error_message="Liquidity check failed"
                )
            # Enforce maximum liquidity early to avoid extra work on saturated pools
            try:
                from app.config_unified import MAX_LIQUIDITY_USD
                liq_usd = float(stats.liquidity_usd or 0.0)
                if (MAX_LIQUIDITY_USD or 0) > 0 and liq_usd > MAX_LIQUIDITY_USD:
                    return ProcessResult(
                        status="skipped",
                        token_address=token_address,
                        preliminary_score=preliminary_score,
                        error_message="Liquidity above max cap"
                    )
            except Exception:
                pass
        
        # EARLY GATE: Market cap filter ($50k-$200k sweet spot)
        # DATA-DRIVEN: <$50k = 63.9% rug rate, $50k-$100k = 28.8% 2x+ rate (best!)
        if not self._check_market_cap_range(stats, token_address):
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                error_message="Market cap outside target range"
            )
        
        # ANTI-FOMO FILTER: Reject tokens that already pumped (late entry!)
        if not self._check_fomo_filter(stats, token_address):
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                error_message="Already pumped - late entry rejected"
            )
        
        # EARLY GATE: Quick security check (fast rejection before expensive scoring)
        # NOTE: Currently disabled (REQUIRE_LP_LOCKED=False, REQUIRE_MINT_REVOKED=False)
        # Also checked in senior_strict, but this provides early exit if requirements enabled
        if not self._check_quick_security(stats, REQUIRE_LP_LOCKED, REQUIRE_MINT_REVOKED, ALLOW_UNKNOWN_SECURITY):
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                error_message="Security check failed"
            )
        
        # Score token
        score, scoring_details = score_token(stats_raw, smart_money_detected=feed_tx.smart_money, token_address=token_address)
        
        # Post-score gates
        if REQUIRE_SMART_MONEY_FOR_ALERT and not feed_tx.smart_money:
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                final_score=score,
                error_message="Smart money required but not detected"
            )
        
        # OPTIMIZED: Removed velocity check - always 0, check always passes
        # if REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT:
        #     if (velocity_bonus // 2) < (REQUIRE_VELOCITY_MIN_SCORE_FOR_ALERT // 2):
        #         return ProcessResult(...)
        
        # General cycle score requirement
        if not feed_tx.smart_money and score < GENERAL_CYCLE_MIN_SCORE:
            self._log(f"REJECTED (General Cycle Low Score): {token_address} (score: {score}/{GENERAL_CYCLE_MIN_SCORE})")
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                final_score=score,
                error_message="General cycle score too low"
            )
        
        # Senior strict check
        if not check_senior_strict(stats_raw, token_address):
            self._log(f"REJECTED (Senior Strict): {token_address}")
            return ProcessResult(
                status="skipped",
                token_address=token_address,
                preliminary_score=preliminary_score,
                final_score=score,
                error_message="Failed senior strict check"
            )
        
        # Junior strict and nuanced checks
        # FIXED: Give ALL tokens equal treatment - smart money or not
        # Data showed non-smart outperformed (3.03x vs 1.12x), so no special treatment
        # Both paths now get nuanced fallback
        jr_strict_ok = check_junior_strict(stats_raw, score)
        conviction_type = None
        
        if jr_strict_ok:
            if feed_tx.smart_money:
                self._log(f"PASSED (Strict + Smart Money): {token_address}")
                conviction_type = "High Confidence (Smart Money)"
            else:
                self._log(f"PASSED (Strict Rules): {token_address}")
                conviction_type = "High Confidence (Strict)"
        else:
            self._log(f"ENTERING DEBATE (Strict-Junior failed): {token_address}")
            if check_junior_nuanced(stats_raw, score):
                self._log(f"PASSED (Nuanced Junior): {token_address}")
                if feed_tx.smart_money:
                    conviction_type = "Nuanced Conviction (Smart Money)"
                else:
                    conviction_type = "Nuanced Conviction"
            else:
                self._log(f"REJECTED (Nuanced Debate): {token_address}")
                return ProcessResult(
                    status="skipped",
                    token_address=token_address,
                    preliminary_score=preliminary_score,
                    final_score=score,
                    error_message="Failed nuanced check"
                )
        
        # ML Enhancement (optional)
        score = self._apply_ml_enhancement(score, stats_raw, feed_tx.smart_money, conviction_type, scoring_details)
        
        # Generate and send alert
        alert_success = self._send_alert(
            token_address,
            stats,
            score,
            preliminary_score,
            conviction_type,
            scoring_details,
            feed_tx,
            jr_strict_ok,
            trader
        )
        
        if alert_success:
            self._session_alerted_tokens.add(token_address)
            return ProcessResult(
                status="alert_sent",
                token_address=token_address,
                preliminary_score=preliminary_score,
                final_score=score
            )
        else:
            return ProcessResult(
                status="error",
                token_address=token_address,
                preliminary_score=preliminary_score,
                final_score=score,
                error_message="Failed to send alert"
            )
    
    def _tx_has_smart_money(self, tx: dict) -> bool:
        """Detect smart money from transaction hints"""
        try:
            if any(bool(tx.get(k)) for k in ("smart_money", "is_smart", "isTopWallet")):
                return True
            top_wallets = tx.get("top_wallets")
            if isinstance(top_wallets, (list, tuple)) and len(top_wallets) > 0:
                return True
            for key in ("wallet_pnl", "min_wallet_pnl", "trader_pnl", "pnl_usd"):
                val = tx.get(key)
                if isinstance(val, (int, float)) and float(val) >= 1000:
                    return True
            labels = tx.get("labels") or tx.get("wallet_labels")
            if labels:
                if isinstance(labels, (list, tuple)):
                    label_text = ",".join(str(x) for x in labels).lower()
                else:
                    label_text = str(labels).lower()
                if any(tag in label_text for tag in ("smart", "top", "alpha", "elite")):
                    return True
            return False
        except Exception:
            return False
    
    def _check_token_age(self, token_address: str, min_age_minutes: int) -> bool:
        """Check if token meets minimum age requirement"""
        try:
            obs = get_recent_token_signals(token_address, 365*24*3600)
            if obs:
                first_seen = obs[-1]
                first_dt = datetime.strptime(first_seen, '%Y-%m-%d %H:%M:%S')
                age_minutes = (datetime.now() - first_dt).total_seconds() / 60.0
                if age_minutes < float(min_age_minutes):
                    self._log(f"Rejected (Too new: {age_minutes:.1f}m < {min_age_minutes}m): {token_address}")
                    return False
            return True
        except Exception:
            return True
    
    def _check_liquidity(self, stats: TokenStats, min_liq: float, excellent_liq: float) -> bool:
        """
        Check liquidity requirements with maximum cap
        DATA-DRIVEN: $30k-$50k = 26.5% 2x+ rate, 335% avg gain (best!)
        COUNTER-INTUITIVE: $75k+ has 65% rug rate (worse than lower liquidity!)
        """
        from app.config_unified import MAX_LIQUIDITY_USD
        
        liquidity = stats.liquidity_usd or 0

        # CRITICAL FIX: Handle NaN/inf values (NaN comparisons always False!)
        if not (liquidity == liquidity):  # NaN check
            self._log(f"❌ REJECTED (INVALID LIQUIDITY - NaN): {stats.token_address}")
            return False
        if liquidity == float('inf') or liquidity == float('-inf'):
            self._log(f"❌ REJECTED (INVALID LIQUIDITY - inf): {stats.token_address}")
            return False

        if liquidity <= 0:
            self._log(f"❌ REJECTED (ZERO LIQUIDITY): {stats.token_address}")
            return False

        if liquidity < min_liq:
            self._log(f"❌ REJECTED (LOW LIQUIDITY): {stats.token_address} - ${liquidity:,.0f} < ${min_liq:,.0f}")
            return False
        
        # Check maximum liquidity (counter-intuitive but data-driven!)
        max_liq = MAX_LIQUIDITY_USD or 0
        if max_liq > 0 and liquidity > max_liq:
            self._log(f"❌ REJECTED (LIQUIDITY TOO HIGH): {stats.token_address} - ${liquidity:,.0f} > ${max_liq:,.0f} (data shows 65% rug rate!)")
            return False

        # Log liquidity sweet spot
        if 30000 <= liquidity <= 50000:
            self._log(f"✅ LIQUIDITY SWEET SPOT: {stats.token_address} - ${liquidity:,.0f} ($30k-$50k zone - 26.5% 2x+ rate, 335% avg gain!)")
        else:
            quality = "EXCELLENT" if liquidity >= excellent_liq else "GOOD"
            self._log(f"✅ LIQUIDITY CHECK PASSED: {stats.token_address} - ${liquidity:,.0f} ({quality})")
        return True
    
    def _check_fomo_filter(self, stats: TokenStats, token_address: str) -> bool:
        """
        ANTI-FOMO FILTER: Reject tokens that already pumped too much.
        
        Goal: Catch tokens BEFORE they moon (5-50% momentum), not AFTER (>100% pump)
        
        Returns:
            True if token passes (early momentum), False if rejected (late entry)
        """
        from app.config_unified import MAX_24H_CHANGE_FOR_ALERT, MAX_1H_CHANGE_FOR_ALERT
        
        change_1h = stats.change_1h or 0
        change_24h = stats.change_24h or 0
        
        # DEBUG: Log actual values to diagnose FOMO filter
        self._log(f"🔍 FOMO CHECK: {token_address[:8]}... → 1h:{change_1h:.1f}%, 24h:{change_24h:.1f}% (threshold: {MAX_24H_CHANGE_FOR_ALERT:.0f}%)")
        
        # Handle NaN values
        if not (change_1h == change_1h):
            change_1h = 0
        if not (change_24h == change_24h):
            change_24h = 0

        # Reject if already dumped significantly (>60% in 24h) - dead token!
        # FIXED: Use DRAW_24H_MAJOR config instead of hardcoded -30%
        from app.config_unified import DRAW_24H_MAJOR
        if change_24h < DRAW_24H_MAJOR:
            self._log(f"❌ REJECTED (MAJOR DUMP): {token_address} - {change_24h:.1f}% in 24h (already crashed!)")
            return False

        # Reject if already pumped >150% in 24h (late entry!)
        if change_24h > MAX_24H_CHANGE_FOR_ALERT:
            self._log(f"❌ REJECTED (LATE ENTRY - 24H PUMP): {token_address} - {change_24h:.1f}% > {MAX_24H_CHANGE_FOR_ALERT:.0f}% (already mooned!)")
            return False

        # Reject if already pumped >300% in 1h (extreme late entry!)
        if change_1h > MAX_1H_CHANGE_FOR_ALERT:
            self._log(f"❌ REJECTED (LATE ENTRY - 1H PUMP): {token_address} - {change_1h:.1f}% > {MAX_1H_CHANGE_FOR_ALERT:.0f}% (extreme pump!)")
            return False
        
        # Log entry type for monitoring (CRITICAL: Must log for debugging!)
        try:
            if 5 <= change_24h <= 50:
                self._log(f"✅ EARLY MOMENTUM: {token_address} - {change_24h:.1f}% (ideal entry zone!)")
            elif change_24h > 50:
                self._log(f"⚠️  MODERATE PUMP: {token_address} - {change_24h:.1f}% (getting late, but within limits)")
            else:
                self._log(f"✅ FOMO CHECK PASSED: {token_address} - {change_24h:.1f}% in 24h")
        except Exception as e:
            # Log the error to debug formatting issues
            self._log(f"⚠️  ERROR in FOMO log formatting: {e} (change_24h={change_24h})")
        
        return True
    
    def _check_market_cap_range(self, stats: TokenStats, token_address: str) -> bool:
        """
        Check if market cap is within optimal range for 2x+ gains
        DATA-DRIVEN: <$50k = 63.9% rug rate, $50k-$100k = 28.8% 2x+ rate (best!)
        """
        from app.config_unified import MIN_MARKET_CAP_USD, MAX_MARKET_CAP_FOR_DEFAULT_ALERT
        
        market_cap = stats.market_cap_usd or 0
        
        if market_cap <= 0:
            self._log(f"❌ REJECTED (NO MARKET CAP DATA): {token_address}")
            return False
        
        # Reject if below minimum (avoid <$50k death zone with 63.9% rug rate)
        if market_cap < MIN_MARKET_CAP_USD:
            self._log(f"❌ REJECTED (MARKET CAP TOO LOW): {token_address} - ${market_cap:,.0f} < ${MIN_MARKET_CAP_USD:,.0f} (death zone - 63.9% rug rate!)")
            return False
        
        # Reject if above maximum (stay in sweet spot)
        if market_cap > MAX_MARKET_CAP_FOR_DEFAULT_ALERT:
            self._log(f"❌ REJECTED (MARKET CAP TOO HIGH): {token_address} - ${market_cap:,.0f} > ${MAX_MARKET_CAP_FOR_DEFAULT_ALERT:,.0f}")
            return False
        
        # Log entry in sweet spot
        if MIN_MARKET_CAP_USD <= market_cap <= 100000:
            self._log(f"✅ MARKET CAP SWEET SPOT: {token_address} - ${market_cap:,.0f} ($50k-$100k zone - 28.8% 2x+ rate!)")
        else:
            self._log(f"✅ MARKET CAP OK: {token_address} - ${market_cap:,.0f}")
        
        return True
    
    def _check_quick_security(self, stats: TokenStats, require_lp: bool, require_mint: bool, allow_unknown: bool) -> bool:
        """Quick security checks before detailed scoring"""
        lp_locked = stats.is_lp_locked
        mint_revoked = stats.is_mint_revoked
        
        if require_lp and (lp_locked is False or (lp_locked is None and not allow_unknown)):
            self._log(f"REJECTED (Quick Security: LP not locked): {stats.token_address}")
            return False
        
        if require_mint and (mint_revoked is False or (mint_revoked is None and not allow_unknown)):
            self._log(f"REJECTED (Quick Security: Mint not revoked): {stats.token_address}")
            return False
        
        return True
    
    def _apply_ml_enhancement(self, score: int, stats: dict, smart_money: bool, conviction: str, details: list) -> int:
        """Apply ML score enhancement if available"""
        try:
            from app.ml_scorer import get_ml_scorer
            ml_scorer = get_ml_scorer()
            if ml_scorer.is_available():
                enhanced_score, ml_reason = ml_scorer.enhance_score(score, stats, smart_money, conviction)
                if enhanced_score != score:
                    self._log(f"  🤖 ML Adjustment: {score} → {enhanced_score} ({ml_reason})")
                    details.append(f"ML: {ml_reason}")
                    return enhanced_score
        except Exception as e:
            self._log(f"⚠️  ML enhancement failed: {e}")
        return score
    
    def _send_alert(
        self,
        token_address: str,
        stats: TokenStats,
        score: int,
        prelim_score: int,
        conviction: str,
        details: list,
        feed_tx: FeedTransaction,
        jr_strict_ok: bool,
        trader: Optional[str]
    ) -> bool:
        """Generate and send alert via all configured channels"""
        # Build alert message
        message = self._build_alert_message(token_address, stats, score, conviction, details)

        # Throttle alerts
        from app.config_unified import TELEGRAM_ALERT_MIN_INTERVAL
        import os
        
        if TELEGRAM_ALERT_MIN_INTERVAL and TELEGRAM_ALERT_MIN_INTERVAL > 0:
            now_ts = time.time()
            delta = now_ts - self._last_alert_time
            if self._last_alert_time > 0 and delta < TELEGRAM_ALERT_MIN_INTERVAL:
                wait_s = int(TELEGRAM_ALERT_MIN_INTERVAL - delta)
                self._log(f"Throttling alerts; waiting {wait_s}s")
                time.sleep(wait_s)
            self._last_alert_time = time.time()
        
        # Send via Telegram
        telegram_ok = False
        if os.getenv('DRY_RUN', 'false').strip().lower() != 'true':
            try:
                telegram_ok = send_telegram_alert(message)
            except Exception as e:
                log_process({
                    "type": "alert_error",
                    "channel": "telegram",
                    "error": str(e),
                })
        
        # Send to group via Telethon
        if os.getenv('DRY_RUN', 'false').strip().lower() != 'true':
            try:
                send_group_message(message)
            except Exception as e:
                log_process({
                    "type": "alert_error",
                    "channel": "telethon",
                    "error": str(e),
                })
        
        # Mark as alerted
        mark_alerted(token_address, score, feed_tx.smart_money, conviction)
        
        # Record comprehensive metadata
        self._record_alert_metadata(
            token_address,
            prelim_score,
            score,
            conviction,
            stats,
            jr_strict_ok,
            trader,
            feed_tx
        )
        
        # Push to Redis for traders
        self._push_to_redis(token_address, stats, score, prelim_score, conviction, feed_tx.smart_money)
        
        # Log alert
        self._log_alert_event(token_address, stats, score, prelim_score, conviction, feed_tx)
        
        self._log(f"Alert for token {token_address} (Final: {score}/10, Prelim: {prelim_score}/10, telegram_ok={telegram_ok})")
        
        return True
    
    def _build_alert_message(self, token_address: str, stats: TokenStats, score: int, conviction: str, details: list) -> str:
        """Build HTML alert message"""
        name = html.escape(stats.name or "Token")
        symbol = html.escape(stats.symbol or "?")
        price = stats.price_usd or 0
        market_cap = stats.market_cap_usd or 0
        liquidity = stats.liquidity_usd or 0
        volume_24h = stats.volume_24h_usd or 0
        change_1h = stats.change_1h or 0
        change_24h = stats.change_24h or 0
        
        chart_link = f"https://dexscreener.com/solana/{token_address}?t={int(time.time())}"
        swap_link = f"https://raydium.io/swap/?inputMint=So11111111111111111111111111111111111111112&outputMint={token_address}"
        
        # Build badges
        badges = []
        if stats.is_mint_revoked is True:
            badges.append("✅ Mint Revoked")
        elif stats.is_mint_revoked is False:
            badges.append("⚠️ Mintable")
        if stats.is_lp_locked is True:
            badges.append("✅ LP Locked/Burned")
        elif stats.is_lp_locked is False:
            badges.append("⚠️ LP Unlocked")
        top10 = stats.top_10_concentration_percent or 0
        if top10:
            badges.append(f"{'⚠️ ' if top10 > 40 else ''}Top10 {top10:.1f}%")
        badges_text = " | ".join(badges) if badges else ""
        
        parts = []
        parts.append(f"<b>{name} (${symbol})</b>\n\n")
        parts.append("Fresh signal on Solana.\n\n")
        parts.append(f"💰 <b>MCap:</b> ${market_cap:,.0f}\n")
        parts.append(f"💧 <b>Liquidity:</b> ${liquidity:,.0f}\n")
        if badges_text:
            parts.append(f"{badges_text}\n")
        parts.append(f"📈 <b>Chart:</b> <a href='{chart_link}'>DexScreener</a>\n")
        parts.append(f"🔁 <b>Swap:</b> <a href='{swap_link}'>Raydium</a>\n\n")
        parts.append(f"{html.escape(token_address)}\n")
        parts.append("━━━━━━━━━━━━━━━\n")
        parts.append(f"📊 <b>Score:</b> {score}/10\n")
        parts.append(f"💸 <b>24h Vol:</b> ${volume_24h:,.0f}\n")
        parts.append(f"💰 <b>Price:</b> ${float(price):.8f}\n")
        parts.append(f"⏱ <b>1h Change:</b> {float(change_1h):+.1f}%\n")
        parts.append(f"📆 <b>24h Change:</b> {float(change_24h):+.1f}%\n")
        parts.append("━━━━━━━━━━━━━━━")
        message = "".join(parts)
        message += f"\n<b>Conviction:</b> {conviction}"
        message += "\n<b>Scoring Analysis:</b>\n"
        for detail in details[:4]:
            clean_detail = detail.replace("✅ ", "").replace("⚡ ", "").replace("🟡 ", "").replace("❌ ", "")
            message += f"  - {clean_detail}\n"
        message += f"\n<b>Alert Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    def _record_alert_metadata(self, token_address: str, prelim: int, score: int, conviction: str, 
                               stats: TokenStats, jr_strict_ok: bool, trader: Optional[str], feed_tx: FeedTransaction):
        """Record comprehensive alert metadata"""
        try:
            token_age_minutes = None
            try:
                all_obs = get_recent_token_signals(token_address, 365*24*3600)
                if all_obs:
                    first_seen = all_obs[-1]
                    first_dt = datetime.strptime(first_seen, '%Y-%m-%d %H:%M:%S')
                    token_age_minutes = (datetime.now() - first_dt).total_seconds() / 60.0
            except Exception:
                pass
            
            alert_metadata = {
                'token_age_minutes': token_age_minutes,
                'unique_traders_15m': None,
                'smart_money_involved': feed_tx.smart_money,
                'smart_wallet_address': trader if feed_tx.smart_money else None,
                'smart_wallet_pnl': None,
                'velocity_score_15m': None,
                'velocity_bonus': 0,
                'passed_junior_strict': jr_strict_ok,
                'passed_senior_strict': True,
                'passed_debate': conviction == "Nuanced Conviction",
                'sol_price_usd': None,
                'feed_source': stats.source,
                'dex_name': feed_tx.dex,
            }
            
            record_alert_with_metadata(
                token_address=token_address,
                preliminary_score=prelim,
                final_score=score,
                conviction_type=conviction,
                stats=stats.raw_data,
                alert_metadata=alert_metadata
            )
        except Exception as e:
            self._log(f"Warning: Could not record alert metadata: {e}")
    
    def _push_to_redis(self, token: str, stats: TokenStats, score: int, prelim: int, conviction: str, smart: bool):
        """Push signal to Redis for real-time trader consumption"""
        try:
            signal_payload = {
                "ca": token,
                "token": token,
                "name": stats.name,
                "symbol": stats.symbol,
                "score": score,
                "prelim_score": prelim,
                "conviction_type": conviction,
                "price": float(stats.price_usd or 0),
                "market_cap": stats.market_cap_usd,
                "liquidity": stats.liquidity_usd,
                "liquidity_usd": stats.liquidity_usd,
                "volume_24h": stats.volume_24h_usd,
                "change_1h": stats.change_1h,
                "change_24h": stats.change_24h,
                "smart_money_detected": bool(smart),
                "timestamp": time.time(),
            }
            push_signal_to_redis(signal_payload)
        except Exception as e:
            self._log(f"⚠️ Redis signal push failed: {e}")
    
    def _log_alert_event(self, token: str, stats: TokenStats, score: int, prelim: int, conviction: str, feed_tx: FeedTransaction):
        """Log enriched alert event"""
        try:
            log_alert({
                "token": token,
                "name": stats.name,
                "symbol": stats.symbol,
                "final_score": score,
                "prelim_score": prelim,
                "velocity_bonus": 0,
                "velocity_score_15m": None,
                "unique_traders_15m": None,
                "volume_24h": stats.volume_24h_usd,
                "market_cap": stats.market_cap_usd,
                "price": float(stats.price_usd or 0),
                "change_1h": stats.change_1h,
                "change_24h": stats.change_24h,
                "liquidity": stats.liquidity_usd,
                "conviction_type": conviction,
                "badges": [],
                "data_source": stats.source,
                "smart_cycle": feed_tx.smart_money,
                "smart_money_detected": feed_tx.smart_money,
            })
        except Exception:
            pass
    
    def _log_prelim_debug(self, tx: dict):
        """Log preliminary scoring debug info"""
        try:
            print("    ⤷ prelim_debug: " + str({
                'usd_value': round(tx.get('usd_value', 0) or 0, 2),
                'token0_usd': round(tx.get('token0_amount_usd', 0) or 0, 2),
                'token1_usd': round(tx.get('token1_amount_usd', 0) or 0, 2),
                'tx_type': tx.get('tx_type'),
                'dex': tx.get('dex')
            }))
        except Exception:
            pass
    
    def _log(self, message: str):
        """Simple logging wrapper"""
        try:
            print(message)
        except Exception:
            pass
    
    @property
    def api_calls_saved(self) -> int:
        """Get count of API calls saved by preliminary filtering"""
        return self._api_calls_saved
    
    def reset_session_state(self):
        """Reset session-specific state (for testing)"""
        self._session_alerted_tokens.clear()
        self._last_alert_time = 0.0
        self._api_calls_saved = 0

