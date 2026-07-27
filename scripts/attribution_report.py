import sqlite3
import os
import argparse
from typing import List, Dict, Any

DB_PATH = os.getenv("TRADING_DB_PATH", "var/trading.db")

def get_db():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return None
    return sqlite3.connect(DB_PATH)

def fetch_top_funnel_stats(conn):
    c = conn.cursor()
    c.execute("""
        SELECT 
            source_name,
            COUNT(*) as total_signals,
            SUM(CASE WHEN entered_trade = 1 THEN 1 ELSE 0 END) as traded_signals
        FROM signals
        WHERE timestamp >= datetime('now', '-30 days')
        GROUP BY source_name
        ORDER BY total_signals DESC
    """)
    return c.fetchall()

def fetch_trade_attribution(conn):
    c = conn.cursor()
    c.execute("""
        SELECT 
            entry_source,
            COUNT(*) as num_trades,
            SUM(CASE WHEN status = 'closed' AND pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_trades,
            SUM(pnl_usd) as total_pnl_usd,
            SUM(CASE WHEN status = 'closed' AND pnl_usd > 0 THEN pnl_usd ELSE 0 END) as gross_profit,
            ABS(SUM(CASE WHEN status = 'closed' AND pnl_usd < 0 THEN pnl_usd ELSE 0 END)) as gross_loss,
            SUM(CASE WHEN status = 'closed' AND pnl_usd > 0 THEN pnl_usd ELSE 0 END) / NULLIF(SUM(CASE WHEN status = 'closed' AND pnl_usd > 0 THEN 1 ELSE 0 END), 0) as avg_win,
            ABS(SUM(CASE WHEN status = 'closed' AND pnl_usd < 0 THEN pnl_usd ELSE 0 END) / NULLIF(SUM(CASE WHEN status = 'closed' AND pnl_usd < 0 THEN 1 ELSE 0 END), 0)) as avg_loss,
            AVG(CASE WHEN initial_risk_usd > 0 THEN pnl_usd / initial_risk_usd ELSE NULL END) as avg_r_multiple,
            AVG(time_to_entry_mins) as avg_time_to_entry
        FROM positions
        WHERE open_at >= datetime('now', '-30 days') AND entry_source IS NOT NULL AND entry_source != 'unknown'
        GROUP BY entry_source
        ORDER BY total_pnl_usd DESC
    """)
    return c.fetchall()

def fetch_source_combinations(conn):
    c = conn.cursor()
    c.execute("""
        SELECT 
            all_sources,
            COUNT(*) as num_trades,
            SUM(CASE WHEN status = 'closed' AND pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_trades,
            SUM(pnl_usd) as total_pnl_usd,
            AVG(CASE WHEN initial_risk_usd > 0 THEN pnl_usd / initial_risk_usd ELSE NULL END) as avg_r_multiple
        FROM positions
        WHERE open_at >= datetime('now', '-30 days') AND all_sources IS NOT NULL AND all_sources != '[]'
        GROUP BY all_sources
        ORDER BY total_pnl_usd DESC
        LIMIT 10
    """)
    return c.fetchall()

def fetch_source_x_confidence(conn):
    c = conn.cursor()
    c.execute("""
        SELECT 
            entry_source,
            entry_score as score,
            COUNT(*) as num_trades,
            SUM(CASE WHEN status = 'closed' AND pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_trades,
            SUM(pnl_usd) as total_pnl_usd
        FROM positions
        WHERE open_at >= datetime('now', '-30 days') AND entry_score > 0 AND entry_source IS NOT NULL AND entry_source != 'unknown'
        GROUP BY entry_source, entry_score
        ORDER BY entry_source, entry_score DESC
    """)
    return c.fetchall()

def fetch_opportunity_cost(conn):
    c = conn.cursor()
    c.execute("""
        SELECT 
            source_name,
            COUNT(*) as total_signals,
            AVG(peak_return_24h) as avg_peak_24h,
            AVG(drawdown_24h) as avg_dd_24h,
            AVG(time_to_peak) as avg_time_to_peak
        FROM signals
        WHERE timestamp >= datetime('now', '-30 days') AND peak_return_24h IS NOT NULL
        GROUP BY source_name
        ORDER BY avg_peak_24h DESC
    """)
    return c.fetchall()

