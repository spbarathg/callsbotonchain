#!/usr/bin/env python3
"""
Trading System Readiness Verification Script

Checks all critical components before enabling live trading:
- Configuration validation
- Database connectivity
- Redis connection
- Wallet validation
- RPC connectivity
- Signal flow test
"""

import os
import sys
import json
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Colors:
    """Terminal colors"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}\n")


def print_check(name: str, status: bool, details: str = ""):
    """Print check result"""
    icon = f"{Colors.GREEN}✅" if status else f"{Colors.RED}❌"
    status_text = "PASS" if status else "FAIL"
    print(f"{icon} {Colors.BOLD}{name}:{Colors.END} {status_text}")
    if details:
        print(f"   {Colors.YELLOW}→ {details}{Colors.END}")


def print_warning(text: str):
    """Print warning"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_info(text: str):
    """Print info"""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")


def check_environment_variables() -> Tuple[bool, List[str]]:
    """Check critical environment variables"""
    print_header("Environment Variables")
    
    issues = []
    all_ok = True
    
    # Critical variables
    critical = {
        'TS_WALLET_SECRET': 'Wallet private key (required for live trading)',
        'TS_RPC_URL': 'Solana RPC endpoint',
        'REDIS_URL': 'Redis connection for signal flow',
        'CIELO_API_KEY': 'Cielo API key for signal generation',
    }
    
    for var, description in critical.items():
        value = os.getenv(var, '')
        is_set = bool(value and len(value) > 8)
        print_check(var, is_set, description)
        if not is_set:
            issues.append(f"Missing or invalid: {var}")
            all_ok = False
    
    # Important but optional
    print("\nOptional (recommended):")
    optional = {
        'TELEGRAM_BOT_TOKEN': 'Telegram notifications',
        'TELEGRAM_CHAT_ID': 'Telegram chat ID',
    }
    
    for var, description in optional.items():
        value = os.getenv(var, '')
        is_set = bool(value and len(value) > 5)
        print_check(var, is_set, description)
        if not is_set:
            print_warning(f"Optional: {var} not set - {description} disabled")
    
    return all_ok, issues


def check_redis_connection() -> Tuple[bool, str]:
    """Check Redis connectivity"""
    print_header("Redis Connection")
    
    redis_url = os.getenv('REDIS_URL', '')
    if not redis_url:
        return False, "REDIS_URL not set"
    
    try:
        import redis
        client = redis.from_url(redis_url, decode_responses=True)
        client.ping()
        
        # Check signal list
        signal_count = client.llen('trading_signals')
        print_check("Redis Connection", True, f"Connected to {redis_url}")
        print_info(f"Signal queue length: {signal_count}")
        
        return True, ""
    except ImportError:
        return False, "redis-py not installed (pip install redis)"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def check_wallet_configuration() -> Tuple[bool, str]:
    """Check wallet configuration"""
    print_header("Wallet Configuration")
    
    wallet_secret = os.getenv('TS_WALLET_SECRET', '')
    if not wallet_secret or len(wallet_secret) < 32:
        return False, "TS_WALLET_SECRET not set or too short"
    
    try:
        # Try to parse wallet
        from tradingSystem.broker_optimized import Broker
        broker = Broker()
        
        if broker._dry:
            print_warning("Dry run mode enabled - wallet not loaded")
            print_info("Set TS_DRY_RUN=false to enable live trading")
            return True, "Dry run mode (safe)"
        
        if broker._pubkey:
            print_check("Wallet Loaded", True, f"Public key: {broker._pubkey[:8]}...{broker._pubkey[-8:]}")
            return True, ""
        else:
            return False, "Wallet loaded but no public key"
            
    except Exception as e:
        return False, f"Failed to load wallet: {str(e)}"


def check_rpc_connection() -> Tuple[bool, str]:
    """Check RPC connectivity"""
    print_header("RPC Connection")
    
    rpc_url = os.getenv('TS_RPC_URL', 'https://api.mainnet-beta.solana.com')
    print_info(f"Using RPC: {rpc_url}")
    
    try:
        from solana.rpc.api import Client
        client = Client(rpc_url)
        
        # Try to get epoch info
        response = client.get_epoch_info()
        if response.value:
            epoch = response.value.epoch
            slot = response.value.absolute_slot
            print_check("RPC Connection", True, f"Epoch {epoch}, Slot {slot}")
            
            # Check if premium RPC
            if 'mainnet-beta.solana.com' in rpc_url:
                print_warning("Using public RPC - consider premium RPC (Helius, Quicknode) for production")
            
            return True, ""
        else:
            return False, "No response from RPC"
            
    except Exception as e:
        return False, f"RPC connection failed: {str(e)}"


