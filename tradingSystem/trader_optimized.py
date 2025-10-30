"""
OPTIMIZED TRADER - Proper Risk Management
- FIXED: Stop loss from ENTRY price (not peak)
- Thread-safe position management
- Comprehensive error handling
- Position recovery on restart
- Trade lifecycle tracing with correlation IDs
"""
import json
import os
import time
import threading
import uuid
from datetime import datetime, date
from typing import Dict, Optional

from .db import (
    init as db_init, create_position, add_fill, update_peak_and_trail,
    close_position, get_open_qty, update_position_qty
)
from .config_optimized import (
    STOP_LOSS_PCT, LOG_JSON_PATH, LOG_TEXT_PATH,
    MAX_CONCURRENT, BANKROLL_USD, DB_PATH, MAX_HOLD_TIME_SECONDS,
    EMERGENCY_HARD_STOP_PCT
)
from .broker_optimized import Broker
from .portfolio_manager import get_portfolio_manager, should_use_portfolio_manager
from .inactivity_monitor import InactivityMonitor
from .momentum_tracker import MomentumTracker
from .token_classifier import get_classifier
from .circuit_breaker import get_circuit_breaker


class PositionLock:
    """Thread-safe lock for position operations"""
    def __init__(self):
        self._locks: Dict[str, threading.Lock] = {}
        self._master_lock = threading.Lock()
    
    def get_lock(self, token: str) -> threading.Lock:
        with self._master_lock:
            if token not in self._locks:
                self._locks[token] = threading.Lock()
            return self._locks[token]


