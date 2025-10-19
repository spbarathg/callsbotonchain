#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from app.notify import send_telegram_alert

msg = """🧪 FINAL TEST (Signal Aggregator Stopped)

This test verifies alerts work without Signal Aggregator.

Time: Now
Status: ✅ System operational

Did you receive this message? (y/n)"""

result = send_telegram_alert(msg)
print(f"\n✅ Result: {result}")