def check_database_initialization() -> Tuple[bool, str]:
    """Check database setup"""
    print_header("Database Initialization")
    
    try:
        from tradingSystem.db import init, _conn
        
        # Initialize database
        init()
        print_check("Trading Database", True, "Initialized successfully")
        
        # Check if we can connect
        conn = _conn()
        cursor = conn.cursor()
        
        # Check positions table
        cursor.execute("SELECT COUNT(*) FROM positions")
        position_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM positions WHERE status='open'")
        open_count = cursor.fetchone()[0]
        
        conn.close()
        
        print_info(f"Total positions: {position_count}, Open: {open_count}")
        
        if open_count > 0:
            print_warning(f"Found {open_count} open positions - will recover on startup")
        
        return True, ""
        
    except Exception as e:
        return False, f"Database initialization failed: {str(e)}"


def check_signal_bot_database() -> Tuple[bool, str]:
    """Check signal bot database"""
    print_header("Signal Bot Database")
    
    try:
        from app.storage import init_db
        
        init_db()
        print_check("Alert Database", True, "Initialized successfully")
        
        return True, ""
        
    except Exception as e:
        return False, f"Database initialization failed: {str(e)}"


def check_circuit_breaker() -> Tuple[bool, str]:
    """Check circuit breaker configuration"""
    print_header("Circuit Breaker Configuration")
    
    try:
        from tradingSystem.config_optimized import (
            MAX_DAILY_LOSS_PCT,
            MAX_CONSECUTIVE_LOSSES,
            BANKROLL_USD,
        )
        
        max_loss_usd = BANKROLL_USD * (MAX_DAILY_LOSS_PCT / 100.0)
        
        print_check("Circuit Breaker", True, "Configured")
        print_info(f"Max daily loss: {MAX_DAILY_LOSS_PCT}% (${max_loss_usd:.2f})")
        print_info(f"Max consecutive losses: {MAX_CONSECUTIVE_LOSSES}")
        print_info(f"Bankroll: ${BANKROLL_USD:.2f}")
        
        return True, ""
        
    except Exception as e:
        return False, f"Configuration error: {str(e)}"


def check_toggles() -> Tuple[bool, str]:
    """Check runtime toggles"""
    print_header("Runtime Toggles")
    
    try:
        from app.toggles import signals_enabled, trading_enabled
        
        signals_on = signals_enabled()
        trading_on = trading_enabled()
        
        print_check("Signals Enabled", signals_on, "Bot will generate signals")
        print_check("Trading Enabled", trading_on, "Trading system will execute trades")
        
        if not signals_on:
            print_warning("Signals are disabled - bot will not generate alerts")
        
        if not trading_on:
            print_warning("Trading is disabled - use API or toggles.json to enable")
            print_info("Enable via: curl -X POST http://localhost:8080/api/admin/toggle -d '{\"trading_enabled\": true}'")
        
        return True, ""
        
    except Exception as e:
        return False, f"Toggle check failed: {str(e)}"


def check_configuration_alignment() -> Tuple[bool, str]:
    """Check that bot and trading system configs are aligned"""
    print_header("Configuration Alignment")
    
    try:
        from app.config_unified import MIN_LIQUIDITY_USD as BOT_MIN_LIQ
        from tradingSystem.config_optimized import MIN_LIQUIDITY_USD as TS_MIN_LIQ
        
        aligned = BOT_MIN_LIQ == TS_MIN_LIQ
        print_check("Liquidity Filters", aligned, 
                   f"Bot: ${BOT_MIN_LIQ:,.0f}, Trading: ${TS_MIN_LIQ:,.0f}")
        
        if not aligned:
            print_warning("Bot and trading system have different liquidity filters")
            print_info("This may cause trading system to reject valid signals")
        
        return True, ""  # Non-critical
        
    except Exception as e:
        return False, f"Configuration check failed: {str(e)}"


