#!/usr/bin/env python3
"""Direct buy of BONK memecoin"""
import sys
sys.path.insert(0, '/app')

from tradingSystem.broker_optimized import Broker

# BONK token address (well-established Solana memecoin)
BONK_TOKEN = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

print(f"Buying $10 worth of BONK...")
print(f"Token: {BONK_TOKEN}")

broker = Broker()
print(f"Broker initialized (dry_run={broker._dry})")

result = broker.market_buy(BONK_TOKEN, 10.0)

print(f"\n{'='*60}")
print(f"TRADE RESULT:")
print(f"{'='*60}")
print(f"Success: {result.success}")
print(f"Quantity: {result.qty:.2f} BONK")
print(f"Price: ${result.price:.8f}")
print(f"USD Spent: ${result.usd:.2f}")
print(f"Transaction: {result.tx if result.tx else 'N/A'}")
if result.error:
    print(f"Error: {result.error}")
print(f"{'='*60}")


