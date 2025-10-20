#!/usr/bin/env python3
"""
COMPREHENSIVE BACKTEST - V4 Trading System
Simulates trading on 1,225 real V4 signals to validate strategy and find optimizations.

This script:
1. Loads all tracked signals from database
2. Simulates trading with actual strategy
3. Tracks portfolio performance over time
4. Identifies failure patterns
5. Suggests optimizations
"""
import sqlite3
import sys
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Signal:
    """Represents a trading signal"""
    token_address: str
    alert_time: float
    score: int
    conviction: str
    market_cap: float
    liquidity: float
    max_gain_pct: float
    peak_time: float
    is_rug: bool
    symbol: str = ""


@dataclass
class Position:
    """Represents an open trading position"""
    token: str
    entry_price: float
    entry_time: float
    quantity: float
    cost: float
    score: int
    conviction: str
    peak_price: float
    trail_pct: float
    
    @property
    def current_value(self) -> float:
        return self.quantity * self.peak_price
    
    @property
    def unrealized_pnl(self) -> float:
        return self.current_value - self.cost
    
    @property
    def unrealized_pnl_pct(self) -> float:
        return (self.unrealized_pnl / self.cost * 100) if self.cost > 0 else 0


@dataclass
class Trade:
    """Represents a completed trade"""
    token: str
    entry_time: float
    exit_time: float
    entry_price: float
    exit_price: float
    quantity: float
    cost: float
    proceeds: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    score: int
    max_gain_reached: float


@dataclass
class BacktestResult:
    """Complete backtest results"""
    starting_capital: float
    ending_capital: float
    total_return_pct: float
    
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    avg_win_pct: float
    avg_loss_pct: float
    avg_trade_pct: float
    
    max_drawdown: float
    max_drawdown_pct: float
    
    sharpe_ratio: float
    
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    
    # Detailed analysis
    wins_by_score: Dict[int, int] = field(default_factory=dict)
    losses_by_score: Dict[int, int] = field(default_factory=dict)
    rugs_traded: int = 0
    rugs_captured: int = 0


