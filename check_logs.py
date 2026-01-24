"""Quick script to check trading logs"""
import sqlite3
from datetime import datetime, timedelta

print("="*60)
print("TRADING BOT STATUS CHECK")
print("="*60)
print(f"\nCurrent Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Check Period: Last 7 days")
print()

# Check trading database
conn = sqlite3.connect('var/trading.db')
c = conn.cursor()

# Total positions
c.execute("SELECT COUNT(*) FROM positions")
total = c.fetchone()[0]
print(f"Total positions ever: {total}")

# Date range
c.execute("SELECT MIN(open_at), MAX(open_at) FROM positions")
min_date, max_date = c.fetchone()
print(f"Date range: {min_date} to {max_date}")

# Days since last position
if max_date:
    last_pos_date = datetime.strptime(max_date, '%Y-%m-%d %H:%M:%S')
    days_ago = (datetime.now() - last_pos_date).days
    print(f"Days since last position: {days_ago} days")

# Status breakdown
c.execute("SELECT status, COUNT(*) FROM positions GROUP BY status")
status_counts = c.fetchall()
print("\nPosition status:")
for status, count in status_counts:
    print(f"  {status}: {count}")

# Recent positions (last 10 non-test)
print("\nLast 10 positions:")
c.execute("""
    SELECT id, token_address, open_at, status 
    FROM positions 
    ORDER BY id DESC 
    LIMIT 10
""")
rows = c.fetchall()
for row in rows:
    token = row[1][:15] + "..." if len(row[1]) > 15 else row[1]
    print(f"  #{row[0]:4d} | {row[2]:19s} | {row[3]:8s} | {token}")

conn.close()

# Check alerted tokens
print("\n" + "="*60)
print("SIGNAL DETECTION STATUS")
print("="*60)

conn2 = sqlite3.connect('var/alerted_tokens.db')
c2 = conn2.cursor()

# Get schema first
c2.execute("PRAGMA table_info(alerted_tokens)")
columns = [col[1] for col in c2.fetchall()]
print(f"\nAlerted tokens DB columns: {', '.join(columns)}")

c2.execute("SELECT COUNT(*) FROM alerted_tokens")
total_alerts = c2.fetchone()[0]
print(f"Total signals alerted: {total_alerts}")

# Get time column name
time_col = 'alerted_at' if 'alerted_at' in columns else 'timestamp'
if time_col in columns:
    c2.execute(f"SELECT MIN({time_col}), MAX({time_col}) FROM alerted_tokens")
    min_alert, max_alert = c2.fetchone()
    print(f"Alert date range: {min_alert} to {max_alert}")
    
    if max_alert:
        try:
            last_alert_date = datetime.fromisoformat(max_alert.replace('Z', '+00:00'))
            days_since_alert = (datetime.now() - last_alert_date.replace(tzinfo=None)).days
            print(f"Days since last alert: {days_since_alert} days")
        except:
            print(f"Last alert time: {max_alert}")

# Recent alerts
print("\nLast 10 signals:")
c2.execute(f"SELECT token_address, {time_col} FROM alerted_tokens ORDER BY {time_col} DESC LIMIT 10")
rows = c2.fetchall()
for row in rows:
    token = row[0][:15] + "..." if len(row[0]) > 15 else row[0]
    print(f"  {row[1]} | {token}")

conn2.close()

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)

if days_ago > 10:
    print(f"\n⚠️  BOT APPEARS INACTIVE")
    print(f"   Last trading activity: {days_ago} days ago")
    print(f"   Last position: {max_date}")
    print("\n   This suggests:")
    print("   - Bot not running")
    print("   - No signals being generated")
    print("   - System needs to be started")
else:
    print(f"\n✅ BOT APPEARS ACTIVE")
    print(f"   Recent activity: {days_ago} days ago")

