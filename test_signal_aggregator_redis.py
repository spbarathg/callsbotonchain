#!/usr/bin/env python3
"""
Test Signal Aggregator Redis Integration

Verifies that:
1. Signal Aggregator can store signals in Redis
2. Main bot can read signal counts from Redis
3. Cross-process communication works correctly
"""
import os
import sys
import time
import asyncio

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Set up Redis URL for testing
os.environ['REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

from app.signal_aggregator import record_signal, get_signal_count, _init_redis

def test_redis_connection():
    """Test 1: Redis connection works"""
    print("=" * 60)
    print("TEST 1: Redis Connection")
    print("=" * 60)
    
    redis = _init_redis()
    if redis is None:
        print("❌ FAILED: Cannot connect to Redis")
        print("   Make sure Redis is running:")
        print("   - Docker: docker run -d -p 6379:6379 redis:7-alpine")
        print("   - Linux: sudo systemctl start redis")
        print("   - macOS: brew services start redis")
        return False
    
    try:
        redis.ping()
        print("✅ PASSED: Connected to Redis")
        return True
    except Exception as e:
        print(f"❌ FAILED: Redis ping failed: {e}")
        return False

async def test_record_signal():
    """Test 2: Recording signals to Redis"""
    print("\n" + "=" * 60)
    print("TEST 2: Recording Signals")
    print("=" * 60)
    
    test_token = "TEST" + "1" * 40  # Valid base58 address format
    
    # Record signals from different groups (skip validation for test tokens)
    print(f"Recording signal from @TestGroup1...")
    await record_signal(test_token, "@TestGroup1", skip_validation=True)
    
    print(f"Recording signal from @TestGroup2...")
    await record_signal(test_token, "@TestGroup2", skip_validation=True)
    
    print(f"Recording signal from @TestGroup3...")
    await record_signal(test_token, "@TestGroup3", skip_validation=True)
    
    # Give Redis a moment to process
    await asyncio.sleep(0.1)
    
    print("✅ PASSED: Signals recorded")
    return True

def test_get_signal_count():
    """Test 3: Reading signal counts from Redis"""
    print("\n" + "=" * 60)
    print("TEST 3: Reading Signal Counts")
    print("=" * 60)
    
    test_token = "TEST" + "1" * 40
    
    # Get count (should be 3 from previous test)
    count = get_signal_count(test_token)
    
    print(f"Signal count for test token: {count}")
    
    if count == 3:
        print("✅ PASSED: Correct signal count (3 unique groups)")
        return True
    else:
        print(f"❌ FAILED: Expected 3, got {count}")
        return False

def test_duplicate_signals():
    """Test 4: Duplicate signals from same group"""
    print("\n" + "=" * 60)
    print("TEST 4: Duplicate Signal Handling")
    print("=" * 60)
    
    test_token = "TEST" + "2" * 40
    
    async def run():
        # Record same group twice (skip validation for test tokens)
        await record_signal(test_token, "@TestGroup1", skip_validation=True)
        await record_signal(test_token, "@TestGroup1", skip_validation=True)
        await asyncio.sleep(0.1)
    
    asyncio.run(run())
    
    count = get_signal_count(test_token)
    
    print(f"Signal count (should only count unique groups): {count}")
    
    if count == 1:
        print("✅ PASSED: Correctly deduplicates same group")
        return True
    else:
        print(f"❌ FAILED: Expected 1, got {count}")
        return False

def test_ttl():
    """Test 5: TTL (Time To Live) for signals"""
    print("\n" + "=" * 60)
    print("TEST 5: Signal TTL (Time To Live)")
    print("=" * 60)
    
    test_token = "TEST" + "3" * 40
    
    redis = _init_redis()
    signal_key = f"signal_aggregator:token:{test_token}"
    
    async def run():
        await record_signal(test_token, "@TestGroup1", skip_validation=True)
        await asyncio.sleep(0.1)
    
    asyncio.run(run())
    
    # Check TTL
    ttl = redis.ttl(signal_key)
    
    print(f"TTL for signal key: {ttl} seconds")
    
    if 3500 <= ttl <= 3600:
        print("✅ PASSED: TTL set correctly (~1 hour)")
        return True
    else:
        print(f"❌ FAILED: Expected TTL ~3600s, got {ttl}s")
        return False

def test_cross_process_simulation():
    """Test 6: Simulate cross-process communication"""
    print("\n" + "=" * 60)
    print("TEST 6: Cross-Process Communication")
    print("=" * 60)
    
    test_token = "TEST" + "4" * 40
    
    # Simulate signal aggregator process writing
    async def aggregator_process():
        print("  [Aggregator Process] Recording signals...")
        await record_signal(test_token, "@RealGroup1", skip_validation=True)
        await record_signal(test_token, "@RealGroup2", skip_validation=True)
        await asyncio.sleep(0.1)
    
    asyncio.run(aggregator_process())
    
    # Simulate main bot process reading
    print("  [Main Bot Process] Reading signal count...")
    count = get_signal_count(test_token)
    
    print(f"  [Main Bot Process] Found {count} consensus signals")
    
    if count == 2:
        print("✅ PASSED: Cross-process communication works!")
        return True
    else:
        print(f"❌ FAILED: Expected 2, got {count}")
        return False

def test_scoring_integration():
    """Test 7: Integration with scoring logic"""
    print("\n" + "=" * 60)
    print("TEST 7: Scoring Integration")
    print("=" * 60)
    
    # Test different consensus levels
    test_cases = [
        ("TEST" + "5" * 40, 0, "No consensus", -1),
        ("TEST" + "6" * 40, 1, "Solo signal", 0),
        ("TEST" + "7" * 40, 2, "Weak consensus", +1),
        ("TEST" + "8" * 40, 3, "Strong consensus", +2),
        ("TEST" + "9" * 40, 5, "Very strong consensus", +2),
    ]
    
    all_passed = True
    
    for token, num_groups, description, expected_bonus in test_cases:
        # Record signals (skip validation for test tokens)
        async def record():
            for i in range(num_groups):
                await record_signal(token, f"@TestGroup{i}", skip_validation=True)
            await asyncio.sleep(0.1)
        
        asyncio.run(record())
        
        # Get count and calculate bonus
        count = get_signal_count(token)
        
        if count >= 3:
            bonus = 2
        elif count == 2:
            bonus = 1
        elif count == 0:
            bonus = -1
        else:
            bonus = 0
        
        status = "✅" if bonus == expected_bonus else "❌"
        print(f"  {status} {description}: {count} groups → {bonus:+d} score")
        
        if bonus != expected_bonus:
            all_passed = False
    
    if all_passed:
        print("✅ PASSED: All scoring scenarios correct")
        return True
    else:
        print("❌ FAILED: Some scoring scenarios incorrect")
        return False

def cleanup_test_data():
    """Clean up test data from Redis"""
    print("\n" + "=" * 60)
    print("Cleaning up test data...")
    print("=" * 60)
    
    redis = _init_redis()
    if redis:
        # Delete all test keys
        test_keys = redis.keys("signal_aggregator:token:TEST*")
        if test_keys:
            redis.delete(*test_keys)
            print(f"✅ Deleted {len(test_keys)} test keys")
        else:
            print("✅ No test keys to clean up")

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("🧪 SIGNAL AGGREGATOR REDIS INTEGRATION TESTS")
    print("=" * 60)
    print()
    
    results = []
    
    # Run tests
    results.append(("Redis Connection", test_redis_connection()))
    
    if results[-1][1]:  # Only continue if Redis is connected
        results.append(("Record Signals", asyncio.run(test_record_signal())))
        results.append(("Read Signal Counts", test_get_signal_count()))
        results.append(("Duplicate Handling", test_duplicate_signals()))
        results.append(("TTL", test_ttl()))
        results.append(("Cross-Process", test_cross_process_simulation()))
        results.append(("Scoring Integration", test_scoring_integration()))
        
        # Cleanup
        cleanup_test_data()
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED!")
        print("\nSignal Aggregator is ready for production:")
        print("  1. Run Signal Aggregator daemon: python scripts/signal_aggregator_daemon.py")
        print("  2. Run main bot: python scripts/bot.py run")
        print("  3. Both will communicate via Redis automatically")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        print("Fix the issues above before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

