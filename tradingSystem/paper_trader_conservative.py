"""
CONSERVATIVE PAPER TRADING SYSTEM
Implements CAPITAL_MANAGEMENT_STRATEGY.md principles:
- Small position sizes (5-12% max)
- 50% cash reserve always
- Daily/Weekly loss limits
- Risk-tier based sizing
- Max 4-6 positions
"""
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

from .config_conservative import (
    get_position_size_conservative,
    get_stop_loss_for_tier,
    get_trailing_stop_for_tier,
    get_profit_target_for_tier,
    check_can_trade,
    BANKROLL_USD,
    MAX_CONCURRENT,
    MAX_CAPITAL_DEPLOYED_PCT,
    MIN_CASH_RESERVE_PCT,
    MAX_DAILY_LOSS_USD,
    MAX_WEEKLY_LOSS_USD,
    MAX_CONSECUTIVE_LOSSES,
    RECOVERY_MODE_POSITION_REDUCTION_PCT,
)
from app.risk_tiers import RiskTier


@dataclass
class PaperFill:
    """Simulated trade fill with realistic parameters"""
    token: str
    side: str  # 'buy' or 'sell'
    quoted_price: float
    execution_price: float
    quantity: float
    usd_value: float
    fee_usd: float
    slippage_pct: float
    latency_seconds: float
    timestamp: str


@dataclass
class ConservativePosition:
    """Paper trading position with risk tier info"""
    id: int
    token: str
    risk_tier: RiskTier
    entry_price: float
    entry_time: str
    quantity: float
    usd_invested: float
    stop_loss_pct: float
    trail_pct: float
    peak_price: float
    score: int
    conviction_type: str
    
    # Calculated fields
    current_price: float = 0.0
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    hold_time_minutes: float = 0.0


class ConservativeCircuitBreaker:
    """Enhanced circuit breaker with daily/weekly tracking"""
    def __init__(self):
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.consecutive_losses = 0
        self.tripped = False
        self.trip_reason = ""
        self.last_daily_reset = datetime.now().date()
        self.last_weekly_reset = datetime.now().date()
        self.recovery_mode = False
    
    def is_tripped(self) -> bool:
        """Check if circuit breaker is tripped"""
        self.check_and_reset()
        return self.tripped
    
    def check_and_reset(self):
        """Check and reset counters if needed"""
        today = datetime.now().date()
        
        # Daily reset
        if today > self.last_daily_reset:
            self.daily_pnl = 0.0
            self.last_daily_reset = today
            # Un trip if was only daily limit
            if self.tripped and "Daily" in self.trip_reason:
                self.tripped = False
                self.trip_reason = ""
        
        # Weekly reset (Monday)
        if today.weekday() == 0 and today > self.last_weekly_reset:  # Monday
            self.weekly_pnl = 0.0
            self.last_weekly_reset = today
            self.consecutive_losses = 0  # Reset on new week
            # Un trip if was weekly limit
            if self.tripped and "Weekly" in self.trip_reason:
                self.tripped = False
                self.trip_reason = ""
                self.recovery_mode = False
    
    def record_trade(self, pnl_usd: float) -> Tuple[bool, str]:
        """
        Record trade and check limits.
        Returns: (can_continue, message)
        """
        self.check_and_reset()
        
        # Update PnL
        self.daily_pnl += pnl_usd
        self.weekly_pnl += pnl_usd
        
        # Update consecutive losses
        if pnl_usd < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            # Exit recovery mode on win
            if self.recovery_mode:
                self.recovery_mode = False
        
        # Check limits
        can_trade, reason = check_can_trade(self.daily_pnl, self.weekly_pnl, self.consecutive_losses)
        
        if not can_trade:
            self.tripped = True
            self.trip_reason = reason
            self.recovery_mode = True
            return False, reason
        
        # Check if should enter recovery mode (warning threshold)
        if self.daily_pnl <= -MAX_DAILY_LOSS_USD * 0.7:  # 70% of limit
            self.recovery_mode = True
            return True, f"⚠️  Warning: Near daily loss limit ({abs(self.daily_pnl):.2f}/{MAX_DAILY_LOSS_USD:.2f})"
        
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES - 1:  # One before limit
            self.recovery_mode = True
            return True, f"⚠️  Warning: {self.consecutive_losses} consecutive losses"
        
        return True, "OK"


