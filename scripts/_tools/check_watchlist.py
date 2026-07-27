#!/usr/bin/env python3
import redis
import json

# Connect to Redis
r = redis.Redis(host='redis', port=6379, decode_responses=True)

# Get all watchlist signals
signals = r.hgetall('watchlist:signals')

print(f"\n📊 WATCHLIST STATUS: {len(signals)} signals tracked\n")
print("=" * 80)

if signals:
    for token, data_str in list(signals.items())[:25]:  # Show first 25
        try:
            data = json.loads(data_str)
            score = data.get('score', '?')
            age_min = data.get('age', 0) / 60
            entered = data.get('entered', False)
            exited = data.get('exited', False)
            
            status = "✅ ENTERED" if entered else ("🚫 EXITED" if exited else "👁️ WATCHING")
            
            print(f"{token[:16]}... | Score: {score}/10 | Age: {age_min:.0f}min | {status}")
        except:
            print(f"{token[:16]}... | (data parse error)")
else:
    print("No signals in watchlist")

print("=" * 80)



