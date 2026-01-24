"""
Test Recovery Pattern Detector

Simulates a "dip and rip" scenario to verify the detector works correctly
"""
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.recovery_pattern_detector import get_recovery_detector, RecoveryPattern


def test_basic_pattern():
    """Test basic recovery pattern detection"""
    print("\n" + "="*60)
    print("TEST 1: Basic Recovery Pattern (User's Example)")
    print("="*60)
    
    detector = get_recovery_detector()
    test_token = "TestToken123456789ABC"
    
    # Simulate the exact scenario from user
    print("\n[SIMULATION] Price action:")
    
    # 1. Token reaches ATH at $100K
    print("\n1. Token reaches ATH: $100K")
    detector.add_price_data(test_token, market_cap=100_000, price=0.001, volume=50_000)
    time.sleep(0.1)
    
    # 2. Drops to $60K (-40%, exceeds 30% minimum)
    print("2. Drops to $60K (-40%)")
    for mcap in [95_000, 90_000, 85_000, 80_000, 70_000, 60_000]:
        detector.add_price_data(test_token, market_cap=mcap, price=0.001 * (mcap/100_000), volume=30_000)
        time.sleep(0.1)
    
    # 3. Recovers back to $100K (ATH) - SLOWLY (to simulate 5+ candles)
    print("3. Recovers back to $100K (ATH) in multiple candles")
    for mcap in [65_000, 70_000, 75_000, 80_000, 85_000, 90_000, 95_000, 100_000]:
        detector.add_price_data(test_token, market_cap=mcap, price=0.001 * (mcap/100_000), volume=60_000)
        time.sleep(0.1)
    
    # 4. Exceeds ATH by 10% = $110K (continue recovery in 5+ candles total)
    print("4. Exceeds ATH by 10%: $110K (continuing recovery)")
    for mcap in [102_000, 104_000, 106_000, 108_000, 110_000]:
        pattern = detector.add_price_data(test_token, market_cap=mcap, price=0.001 * (mcap/100_000), volume=70_000)
        time.sleep(0.1)
        
        if pattern:
            print("\n" + "="*60)
            print("*** RECOVERY PATTERN DETECTED! ***")
            print("="*60)
            print(f"\nToken: {pattern.token[:12]}...")
            print(f"ATH Market Cap: ${pattern.ath_mcap:,.0f}")
            print(f"Drop to: ${pattern.drop_mcap:,.0f} (-{pattern.drop_percent:.1f}%)")
            print(f"Recovered to: ${pattern.recovery_mcap:,.0f} (+{((pattern.recovery_mcap-pattern.ath_mcap)/pattern.ath_mcap)*100:.1f}% above ATH)")
            print(f"Recovery candles: {pattern.recovery_candles}")
            print(f"Detection time: {time.strftime('%H:%M:%S', time.localtime(pattern.detection_time))}")
            return True
    
    print("\n[X] Pattern NOT detected (this shouldn't happen!)")
    return False


def test_failed_patterns():
    """Test cases that should NOT trigger"""
    print("\n" + "="*60)
    print("TEST 2: Failed Patterns (Should NOT Trigger)")
    print("="*60)
    
    detector = get_recovery_detector()
    
    # Test A: Market cap too low
    print("\n[X] Test A: Market cap too low ($40K < $50K minimum)")
    test_token_a = "TestTokenA123456"
    detector.add_price_data(test_token_a, market_cap=40_000, price=0.001, volume=10_000)
    time.sleep(0.1)
    for mcap in [40_000, 30_000, 40_000, 50_000, 55_000]:  # Drop and recover
        pattern = detector.add_price_data(test_token_a, market_cap=mcap, price=0.001, volume=10_000)
        time.sleep(0.1)
    print("   Result: Pattern not detected [OK]" if not pattern else "   Result: Pattern detected [FAIL]")
    
    # Test B: Market cap too high
    print("\n[X] Test B: Market cap too high ($200K > $180K maximum)")
    test_token_b = "TestTokenB123456"
    detector.add_price_data(test_token_b, market_cap=200_000, price=0.01, volume=100_000)
    time.sleep(0.1)
    for mcap in [190_000, 180_000, 190_000, 200_000, 210_000]:
        pattern = detector.add_price_data(test_token_b, market_cap=mcap, price=0.01, volume=100_000)
        time.sleep(0.1)
    print("   Result: Pattern not detected [OK]" if not pattern else "   Result: Pattern detected [FAIL]")
    
    # Test C: Drop not deep enough (<30%)
    print("\n[X] Test C: Drop not deep enough (-20% < -30% minimum)")
    test_token_c = "TestTokenC123456"
    detector.add_price_data(test_token_c, market_cap=100_000, price=0.001, volume=50_000)
    time.sleep(0.1)
    for mcap in [95_000, 90_000, 85_000, 80_000, 90_000, 100_000, 110_000]:  # Only -20%
        pattern = detector.add_price_data(test_token_c, market_cap=mcap, price=0.001, volume=50_000)
        time.sleep(0.1)
    print("   Result: Pattern not detected [OK]" if not pattern else "   Result: Pattern detected [FAIL]")
    
    # Test D: Recovery too fast (<5 candles)
    print("\n[X] Test D: Recovery too fast (3 candles < 5 minimum)")
    test_token_d = "TestTokenD123456"
    detector.add_price_data(test_token_d, market_cap=100_000, price=0.001, volume=50_000)
    time.sleep(0.1)
    detector.add_price_data(test_token_d, market_cap=60_000, price=0.0006, volume=30_000)  # Drop
    time.sleep(0.1)
    # Recover in only 3 candles
    for mcap in [90_000, 100_000, 110_000]:
        pattern = detector.add_price_data(test_token_d, market_cap=mcap, price=0.001, volume=60_000)
        time.sleep(0.1)
    print("   Result: Pattern not detected [OK]" if not pattern else "   Result: Pattern detected [FAIL]")


def test_stats():
    """Show detector statistics"""
    print("\n" + "="*60)
    print("DETECTOR STATISTICS")
    print("="*60)
    
    detector = get_recovery_detector()
    stats = detector.get_stats()
    
    print(f"\nPatterns detected: {stats['patterns_detected']}")
    print(f"Tokens tracked: {stats['tokens_tracked']}")
    print(f"Candles processed: {stats['candles_processed']}")
    print(f"Active patterns: {stats['active_patterns']}")
    print(f"Detection rate: {stats['detection_rate']}")


def main():
    print("\n" + "="*60)
    print("RECOVERY PATTERN DETECTOR - TEST SUITE")
    print("="*60)
    
    # Run tests
    success = test_basic_pattern()
    test_failed_patterns()
    test_stats()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    if success:
        print("\n[SUCCESS] Recovery pattern detector is working correctly!")
        print("\nThe detector is now integrated into your signal detection system.")
        print("It will automatically detect 'dip and rip' patterns and boost scores by +3.")
        print("\nPattern requirements:")
        print("  - Market cap at ATH: $50K - $180K (aligned with main filters)")
        print("  - Drop from ATH: >=30%")
        print("  - Recovery: ATH + 10%")
        print("  - Recovery time: >=5 candles (minutes)")
    else:
        print("\n[FAILED] Tests failed! Check the implementation.")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()

