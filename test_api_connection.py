#!/usr/bin/env python3
import requests

print("Testing API connections...")

# Test localhost
print("\n1. Testing http://127.0.0.1/api/tracked")
try:
    resp = requests.get("http://127.0.0.1/api/tracked?limit=1", timeout=2)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Rows: {len(data.get('rows', []))}")
except Exception as e:
    print(f"   Error: {e}")

# Test web container
print("\n2. Testing http://callsbot-web/api/tracked")
try:
    resp = requests.get("http://callsbot-web/api/tracked?limit=1", timeout=2)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Rows: {len(data.get('rows', []))}")
except Exception as e:
    print(f"   Error: {e}")

# Test proxy
print("\n3. Testing http://callsbot-proxy/api/tracked")
try:
    resp = requests.get("http://callsbot-proxy/api/tracked?limit=1", timeout=2)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Rows: {len(data.get('rows', []))}")
except Exception as e:
    print(f"   Error: {e}")

