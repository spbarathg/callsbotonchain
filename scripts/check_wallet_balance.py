#!/usr/bin/env python3
"""Check wallet's on-chain balance for a specific token"""

import sys
sys.path.insert(0, '/app')

from tradingSystem.token_balance import get_token_balance

token = 'SPeoKNTCG4knwrCC2pgAS98CMqnpy8AY1PyHmKyV7fE'

print(f"🔍 Checking wallet balance for: {token[:15]}...\n")

try:
    balance = get_token_balance(token)
    if balance is None:
        print("❌ Could not fetch balance (token account may not exist)")
    elif balance == 0:
        print("✅ Balance: 0 tokens (token account exists but empty)")
    else:
        print(f"✅ Balance: {balance:,.4f} tokens")
        print(f"   This position EXISTS in wallet but NOT in database!")
except Exception as e:
    print(f"❌ Error: {e}")


