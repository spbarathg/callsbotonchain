#!/usr/bin/env python3
"""
Jupiter API Connection Diagnostic Test
Tests DNS resolution, API connectivity, and quote/swap functionality
"""
import sys
import socket
import requests
from datetime import datetime

def test_dns_resolution():
    """Test DNS resolution for Jupiter API"""
    print("="*60)
    print("1. DNS RESOLUTION TEST")
    print("="*60)
    
    domains = [
        "quote-api.jup.ag",
        "api.jup.ag",
        "jup.ag"
    ]
    
    results = {}
    for domain in domains:
        try:
            ip = socket.gethostbyname(domain)
            results[domain] = {"status": "✅", "ip": ip}
            print(f"✅ {domain} → {ip}")
        except socket.gaierror as e:
            results[domain] = {"status": "❌", "error": str(e)}
            print(f"❌ {domain} → FAILED: {e}")
    
    return all(r["status"] == "✅" for r in results.values())

def test_api_health():
    """Test Jupiter API health endpoint"""
    print("\n" + "="*60)
    print("2. API HEALTH CHECK")
    print("="*60)
    
    endpoints = [
        "https://quote-api.jup.ag/v6/quote",
        "https://api.jup.ag/"
    ]
    
    for endpoint in endpoints:
        try:
            # Test with a simple SOL/USDC quote
            if "v6/quote" in endpoint:
                r = requests.get(
                    endpoint,
                    params={
                        "inputMint": "So11111111111111111111111111111111111111112",
                        "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        "amount": "1000000000",
                        "slippageBps": "50"
                    },
                    timeout=10
                )
            else:
                r = requests.get(endpoint, timeout=10)
            
            if r.status_code == 200:
                print(f"✅ {endpoint} → HTTP {r.status_code}")
                if "v6/quote" in endpoint:
                    data = r.json()
                    if data.get("outAmount"):
                        print(f"   Quote received: {data.get('outAmount')} lamports")
                return True
            else:
                print(f"⚠️  {endpoint} → HTTP {r.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ {endpoint} → FAILED: {e}")
            return False
    
    return False

def test_memecoin_quote():
    """Test quote for a memecoin (not just SOL/USDC)"""
    print("\n" + "="*60)
    print("3. MEMECOIN QUOTE TEST")
    print("="*60)
    
    # Use a known memecoin address (BONK)
    memecoin = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    
    try:
        r = requests.get(
            "https://quote-api.jup.ag/v6/quote",
            params={
                "inputMint": "So11111111111111111111111111111111111111112",  # SOL
                "outputMint": memecoin,  # BONK
                "amount": "1000000000",  # 1 SOL
                "slippageBps": "2000"  # 20%
            },
            timeout=10
        )
        
        if r.status_code == 200:
            data = r.json()
            print(f"✅ Memecoin quote successful")
            print(f"   Input: 1 SOL")
            print(f"   Output: {data.get('outAmount')} tokens")
            print(f"   Route: {len(data.get('routePlan', []))} steps")
            return True
        else:
            print(f"❌ Failed: HTTP {r.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_circuit_breaker_state():
    """Check if circuit breaker is blocking"""
    print("\n" + "="*60)
    print("4. CIRCUIT BREAKER STATE")
    print("="*60)
    
    try:
        from app.http_client import get_circuit_breaker_status
        status = get_circuit_breaker_status()
        
        if not status:
            print("✅ No circuit breakers active")
            return True
        
        for domain, info in status.items():
            state = info.get("state", "UNKNOWN")
            failures = info.get("failure_count", 0)
            
            if state == "OPEN":
                print(f"❌ {domain}: {state} (failures: {failures})")
                return False
            else:
                print(f"✅ {domain}: {state} (failures: {failures})")
        
        return True
        
    except ImportError:
        print("⚠️  Cannot import circuit breaker module")
        return True

def main():
    """Run all diagnostics"""
    print("\n" + "="*60)
    print("JUPITER API CONNECTION DIAGNOSTIC")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*60 + "\n")
    
    results = {
        "dns": test_dns_resolution(),
        "api_health": test_api_health(),
        "memecoin": test_memecoin_quote(),
        "circuit_breaker": test_circuit_breaker_state()
    }
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_pass = all(results.values())
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test.replace('_', ' ').title()}")
    
    print("\n" + "="*60)
    if all_pass:
        print("✅ ALL TESTS PASSED - Jupiter API is ready")
        print("="*60)
        return 0
    else:
        print("❌ SOME TESTS FAILED - Trading may not work")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())

