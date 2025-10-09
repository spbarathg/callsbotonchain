"""
PAPER TRADING SYSTEM - Realistic Simulation
Emulates real trading with:
- $500 starting capital
- Realistic latency (1-3s execution delay)
- Swap fees (0.25% Jupiter)
- Slippage (1-3% depending on liquidity)
- Price impact
- Optimized position sizing
- Circuit breakers
- Stop losses and trailing stops
"""
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, asdict

from .config_optimized import (
    get_position_size,
    get_trailing_stop,
    STOP_LOSS_PCT,
    MAX_DAILY_LOSS_PCT,
    MAX_CONSECUTIVE_LOSSES,
    BANKROLL_USD,
)


@dataclass
class PaperFill:
    """Simulated trade fill with realistic parameters"""
    token: str
    side: str  # 'buy' or 'sell'
    quoted_price: float  # Price at signal
    execution_price: float  # Actual fill price after latency/slippage
    quantity: float
    usd_value: float
    fee_usd: float
    slippage_pct: float
    latency_seconds: float
    timestamp: str


@dataclass
class PaperPosition:
    """Open paper trading position"""
    id: int
    token: str
    strategy: str
    entry_price: float
    entry_time: str
    quantity: float
    usd_invested: float
    trail_pct: float
    peak_price: float
    score: int
    conviction_type: str
    
    # Calculated fields
    current_price: float = 0.0
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    hold_time_minutes: float = 0.0


@dataclass
class PaperTrade:
    """Closed paper trade"""
    id: int
    token: str
    strategy: str
    score: int
    conviction_type: str
    
    # Entry
    entry_price: float
    entry_time: str
    entry_usd: float
    entry_fee_usd: float
    
    # Exit
    exit_price: float
    exit_time: str
    exit_usd: float
    exit_fee_usd: float
    exit_reason: str  # 'stop', 'trail', 'manual'
    
    # Performance
    pnl_usd: float
    pnl_pct: float
    hold_time_minutes: float
    peak_price: float
    peak_gain_pct: float


class CircuitBreaker:
    """Same circuit breaker as optimized trader"""
    def __init__(self):
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.tripped = False
        self.trip_reason = ""
        self.last_reset = datetime.now().date()
    
    def is_tripped(self) -> bool:
        """Check if circuit breaker is tripped"""
        self.check_and_reset()
        return self.tripped
    
    def check_and_reset(self):
        today = datetime.now().date()
        if today > self.last_reset:
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.last_reset = today
            if self.tripped:
                self.tripped = False
                self.trip_reason = ""
    
    def record_trade(self, pnl_usd: float) -> bool:
        """Returns True if can continue trading"""
        self.check_and_reset()
        self.daily_pnl += pnl_usd
        
        if pnl_usd < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Check daily loss
        max_loss = BANKROLL_USD * (MAX_DAILY_LOSS_PCT / 100.0)
        if self.daily_pnl < -max_loss:
            self.tripped = True
            self.trip_reason = f"Daily loss limit: ${abs(self.daily_pnl):.2f}"
            return False
        
        # Check consecutive losses
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            self.tripped = True
            self.trip_reason = f"Consecutive losses: {self.consecutive_losses}"
            return False
        
        return True


class PaperBroker:
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
        # Lower liquidity = higher slippage
        if liquidity_usd < 10000:
            return random.uniform(2.0, 4.0)  # 2-4%
        elif liquidity_usd < 30000:
            return random.uniform(1.0, 2.5)  # 1-2.5%
        else:
            return random.uniform(0.5, 1.5)  # 0.5-1.5%
    
    def simulate_buy(self, token: str, usd_size: float, quoted_price: float, 
                     liquidity_usd: float) -> PaperFill:
        """Simulate a buy order with realistic execution"""
        # Latency
        latency = self._simulate_latency()
        time.sleep(min(latency, 0.1))  # Small actual delay for realism
        
        # Slippage (unfavorable for buy)
        slippage_pct = self._simulate_slippage(liquidity_usd)
        execution_price = quoted_price * (1.0 + slippage_pct / 100.0)
        
        # Calculate fill
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
        """Simulate a sell order with realistic execution"""
        # Latency
        latency = self._simulate_latency()
        time.sleep(min(latency, 0.1))
        
        # Slippage (unfavorable for sell)
        slippage_pct = self._simulate_slippage(liquidity_usd)
        execution_price = quoted_price * (1.0 - slippage_pct / 100.0)
        
        # Calculate fill
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


