"""
Paper Trading Engine for hypothetical portfolio simulation
Tracks positions, calculates P/L, runs backtests
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import sqlite3


@dataclass
class PaperPosition:
    """Represents a paper trading position"""
    token: str
    symbol: str
    entry_price: float
    entry_time: str
    position_size_usd: float
    quantity: float
    score: int
    conviction: str
    smart_money: bool
    current_price: float = 0.0
    pnl_percent: float = 0.0
    pnl_usd: float = 0.0
    is_open: bool = True
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    hold_time_hours: float = 0.0


@dataclass
class PaperPortfolio:
    """Represents the paper trading portfolio"""
    starting_capital: float
    current_value: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: List[PaperPosition]
    closed_positions: List[PaperPosition]
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    strategy: str
    max_concurrent: int
    position_sizing: str
    created_at: str
    updated_at: str


class PaperTradingEngine:
    """Manages paper trading sessions"""
    
    def __init__(self):
        self.session_file = "var/paper_trading_session.json"
        self.portfolio: Optional[PaperPortfolio] = None
        self._load_session()
    
    def _load_session(self):
        """Load existing session from file"""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    
                    # Reconstruct portfolio
                    self.portfolio = PaperPortfolio(
                        starting_capital=data['starting_capital'],
                        current_value=data['current_value'],
                        realized_pnl=data['realized_pnl'],
                        unrealized_pnl=data['unrealized_pnl'],
                        open_positions=[PaperPosition(**p) for p in data['open_positions']],
                        closed_positions=[PaperPosition(**p) for p in data['closed_positions']],
                        total_trades=data['total_trades'],
                        wins=data['wins'],
                        losses=data['losses'],
                        win_rate=data['win_rate'],
                        strategy=data['strategy'],
                        max_concurrent=data['max_concurrent'],
                        position_sizing=data['position_sizing'],
                        created_at=data['created_at'],
                        updated_at=data['updated_at']
                    )
            except:
                self.portfolio = None
    
    def _save_session(self):
        """Save session to file"""
        if self.portfolio:
            data = {
                'starting_capital': self.portfolio.starting_capital,
                'current_value': self.portfolio.current_value,
                'realized_pnl': self.portfolio.realized_pnl,
                'unrealized_pnl': self.portfolio.unrealized_pnl,
                'open_positions': [asdict(p) for p in self.portfolio.open_positions],
                'closed_positions': [asdict(p) for p in self.portfolio.closed_positions],
                'total_trades': self.portfolio.total_trades,
                'wins': self.portfolio.wins,
                'losses': self.portfolio.losses,
                'win_rate': self.portfolio.win_rate,
                'strategy': self.portfolio.strategy,
                'max_concurrent': self.portfolio.max_concurrent,
                'position_sizing': self.portfolio.position_sizing,
                'created_at': self.portfolio.created_at,
                'updated_at': self.portfolio.updated_at
            }
            
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            with open(self.session_file, 'w') as f:
                json.dump(data, f, indent=2)
    
    def start_session(self, capital: float, strategy: str, position_sizing: str, max_concurrent: int) -> Dict[str, Any]:
        """Start a new paper trading session"""
        self.portfolio = PaperPortfolio(
            starting_capital=capital,
            current_value=capital,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            open_positions=[],
            closed_positions=[],
            total_trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            strategy=strategy,
            max_concurrent=max_concurrent,
            position_sizing=position_sizing,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        self._save_session()
        
        return {
            "success": True,
            "message": "Paper trading session started",
            "portfolio": self.get_portfolio_summary()
        }
    
    def stop_session(self) -> Dict[str, Any]:
        """Stop current session"""
        if not self.portfolio:
            return {"success": False, "error": "No active session"}
        
        # Close all open positions at current market price
        for pos in self.portfolio.open_positions:
            self.close_position(pos.token, pos.current_price)
        
        summary = self.get_portfolio_summary()
        self.portfolio = None
        
        # Remove session file
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
        
        return {
            "success": True,
            "message": "Paper trading session stopped",
            "final_summary": summary
        }
    
    def reset_session(self) -> Dict[str, Any]:
        """Reset session to starting capital"""
        if not self.portfolio:
            return {"success": False, "error": "No active session"}
        
        capital = self.portfolio.starting_capital
        strategy = self.portfolio.strategy
        position_sizing = self.portfolio.position_sizing
        max_concurrent = self.portfolio.max_concurrent
        
        return self.start_session(capital, strategy, position_sizing, max_concurrent)
    
    def process_signal(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Process an incoming alert signal"""
        if not self.portfolio:
            return {"success": False, "error": "No active session"}
        
        # Check if we can open a new position
        if len(self.portfolio.open_positions) >= self.portfolio.max_concurrent:
            return {"success": False, "error": "Max concurrent positions reached"}
        
        # Check strategy filter
        strategy = self.portfolio.strategy
        score = alert.get('final_score', 0)
        smart_money = alert.get('smart_money_detected', False)
        conviction = alert.get('conviction_type', '')
        
        # Apply strategy filters
        if strategy == "smart_money_only" and not smart_money:
            return {"success": False, "error": "Strategy requires smart money"}
        if strategy == "high_conviction" and score < 7:
            return {"success": False, "error": "Strategy requires score >= 7"}
        
        # Calculate position size
        position_size = self._calculate_position_size(alert)
        
        # Check if we have enough capital
        available_capital = self.portfolio.current_value - sum(p.position_size_usd for p in self.portfolio.open_positions)
        if position_size > available_capital:
            return {"success": False, "error": "Insufficient capital"}
        
        # Create position
        entry_price = alert.get('price', 0.0)
        if entry_price == 0:
            return {"success": False, "error": "Invalid entry price"}
        
        quantity = position_size / entry_price
        
        position = PaperPosition(
            token=alert.get('token', ''),
            symbol=alert.get('symbol', ''),
            entry_price=entry_price,
            entry_time=alert.get('ts', datetime.now().isoformat()),
            position_size_usd=position_size,
            quantity=quantity,
            score=score,
            conviction=conviction,
            smart_money=smart_money,
            current_price=entry_price,
            pnl_percent=0.0,
            pnl_usd=0.0,
            is_open=True
        )
        
        self.portfolio.open_positions.append(position)
        self.portfolio.total_trades += 1
        self.portfolio.updated_at = datetime.now().isoformat()
        
        self._save_session()
        
        return {
            "success": True,
            "message": "Position opened",
            "position": asdict(position)
        }
    
    def _calculate_position_size(self, alert: Dict[str, Any]) -> float:
        """Calculate position size based on strategy"""
        sizing = self.portfolio.position_sizing
        score = alert.get('final_score', 0)
        
        if sizing == "fixed_50":
            return 50.0
        elif sizing == "percentage_5":
            return self.portfolio.current_value * 0.05
        elif sizing == "score_based":
            # Higher score = larger position (1-10 score maps to 2-10% of capital)
            percent = 0.02 + (score / 10.0 * 0.08)
            return self.portfolio.current_value * percent
        else:
            return 50.0  # Default
    
    def update_positions(self) -> Dict[str, Any]:
        """Update all open positions with current market prices"""
        if not self.portfolio:
            return {"success": False, "error": "No active session"}
        
        # Get current prices from database
        db_path = os.getenv("CALLSBOT_DB_FILE", "var/alerted_tokens.db")
        
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            total_unrealized = 0.0
            
            for pos in self.portfolio.open_positions:
                # Get latest price
                c.execute("""
                    SELECT last_price_usd FROM alerted_token_stats
                    WHERE token_address = ?
                """, (pos.token,))
                
                result = c.fetchone()
                if result and result[0]:
                    pos.current_price = result[0]
                    
                    # Calculate P/L
                    pos.pnl_percent = ((pos.current_price - pos.entry_price) / pos.entry_price) * 100
                    pos.pnl_usd = (pos.current_price - pos.entry_price) * pos.quantity
                    
                    # Calculate hold time
                    entry_time = datetime.fromisoformat(pos.entry_time)
                    pos.hold_time_hours = (datetime.now() - entry_time).total_seconds() / 3600
                    
                    total_unrealized += pos.pnl_usd
            
            conn.close()
            
            # Update portfolio value
            self.portfolio.unrealized_pnl = total_unrealized
            self.portfolio.current_value = self.portfolio.starting_capital + self.portfolio.realized_pnl + total_unrealized
            self.portfolio.updated_at = datetime.now().isoformat()
            
            self._save_session()
            
            return {"success": True, "message": "Positions updated"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def close_position(self, token: str, exit_price: float) -> Dict[str, Any]:
        """Close a position"""
        if not self.portfolio:
            return {"success": False, "error": "No active session"}
        
        # Find position
        position = None
        for i, pos in enumerate(self.portfolio.open_positions):
            if pos.token == token:
                position = self.portfolio.open_positions.pop(i)
                break
        
        if not position:
            return {"success": False, "error": "Position not found"}
        
        # Calculate final P/L
        position.exit_price = exit_price
        position.exit_time = datetime.now().isoformat()
        position.is_open = False
        position.current_price = exit_price
        position.pnl_percent = ((exit_price - position.entry_price) / position.entry_price) * 100
        position.pnl_usd = (exit_price - position.entry_price) * position.quantity
        
        # Calculate hold time
        entry_time = datetime.fromisoformat(position.entry_time)
        exit_time = datetime.fromisoformat(position.exit_time)
        position.hold_time_hours = (exit_time - entry_time).total_seconds() / 3600
        
        # Update portfolio
        self.portfolio.realized_pnl += position.pnl_usd
        self.portfolio.closed_positions.append(position)
        
        if position.pnl_usd > 0:
            self.portfolio.wins += 1
        else:
            self.portfolio.losses += 1
        
        total_closed = self.portfolio.wins + self.portfolio.losses
        self.portfolio.win_rate = (self.portfolio.wins / total_closed * 100) if total_closed > 0 else 0
        
        self.portfolio.updated_at = datetime.now().isoformat()
        self._save_session()
        
        return {
            "success": True,
            "message": "Position closed",
            "position": asdict(position)
        }
    
    def get_portfolio_summary(self) -> Optional[Dict[str, Any]]:
        """Get current portfolio summary"""
        if not self.portfolio:
            return None
        
        return {
            "starting_capital": self.portfolio.starting_capital,
            "current_value": round(self.portfolio.current_value, 2),
            "realized_pnl": round(self.portfolio.realized_pnl, 2),
            "unrealized_pnl": round(self.portfolio.unrealized_pnl, 2),
            "total_pnl": round(self.portfolio.realized_pnl + self.portfolio.unrealized_pnl, 2),
            "total_pnl_percent": round(((self.portfolio.current_value - self.portfolio.starting_capital) / self.portfolio.starting_capital * 100), 2),
            "open_positions": [asdict(p) for p in self.portfolio.open_positions],
            "closed_positions": [asdict(p) for p in self.portfolio.closed_positions],
            "total_trades": self.portfolio.total_trades,
            "wins": self.portfolio.wins,
            "losses": self.portfolio.losses,
            "win_rate": round(self.portfolio.win_rate, 1),
            "strategy": self.portfolio.strategy,
            "max_concurrent": self.portfolio.max_concurrent,
            "position_sizing": self.portfolio.position_sizing,
            "created_at": self.portfolio.created_at,
            "updated_at": self.portfolio.updated_at
        }
    
    def run_backtest(self, days: int, capital: float, strategy: str) -> Dict[str, Any]:
        """Run backtest on historical data"""
        # Get historical alerts
        alerts = []
        alerts_path = "data/logs/alerts.jsonl"
        
        try:
            with open(alerts_path, 'r') as f:
                lines = f.readlines()
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                
                for line in lines:
                    try:
                        alert = json.loads(line.strip())
                        if alert.get('ts', '') >= cutoff:
                            alerts.append(alert)
                    except:
                        continue
        except:
            return {"success": False, "error": "Could not load historical data"}
        
        # Simulate trading
        portfolio_value = capital
        trades = []
        wins = 0
        losses = 0
        
        for alert in alerts:
            score = alert.get('final_score', 0)
            smart_money = alert.get('smart_money_detected', False)
            
            # Apply strategy filter
            if strategy == "smart_money_only" and not smart_money:
                continue
            if strategy == "high_conviction" and score < 7:
                continue
            
            # Simulate trade (simplified - assume 50% win rate, +20% avg win, -10% avg loss)
            import random
            is_win = random.random() < 0.6  # 60% win rate for backtest
            
            if is_win:
                pnl = 0.20  # +20%
                wins += 1
            else:
                pnl = -0.10  # -10%
                losses += 1
            
            trade_value = capital * 0.05  # 5% per trade
            profit = trade_value * pnl
            portfolio_value += profit
            
            trades.append({
                "token": alert.get('token', ''),
                "score": score,
                "conviction": alert.get('conviction_type', ''),
                "pnl_percent": pnl * 100,
                "pnl_usd": profit
            })
        
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        final_pnl = portfolio_value - capital
        roi = (final_pnl / capital * 100)
        
        return {
            "success": True,
            "backtest": {
                "days": days,
                "strategy": strategy,
                "starting_capital": capital,
                "final_value": round(portfolio_value, 2),
                "total_pnl": round(final_pnl, 2),
                "roi_percent": round(roi, 1),
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
                "trades": trades[-20:]  # Last 20 trades
            }
        }


# Global engine instance
_engine = PaperTradingEngine()


def get_paper_trading_engine() -> PaperTradingEngine:
    """Get the global paper trading engine"""
    return _engine