def main():
    conn = get_db()
    if not conn:
        return

    print("=========================================================")
    print("      ADVANCED SIGNAL ATTRIBUTION REPORT (30 DAYS)       ")
    print("=========================================================\n")

    print("1. SIGNAL FUNNEL (Total Signals -> Executed Trades)")
    print(f"{'Source':<20} | {'Signals':<8} | {'Traded':<8} | {'Conversion %':<12}")
    print("-" * 60)
    for row in fetch_top_funnel_stats(conn):
        source, total, traded = row
        conv = (traded / total * 100) if total > 0 else 0
        print(f"{source:<20} | {total:<8} | {traded:<8} | {conv:<12.1f}%")
    print("\n")

    print("2. SOURCE PNL & EXPECTANCY ATTRIBUTION (By Entry Source)")
    print(f"{'Source':<18} | {'Trades':<6} | {'Win %':<6} | {'Exp($)':<8} | {'Exp(R)':<8} | {'Net PnL($)':<10} | {'Avg Delay':<10}")
    print("-" * 85)
    for row in fetch_trade_attribution(conn):
        source, num, wins, closed, pnl_usd, gross_profit, gross_loss, avg_win, avg_loss, avg_r, avg_delay = row
        win_rate = (wins / closed) if closed > 0 else 0.0
        loss_rate = 1.0 - win_rate
        avg_win = avg_win or 0.0
        avg_loss = avg_loss or 0.0
        expectancy_usd = (win_rate * avg_win) - (loss_rate * avg_loss)
        avg_r = avg_r or 0.0
        avg_delay = avg_delay or 0.0
        
        win_rate_pct = win_rate * 100
        pnl_usd = pnl_usd or 0.0
        delay_str = f"{avg_delay:.1f}m"
        print(f"{source:<18} | {num:<6} | {win_rate_pct:>5.1f}% | ${expectancy_usd:>6.2f} | {avg_r:>5.2f}R   | ${pnl_usd:>8.2f} | {delay_str:<10}")
    print("\n")

    print("3. SOURCE COMBINATIONS (All Sources Flagged Before Entry)")
    print(f"{'Combination':<40} | {'Trades':<6} | {'Win %':<6} | {'Exp(R)':<8} | {'Net PnL($)':<10}")
    print("-" * 80)
    for row in fetch_source_combinations(conn):
        combo, num, wins, closed, pnl_usd, avg_r = row
        win_rate = (wins / closed * 100) if closed > 0 else 0.0
        avg_r = avg_r or 0.0
        pnl_usd = pnl_usd or 0.0
        # truncate combo string if too long
        combo_str = str(combo)[:38] + ".." if len(str(combo)) > 40 else str(combo)
        print(f"{combo_str:<40} | {num:<6} | {win_rate:>5.1f}% | {avg_r:>5.2f}R   | ${pnl_usd:>8.2f}")
    print("\n")

    print("4. SOURCE X CONFIDENCE SCORE (Alpha Zones)")
    print(f"{'Source':<18} | {'Score':<5} | {'Trades':<6} | {'Win %':<6} | {'Net PnL($)':<10}")
    print("-" * 60)
    for row in fetch_source_x_confidence(conn):
        source, score, num, wins, closed, pnl_usd = row
        win_rate = (wins / closed * 100) if closed > 0 else 0.0
        pnl_usd = pnl_usd or 0.0
        print(f"{source:<18} | {score:<5} | {num:<6} | {win_rate:>5.1f}% | ${pnl_usd:>8.2f}")
    print("\n")

    print("5. OPPORTUNITY COST / SIGNAL QUALITY (Including Rejected Signals)")
    print(f"{'Source':<20} | {'Signals':<8} | {'Avg Peak 24h':<15} | {'Avg Drawdown':<15} | {'Avg Time To Peak':<15}")
    print("-" * 85)
    for row in fetch_opportunity_cost(conn):
        source, total, avg_peak, avg_dd, avg_time = row
        peak_str = f"+{(avg_peak*100):.1f}%" if avg_peak else "N/A"
        dd_str = f"{(avg_dd*100):.1f}%" if avg_dd else "N/A"
        time_str = f"{avg_time:.1f}h" if avg_time else "N/A"
        print(f"{source:<20} | {total:<8} | {peak_str:<15} | {dd_str:<15} | {time_str:<15}")

    print("\n=========================================================")
    conn.close()

if __name__ == '__main__':
    main()