class ConservativePaperBroker:
    """Simulates realistic trade execution"""
    
    def __init__(self):
        self.swap_fee_pct = 0.25  # Jupiter typical fee
    
    def _simulate_latency(self) -> float:
        """Simulate 1-3 second execution delay"""
        import random
        return random.uniform(1.0, 3.0)
    
    def _simulate_slippage(self, liquidity_usd: float) -> float:
        """Simulate slippage based on liquidity"""
        import random
        if liquidity_usd < 10000:
            return random.uniform(2.0, 4.0)  # 2-4%
        elif liquidity_usd < 30000:
            return random.uniform(1.0, 2.5)  # 1-2.5%
        else:
            return random.uniform(0.5, 1.5)  # 0.5-1.5%
    
    def simulate_buy(self, token: str, usd_size: float, quoted_price: float, 
                     liquidity_usd: float) -> PaperFill:
        """Simulate a buy order"""
        latency = self._simulate_latency()
        time.sleep(min(latency, 0.1))
        
        slippage_pct = self._simulate_slippage(liquidity_usd)
        execution_price = quoted_price * (1.0 + slippage_pct / 100.0)
        
        fee_usd = usd_size * (self.swap_fee_pct / 100.0)
        actual_usd_for_tokens = usd_size - fee_usd
        quantity = actual_usd_for_tokens / execution_price
        
        return PaperFill(
            token=token,
            side='buy',
            quoted_price=quoted_price,
            execution_price=execution_price,
            quantity=quantity,
            usd_value=usd_size,
            fee_usd=fee_usd,
            slippage_pct=slippage_pct,
            latency_seconds=latency,
            timestamp=datetime.utcnow().isoformat()
        )
    
    def simulate_sell(self, token: str, quantity: float, quoted_price: float,
                      liquidity_usd: float) -> PaperFill:
        """Simulate a sell order"""
        latency = self._simulate_latency()
        time.sleep(min(latency, 0.1))
        
        slippage_pct = self._simulate_slippage(liquidity_usd)
        execution_price = quoted_price * (1.0 - slippage_pct / 100.0)
        
        gross_usd = quantity * execution_price
        fee_usd = gross_usd * (self.swap_fee_pct / 100.0)
        net_usd = gross_usd - fee_usd
        
        return PaperFill(
            token=token,
            side='sell',
            quoted_price=quoted_price,
            execution_price=execution_price,
            quantity=quantity,
            usd_value=net_usd,
            fee_usd=fee_usd,
            slippage_pct=slippage_pct,
            latency_seconds=latency,
            timestamp=datetime.utcnow().isoformat()
        )