class PaperTrader:
    """Paper trading engine with optimized strategy"""
    
    def __init__(self, starting_capital: float = 500.0):
        self.starting_capital = starting_capital
        self.current_capital = starting_capital
        self.positions: Dict[str, PaperPosition] = {}
        self.trades: List[PaperTrade] = []
        self.broker = PaperBroker()
        self.circuit_breaker = CircuitBreaker()
        self.next_position_id = 1
        self.db_path = "var/paper_trading.db"
        self._init_db()
        self._log_file = "data/logs/paper_trading.jsonl"
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
    
    def _init_db(self):
        """Initialize paper trading database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY,
                token TEXT NOT NULL,
                strategy TEXT,
                score INTEGER,
                conviction_type TEXT,
                entry_price REAL,
                entry_time TEXT,
                quantity REAL,
                usd_invested REAL,
                entry_fee_usd REAL,
                trail_pct REAL,
                peak_price REAL,
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
            CREATE TABLE IF NOT EXISTS paper_portfolio (
                timestamp TEXT PRIMARY KEY,
                capital REAL,
                open_positions INTEGER,
                total_trades INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate REAL,
                total_pnl REAL,
                daily_pnl REAL,
                circuit_breaker_tripped INTEGER
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
    
    def can_trade(self) -> Tuple[bool, str]:
        """Check if can open new position"""
        if self.circuit_breaker.is_tripped():
            return False, f"Circuit breaker tripped: {self.circuit_breaker.trip_reason}"
        
        if len(self.positions) >= 5:
            return False, "Max concurrent positions (5) reached"
        
        if self.current_capital < 50:
            return False, f"Insufficient capital: ${self.current_capital:.2f}"
        
        return True, ""
    
    def open_position(self, token: str, signal_data: Dict) -> Optional[int]:
        """Open a paper trading position"""
        can_trade, reason = self.can_trade()
        if not can_trade:
            self._log("open_rejected", token=token, reason=reason)
            return None
        
        # Get position size from optimized strategy
        score = signal_data.get('score', 7)
        conviction = signal_data.get('conviction_type', 'High Confidence')
        usd_size = get_position_size(score, conviction)
        
        # Cap at available capital
        usd_size = min(usd_size, self.current_capital * 0.25)  # Max 25% per trade
        
        if usd_size < 20:
            self._log("open_rejected", token=token, reason=f"Size too small: ${usd_size:.2f}")
            return None
        
        # Get price and liquidity
        quoted_price = signal_data.get('price', 0.0)
        liquidity = signal_data.get('liquidity_usd', 30000)
        
        if quoted_price <= 0:
            self._log("open_rejected", token=token, reason="Invalid price")
            return None
        
        # Simulate buy
        fill = self.broker.simulate_buy(token, usd_size, quoted_price, liquidity)
        
        # Create position
        pos_id = self.next_position_id
        self.next_position_id += 1
        
        trail_pct = get_trailing_stop(score, signal_data.get('change_1h', 0))
        
        position = PaperPosition(
            id=pos_id,
            token=token,
            strategy=signal_data.get('strategy', 'optimized'),
            entry_price=fill.execution_price,
            entry_time=fill.timestamp,
            quantity=fill.quantity,
            usd_invested=usd_size,
            trail_pct=trail_pct,
            peak_price=fill.execution_price,
            score=score,
            conviction_type=conviction
        )
        
        self.positions[token] = position
        self.current_capital -= usd_size
        
        # Save to DB
        self._save_position(position, fill)
        
        self._log("paper_position_opened",
                 token=token,
                 position_id=pos_id,
                 entry_price=fill.execution_price,
                 quantity=fill.quantity,
                 usd_invested=usd_size,
                 fee_usd=fill.fee_usd,
                 slippage_pct=fill.slippage_pct,
                 latency_s=fill.latency_seconds,
                 score=score,
                 conviction=conviction,
                 trail_pct=trail_pct)
        
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
        stop_price = pos.entry_price * (1.0 - STOP_LOSS_PCT / 100.0)
        if current_price <= stop_price:
            self._exit_position(token, current_price, 'stop')
            return True
        
        # Check trailing stop (from PEAK)
        trail_price = pos.peak_price * (1.0 - pos.trail_pct / 100.0)
        if pos.peak_price > 0 and current_price <= trail_price:
            self._exit_position(token, current_price, 'trail')
            return True
        
        return False
    
    def _exit_position(self, token: str, exit_price: float, reason: str):
        """Exit a position"""
        if token not in self.positions:
            return
        
        pos = self.positions[token]
        
        # Get liquidity (use cached or default)
        liquidity = 30000  # Default assumption
        
        # Simulate sell
        fill = self.broker.simulate_sell(token, pos.quantity, exit_price, liquidity)
        
        # Calculate PnL
        gross_proceeds = fill.usd_value + fill.fee_usd  # Add back fee for gross
        net_proceeds = fill.usd_value
        total_fees = pos.usd_invested * 0.0025 + fill.fee_usd  # Entry + exit fees
        pnl_usd = net_proceeds - pos.usd_invested
        pnl_pct = (pnl_usd / pos.usd_invested) * 100
        
        # Hold time
        entry_dt = datetime.fromisoformat(pos.entry_time.replace('Z', ''))
        exit_dt = datetime.fromisoformat(fill.timestamp.replace('Z', ''))
        hold_minutes = (exit_dt - entry_dt).total_seconds() / 60.0
        
        # Peak gain
        peak_gain_pct = ((pos.peak_price - pos.entry_price) / pos.entry_price) * 100
        
        # Create trade record
        trade = PaperTrade(
            id=pos.id,
            token=token,
            strategy=pos.strategy,
            score=pos.score,
            conviction_type=pos.conviction_type,
            entry_price=pos.entry_price,
            entry_time=pos.entry_time,
            entry_usd=pos.usd_invested,
            entry_fee_usd=pos.usd_invested * 0.0025,
            exit_price=fill.execution_price,
            exit_time=fill.timestamp,
            exit_usd=net_proceeds,
            exit_fee_usd=fill.fee_usd,
            exit_reason=reason,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            hold_time_minutes=hold_minutes,
            peak_price=pos.peak_price,
            peak_gain_pct=peak_gain_pct
        )
        
        self.trades.append(trade)
        self.current_capital += net_proceeds
        
        # Update circuit breaker
        self.circuit_breaker.record_trade(pnl_usd)
        
        # Save to DB
        self._save_trade(trade, fill)
        
        # Remove from open positions
        del self.positions[token]
        
        self._log("paper_position_closed",
                 token=token,
                 position_id=pos.id,
                 exit_reason=reason,
                 entry_price=pos.entry_price,
                 exit_price=fill.execution_price,
                 pnl_usd=pnl_usd,
                 pnl_pct=pnl_pct,
                 hold_minutes=hold_minutes,
                 peak_price=pos.peak_price,
                 peak_gain_pct=peak_gain_pct,
                 fee_total_usd=total_fees,
                 slippage_pct=fill.slippage_pct)
    
    def _save_position(self, pos: PaperPosition, fill: PaperFill):
        """Save position to database"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            INSERT INTO paper_positions 
            (id, token, strategy, score, conviction_type, entry_price, entry_time,
             quantity, usd_invested, entry_fee_usd, trail_pct, peak_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (pos.id, pos.token, pos.strategy, pos.score, pos.conviction_type,
              pos.entry_price, pos.entry_time, pos.quantity, pos.usd_invested,
              fill.fee_usd, pos.trail_pct, pos.peak_price))
        con.commit()
        con.close()
    
    def _save_trade(self, trade: PaperTrade, fill: PaperFill):
        """Save closed trade to database"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            UPDATE paper_positions
            SET exit_price=?, exit_time=?, exit_usd=?, exit_fee_usd=?,
                exit_reason=?, pnl_usd=?, pnl_pct=?, hold_time_minutes=?,
                peak_gain_pct=?, status='closed'
            WHERE id=?
        """, (trade.exit_price, trade.exit_time, trade.exit_usd, trade.exit_fee_usd,
              trade.exit_reason, trade.pnl_usd, trade.pnl_pct, trade.hold_time_minutes,
              trade.peak_gain_pct, trade.id))
        con.commit()
        con.close()
    
    def get_stats(self) -> Dict:
        """Get current portfolio stats"""
        total_trades = len(self.trades)
        wins = sum(1 for t in self.trades if t.pnl_usd > 0)
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        
        total_pnl = sum(t.pnl_usd for t in self.trades)
        unrealized_pnl = sum(
            (pos.quantity * pos.current_price - pos.usd_invested)
            for pos in self.positions.values()
        )
        
        total_value = self.current_capital + sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
        )
        
        roi = ((total_value - self.starting_capital) / self.starting_capital) * 100
        
        return {
            "starting_capital": self.starting_capital,
            "current_capital": self.current_capital,
            "total_value": total_value,
            "roi_pct": roi,
            "total_pnl": total_pnl,
            "unrealized_pnl": unrealized_pnl,
            "open_positions": len(self.positions),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "circuit_breaker_tripped": self.circuit_breaker.tripped,
            "daily_pnl": self.circuit_breaker.daily_pnl,
            "consecutive_losses": self.circuit_breaker.consecutive_losses,
        }