def test_signal_flow() -> Tuple[bool, str]:
    """Test signal flow from Redis"""
    print_header("Signal Flow Test")
    
    try:
        import redis
        import json
        import time
        
        redis_url = os.getenv('REDIS_URL', '')
        if not redis_url:
            return False, "REDIS_URL not set"
        
        client = redis.from_url(redis_url, decode_responses=True)
        
        # Create test signal
        test_signal = {
            'token': 'TEST_TOKEN_' + str(int(time.time())),
            'score': 8,
            'conviction_type': 'High Confidence (Smart Money)',
            'price': 0.001,
            'market_cap': 75000,
            'liquidity': 40000,
            'timestamp': time.time()
        }
        
        # Push to Redis
        client.lpush('trading_signals', json.dumps(test_signal))
        print_check("Push Test Signal", True, f"Token: {test_signal['token']}")
        
        # Verify it's there
        signal_count = client.llen('trading_signals')
        print_info(f"Signal queue now has {signal_count} items")
        
        # Pop it back off (cleanup)
        client.rpop('trading_signals')
        
        print_check("Signal Flow", True, "Redis communication working")
        
        return True, ""
        
    except Exception as e:
        return False, f"Signal flow test failed: {str(e)}"


def print_summary(results: Dict[str, Tuple[bool, str]]):
    """Print summary of all checks"""
    print_header("Summary")
    
    passed = sum(1 for status, _ in results.values() if status)
    total = len(results)
    
    print(f"\nChecks Passed: {passed}/{total}\n")
    
    # Group by status
    failures = []
    warnings = []
    
    for name, (status, message) in results.items():
        if not status:
            failures.append((name, message))
        elif message and "warning" in message.lower():
            warnings.append((name, message))
    
    if failures:
        print(f"{Colors.RED}{Colors.BOLD}❌ FAILURES:{Colors.END}")
        for name, message in failures:
            print(f"  • {name}: {message}")
    
    if warnings:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  WARNINGS:{Colors.END}")
        for name, message in warnings:
            print(f"  • {name}: {message}")
    
    if not failures:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ All critical checks passed!{Colors.END}")
        
        dry_run = os.getenv('TS_DRY_RUN', 'true').lower() == 'true'
        if dry_run:
            print(f"\n{Colors.YELLOW}System ready for DRY RUN testing{Colors.END}")
            print(f"To enable live trading:")
            print(f"  1. Set TS_DRY_RUN=false in environment")
            print(f"  2. Enable trading toggle via API or toggles.json")
            print(f"  3. Verify wallet has SOL for transactions")
        else:
            trading_enabled = os.getenv('TRADING_ENABLED', 'false').lower() == 'true'
            if trading_enabled:
                print(f"\n{Colors.RED}{Colors.BOLD}⚠️  LIVE TRADING IS ENABLED!{Colors.END}")
                print(f"{Colors.RED}System will execute real transactions with real money!{Colors.END}")
            else:
                print(f"\n{Colors.YELLOW}Ready for live trading (toggle currently disabled){Colors.END}")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ Fix failures before proceeding{Colors.END}")
        return False
    
    return not failures


def main():
    """Run all verification checks"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("=" * 80)
    print("TRADING SYSTEM READINESS VERIFICATION".center(80))
    print("=" * 80)
    print(f"{Colors.END}\n")
    
    results = {}
    
    # Run all checks
    checks = [
        ("Environment Variables", check_environment_variables),
        ("Redis Connection", check_redis_connection),
        ("Wallet Configuration", check_wallet_configuration),
        ("RPC Connection", check_rpc_connection),
        ("Trading Database", check_database_initialization),
        ("Signal Bot Database", check_signal_bot_database),
        ("Circuit Breaker", check_circuit_breaker),
        ("Runtime Toggles", check_toggles),
        ("Config Alignment", check_configuration_alignment),
        ("Signal Flow", test_signal_flow),
    ]
    
    for name, check_func in checks:
        try:
            status, message = check_func()
            results[name] = (status, message)
        except Exception as e:
            results[name] = (False, f"Check failed: {str(e)}")
    
    # Print summary
    success = print_summary(results)
    
    # Exit code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()







