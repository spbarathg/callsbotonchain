#!/usr/bin/env python3
"""Validate P&L for specific positions"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3

def main():
    conn = sqlite3.connect('var/trading.db')
    
    tokens = [
        'zgQnq6GEUWuEEa2QvqT69amJtKaj7oU4nKDP4cTpump',
        '6bD71gqiAkdh4SVCVqy6X2F7o96n1RXL5JaWYU9xpump',
        'GHTsyY8doW5vziZXgpmkDdfAypMeFjeaVZ9HYpU7sYK9',
        'HRDHMH8LGR4do6rv2Hgd16y85R18xUeio1YFygKzpump',
        '9fURVh8YkzXDch2KmiBK7YT1zPYGC9UcWfXATvcupump',
        '82CffBux1BTXk2aHvB9jbWecVUGMGHToEADnNaipump'
    ]
    
    print('\n=== P&L VALIDATION ===\n')
    total_pnl = 0
    wins = 0
    losses = 0
    
    for token in tokens:
        cur = conn.execute('''
            SELECT token_address, usd_size, status,
                   (SELECT SUM(usd) FROM fills WHERE position_id = positions.id AND side='sell') as total_sold,
                   (SELECT SUM(usd) FROM fills WHERE position_id = positions.id AND side='buy') as total_bought
            FROM positions 
            WHERE token_address = ?
            ORDER BY id DESC LIMIT 1
        ''', (token,))
        row = cur.fetchone()
        
        if row:
            _, entry_usd, status, total_sold, total_bought = row
            if total_sold and total_bought:
                pnl_usd = total_sold - total_bought
                pnl_pct = (pnl_usd / total_bought) * 100 if total_bought > 0 else 0
                total_pnl += pnl_usd
                
                if pnl_pct > 0:
                    wins += 1
                    emoji = '✅'
                else:
                    losses += 1
                    emoji = '❌'
                    
                print(f'{emoji} {token[:8]}... | Entry: ${total_bought:.2f} Exit: ${total_sold:.2f} | P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f})')
            else:
                print(f'⚠️  {token[:8]}... | Status: {status} (incomplete data)')
        else:
            print(f'❌ {token[:8]}... | NOT FOUND in database')
    
    print('\n' + '='*60)
    print(f'Total P&L: ${total_pnl:.2f}')
    if wins + losses > 0:
        print(f'Win Rate: {wins}/{wins+losses} ({wins/(wins+losses)*100:.1f}%)')
    if wins > 0:
        print(f'Winners: {wins} positions')
    if losses > 0:
        print(f'Losers: {losses} positions')
    print('='*60)

if __name__ == "__main__":
    main()