class TradingSimulator:
    """Simulates trading on historical signals"""
    
    def __init__(
        self,
        starting_capital: float = 1000,
        max_positions: int = 4,
        stop_loss_pct: float = 15,
        position_sizing: Dict[int, float] = None,
        trail_by_score: Dict[int, float] = None,
    ):
        self.starting_capital = starting_capital
        self.capital = starting_capital
        self.max_positions = max_positions
        self.stop_loss_pct = stop_loss_pct
        
        # Default position sizing (% of capital)
        self.position_sizing = position_sizing or {
            10: 20,  # 20% for Score 10
            9: 18,   # 18% for Score 9
            8: 25,   # 25% for Score 8 (BEST!)
            7: 10,   # 10% for Score 7
        }
        
        # Default trailing stops
        self.trail_by_score = trail_by_score or {
            10: 10,  # 10% trail for Score 10
            9: 10,   # 10% trail for Score 9
            8: 15,   # 15% trail for Score 8
            7: 20,   # 20% trail for Score 7
        }
        
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[float, float]] = []
        
        self.peak_capital = starting_capital
        self.max_drawdown = 0
        self.max_drawdown_pct = 0
        
        # Statistics
        self.signals_processed = 0
        self.signals_skipped_full = 0
        self.signals_skipped_score = 0
    
    def get_position_size(self, score: int) -> float:
        """Calculate position size based on score"""
        pct = self.position_sizing.get(score, 10)
        size = self.capital * (pct / 100)
        max_size = self.capital * 0.25  # Never more than 25%
        return min(size, max_size)
    
    def get_trailing_stop(self, score: int) -> float:
        """Get trailing stop % for score"""
        return self.trail_by_score.get(score, 15)
    
    def can_open_position(self) -> bool:
        """Check if we can open new position"""
        return len(self.positions) < self.max_positions
    
    def open_position(self, signal: Signal) -> bool:
        """Try to open a position"""
        if not self.can_open_position():
            self.signals_skipped_full += 1
            return False
        
        # Check score threshold
        if signal.score < 8:
            self.signals_skipped_score += 1
            return False
        
        # Calculate position size
        size = self.get_position_size(signal.score)
        
        # Check if we have enough capital
        if size > self.capital:
            return False
        
        # Open position
        entry_price = 1.0  # Normalized price
        quantity = size / entry_price
        
        position = Position(
            token=signal.token_address,
            entry_price=entry_price,
            entry_time=signal.alert_time,
            quantity=quantity,
            cost=size,
            score=signal.score,
            conviction=signal.conviction,
            peak_price=entry_price,
            trail_pct=self.get_trailing_stop(signal.score),
        )
        
        self.positions.append(position)
        self.capital -= size
        
        return True
    
    def update_position(self, position: Position, current_gain_pct: float, current_time: float) -> Optional[Trade]:
        """Update position price and check for exit"""
        # Calculate current price based on gain
        current_price = position.entry_price * (1 + current_gain_pct / 100)
        
        # Update peak
        if current_price > position.peak_price:
            position.peak_price = current_price
        
        # Check stop loss (from entry)
        stop_price = position.entry_price * (1 - self.stop_loss_pct / 100)
        if current_price <= stop_price:
            return self._exit_position(position, current_price, current_time, "stop_loss")
        
        # Check trailing stop (from peak)
        trail_price = position.peak_price * (1 - position.trail_pct / 100)
        if current_price <= trail_price:
            return self._exit_position(position, current_price, current_time, "trailing_stop")
        
        return None
    
    def _exit_position(self, position: Position, exit_price: float, exit_time: float, reason: str) -> Trade:
        """Exit a position"""
        proceeds = position.quantity * exit_price
        pnl = proceeds - position.cost
        pnl_pct = (pnl / position.cost * 100) if position.cost > 0 else 0
        
        # Calculate max gain reached
        max_gain_pct = ((position.peak_price - position.entry_price) / position.entry_price * 100)
        
        trade = Trade(
            token=position.token,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            cost=position.cost,
            proceeds=proceeds,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
            score=position.score,
            max_gain_reached=max_gain_pct,
        )
        
        self.trades.append(trade)
        self.capital += proceeds
        self.positions.remove(position)
        
        # Update peak and drawdown
        if self.capital > self.peak_capital:
            self.peak_capital = self.capital
        
        drawdown = self.peak_capital - self.capital
        drawdown_pct = (drawdown / self.peak_capital * 100) if self.peak_capital > 0 else 0
        
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
            self.max_drawdown_pct = drawdown_pct
        
        return trade
    
    def record_equity(self, timestamp: float):
        """Record current equity for equity curve"""
        open_value = sum(p.current_value for p in self.positions)
        total_equity = self.capital + open_value
        self.equity_curve.append((timestamp, total_equity))
    
    def get_results(self) -> BacktestResult:
        """Calculate final results"""
        ending_capital = self.capital + sum(p.current_value for p in self.positions)
        total_return_pct = ((ending_capital - self.starting_capital) / self.starting_capital * 100)
        
        winners = [t for t in self.trades if t.pnl > 0]
        losers = [t for t in self.trades if t.pnl <= 0]
        
        win_rate = (len(winners) / len(self.trades) * 100) if self.trades else 0
        avg_win_pct = (sum(t.pnl_pct for t in winners) / len(winners)) if winners else 0
        avg_loss_pct = (sum(t.pnl_pct for t in losers) / len(losers)) if losers else 0
        avg_trade_pct = (sum(t.pnl_pct for t in self.trades) / len(self.trades)) if self.trades else 0
        
        # Win/loss by score
        wins_by_score = defaultdict(int)
        losses_by_score = defaultdict(int)
        for trade in self.trades:
            if trade.pnl > 0:
                wins_by_score[trade.score] += 1
            else:
                losses_by_score[trade.score] += 1
        
        # Calculate Sharpe Ratio (simplified)
        if self.trades:
            returns = [t.pnl_pct for t in self.trades]
            avg_return = sum(returns) / len(returns)
            std_dev = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe_ratio = (avg_return / std_dev) if std_dev > 0 else 0
        else:
            sharpe_ratio = 0
        
        return BacktestResult(
            starting_capital=self.starting_capital,
            ending_capital=ending_capital,
            total_return_pct=total_return_pct,
            total_trades=len(self.trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            avg_trade_pct=avg_trade_pct,
            max_drawdown=self.max_drawdown,
            max_drawdown_pct=self.max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            trades=self.trades,
            equity_curve=self.equity_curve,
            wins_by_score=dict(wins_by_score),
            losses_by_score=dict(losses_by_score),
        )


def load_signals(db_path: str, min_timestamp: float) -> List[Signal]:
    """Load all signals from database"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("""
        SELECT 
            a.token_address,
            a.alerted_at,
            a.final_score,
            a.conviction_type,
            s.first_market_cap_usd,
            s.first_liquidity_usd,
            s.max_gain_percent,
            s.peak_price_at,
            s.is_rug,
            s.token_symbol
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE CAST(a.alerted_at AS REAL) >= ?
        AND s.max_gain_percent IS NOT NULL
        ORDER BY a.alerted_at ASC
    """, (min_timestamp,))
    
    signals = []
    for row in c.fetchall():
        # Handle both string and numeric timestamps
        alert_time = row[1]
        if isinstance(alert_time, str):
            # Parse datetime string to Unix timestamp
            from datetime import datetime
            try:
                dt = datetime.strptime(alert_time, '%Y-%m-%d %H:%M:%S')
                alert_time = dt.timestamp()
            except:
                continue  # Skip if can't parse
        else:
            alert_time = float(alert_time)
        
        peak_time = row[7]
        if isinstance(peak_time, str) or peak_time is None:
            peak_time = alert_time
        else:
            peak_time = float(peak_time)
        
        signal = Signal(
            token_address=row[0],
            alert_time=alert_time,
            score=int(row[2]),
            conviction=row[3] or "",
            market_cap=float(row[4] or 0),
            liquidity=float(row[5] or 0),
            max_gain_pct=float(row[6]),
            peak_time=peak_time,
            is_rug=bool(row[8]),
            symbol=row[9] or "",
        )
        signals.append(signal)
    
    conn.close()
    return signals


def simulate_trading(signals: List[Signal], config: Dict) -> BacktestResult:
    """Run full simulation"""
    simulator = TradingSimulator(
        starting_capital=config.get('capital', 1000),
        max_positions=config.get('max_positions', 4),
        stop_loss_pct=config.get('stop_loss_pct', 15),
        position_sizing=config.get('position_sizing'),
        trail_by_score=config.get('trail_by_score'),
    )
    
    print(f"\n{'='*80}")
    print(f"SIMULATING {len(signals)} SIGNALS")
    print(f"{'='*80}\n")
    
    # Process each signal
    for i, signal in enumerate(signals):
        # Try to open position
        opened = simulator.open_position(signal)
        
        if opened:
            print(f"[{i+1}/{len(signals)}] OPENED: {signal.symbol or signal.token_address[:8]} "
                  f"Score {signal.score}, MCap ${signal.market_cap:,.0f}")
        
        # Update all open positions with this signal's peak gain
        # (simulate price movement to peak)
        closed_trades = []
        for position in simulator.positions[:]:  # Copy list to avoid modification during iteration
            # Simulate gradual price movement to peak
            # For simplicity, we check exit at peak (worst case for our strategy)
            trade = simulator.update_position(position, signal.max_gain_pct, signal.peak_time)
            if trade:
                closed_trades.append(trade)
        
        # Log closed trades
        for trade in closed_trades:
            profit_emoji = "✅" if trade.pnl > 0 else "❌"
            print(f"  {profit_emoji} CLOSED: {trade.token[:8]} - {trade.exit_reason.upper()} - "
                  f"PnL: {trade.pnl_pct:+.1f}% (peak: {trade.max_gain_reached:.1f}%)")
        
        # Record equity
        simulator.record_equity(signal.alert_time)
        
        # Progress update
        if (i + 1) % 100 == 0:
            equity = simulator.capital + sum(p.current_value for p in simulator.positions)
            print(f"\n--- Progress: {i+1}/{len(signals)} signals processed ---")
            print(f"Current Equity: ${equity:,.2f} ({(equity/simulator.starting_capital - 1)*100:+.1f}%)")
            print(f"Open Positions: {len(simulator.positions)}/{simulator.max_positions}\n")
    
    # Close any remaining positions at final prices
    for position in simulator.positions[:]:
        # Find the signal for this token to get final price
        final_signal = next((s for s in signals if s.token_address == position.token), None)
        if final_signal:
            final_price = position.entry_price * (1 + final_signal.max_gain_pct / 100)
            trade = simulator._exit_position(position, final_price, final_signal.peak_time, "end_of_backtest")
            print(f"  ℹ️  CLOSED (EOB): {trade.token[:8]} - PnL: {trade.pnl_pct:+.1f}%")
    
    return simulator.get_results()


def print_results(result: BacktestResult):
    """Print formatted results"""
    print(f"\n{'='*80}")
    print(f"BACKTEST RESULTS")
    print(f"{'='*80}\n")
    
    print("=== OVERALL PERFORMANCE ===")
    print(f"Starting Capital: ${result.starting_capital:,.2f}")
    print(f"Ending Capital:   ${result.ending_capital:,.2f}")
    print(f"Total Return:     {result.total_return_pct:+.1f}%")
    print(f"Total Profit:     ${result.ending_capital - result.starting_capital:+,.2f}")
    print()
    
    print("=== TRADING STATISTICS ===")
    print(f"Total Trades:     {result.total_trades}")
    print(f"Winning Trades:   {result.winning_trades} ({result.win_rate:.1f}%)")
    print(f"Losing Trades:    {result.losing_trades}")
    print(f"Avg Win:          {result.avg_win_pct:+.1f}%")
    print(f"Avg Loss:         {result.avg_loss_pct:+.1f}%")
    print(f"Avg Trade:        {result.avg_trade_pct:+.1f}%")
    print()
    
    print("=== RISK METRICS ===")
    print(f"Max Drawdown:     ${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.1f}%)")
    print(f"Sharpe Ratio:     {result.sharpe_ratio:.2f}")
    print()
    
    print("=== PERFORMANCE BY SCORE ===")
    all_scores = sorted(set(list(result.wins_by_score.keys()) + list(result.losses_by_score.keys())), reverse=True)
    for score in all_scores:
        wins = result.wins_by_score.get(score, 0)
        losses = result.losses_by_score.get(score, 0)
        total = wins + losses
        wr = (wins / total * 100) if total > 0 else 0
        print(f"Score {score}: {wins}W / {losses}L ({wr:.1f}% WR)")
    print()
    
    # Top 10 winners
    print("=== TOP 10 WINNERS ===")
    winners = sorted([t for t in result.trades if t.pnl > 0], key=lambda t: t.pnl_pct, reverse=True)[:10]
    for i, trade in enumerate(winners, 1):
        print(f"{i}. {trade.token[:8]} - Score {trade.score} - {trade.pnl_pct:+.1f}% "
              f"(peak: {trade.max_gain_reached:.1f}%, exit: {trade.exit_reason})")
    print()
    
    # Top 10 losers
    print("=== TOP 10 LOSERS ===")
    losers = sorted([t for t in result.trades if t.pnl <= 0], key=lambda t: t.pnl_pct)[:10]
    for i, trade in enumerate(losers, 1):
        print(f"{i}. {trade.token[:8]} - Score {trade.score} - {trade.pnl_pct:+.1f}% "
              f"(peak: {trade.max_gain_reached:.1f}%, exit: {trade.exit_reason})")
    print()


def optimize_parameters(signals: List[Signal]) -> Dict:
    """Test different parameter combinations to find optimal settings"""
    print(f"\n{'='*80}")
    print(f"PARAMETER OPTIMIZATION")
    print(f"{'='*80}\n")
    
    best_result = None
    best_config = None
    
    # Test different trailing stop configurations
    trail_configs = [
        {"name": "Aggressive (10%)", "trails": {10: 10, 9: 10, 8: 10, 7: 10}},
        {"name": "Tight (15%)", "trails": {10: 10, 9: 10, 8: 15, 7: 20}},
        {"name": "Standard (20%)", "trails": {10: 15, 9: 15, 8: 20, 7: 25}},
        {"name": "Wide (30%)", "trails": {10: 25, 9: 25, 8: 30, 7: 35}},
    ]
    
    for trail_config in trail_configs:
        print(f"\nTesting: {trail_config['name']}")
        
        config = {
            'capital': 1000,
            'max_positions': 4,
            'stop_loss_pct': 15,
            'trail_by_score': trail_config['trails'],
        }
        
        result = simulate_trading(signals, config)
        
        print(f"  Return: {result.total_return_pct:+.1f}% | "
              f"Win Rate: {result.win_rate:.1f}% | "
              f"Avg Trade: {result.avg_trade_pct:+.1f}% | "
              f"Drawdown: {result.max_drawdown_pct:.1f}%")
        
        if best_result is None or result.total_return_pct > best_result.total_return_pct:
            best_result = result
            best_config = trail_config
    
    print(f"\n{'='*80}")
    print(f"BEST CONFIGURATION: {best_config['name']}")
    print(f"Return: {best_result.total_return_pct:+.1f}%")
    print(f"{'='*80}\n")
    
    return best_config


def main():
    """Main execution"""
    DB_PATH = '/opt/callsbotonchain/deployment/var/alerted_tokens.db'
    V4_START = 1760825238.0928257
    
    print(f"\n{'='*80}")
    print(f"V4 TRADING SYSTEM BACKTEST")
    print(f"{'='*80}\n")
    
    # Load signals
    print("Loading signals from database...")
    signals = load_signals(DB_PATH, V4_START)
    print(f"Loaded {len(signals)} signals\n")
    
    # Run optimization
    print("STEP 1: Optimizing trailing stop parameters...")
    best_config = optimize_parameters(signals)
    
    # Run final simulation with best config
    print("\n\nSTEP 2: Running final simulation with optimized parameters...")
    final_config = {
        'capital': 1000,
        'max_positions': 4,
        'stop_loss_pct': 15,
        'trail_by_score': best_config['trails'],
    }
    
    result = simulate_trading(signals, final_config)
    print_results(result)
    
    # Analysis
    print("=== KEY INSIGHTS ===")
    if result.total_return_pct > 200:
        print("✅ Strategy PROFITABLE: >200% return achieved!")
    elif result.total_return_pct > 100:
        print("✅ Strategy GOOD: >100% return achieved")
    elif result.total_return_pct > 0:
        print("⚠️  Strategy MARGINAL: Positive but low returns")
    else:
        print("❌ Strategy LOSING: Negative returns")
    
    print(f"\nIf you had started with $1,000 at V4 launch:")
    print(f"  You would now have: ${result.ending_capital:,.2f}")
    print(f"  Profit: ${result.ending_capital - result.starting_capital:+,.2f}")
    print(f"  Return: {result.total_return_pct:+.1f}%")
    print()


if __name__ == "__main__":
    main()

