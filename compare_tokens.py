import json
import sqlite3

# Connect to database
conn = sqlite3.connect("/opt/callsbotonchain/deployment/var/alerted_tokens.db")
cursor = conn.cursor()

# Get top 15 tokens by gain
cursor.execute("""
SELECT a.token_address, s.max_gain_percent, ROUND((s.max_gain_percent/100.0 + 1), 1) as multiplier
FROM alerted_tokens a 
JOIN alerted_token_stats s ON a.token_address = s.token_address
ORDER BY s.max_gain_percent DESC 
LIMIT 15
""")
top_tokens = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

# Read alerts log to get names
token_names = {}
with open("/opt/callsbotonchain/data/logs/alerts.jsonl", "r") as f:
    for line in f:
        try:
            alert = json.loads(line.strip())
            token_addr = alert.get("token")
            if token_addr and token_addr in top_tokens:
                token_names[token_addr] = {
                    "name": alert.get("name", "?"),
                    "symbol": alert.get("symbol", "?"),
                    "gain_pct": top_tokens[token_addr][0],
                    "multiplier": top_tokens[token_addr][1]
                }
        except:
            pass

# Print results
print("\n=== DATABASE TOP 15 (with names from alerts log) ===")
print(f"{'Name':<25} {'Symbol':<15} {'Multiplier':<12} {'Gain %':<12} {'Token'}")
print("-" * 90)
for addr, data in sorted(token_names.items(), key=lambda x: x[1]["gain_pct"], reverse=True):
    print(f"{data['name'][:24]:<25} {data['symbol'][:14]:<15} {data['multiplier']:<12.1f} {data['gain_pct']:<12.1f} {addr[:12]}")

conn.close()