class ConservativePaperTrader:
    """Paper trading engine with conservative capital management"""
    
    def __init__(self, starting_capital: float = 1000.0):
        self.starting_capital = starting_capital
        self.current_capital = starting_capital
        self.positions: Dict[str, ConservativePosition] = {}
        self.broker = ConservativePaperBroker()
        self.circuit_breaker = ConservativeCircuitBreaker()
        self.next_position_id = 1
        self.db_path = "var/paper_trading_conservative.db"
        self._init_db()
        self._log_file = "data/logs/paper_trading_conservative.jsonl"
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
    
    def _init_db(self):
        """Initialize database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY,
                token TEXT NOT NULL,
                risk_tier TEXT,
                score INTEGER,
                conviction_type TEXT,
                entry_price REAL,
                entry_time TEXT,
                quantity REAL,
                usd_invested REAL,
                entry_fee_usd REAL,
                stop_loss_pct REAL,
                trail_pct REAL,
                peak_price REAL,
                profit_target_mult REAL,
                exit_price REAL,
                exit_time TEXT,
                exit_usd REAL,
                exit_fee_usd REAL,
                exit_reason TEXT,
                pnl_usd REAL,
                pnl_pct REAL,
                hold_time_minutes REAL,
                peak_gain_pct REAL,
                status TEXT DEFAULT 'open'
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                timestamp TEXT PRIMARY KEY,
                capital REAL,
                deployed REAL,
                deployed_pct REAL,
                cash_reserve REAL,
                cash_reserve_pct REAL,
                open_positions INTEGER,
                total_trades INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate REAL,
                total_pnl REAL,
                daily_pnl REAL,
                weekly_pnl REAL,
                consecutive_losses INTEGER,
                circuit_breaker_tripped INTEGER,
                recovery_mode INTEGER
            )
        """)
        
        con.commit()
        con.close()
    
    def _log(self, event: str, **fields):
        """Log event"""
        payload = {"ts": datetime.utcnow().isoformat(), "event": event}
        payload.update(fields)
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass
    
    def get_deployed_capital(self) -> float:
        """Get total capital deployed in positions"""
        return sum(pos.usd_invested for pos in self.positions.values())
    
    def get_deployed_pct(self) -> float:
        """Get percentage of capital deployed"""
        total = self.current_capital + self.get_deployed_capital()
        return (self.get_deployed_capital() / total * 100) if total > 0 else 0.0
    
    def can_trade(self, signal_data: Dict) -> Tuple[bool, str]:
        """Check if can open new position"""
        # Check circuit breaker
        if self.circuit_breaker.is_tripped():
            return False, f"Circuit breaker tripped: {self.circuit_breaker.trip_reason}"
        
        # Check max positions
        if len(self.positions) >= MAX_CONCURRENT:
            return False, f"Max concurrent positions ({MAX_CONCURRENT}) reached"
        
        # Check capital
        if self.current_capital < 50:
            return False, f"Insufficient capital: ${self.current_capital:.2f}"
        
        # Check deployment limit
        deployed_pct = self.get_deployed_pct()
        if deployed_pct >= MAX_CAPITAL_DEPLOYED_PCT:
            return False, f"Max deployment reached ({deployed_pct:.1f}% >= {MAX_CAPITAL_DEPLOYED_PCT}%)"
        
        # Calculate position size
        deployed = self.get_deployed_capital()
        total_capital = self.current_capital + deployed
        position_size, tier, explanation = get_position_size_conservative(signal_data, total_capital, deployed)
        
        if position_size <= 0:
            return False, f"Position size invalid: {explanation}"
        
        if position_size > self.current_capital:
            return False, f"Position size (${position_size:.2f}) exceeds available capital (${self.current_capital:.2f})"
        
        return True, ""
    
    def open_position(self, token: str, signal_data: Dict) -> Optional[int]:
        """Open a conservative position"""
        can_trade, reason = self.can_trade(signal_data)
        if not can_trade:
            self._log("open_rejected", token=token, reason=reason)
            return None
        
        # Calculate position size
        deployed = self.get_deployed_capital()
        total_capital = self.current_capital + deployed
        position_size, tier, explanation = get_position_size_conservative(signal_data, total_capital, deployed)
        
        # Apply recovery mode reduction if needed
        if self.circuit_breaker.recovery_mode:
            position_size *= (1.0 - RECOVERY_MODE_POSITION_REDUCTION_PCT / 100.0)
            self._log("recovery_mode_sizing", token=token, original_size=position_size, 
                     reduced_size=position_size, reduction_pct=RECOVERY_MODE_POSITION_REDUCTION_PCT)
        
        # Get price and liquidity
        quoted_price = signal_data.get('price', 0.0)
        liquidity = signal_data.get('liquidity_usd', signal_data.get('first_liquidity_usd', 30000))
        
        if quoted_price <= 0:
            self._log("open_rejected", token=token, reason="Invalid price")
            return None
        
        # Simulate buy
        fill = self.broker.simulate_buy(token, position_size, quoted_price, liquidity)
        
        # Create position
        pos_id = self.next_position_id
        self.next_position_id += 1
        
        stop_loss_pct = get_stop_loss_for_tier(tier)
        trail_pct = get_trailing_stop_for_tier(tier)
        profit_target = get_profit_target_for_tier(tier)
        
        position = ConservativePosition(
            id=pos_id,
            token=token,
            risk_tier=tier,
            entry_price=fill.execution_price,
            entry_time=fill.timestamp,
            quantity=fill.quantity,
            usd_invested=position_size,
            stop_loss_pct=stop_loss_pct,
            trail_pct=trail_pct,
            peak_price=fill.execution_price,
            score=signal_data.get('final_score', signal_data.get('score', 0)),
            conviction_type=signal_data.get('conviction_type', 'High Confidence')
        )
        
        self.positions[token] = position
        self.current_capital -= position_size
        
        # Save to DB
        self._save_position(position, fill, profit_target)
        
        # Log
        new_deployed_pct = self.get_deployed_pct()
        cash_reserve_pct = 100 - new_deployed_pct
        
        self._log("paper_position_opened",
                 token=token,
                 position_id=pos_id,
                 risk_tier=tier.tier_name,
                 entry_price=fill.execution_price,
                 quantity=fill.quantity,
                 usd_invested=position_size,
                 position_pct=(position_size / total_capital * 100),
                 stop_loss_pct=stop_loss_pct,
                 trail_pct=trail_pct,
                 profit_target_mult=profit_target,
                 deployed_pct=new_deployed_pct,
                 cash_reserve_pct=cash_reserve_pct,
                 recovery_mode=self.circuit_breaker.recovery_mode,
                 fee_usd=fill.fee_usd,
                 slippage_pct=fill.slippage_pct)
        
        return pos_id
    
    def update_and_check_exits(self, token: str, current_price: float) -> bool:
        """Update position and check exit conditions"""
        if token not in self.positions:
            return False
        
        pos = self.positions[token]
        pos.current_price = current_price
        
        # Update peak
        if current_price > pos.peak_price:
            pos.peak_price = current_price
        
        # Calculate unrealized PnL
        current_value = pos.quantity * current_price
        pos.unrealized_pnl_usd = current_value - pos.usd_invested
        pos.unrealized_pnl_pct = (pos.unrealized_pnl_usd / pos.usd_invested) * 100
        
        # Check stop loss (from ENTRY)
        stop_price = pos.entry_price * (1.0 - pos.stop_loss_pct / 100.0)
        if current_price <= stop_price:
            self._exit_position(token, current_price, 'stop_loss')
            return True
        
        # Check trailing stop (from PEAK)
        trail_price = pos.peak_price * (1.0 - pos.trail_pct / 100.0)
        if pos.peak_price > pos.entry_price and current_price <= trail_price:
            self._exit_position(token, current_price, 'trailing_stop')
            return True
        
        return False
    
    def _exit_position(self, token: str, exit_price: float, reason: str):
        """Exit a position"""
        if token not in self.positions:
            return
        
        pos = self.positions[token]
        
        liquidity = 30000  # Default
        fill = self.broker.simulate_sell(token, pos.quantity, exit_price, liquidity)
        
        # Calculate PnL
        net_proceeds = fill.usd_value
        total_fees = pos.usd_invested * 0.0025 + fill.fee_usd
        pnl_usd = net_proceeds - pos.usd_invested
        pnl_pct = (pnl_usd / pos.usd_invested) * 100
        
        # Hold time
        entry_dt = datetime.fromisoformat(pos.entry_time.replace('Z', ''))
        exit_dt = datetime.fromisoformat(fill.timestamp.replace('Z', ''))
        hold_minutes = (exit_dt - entry_dt).total_seconds() / 60.0
        
        # Peak gain
        peak_gain_pct = ((pos.peak_price - pos.entry_price) / pos.entry_price) * 100
        
        # Return capital
        self.current_capital += net_proceeds
        
        # Update circuit breaker
        can_continue, message = self.circuit_breaker.record_trade(pnl_usd)
        
        # Save to DB
        self._save_exit(pos, fill, pnl_usd, pnl_pct, hold_minutes, peak_gain_pct, reason)
        
        # Remove from positions
        del self.positions[token]
        
        # Log
        self._log("paper_position_closed",
                 token=token,
                 position_id=pos.id,
                 risk_tier=pos.risk_tier.tier_name,
                 exit_reason=reason,
                 entry_price=pos.entry_price,
                 exit_price=fill.execution_price,
                 pnl_usd=pnl_usd,
                 pnl_pct=pnl_pct,
                 hold_minutes=hold_minutes,
                 peak_price=pos.peak_price,
                 peak_gain_pct=peak_gain_pct,
                 deployed_pct=self.get_deployed_pct(),
                 cash_reserve_pct=100 - self.get_deployed_pct(),
                 circuit_breaker_status=message)
    
    def _save_position(self, pos: ConservativePosition, fill: PaperFill, profit_target: float):
        """Save position to database"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            INSERT INTO paper_positions 
            (id, token, risk_tier, score, conviction_type, entry_price, entry_time,
             quantity, usd_invested, entry_fee_usd, stop_loss_pct, trail_pct, 
             peak_price, profit_target_mult, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (pos.id, pos.token, pos.risk_tier.tier_name, pos.score, pos.conviction_type,
              pos.entry_price, pos.entry_time, pos.quantity, pos.usd_invested,
              fill.fee_usd, pos.stop_loss_pct, pos.trail_pct, pos.peak_price, profit_target))
        con.commit()
        con.close()
    
    def _save_exit(self, pos: ConservativePosition, fill: PaperFill, pnl_usd: float,
                   pnl_pct: float, hold_minutes: float, peak_gain_pct: float, reason: str):
        """Save closed trade"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            UPDATE paper_positions
            SET exit_price=?, exit_time=?, exit_usd=?, exit_fee_usd=?,
                exit_reason=?, pnl_usd=?, pnl_pct=?, hold_time_minutes=?,
                peak_gain_pct=?, status='closed'
            WHERE id=?
        """, (fill.execution_price, fill.timestamp, fill.usd_value, fill.fee_usd,
              reason, pnl_usd, pnl_pct, hold_minutes, peak_gain_pct, pos.id))
        con.commit()
        con.close()
    
    def get_stats(self) -> Dict:
        """Get current portfolio stats"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        
        # Get closed trades stats
        cur.execute("SELECT COUNT(*), SUM(pnl_usd) FROM paper_positions WHERE status='closed'")
        total_trades, total_pnl = cur.fetchone()
        total_trades = total_trades or 0
        total_pnl = total_pnl or 0.0
        
        cur.execute("SELECT COUNT(*) FROM paper_positions WHERE status='closed' AND pnl_usd > 0")
        wins = cur.fetchone()[0] or 0
        
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        
        con.close()
        
        # Current deployment
        deployed = self.get_deployed_capital()
        deployed_pct = self.get_deployed_pct()
        total_value = self.current_capital + sum(pos.quantity * pos.current_price for pos in self.positions.values())
        cash_reserve_pct = 100 - deployed_pct
        
        roi = ((total_value - self.starting_capital) / self.starting_capital) * 100
        
        return {
            "starting_capital": self.starting_capital,
            "current_capital": self.current_capital,
            "cash_reserve_pct": cash_reserve_pct,
            "deployed_capital": deployed,
            "deployed_pct": deployed_pct,
            "total_value": total_value,
            "roi_pct": roi,
            "total_pnl": total_pnl,
            "open_positions": len(self.positions),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "circuit_breaker_tripped": self.circuit_breaker.tripped,
            "circuit_breaker_reason": self.circuit_breaker.trip_reason,
            "daily_pnl": self.circuit_breaker.daily_pnl,
            "weekly_pnl": self.circuit_breaker.weekly_pnl,
            "consecutive_losses": self.circuit_breaker.consecutive_losses,
            "recovery_mode": self.circuit_breaker.recovery_mode,
        }




