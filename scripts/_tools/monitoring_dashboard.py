#!/usr/bin/env python3
"""
Real-time Trading Monitor Dashboard
Shows current positions, P&L, circuit breaker status, and system health
"""

import sys
import os
import time
import sqlite3
from datetime import datetime
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tradingSystem.config_optimized import DB_PATH
from src.tradingSystem.circuit_breaker import get_circuit_breaker


def get_open_positions() -> List[Dict]:
    """Get all open positions from database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, token_address, strategy, qty, entry_price, peak_price, opened_at
            FROM positions
            WHERE status = 'open'
            ORDER BY opened_at DESC
        """)
        
        positions = []
        for row in cursor.fetchall():
            positions.append({
                "id": row[0],
                "token": row[1],
                "strategy": row[2],
                "qty": row[3],
                "entry_price": row[4],
                "peak_price": row[5],
                "opened_at": row[6],
            })
        
        conn.close()
        return positions
    
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []


def get_recent_trades(limit: int = 10) -> List[Dict]:
    """Get recent closed positions"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, token_address, strategy, entry_price, peak_price, closed_at
            FROM positions
            WHERE status = 'closed'
            ORDER BY closed_at DESC
            LIMIT ?
        """, (limit,))
        
        trades = []
        for row in cursor.fetchall():
            trades.append({
                "id": row[0],
                "token": row[1],
                "strategy": row[2],
                "entry_price": row[3],
                "peak_price": row[4],
                "closed_at": row[5],
            })
        
        conn.close()
        return trades
    
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return []


def get_daily_pnl() -> Dict:
    """Calculate today's P&L"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        today = datetime.now().date().isoformat()
        
        # Get all closed positions from today
        cursor.execute("""
            SELECT entry_price, qty
            FROM positions
            JOIN fills ON positions.id = fills.position_id
            WHERE positions.status = 'closed'
            AND DATE(positions.closed_at) = ?
            AND fills.side = 'buy'
        """, (today,))
        
        total_cost = sum(entry * qty for entry, qty in cursor.fetchall())
        
        cursor.execute("""
            SELECT price, qty
            FROM positions
            JOIN fills ON positions.id = fills.position_id
            WHERE positions.status = 'closed'
            AND DATE(positions.closed_at) = ?
            AND fills.side = 'sell'
        """, (today,))
        
        total_revenue = sum(price * qty for price, qty in cursor.fetchall())
        
        conn.close()
        
        pnl = total_revenue - total_cost
        pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0
        
        return {
            "pnl_usd": pnl,
            "pnl_pct": pnl_pct,
            "total_cost": total_cost,
            "total_revenue": total_revenue,
        }
    
    except Exception as e:
        print(f"Error calculating P&L: {e}")
        return {"pnl_usd": 0, "pnl_pct": 0, "total_cost": 0, "total_revenue": 0}


def print_dashboard():
    """Print the monitoring dashboard"""
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("=" * 80)
    print("  🚀 MEMECOIN BOT MONITORING DASHBOARD")
    print("=" * 80)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Circuit Breaker Status
    circuit_breaker = get_circuit_breaker()
    cb_status = circuit_breaker.get_status()
    
    print("\n🛡️  CIRCUIT BREAKER STATUS")
    print("-" * 80)
    
    if cb_status["can_trade"]:
        print("  Status: ✅ ACTIVE (trading enabled)")
    else:
        print(f"  Status: 🚨 TRIPPED (trading halted)")
        print(f"  Reason: {cb_status['trip_reason']}")
    
    print(f"  Daily P&L: ${cb_status['daily_pnl_usd']:+.2f} / -${cb_status['daily_loss_limit_usd']:.2f} limit")
    print(f"  Weekly P&L: ${cb_status['weekly_pnl_usd']:+.2f} / -${cb_status['weekly_loss_limit_usd']:.2f} limit")
    print(f"  Consecutive Losses: {cb_status['consecutive_losses']} / {cb_status['consecutive_loss_limit']} max")
    print(f"  Slippage Events: {cb_status['excessive_slippage_count']} / {cb_status['slippage_event_limit']} max")
    
    # Open Positions
    print("\n📈  OPEN POSITIONS")
    print("-" * 80)
    
    positions = get_open_positions()
    
    if positions:
        print(f"  {'ID':<6} {'Token':<10} {'Strategy':<15} {'Entry':<12} {'Peak':<12} {'Profit':<8} {'Age':<8}")
        print("  " + "-" * 76)
        
        for pos in positions:
            token_short = pos["token"][:8] + "..."
            entry = pos["entry_price"]
            peak = pos["peak_price"]
            profit_pct = ((peak - entry) / entry * 100) if entry > 0 else 0
            
            opened = datetime.fromisoformat(pos["opened_at"].replace("Z", ""))
            age_minutes = (datetime.now() - opened).total_seconds() / 60
            
            if age_minutes < 60:
                age_str = f"{age_minutes:.0f}m"
            elif age_minutes < 1440:
                age_str = f"{age_minutes/60:.1f}h"
            else:
                age_str = f"{age_minutes/1440:.1f}d"
            
            profit_icon = "🟢" if profit_pct > 0 else "🔴" if profit_pct < -5 else "⚪"
            
            print(f"  {pos['id']:<6} {token_short:<10} {pos['strategy']:<15} "
                  f"${entry:<11.8f} ${peak:<11.8f} {profit_icon}{profit_pct:+6.1f}% {age_str:<8}")
    else:
        print("  No open positions")
    
    # Recent Trades
    print("\n📊  RECENT TRADES (Last 10)")
    print("-" * 80)
    
    trades = get_recent_trades(10)
    
    if trades:
        print(f"  {'ID':<6} {'Token':<10} {'Strategy':<15} {'Entry':<12} {'Peak':<12} {'Profit':<8}")
        print("  " + "-" * 76)
        
        for trade in trades:
            token_short = trade["token"][:8] + "..."
            entry = trade["entry_price"]
            peak = trade["peak_price"]
            profit_pct = ((peak - entry) / entry * 100) if entry > 0 else 0
            
            profit_icon = "🟢" if profit_pct > 0 else "🔴"
            
            print(f"  {trade['id']:<6} {token_short:<10} {trade['strategy']:<15} "
                  f"${entry:<11.8f} ${peak:<11.8f} {profit_icon}{profit_pct:+6.1f}%")
    else:
        print("  No recent trades")
    
    # Daily P&L
    print("\n💰  TODAY'S PERFORMANCE")
    print("-" * 80)
    
    daily_pnl = get_daily_pnl()
    pnl_icon = "🟢" if daily_pnl["pnl_usd"] > 0 else "🔴" if daily_pnl["pnl_usd"] < 0 else "⚪"
    
    print(f"  P&L: {pnl_icon} ${daily_pnl['pnl_usd']:+.2f} ({daily_pnl['pnl_pct']:+.1f}%)")
    print(f"  Capital Deployed: ${daily_pnl['total_cost']:.2f}")
    print(f"  Revenue: ${daily_pnl['total_revenue']:.2f}")
    
    print("\n" + "=" * 80)
    print("  Press Ctrl+C to exit | Refreshing in 5 seconds...")
    print("=" * 80)


def main():
    """Main monitoring loop"""
    print("Starting monitoring dashboard...")
    print("Press Ctrl+C to exit")
    time.sleep(2)
    
    try:
        while True:
            print_dashboard()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


if __name__ == "__main__":
    main()















