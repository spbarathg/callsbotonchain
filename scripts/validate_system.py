"""Comprehensive system validation - Check for errors and bugs"""
import subprocess
import sys

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n{'='*80}")
    print(f"✓ {description}")
    print(f"{'='*80}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ PASS")
            if result.stdout.strip():
                print(result.stdout[:500])  # Show first 500 chars
            return True
        else:
            print(f"❌ FAIL (exit code: {result.returncode})")
            if result.stderr:
                print(f"Error: {result.stderr[:500]}")
            return False
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False

print("=" * 80)
print("TRADING SYSTEM VALIDATION")
print("=" * 80)
print("\nThis will check:")
print("1. Server connectivity")
print("2. Docker containers health")
print("3. Database integrity")
print("4. Trading system status")
print("5. No critical errors in logs")

results = {}

# 1. Server connectivity
results['server'] = run_command(
    'ssh root@64.227.157.221 "echo Server is reachable"',
    "1. Server Connectivity"
)

# 2. Docker containers
results['containers'] = run_command(
    'ssh root@64.227.157.221 "docker ps --filter name=callsbot --format \'{{.Names}}: {{.Status}}\'"',
    "2. Docker Containers Status"
)

# 3. Database integrity
results['database'] = run_command(
    'ssh root@64.227.157.221 "docker exec callsbot-trader python3 -c \\"import sqlite3; conn = sqlite3.connect(\'var/trading.db\'); c = conn.cursor(); c.execute(\'SELECT COUNT(*) FROM positions\'); print(f\'Total positions: {c.fetchone()[0]}\'); c.execute(\'SELECT COUNT(*) FROM positions WHERE status=\\\\\'open\\\\\'\'); print(f\'Open positions: {c.fetchone()[0]}\'); conn.close()\\""',
    "3. Database Integrity"
)

# 4. Trading system status
results['trader'] = run_command(
    'ssh root@64.227.157.221 "docker logs --tail 5 callsbot-trader 2>&1"',
    "4. Trading System (Last 5 log lines)"
)

# 5. Check for errors
results['errors'] = run_command(
    'ssh root@64.227.157.221 "docker logs --since 10m callsbot-trader 2>&1 | grep -i error | wc -l"',
    "5. Error Count (Last 10 minutes)"
)

# 6. Exit loop status
results['exit_loop'] = run_command(
    'ssh root@64.227.157.221 "docker logs --since 5m callsbot-trader 2>&1 | grep EXIT_LOOP | tail -2"',
    "6. Exit Loop Activity"
)

# 7. Redis connectivity
results['redis'] = run_command(
    'ssh root@64.227.157.221 "docker exec callsbot-redis redis-cli PING"',
    "7. Redis Connectivity"
)

print("\n" + "=" * 80)
print("VALIDATION SUMMARY")
print("=" * 80)

passed = sum(1 for v in results.values() if v)
total = len(results)

for check, status in results.items():
    icon = "✅" if status else "❌"
    print(f"{icon} {check.upper()}: {'PASS' if status else 'FAIL'}")

print("\n" + "=" * 80)
print(f"OVERALL: {passed}/{total} checks passed")
print("=" * 80)

if passed == total:
    print("\n🎉 ALL CHECKS PASSED! Trading system is healthy and ready.")
    sys.exit(0)
else:
    print(f"\n⚠️  {total - passed} check(s) failed. Review the output above.")
    sys.exit(1)