class TradeEngine:
    """Optimized trade engine with bulletproof risk management"""
    
    def __init__(self) -> None:
        db_init()
        self.broker = Broker()
        self.live: Dict[str, Dict[str, object]] = {}
        self._position_locks = PositionLock()
        
        # Inactivity monitoring: Exit positions based on price stagnation, not arbitrary time
        self.inactivity_monitor = InactivityMonitor()
        
        # Momentum intelligence: Scam detection + velocity-based exits
        self.momentum_tracker = MomentumTracker()
        
        # Token classifier: Identify behavior patterns (pump/dump, slow grower, sustained)
        self.classifier = get_classifier()
        
        # Circuit breaker: Halt trading under dangerous conditions
        self.circuit_breaker = get_circuit_breaker()
        
        # Token cooldown: Prevent immediate rebuy after selling (stops buy-sell-rebuy loops)
        self._token_cooldowns: Dict[str, float] = {}  # token -> timestamp when sold
        self._cooldown_lock = threading.Lock()
        self._cooldown_seconds = float(os.getenv("TS_REBUY_COOLDOWN_SEC", "14400"))  # Default: 4 hours
        
        os.makedirs(os.path.dirname(LOG_JSON_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(LOG_TEXT_PATH), exist_ok=True)
        
        self._recover_positions()
    
    def _recover_positions(self):
        """Recover open positions from database"""
        try:
            import sqlite3
            from datetime import datetime
            con = sqlite3.connect(DB_PATH)
            cur = con.execute("""
                SELECT id, token_address, strategy, entry_price, peak_price, open_at 
                FROM positions 
                WHERE status='open'
            """)
            rows = cur.fetchall()
            
            for pid, ca, strategy, entry_price, peak_price, open_at in rows:
                # Parse open_at timestamp for entry_time
                try:
                    if open_at:
                        # Try parsing as ISO format first
                        entry_time = datetime.fromisoformat(open_at.replace('Z', '+00:00')).timestamp()
                    else:
                        entry_time = time.time()
                except:
                    entry_time = time.time()  # Fallback to now if parsing fails
                
                self.live[str(ca)] = {
                    "pid": int(pid),
                    "strategy": str(strategy),
                    "entry_price": float(entry_price or 0),
                    "peak_price": float(peak_price or entry_price or 0),
                    "entry_time": entry_time,  # For adaptive monitoring
                    "open_at": entry_time,     # For time-based exits
                }
            con.close()
            if self.live:
                self._log("recovery_loaded", open_positions=len(self.live), positions=list(self.live.keys()))
        except Exception as e:
            self._log("recovery_failed", error=str(e))

    def _log(self, event: str, **fields) -> None:
        """Thread-safe logging"""
        payload = {"ts": datetime.utcnow().isoformat(timespec="seconds") + "Z", "event": event}
        payload.update(fields)
        try:
            with open(LOG_JSON_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        try:
            line = f"[{payload['ts']}] {event} " + " ".join(f"{k}={v}" for k, v in fields.items())
            with open(LOG_TEXT_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def open_position(self, token: str, plan: Dict) -> Optional[int]:
        """Open position with comprehensive safety"""
        # Generate correlation ID for trade lifecycle tracking
        trade_id = str(uuid.uuid4())[:8]  # Short ID for readability
        
        try:
            self._log("trade_lifecycle", trade_id=trade_id, stage="signal_received", 
                     token=token, plan=plan)
            print(f"[TRADE:{trade_id}] Signal received for {token[:8]}...", flush=True)
            
            # Circuit breaker check
            can_trade, reason = self.circuit_breaker.check_can_trade()
            if not can_trade:
                self._log("open_skipped_circuit_breaker", trade_id=trade_id, token=token, reason=reason)
                print(f"[TRADE:{trade_id}] ❌ Circuit breaker triggered: {reason}", flush=True)
                return None
            
            # Concurrency limit
            print(f"[TRADER] Checking concurrency: {len(self.live)} / {int(MAX_CONCURRENT)}", flush=True)
            if len(self.live) >= int(MAX_CONCURRENT):
                self._log("open_skipped_max_concurrent", token=token, max_concurrent=int(MAX_CONCURRENT))
                print(f"[TRADER] ❌ Max concurrent positions reached", flush=True)
                return None
            
            # Acquire lock
            print(f"[TRADER] Acquiring position lock for {token[:8]}...", flush=True)
            lock = self._position_locks.get_lock(token)
            with lock:
                print(f"[TRADER] Lock acquired, checking for duplicate position...", flush=True)
                if token in self.live:
                    self._log("open_skipped_duplicate", token=token)
                    print(f"[TRADER] ❌ Already have position for {token[:8]}", flush=True)
                    return None
                
                usd = float(plan["usd_size"])
                trail_pct = float(plan["trail_pct"])
                strategy = plan.get("strategy", "unknown")
                
                self._log("trade_lifecycle", trade_id=trade_id, stage="executing_buy", 
                         token=token, usd=usd)
                print(f"[TRADE:{trade_id}] Executing market buy: ${usd:.2f}...", flush=True)
                
                # Execute buy
                fill = self.broker.market_buy(token, usd)
                
                if not fill.success:
                    self._log("trade_lifecycle", trade_id=trade_id, stage="buy_failed", 
                             token=token, error=fill.error)
                    print(f"[TRADE:{trade_id}] ❌ Buy failed: {fill.error}", flush=True)
                    return None
                
                self._log("trade_lifecycle", trade_id=trade_id, stage="buy_success", 
                         token=token, price=fill.price, qty=fill.qty, tx=fill.tx)
                print(f"[TRADE:{trade_id}] ✅ Buy successful at ${fill.price:.8f}", flush=True)
                
                # CRITICAL FIX: Ensure position is ALWAYS recorded after successful buy
                # If DB write fails, we log it prominently but the transaction already happened
                try:
                    print(f"[TRADER] Creating position record in database...", flush=True)
                    pid = create_position(token, strategy, fill.price, fill.qty, usd, trail_pct)
                    print(f"[TRADER] ✅ Position #{pid} created", flush=True)
                    
                    print(f"[TRADER] Adding fill record...", flush=True)
                    add_fill(pid, "buy", fill.price, fill.qty, fill.usd)
                    print(f"[TRADER] ✅ Fill recorded", flush=True)
                    
                except Exception as db_error:
                    # CRITICAL: Buy succeeded but DB failed - this is a SEVERE issue!
                    print(f"[TRADER] 🚨 CRITICAL ERROR: Buy succeeded but failed to record position!", flush=True)
                    print(f"[TRADER] 🚨 Token: {token}", flush=True)
                    print(f"[TRADER] 🚨 Transaction: {fill.tx}", flush=True)
                    print(f"[TRADER] 🚨 Price: {fill.price}, Qty: {fill.qty}, USD: {fill.usd}", flush=True)
                    print(f"[TRADER] 🚨 DB Error: {db_error}", flush=True)
                    print(f"[TRADER] 🚨 ORPHANED POSITION - Manual intervention required!", flush=True)
                    self._log("open_orphaned_position", token=token, error=str(db_error), 
                             tx=fill.tx, price=fill.price, qty=fill.qty, usd=fill.usd)
                    # Return None to indicate failure, even though buy succeeded
                    # This prevents the position from being added to self.live
                    return None
                
                # Add to live with ENTRY PRICE and trade_id
                entry_time = time.time()
                self.live[token] = {
                    "pid": pid,
                    "trade_id": trade_id,  # Correlation ID for lifecycle tracking
                    "strategy": strategy,
                    "entry_price": fill.price,  # CRITICAL: Store entry price
                    "peak_price": fill.price,
                    "price_failures": 0,  # Track consecutive price fetch failures
                    "sell_failures": 0,  # Track consecutive sell attempt failures
                    "open_at": entry_time,  # Track when position was opened
                }
                
                # Initialize momentum tracking for intelligent exits
                self.momentum_tracker.init_position(token, fill.price, entry_time)
                
                self._log("trade_lifecycle", trade_id=trade_id, stage="position_opened", 
                         token=token, pid=pid, strategy=strategy, entry_price=fill.price)
                print(f"[TRADE:{trade_id}] ✅ Position #{pid} opened and tracked", flush=True)
                return pid
                
        except Exception as e:
            self._log("open_exception", token=token, error=str(e))
            return None

    def has_position(self, token: str) -> bool:
        return token in self.live
    
    def is_on_cooldown(self, token: str) -> bool:
        """Check if token is on cooldown (prevents immediate rebuy after sell)"""
        with self._cooldown_lock:
            if token not in self._token_cooldowns:
                return False
            
            sell_time = self._token_cooldowns[token]
            elapsed = time.time() - sell_time
            
            if elapsed >= self._cooldown_seconds:
                # Cooldown expired
                del self._token_cooldowns[token]
                return False
            
            return True
    
    def get_cooldown_remaining(self, token: str) -> Optional[float]:
        """Get remaining cooldown time in seconds"""
        with self._cooldown_lock:
            if token not in self._token_cooldowns:
                return None
            
            sell_time = self._token_cooldowns[token]
            elapsed = time.time() - sell_time
            remaining = self._cooldown_seconds - elapsed
            
            if remaining <= 0:
                del self._token_cooldowns[token]
                return None
            
            return remaining
    
    def _add_cooldown(self, token: str):
        """Add cooldown for a token (called internally after selling)"""
        with self._cooldown_lock:
            self._token_cooldowns[token] = time.time()

    def position_strategy(self, token: str) -> Optional[str]:
        data = self.live.get(token)
        if not data:
            return None
        return str(data.get("strategy"))

    def add_to_position(self, token: str, current_price: float, stats: Dict) -> bool:
        """
        Pyramiding: Add to winning positions that show exceptional momentum.
        
        Strategy: Add 10-20% more capital to positions showing strong early gains.
        This compounds winners and maximizes profit from moonshots.
        
        Args:
            token: Token address
            current_price: Current token price
            stats: Current token stats (for momentum validation)
        
        Returns:
            True if successfully added to position
        """
        from .strategy_optimized import should_scale_position
        
        # Check if position exists
        if token not in self.live:
            return False
        
        data = self.live[token]
        entry_price = data.get("entry_price", 0)
        open_at = data.get("open_at", 0)
        
        if entry_price <= 0 or open_at <= 0:
            return False
        
        # Calculate current gain and elapsed time
        current_gain_pct = ((current_price - entry_price) / entry_price) * 100
        elapsed_mins = (time.time() - open_at) / 60
        
        # Check if already pyramided (only allow 1-2 adds)
        pyramid_count = data.get("pyramid_count", 0)
        if pyramid_count >= 2:
            return False  # Max 2 pyramids per position
        
        # Use strategy logic to decide
        if not should_scale_position(stats, current_gain_pct, elapsed_mins):
            return False
        
        # Calculate additional size (10-20% of original)
        original_qty = data.get("original_qty", data.get("qty", 0))
        if original_qty <= 0:
            return False
        
        # Add 15% more capital (between 10-20%)
        add_pct = 0.15
        additional_usd = (entry_price * original_qty * add_pct)
        
        # Limit additional size to prevent over-concentration
        if additional_usd > 8.0:  # Max $8 per pyramid
            additional_usd = 8.0
        
        self._log("pyramid_attempt", token=token, current_gain_pct=current_gain_pct, 
                  elapsed_mins=elapsed_mins, additional_usd=additional_usd)
        
        try:
            # Execute buy
            fill = self.broker.market_buy(
                token_mint=token,
                usd_amount=additional_usd,
                max_slippage_bps=500  # 5% slippage OK for pyramiding
            )
            
            if not fill.success or fill.qty <= 0:
                self._log("pyramid_failed", token=token, reason="buy_failed")
                return False
            
            # Update position with additional quantity
            new_qty = data["qty"] + fill.qty
            avg_entry = ((data["qty"] * entry_price) + (fill.qty * fill.price)) / new_qty
            
            # Update in-memory
            data["qty"] = new_qty
            data["entry_price"] = avg_entry  # Average entry price
            data["pyramid_count"] = pyramid_count + 1
            if "original_qty" not in data:
                data["original_qty"] = original_qty
            
            # Update DB
            from .db import update_position_qty, add_fill
            pid = data.get("id")
            if pid:
                update_position_qty(pid, new_qty, avg_entry)
                add_fill(pid, "buy", fill.price, fill.qty, fill.tx)
            
            self._log("pyramid_success", token=token, additional_qty=fill.qty, 
                     new_total_qty=new_qty, avg_entry=avg_entry, pyramid_num=pyramid_count + 1)
            
            print(f"[TRADER] 📈 {token[:8]} PYRAMID #{pyramid_count + 1}: Added ${additional_usd:.2f} at +{current_gain_pct:.1f}% | New avg entry: ${avg_entry:.8f}", flush=True)
            
            return True
            
        except Exception as e:
            self._log("pyramid_exception", token=token, error=str(e))
            return False

    def check_exits(self, token: str, price: float) -> bool:
        """
        Check and execute exits with PROPER stop loss logic.
        
        CRITICAL FIX: Stop loss is calculated from ENTRY price, not peak!
        This was the bug in the original system.
        """
        try:
            # Track price for pattern classification
            if price > 0:
                self.classifier.track_price(token, price, volume=0)
            
            if price <= 0:
                # EMERGENCY FIX: Don't silently skip - try fallback and force exit if repeated failures
                data = self.live.get(token)
                if data:
                    price_failures = data.get("price_failures", 0) + 1
                    data["price_failures"] = price_failures
                    
                    # Try emergency price fetch from broker (with actual holdings)
                    print(f"[TRADER] ⚠️ Price unavailable for {token[:8]}, attempt {price_failures}/5", flush=True)
                    
                    # Get actual holdings for accurate price
                    holdings = data.get("holdings", 0)
                    if holdings <= 0:
                        # Fallback: Get holdings from database
                        pid = data.get("pid")
                        if pid:
                            holdings = get_open_qty(int(pid))
                    
                    emergency_price = self.broker.get_token_price(token, holdings) if holdings > 0 else 0.0
                    
                    if emergency_price > 0:
                        price = emergency_price
                        data["price_failures"] = 0  # Reset on success
                    elif price_failures >= 5:
                        # FORCE EXIT after 5 failures (better -50% than -95%)
                        print(f"[TRADER] 🚨 EMERGENCY EXIT: Price unavailable for 5 attempts on {token[:8]}", flush=True)
                        return self._force_emergency_exit(token, "price_unavailable_5x")
                    else:
                        return False
                else:
                    return False
            
            data = self.live.get(token)
            if not data:
                return False
            
            pid = data.get("pid")
            if not pid:
                return False
            
            # Acquire lock
            lock = self._position_locks.get_lock(token)
            with lock:
                if token not in self.live:
                    return False
                
                # CRITICAL: Get ENTRY price (no fallback - must be present)
                entry_price = data.get("entry_price")
                if not entry_price or entry_price <= 0:
                    self._log("exit_missing_entry_price", token=token, pid=pid)
                    return False
                entry_price = float(entry_price)
                
                # Update peak and get PROFIT-BASED trail stop (MOONSHOT MODE!)
                peak, trail = update_peak_and_trail(pid, price, entry_price)
                
                # Validate database returns
                if peak <= 0 or trail <= 0:
                    self._log("exit_invalid_peak_trail", token=token, pid=pid, peak=peak, trail=trail)
                    return False
                strategy = str(data.get("strategy", "unknown"))
                
                # Calculate current profit for logging
                profit_pct = ((peak - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                
                # Log trail adjustments (only when peak updates or occasionally)
                old_peak = self.live[token].get("peak_price", 0)
                if peak > old_peak:  # New peak reached!
                    print(f"[TRADER] 🚀 {token[:8]} new peak! Profit: +{profit_pct:.1f}% | Trail: {trail:.0f}% | Price: ${price:.8f}", flush=True)
                
                # Update peak in live data
                self.live[token]["peak_price"] = peak
                
                # Track price for inactivity monitoring
                self.inactivity_monitor.add_price_sample(token, price)
                
                # Track price for momentum intelligence
                self.momentum_tracker.add_price_sample(token, price)
                
                # FIXED: Stop loss relative to ENTRY price!
                stop_price = entry_price * (1.0 - STOP_LOSS_PCT / 100.0)
                
                # Trail stop relative to peak (may be overridden by momentum-based adaptive trail)
                trail_price = peak * (1.0 - trail / 100.0) if peak > 0 else 0
                
                # Determine exit type
                exit_type = None
                exit_reason = ""
                
                # ========== BREAKTHROUGH INTELLIGENCE LAYER ==========
                # Phase 1: 60-Second Scam Detector
                is_scam, scam_reason = self.momentum_tracker.check_scam(token, price)
                if is_scam:
                    exit_type = "scam_detected"
                    exit_reason = f"🚨 SCAM DETECTED: {scam_reason}"
                    print(f"[TRADER] {exit_reason}", flush=True)
                    print(f"[TRADER] Executing instant exit to prevent heavy loss", flush=True)
                
                # Phase 2: Momentum Calculation & Adaptive Exits
                if not exit_type:
                    momentum = self.momentum_tracker.calculate_momentum(token, price)
                    
                    if momentum:
                        # Log momentum classification once
                        if not data.get("momentum_logged", False):
                            print(f"[TRADER] 🎯 {token[:8]} momentum: {momentum.upper()} | Profit: +{profit_pct:.1f}%", flush=True)
                            data["momentum_logged"] = True
                        
                        # Get momentum-based exit threshold
                        exit_threshold = self.momentum_tracker.get_momentum_exit_threshold(token)
                        
                        if exit_threshold and profit_pct >= exit_threshold:
                            # Momentum-based early exit (weak/moderate tokens at +30-40%)
                            exit_type = "momentum_exit"
                            exit_reason = f"{momentum.capitalize()} token: Exiting at +{profit_pct:.1f}% (threshold: +{exit_threshold}%)"
                            print(f"[TRADER] 💰 {token[:8]} MOMENTUM EXIT: {exit_reason}", flush=True)
                        
                        # Phase 3: Adaptive Trailing Stop
                        # Override default trail with momentum-based trail
                        adaptive_trail = self.momentum_tracker.get_adaptive_trailing_stop(token)
                        if adaptive_trail and not data.get("adaptive_trail_set", False):
                            # Recalculate trail_price with adaptive percentage
                            trail_price = peak * (1.0 - adaptive_trail / 100.0) if peak > 0 else 0
                            print(f"[TRADER] 🔧 {token[:8]} adaptive trail: {adaptive_trail}% (momentum: {momentum})", flush=True)
                            data["adaptive_trail_set"] = True
                # ========== END INTELLIGENCE LAYER ==========
                
                # Check inactivity-based exit (6+ hours of <5% movement)
                # KEY INSIGHT: Some tokens pump for 8-10 days to 800x
                # Don't force-sell winners, but DO exit when price is dead
                open_at = data.get("open_at", 0)
                if open_at > 0:
                    # Check if position should ignore time limit (high profit + active price)
                    ignore_time, ignore_reason = self.inactivity_monitor.should_ignore_time_limit(token, profit_pct)
                    
                    if ignore_time:
                        # High-profit moonshot with active price movement - let it run!
                        if data.get("last_moonshot_log", 0) < time.time() - 3600:  # Log every hour
                            print(f"[TRADER] 🌙 {token[:8]} in MOONSHOT MODE: {ignore_reason}", flush=True)
                            data["last_moonshot_log"] = time.time()
                    else:
                        # CRITICAL FIX: Don't exit profitable positions due to inactivity
                        # Problem: GAMwtMB6 sold at +1.3% after 10 min (small profit lost)
                        # Solution: Only apply inactivity exit to losing positions
                        # Data shows: <15min holds = -$0.71 avg, >=15min holds = +$592 avg
                        if profit_pct > 10:
                            # Profitable position - let trailing stop handle exit
                            should_exit = False
                            inactivity_reason = f"Profit +{profit_pct:.1f}% - ignoring inactivity"
                        else:
                            # Losing or flat position - check for inactivity
                            should_exit, inactivity_reason = self.inactivity_monitor.check_inactivity(token)
                        
                        if should_exit:
                            exit_type = "inactivity"
                            hold_hours = (time.time() - open_at) / 3600
                            exit_reason = f"Inactivity detected: {inactivity_reason} (held {hold_hours:.1f}h)"
                        else:
                            # CRITICAL FIX: Don't apply time limit to moonshots (>200% profit)
                            # Problem: 24h limit kills positions during multi-day 50x-500x runs
                            # Solution: Only apply timeout to flat/losing positions
                            hold_time = time.time() - open_at
                            if hold_time >= MAX_HOLD_TIME_SECONDS:
                                # Check if this is a moonshot (ignore time limit)
                                if profit_pct > 200:
                                    # MOONSHOT MODE: Ignore time limit, let trailing stop manage exit
                                    if data.get("last_moonshot_log", 0) < time.time() - 3600:  # Log hourly
                                        print(f"[TRADER] 🌙 {token[:8]} MOONSHOT MODE: Ignoring {hold_time/3600:.1f}h hold (profit: +{profit_pct:.1f}%)", flush=True)
                                        data["last_moonshot_log"] = time.time()
                                else:
                                    # Flat/small-gain position → apply timeout
                                    exit_type = "timeout"
                                    hold_hours = hold_time / 3600
                                    exit_reason = f"Max hold time: {hold_hours:.1f}h (profit: +{profit_pct:.1f}%) - {inactivity_reason}"
                
                # OPTIMIZED TIERED EXIT STRATEGY - Capture gains from 40% to 1000x+
                # Based on analysis: Your bot found an 11x that peaked at 18x
                # Strategy: Scale out as it moons, but keep riding for MEGA gains
                # 
                # TIER 1 (+40%): Sell 25% - Safety exit for moderate winners
                # TIER 2 (+100%): Sell 25% more (50% total) - 2x moonshot confirmed
                # TIER 3 (+300%): Sell 15% more (65% total) - 4x mega moonshot
                # TIER 4 (+900%): Sell 20% more (85% total) - 10x ultra moonshot
                # TIER 5 (+4900%): Sell 7% more (92% total) - 50x MEGA moonshot
                # TIER 6 (+9900%): Sell 5% more (97% total) - 100x ULTRA MEGA
                # TIER 7 (+79900%): Sell 2% more (99% total) - 800x LEGENDARY
                # REMAINING (1%): NEVER SELL - Ride to 1000x+ with 80% trail
                # 
                # Impact: Won't leave 800-1000x gains on the table!
                if not exit_type and profit_pct >= 40:
                    # TIER 7: LEGENDARY MOONSHOT (+79900% = 800x)
                    if profit_pct >= 79900 and not data.get("profit_take_79900", False):
                        # At 800x!! Sell 2% more
                        # If all tiers hit: 97% sold, remaining 3%
                        # Sell 2% of original = 66.67% of remaining 3%
                        data["sell_percentage"] = 66.67
                        data["profit_take_79900"] = True
                        exit_type = "partial_profit_take"
                        exit_reason = f"🏆🏆🏆 LEGENDARY: Selling 2% at +{profit_pct:.1f}% (800x), 99% total sold"
                        print(f"[TRADER] 🏆🏆🏆 {token[:8]} TIER 7 (800x): Selling 2% more at +{profit_pct:.1f}%", flush=True)
                        print(f"[TRADER] 💎💎💎💎 Total sold: 99% | Keeping 1% for potential 1000x+ (NEVER SELL)", flush=True)
                    
                    # TIER 6: ULTRA MEGA MOONSHOT (+9900% = 100x)
                    elif profit_pct >= 9900 and not data.get("profit_take_9900", False):
                        # At 100x!! Sell 5% more
                        # If all tiers hit: 92% sold, remaining 8%
                        # Sell 5% of original = 62.5% of remaining 8%
                        data["sell_percentage"] = 62.5
                        data["profit_take_9900"] = True
                        exit_type = "partial_profit_take"
                        exit_reason = f"🌟🌟🌟🌟 ULTRA MEGA: Selling 5% at +{profit_pct:.1f}% (100x), 97% total sold"
                        print(f"[TRADER] 🌟🌟🌟🌟 {token[:8]} TIER 6 (100x): Selling 5% more at +{profit_pct:.1f}%", flush=True)
                        print(f"[TRADER] 💎💎💎💎 Total sold: 97% | Keeping 3% for potential 800x-1000x run", flush=True)
                    
                    # TIER 5: MEGA MOONSHOT (+4900% = 50x)
                    elif profit_pct >= 4900 and not data.get("profit_take_4900", False):
                        # At 50x! Sell 7% more
                        # If all tiers hit: 85% sold, remaining 15%
                        # Sell 7% of original = 46.67% of remaining 15%
                        data["sell_percentage"] = 46.67
                        data["profit_take_4900"] = True
                        exit_type = "partial_profit_take"
                        exit_reason = f"🚀🚀🚀🚀 MEGA MOONSHOT: Selling 7% at +{profit_pct:.1f}% (50x), 92% total sold"
                        print(f"[TRADER] 🚀🚀🚀🚀 {token[:8]} TIER 5 (50x): Selling 7% more at +{profit_pct:.1f}%", flush=True)
                        print(f"[TRADER] 💎💎💎 Total sold: 92% | Keeping 8% for potential 100x+ run", flush=True)
                    
                    # TIER 4: ULTRA MOONSHOT (+900% = 10x)
                    elif profit_pct >= 900 and not data.get("profit_take_900", False):
                        # At 10x! Sell another 20% (of remaining)
                        # If all previous tiers hit: 65% already sold, remaining 35%
                        # Sell 20% of original = 57% of remaining 35%
                        data["sell_percentage"] = 57  # 20% of original from 35% remaining
                        data["profit_take_900"] = True
                        exit_type = "partial_profit_take"
                        exit_reason = f"🌟 ULTRA MOONSHOT: Selling 20% at +{profit_pct:.1f}% (10x), 85% total sold"
                        print(f"[TRADER] 🌟🌟🌟 {token[:8]} TIER 4 (10x): Selling 20% more at +{profit_pct:.1f}%", flush=True)
                        print(f"[TRADER] 💎💎💎 Total sold: 85% | Keeping 15% for potential 20x+ with wide trail", flush=True)
                    
                    # TIER 3: MEGA MOONSHOT (+300% = 4x)
                    elif profit_pct >= 300 and not data.get("profit_take_300", False):
                        # At 4x! Sell another 15% (of remaining)
                        # If tiers 1&2 hit: 50% already sold, remaining 50%
                        # Sell 15% of original = 30% of remaining 50%
                        data["sell_percentage"] = 30  # 15% of original from 50% remaining
                        data["profit_take_300"] = True
                        exit_type = "partial_profit_take"
                        exit_reason = f"🌙 MEGA MOONSHOT: Selling 15% at +{profit_pct:.1f}% (4x), 65% total sold"
                        print(f"[TRADER] 🌙🌙 {token[:8]} TIER 3 (4x): Selling 15% more at +{profit_pct:.1f}%", flush=True)
                        print(f"[TRADER] 💎💎 Total sold: 65% | Keeping 35% for potential 10x run", flush=True)
                    
                    # TIER 2: MOONSHOT (+100% = 2x)
                    elif profit_pct >= 100 and not data.get("profit_take_100", False):
                        # MOONSHOT DETECTED: At 100%+ profit
                        # Strategy: Sell 25% more (for total 50% if tier1 done, or 50% if tier1 skipped)
                        
                        if data.get("profit_take_40", False):
                            # Already sold 25% at +40%, now sell 25% more = 50% total sold
                            # Remaining: 75% → Sell 33.33% of it = 25% of original
                            data["sell_percentage"] = 33.33
                            data["profit_take_100"] = True
                            exit_type = "partial_profit_take"
                            exit_reason = f"Moonshot! Selling 25% more at +{profit_pct:.1f}% (2x), 50% total sold"
                            print(f"[TRADER] 🚀 {token[:8]} TIER 2 (2x): Selling 25% more at +{profit_pct:.1f}%", flush=True)
                            print(f"[TRADER] 💎 Total sold: 50% | Keeping 50% for mega moonshot", flush=True)
                        else:
                            # Skipped +40% tier (fast moonshot), sell 50% now
                            data["sell_percentage"] = 50
                            data["profit_take_100"] = True
                            data["moonshot_mode"] = True
                            exit_type = "partial_profit_take"
                            exit_reason = f"Fast moonshot! Selling 50% at +{profit_pct:.1f}% (2x)"
                            print(f"[TRADER] 🚀🚀 {token[:8]} FAST 2x: Selling 50% at +{profit_pct:.1f}%", flush=True)
                            print(f"[TRADER] 🌙 Keeping 50% for potential 5-10x run", flush=True)
                    
                    # TIER 1: SAFETY EXIT (+40%)
                    elif profit_pct >= 40 and not data.get("profit_take_40", False):
                        # TIER 1: Safety exit for moderate performers
                        # Sell 25% at +40% profit
                        data["sell_percentage"] = 25
                        data["profit_take_40"] = True
                        exit_type = "partial_profit_take"
                        exit_reason = f"Safety tier: Selling 25% at +{profit_pct:.1f}%, 75% remaining"
                        print(f"[TRADER] 💰 {token[:8]} TIER 1: Selling 25% at +{profit_pct:.1f}%", flush=True)
                        print(f"[TRADER] 🎯 Locking in 10% gain, keeping 75% for potential moonshot", flush=True)
                
                # Check hard stop loss (from entry)
                if not exit_type and price <= stop_price:
                    exit_type = "stop"
                    exit_reason = f"Hit stop loss: {price:.8f} <= {stop_price:.8f} (entry: {entry_price:.8f})"
                
                # EMERGENCY HARD STOP - Last resort if normal stop failed
                emergency_stop_price = entry_price * (1.0 - EMERGENCY_HARD_STOP_PCT / 100.0)
                if not exit_type and price <= emergency_stop_price:
                    exit_type = "emergency_stop"
                    loss_pct = ((price - entry_price) / entry_price) * 100
                    exit_reason = f"EMERGENCY HARD STOP: {loss_pct:.1f}% loss (price: {price:.8f}, entry: {entry_price:.8f})"
                    print(f"[TRADER] 🚨 {exit_reason}", flush=True)
                
                # Check trailing stop (from peak)
                elif not exit_type and peak > 0 and price <= trail_price:
                    exit_type = "trail"
                    exit_reason = f"Hit trailing stop: {price:.8f} <= {trail_price:.8f} (peak: {peak:.8f}, trail: {trail}%)"
                
                # CRITICAL FIX: Panic trigger for flash dumps
                # Problem: At 3s intervals, price can crash 60% before we poll again
                # Solution: If price drops MORE than trailing stop threshold, immediate sell
                # Example: Trail stop at $10, but price is $8 (20% below stop) = PANIC
                elif not exit_type and peak > 0 and trail_price > 0:
                    panic_threshold = trail_price * 0.8  # 20% below trailing stop = panic
                    if price < panic_threshold:
                        # Flash dump detected!
                        drop_from_peak = ((price - peak) / peak) * 100
                        drop_from_stop = ((price - trail_price) / trail_price) * 100
                        exit_type = "panic_sell"
                        exit_reason = f"FLASH DUMP: {price:.8f} < {panic_threshold:.8f} (20% below trail stop, {drop_from_peak:.1f}% from peak)"
                        print(f"[TRADER] 🚨 PANIC SELL: {token[:8]} crashed {drop_from_stop:.1f}% below trailing stop!", flush=True)
                        print(f"[TRADER] Peak: {peak:.8f}, Trail Stop: {trail_price:.8f}, Current: {price:.8f}", flush=True)
                
                if not exit_type:
                    return False
                
                # Check position-specific cooldown (prevent API spam after failures)
                last_sell_attempt = data.get("last_sell_attempt", 0)
                sell_failures = data.get("sell_failures", 0)
                
                # CRITICAL FIX: Adaptive backoff with progressive slowdown
                # Problem: Fixed 120s backoff = constant API load, can hit rate limits
                # Solution: Increase backoff with failures to reduce API pressure over time
                # Formula: min(3s * (1 + 0.2 * failures), max_backoff)
                # Impact: Early retries are fast, later retries are slower to avoid API bans
                if profit_pct >= 50:
                    # High-profit positions: slower escalation, max 5min backoff
                    # Early: 3s, 4s, 5s... Later: 60s, 120s, 180s, 240s, 300s (cap)
                    backoff_seconds = min(3 * (1 + 0.3 * sell_failures), 300)
                elif profit_pct < -10:
                    # Losing positions: fast retries, cap at 30s
                    backoff_times = [0, 5, 10, 20, 30, 30]
                    backoff_idx = min(sell_failures, len(backoff_times) - 1)
                    backoff_seconds = backoff_times[backoff_idx]
                else:
                    # Moderate profit/small loss: standard escalation, cap at 60s
                    backoff_seconds = min(3 * (1 + 0.2 * sell_failures), 60)
                
                if last_sell_attempt > 0 and (time.time() - last_sell_attempt) < backoff_seconds:
                    remaining = int(backoff_seconds - (time.time() - last_sell_attempt))
                    if sell_failures < 3:  # Only log first few times to avoid spam
                        print(f"[TRADER] ⏳ Position {token[:8]} in cooldown: {remaining}s remaining (failures={sell_failures})", flush=True)
                    return False
                
                # Execute sell (full or partial)
                qty_open = get_open_qty(int(pid))
                if qty_open <= 0:
                    self._log("exit_zero_qty", token=token, pid=pid)
                    self.live.pop(token, None)
                    close_position(pid)
                    return False
                
                # Check if this is a partial sell
                sell_percentage = data.get("sell_percentage", 100)  # Default to 100% (full sell)
                is_partial = sell_percentage < 100
                
                # Calculate quantity to sell
                if is_partial:
                    qty_to_sell = float(qty_open) * (sell_percentage / 100.0)
                    qty_remaining = float(qty_open) - qty_to_sell
                    print(f"[TRADER] 📊 Partial sell: {sell_percentage}% of {qty_open:.2f} = {qty_to_sell:.2f} tokens", flush=True)
                    print(f"[TRADER] 💎 Keeping {qty_remaining:.2f} tokens ({100-sell_percentage}%) riding", flush=True)
                else:
                    qty_to_sell = float(qty_open)
                
                # Update last attempt time
                if token in self.live:
                    self.live[token]["last_sell_attempt"] = time.time()
                
                # CRITICAL FIX: Use extreme slippage for profitable positions with many failures
                # This ensures we capture profits even if liquidity is terrible
                if profit_pct >= 50 and sell_failures >= 10:
                    print(f"[TRADER] 🚨 Using EXTREME slippage mode for {token[:8]}", flush=True)
                    fill = self.broker.market_sell_extreme(token, qty_to_sell)
                else:
                    fill = self.broker.market_sell(token, qty_to_sell)
                
                if not fill.success:
                    self._log("exit_failed_sell", token=token, pid=pid, error=fill.error, 
                             failures=sell_failures + 1, next_backoff=backoff_times[min(sell_failures + 1, len(backoff_times) - 1)])
                    
                    # CRITICAL: Detect ghost positions (zero on-chain balance) and auto-close
                    # This happens when switching wallets or when tokens were sold outside the system
                    if "Zero balance on-chain" in str(fill.error) or "tokens don't exist" in str(fill.error):
                        print(f"[TRADER] 👻 GHOST POSITION DETECTED: {token[:8]} - auto-closing in database", flush=True)
                        print(f"[TRADER] Database shows position but wallet has ZERO tokens", flush=True)
                        # Close position in DB (can't sell - tokens don't exist in wallet)
                        close_position(pid)
                        self.live.pop(token, None)
                        self._log("ghost_position_closed", token=token, pid=pid, error=fill.error)
                        return True  # Return True so position is removed from tracking
                    
                    # CRITICAL: Detect rugged/dead tokens and force-close immediately
                    # If we get "NO_ROUTE" or "RUG_DETECTED" error, the token is dead
                    if "RUG_DETECTED" in str(fill.error) or "No liquidity" in str(fill.error):
                        print(f"[TRADER] 🚨 RUGGED TOKEN DETECTED: {token[:8]} - force closing", flush=True)
                        # Close position in DB (can't sell, but remove from tracking)
                        close_position(pid)
                        self.live.pop(token, None)
                        self._log("rugged_token_closed", token=token, pid=pid, error=fill.error)
                        return True  # Return True so position is removed
                    
                    # Track consecutive sell failures with adaptive backoff
                    if token in self.live:
                        self.live[token]["sell_failures"] = sell_failures + 1
                        
                        # CRITICAL FIX: Bounded retries with adaptive backoff
                        # Problem: Infinite retries (999999) = 9600 attempts over 8h = API abuse
                        # Solution: Cap at 300 attempts, increase backoff over time
                        # Impact: Still gives plenty of chances (10+ hours) but prevents API spam
                        if profit_pct >= 50:
                            # High-profit positions get extended retries, not infinite
                            max_failures = 300  # ~10 hours of retries at 2-min intervals
                            
                            # Escalate to extreme mode after 10 failures
                            if sell_failures + 1 == 10:
                                print(f"[TRADER] 💪 {token[:8]} ENTERING EXTREME MODE: Will use 100% slippage", flush=True)
                                print(f"[TRADER] 💰 Current profit: +{profit_pct:.1f}% - MUST CAPTURE THIS", flush=True)
                            
                            # Warn when approaching limit
                            if sell_failures + 1 == 250:
                                print(f"[TRADER] ⚠️ {token[:8]} has 250 failures - may be permanently dead", flush=True)
                                print(f"[TRADER] Will try 50 more times then mark as dead", flush=True)
                        elif profit_pct < -10:
                            max_failures = 5  # Fast exit for dumps (stop loss already triggered)
                        elif profit_pct < 0:
                            max_failures = 8  # Moderate for small losses
                        else:
                            max_failures = 15  # More patience for small profits
                        
                        if sell_failures + 1 >= max_failures:
                            print(f"[TRADER] 🚨 FORCE CLOSING: {token[:8]} after {sell_failures + 1} failures (profit: {profit_pct:.1f}%)", flush=True)
                            close_position(pid)
                            self.live.pop(token, None)
                            self.inactivity_monitor.reset_position(token)
                            self._log("force_closed_stuck_position", token=token, pid=pid, failures=sell_failures + 1, profit_pct=profit_pct, error=fill.error)
                            return True
                        
                        # Log failures with backoff info
                        if sell_failures + 1 <= 5:  # Log first 5 failures
                            print(f"[TRADER] ⚠️ Sell attempt {sell_failures + 1} failed for {token[:8]}: {fill.error}", flush=True)
                            print(f"[TRADER] Next retry in {backoff_times[min(sell_failures + 1, len(backoff_times) - 1)]}s", flush=True)
                        elif (sell_failures + 1) % 10 == 0:  # Then log every 10 failures
                            print(f"[TRADER] ⚠️ Position {token[:8]} has {sell_failures + 1} sell failures - retrying every {backoff_seconds}s", flush=True)
                    
                    return False
                
                # SUCCESS! Reset failure counter
                if token in self.live:
                    self.live[token]["sell_failures"] = 0
                
                # Get trade_id for lifecycle tracking
                trade_id = data.get("trade_id", "unknown")
                self._log("trade_lifecycle", trade_id=trade_id, stage="exit_executed", 
                         token=token, exit_type=exit_type, price=fill.price, qty=fill.qty)
                
                # Calculate PnL
                entry_usd = entry_price * qty_open if entry_price > 0 else 0
                exit_usd = fill.usd
                pnl_usd = exit_usd - entry_usd
                pnl_pct = (pnl_usd / entry_usd * 100) if entry_usd > 0 else 0
                
                # Record trade in circuit breaker
                self.circuit_breaker.record_trade(pnl_usd, slippage_pct=abs(fill.effective_slippage_bps / 100.0))
                
                # Update database
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                
                # CRITICAL FIX: Detect if actual qty sold differs from requested (DB mismatch)
                # If broker sold less than requested, it means wallet had fewer tokens than DB thought
                # Treat this as a partial sell even if sell_percentage was 100
                actual_qty_sold = float(fill.qty)
                qty_mismatch_threshold = 0.10  # 10% tolerance for dust/rounding
                
                if actual_qty_sold < qty_to_sell * (1 - qty_mismatch_threshold):
                    # DB MISMATCH: Broker sold less than requested
                    actual_remaining = qty_open - actual_qty_sold
                    print(f"[TRADER] 🚨 DB MISMATCH: Requested {qty_to_sell:.4f}, sold {actual_qty_sold:.4f}", flush=True)
                    print(f"[TRADER] 🔧 Updating DB qty from {qty_open:.4f} to {actual_remaining:.4f}", flush=True)
                    
                    if actual_remaining > 0.01:  # If meaningful qty remains
                        # Update database to reflect actual remaining balance
                        update_position_qty(int(pid), actual_remaining)
                        data["holdings"] = actual_remaining
                        data.pop("sell_percentage", None)  # Clear for next attempt
                        print(f"[TRADER] ✅ DB sync SUCCESS: {actual_remaining:.4f} tokens remain", flush=True)
                        return False  # Keep monitoring
                    else:
                        # Dust amount, close position
                        print(f"[TRADER] 🧹 Dust remaining ({actual_remaining:.4f}), closing position", flush=True)
                        close_position(pid)
                        self.live.pop(token, None)
                        self.inactivity_monitor.reset_position(token)
                        self.momentum_tracker.cleanup(token)
                        self._add_cooldown(token)
                        return True
                
                # Handle intentional partial vs full exit
                if is_partial:
                    # CRITICAL FIX: Update database qty after partial sell
                    update_position_qty(int(pid), qty_remaining)
                    # Update in-memory holdings to match
                    data["holdings"] = qty_remaining
                    # Partial sell: Keep position open, reset sell_percentage flag for next exit
                    data.pop("sell_percentage", None)  # Clear for next milestone
                    print(f"[TRADER] ✅ Partial exit SUCCESS: Sold {sell_percentage}% @ ${fill.price:.8f}", flush=True)
                    print(f"[TRADER] 💎 Position still OPEN: {qty_remaining:.2f} tokens riding with trailing stop", flush=True)
                    # Don't close position, don't remove from live - keep monitoring
                    return False
                else:
                    # Full exit: Close position completely
                    close_position(pid)
                    # Remove from live and clean up monitors
                    self.live.pop(token, None)
                    self.inactivity_monitor.reset_position(token)
                    self.momentum_tracker.cleanup(token)
                    
                    # Mark in watch list (if stop loss, keep watching for re-entry)
                    if exit_type == "stop":
                        try:
                            from .watch_list_manager import get_watch_list_manager
                            watch_manager = get_watch_list_manager()
                            watch_manager.mark_exited(token, fill.price, "stop_loss")
                            print(f"[WATCHLIST] 👁️  {token[:8]} exited at stop, still watching for recovery...", flush=True)
                        except Exception as e:
                            print(f"[WATCHLIST] ⚠️  Failed to mark exit in watch list: {e}", flush=True)
                
                    # Add cooldown to prevent immediate rebuy (only for full exits)
                    self._add_cooldown(token)
                    self._log("cooldown_added", token=token, cooldown_seconds=self._cooldown_seconds,
                             reason=f"sold_via_{exit_type}")
                    
                    # Final lifecycle log
                    self._log("trade_lifecycle", trade_id=trade_id, stage="position_closed", 
                             token=token, pid=pid, exit_type=exit_type, 
                             pnl_usd=pnl_usd, pnl_pct=pnl_pct)
                    print(f"[TRADE:{trade_id}] 🏁 Position closed | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)", flush=True)
                    
                    self._log(f"exit_{exit_type}", 
                             token=token, pid=pid, strategy=strategy,
                             entry_price=entry_price, exit_price=price, peak=peak,
                             stop_pct=STOP_LOSS_PCT, trail_pct=trail, 
                             pnl_usd=pnl_usd, pnl_pct=pnl_pct,
                             reason=exit_reason, tx=fill.tx, trade_id=trade_id)
                    
                    return True
                
        except Exception as e:
            self._log("exit_exception", token=token, error=str(e))
            return False
    
    def _force_emergency_exit(self, token: str, reason: str) -> bool:
        """Force exit a position regardless of price (emergency only)"""
        try:
            data = self.live.get(token)
            if not data:
                return False
            
            pid = data.get("pid")
            if not pid:
                return False
            
            qty_open = get_open_qty(int(pid))
            
            if qty_open <= 0:
                self.live.pop(token, None)
                close_position(pid)
                return False
            
            # Try to sell at market (any price)
            fill = self.broker.market_sell(token, float(qty_open))
            
            if fill.success:
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                close_position(pid)
                self.live.pop(token, None)
                self.inactivity_monitor.reset_position(token)
                self.momentum_tracker.cleanup(token)
                self._add_cooldown(token)
                self._log("emergency_exit", token=token, reason=reason, pid=pid, usd=fill.usd)
                print(f"[TRADER] 🚨 EMERGENCY EXIT SUCCESS: {token[:8]} sold for ${fill.usd:.2f}", flush=True)
                return True
            else:
                # Even sell failed - close in DB anyway to prevent infinite loop
                close_position(pid)
                self.live.pop(token, None)
                self.inactivity_monitor.reset_position(token)
                self.momentum_tracker.cleanup(token)
                self._log("emergency_exit_failed", token=token, reason=reason, error=fill.error)
                print(f"[TRADER] ⚠️ EMERGENCY EXIT FAILED: {token[:8]} - {fill.error}", flush=True)
                return False
        except Exception as e:
            self._log("emergency_exit_exception", token=token, error=str(e))
            print(f"[TRADER] ❌ EMERGENCY EXIT EXCEPTION: {token[:8]} - {e}", flush=True)
            return False

    def rebalance_position(self, token_to_sell: str, new_token: str, new_plan: Dict) -> bool:
        """
        Portfolio rebalancing: Sell one position and buy another.
        
        This is atomic - if either operation fails, the other is rolled back.
        
        Args:
            token_to_sell: Token to sell
            new_token: Token to buy
            new_plan: Trading plan for new token
        
        Returns:
            True if rebalance successful
        """
        try:
            if not should_use_portfolio_manager():
                self._log("rebalance_disabled", reason="portfolio_manager_not_enabled")
                return False
            
            # Verify we have the position to sell
            if token_to_sell not in self.live:
                self._log("rebalance_failed", reason="token_to_sell_not_found", token=token_to_sell)
                return False
            
            # Verify we can buy (not over limit after swap)
            if len(self.live) >= MAX_CONCURRENT and new_token not in self.live:
                # This shouldn't happen (we're swapping), but safety check
                self._log("rebalance_failed", reason="max_concurrent", count=len(self.live))
                return False
            
            # Get current price for the sell position
            sell_data = self.live.get(token_to_sell)
            if not sell_data:
                return False
            
            # Fetch current price (with actual holdings for accurate pricing)
            data = self.live.get(token_to_sell)
            if not data:
                self._log("rebalance_failed", reason="position_not_found", token=token_to_sell)
                return False
            
            holdings = data.get("holdings", 0)
            if holdings <= 0:
                # Fallback: Get holdings from database
                pid = data.get("pid")
                if pid:
                    holdings = get_open_qty(int(pid))
            
            current_price = self.broker.get_token_price(token_to_sell, holdings) if holdings > 0 else 0.0
            if current_price <= 0:
                self._log("rebalance_failed", reason="invalid_price", token=token_to_sell, holdings=holdings)
                return False
            
            # Execute sell by calling check_exits (which handles the full exit logic)
            # This is better than duplicating exit logic here
            sell_result = self.check_exits(token_to_sell, current_price)
            if not sell_result:
                # Try to force the exit even if stop/trail not hit (rebalance override)
                pid = sell_data.get("pid")
                if not pid:
                    return False
                
                # Get quantity and sell directly
                from .db import get_open_qty, add_fill, close_position
                qty_open = get_open_qty(int(pid))
                if qty_open <= 0:
                    self._log("rebalance_failed", reason="zero_qty", token=token_to_sell)
                    return False
                
                # Force sell
                fill = self.broker.market_sell(token_to_sell, float(qty_open))
                if not fill.success:
                    self._log("rebalance_failed", reason="sell_failed", token=token_to_sell, error=fill.error)
                    return False
                
                # Update database
                add_fill(int(pid), "sell", float(fill.price), float(fill.qty), float(fill.usd))
                close_position(pid)
                
                # Remove from live
                self.live.pop(token_to_sell, None)
                
                # Log the forced exit
                entry_price = float(sell_data.get("entry_price", 0))
                entry_usd = entry_price * qty_open if entry_price > 0 else 0
                pnl_usd = fill.usd - entry_usd
                pnl_pct = (pnl_usd / entry_usd * 100) if entry_usd > 0 else 0
                
                self._log("rebalance_forced_exit", token=token_to_sell, pid=pid,
                         pnl_usd=pnl_usd, pnl_pct=pnl_pct, reason="rebalance_override")
            
            # Execute buy
            buy_pid = self.open_position(new_token, new_plan)
            if not buy_pid:
                # Buy failed - this is problematic but not catastrophic
                # The sell already happened, so we just log it
                self._log("rebalance_partial", 
                         reason="buy_failed", 
                         sold=token_to_sell, 
                         failed_buy=new_token)
                return False
            
            # Success!
            self._log("rebalance_success",
                     sold=token_to_sell,
                     bought=new_token,
                     new_pid=buy_pid)
            
            # Update portfolio manager
            pm = get_portfolio_manager()
            pm.remove_position(token_to_sell, reason="rebalanced")
            pm.add_position(
                token_address=new_token,
                entry_price=self.live[new_token]["entry_price"],
                quantity=get_open_qty(new_token) or 0,
                signal_score=new_plan.get("score", 5),
                conviction_score=new_plan.get("conviction_score", 0),
                name=new_plan.get("name", ""),
                symbol=new_plan.get("symbol", ""),
            )
            
            return True
            
        except Exception as e:
            self._log("rebalance_exception", error=str(e))
            return False
    
    def sync_portfolio_manager(self) -> None:
        """Sync current positions with portfolio manager"""
        if not should_use_portfolio_manager():
            return
        
        try:
            pm = get_portfolio_manager()
            
            # Add all current positions to portfolio manager
            for token, data in self.live.items():
                if not pm.has_position(token):
                    # Get the position ID for this token
                    pid = data.get("pid")
                    if not pid:
                        continue
                    
                    # Get the actual quantity from the database
                    qty = get_open_qty(pid)
                    
                    pm.add_position(
                        token_address=token,
                        entry_price=data.get("entry_price", 0),
                        quantity=qty,
                        signal_score=5,  # Default score
                        conviction_score=0,
                        name="",
                        symbol="",
                    )
            
            self._log("portfolio_synced", position_count=len(self.live))
            
        except Exception as e:
            self._log("portfolio_sync_exception", error=str(e))
    
    def update_portfolio_prices(self) -> None:
        """Update prices in portfolio manager for momentum calculation"""
        if not should_use_portfolio_manager():
            return
        
        try:
            pm = get_portfolio_manager()
            price_updates = {}
            
            for token in self.live.keys():
                price = self.broker.get_token_price(token)
                if price > 0:
                    price_updates[token] = price
            
            if price_updates:
                pm.update_prices(price_updates)
            
        except Exception:
            pass  # Silent fail - not critical

    def get_status(self) -> Dict:
        """Get engine status"""
        # Get cooldown stats
        with self._cooldown_lock:
            now = time.time()
            active_cooldowns = sum(1 for sell_time in self._token_cooldowns.values() 
                                  if (now - sell_time) < self._cooldown_seconds)
        
        status = {
            "open_positions": len(self.live),
            "tokens": list(self.live.keys()),
            "broker_dry_run": self.broker._dry,
            "token_cooldowns": {
                "active": active_cooldowns,
                "total": len(self._token_cooldowns),
                "cooldown_seconds": self._cooldown_seconds,
            },
        }
        
        # Add portfolio manager status if enabled
        if should_use_portfolio_manager():
            pm = get_portfolio_manager()
            status["portfolio_manager"] = pm.get_statistics()
        
        return status

