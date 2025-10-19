#!/usr/bin/env python3
"""
Deep Core Diagnostic - Comprehensive Telethon Investigation
"""
import os
import sys
sys.path.insert(0, '/app')

print("=" * 80)
print("🔍 DEEP CORE DIAGNOSTIC - TELETHON INVESTIGATION")
print("=" * 80)

# 1. Check environment variables
print("\n" + "=" * 80)
print("1. ENVIRONMENT VARIABLES")
print("=" * 80)

env_vars = {
    'TELETHON_ENABLED': os.getenv('TELETHON_ENABLED'),
    'TELEGRAM_ENABLED': os.getenv('TELEGRAM_ENABLED'),
    'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
    'TELEGRAM_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID'),
    'TELEGRAM_GROUP_CHAT_ID': os.getenv('TELEGRAM_GROUP_CHAT_ID'),
    'TELEGRAM_USER_API_ID': os.getenv('TELEGRAM_USER_API_ID'),
    'TELEGRAM_USER_API_HASH': os.getenv('TELEGRAM_USER_API_HASH'),
    'TELEGRAM_USER_SESSION_FILE': os.getenv('TELEGRAM_USER_SESSION_FILE'),
    'SIGNAL_AGGREGATOR_SESSION_FILE': os.getenv('SIGNAL_AGGREGATOR_SESSION_FILE'),
}

for key, value in env_vars.items():
    if value:
        if 'HASH' in key or 'TOKEN' in key:
            display = f"{value[:8]}..." if len(value) > 8 else "***"
        else:
            display = value
        print(f"✅ {key}: {display}")
    else:
        print(f"❌ {key}: NOT SET")

# 2. Check config_unified values
print("\n" + "=" * 80)
print("2. CONFIG_UNIFIED VALUES")
print("=" * 80)

try:
    from app.config_unified import (
        TELETHON_ENABLED,
        TELEGRAM_ENABLED,
        TELEGRAM_GROUP_CHAT_ID,
        TELEGRAM_USER_API_ID,
        TELEGRAM_USER_API_HASH,
        TELEGRAM_USER_SESSION_FILE,
    )
    
    print(f"TELETHON_ENABLED: {TELETHON_ENABLED}")
    print(f"TELEGRAM_ENABLED: {TELEGRAM_ENABLED}")
    print(f"TELEGRAM_GROUP_CHAT_ID: {TELEGRAM_GROUP_CHAT_ID}")
    print(f"TELEGRAM_USER_API_ID: {TELEGRAM_USER_API_ID}")
    print(f"TELEGRAM_USER_API_HASH: {TELEGRAM_USER_API_HASH[:8]}..." if TELEGRAM_USER_API_HASH else "None")
    print(f"TELEGRAM_USER_SESSION_FILE: {TELEGRAM_USER_SESSION_FILE}")
    
except Exception as e:
    print(f"❌ Error importing config: {e}")

# 3. Check session files
print("\n" + "=" * 80)
print("3. SESSION FILES")
print("=" * 80)

session_files = [
    'var/relay_user.session',
    'var/memecoin_session.session',
]

for session_file in session_files:
    full_path = f'/app/{session_file}'
    if os.path.exists(full_path):
        size = os.path.getsize(full_path)
        print(f"✅ {session_file}")
        print(f"   Path: {full_path}")
        print(f"   Size: {size:,} bytes")
        
        # Check for journal/lock files
        journal = f"{full_path}-journal"
        if os.path.exists(journal):
            print(f"   ⚠️  Journal file exists: {journal}")
        else:
            print(f"   ✅ No journal file")
            
        # Check if file is readable
        try:
            with open(full_path, 'rb') as f:
                header = f.read(16)
                print(f"   ✅ File is readable")
        except Exception as e:
            print(f"   ❌ Cannot read file: {e}")
    else:
        print(f"❌ {session_file} - NOT FOUND at {full_path}")

# 4. Test Telethon import and initialization
print("\n" + "=" * 80)
print("4. TELETHON IMPORT TEST")
print("=" * 80)

try:
    from telethon import TelegramClient
    print("✅ Telethon imported successfully")
    
    # Try to check if client can be created (without connecting)
    try:
        from app.config_unified import (
            TELEGRAM_USER_API_ID,
            TELEGRAM_USER_API_HASH,
            TELEGRAM_USER_SESSION_FILE,
        )
        
        if TELEGRAM_USER_API_ID and TELEGRAM_USER_API_HASH and TELEGRAM_USER_SESSION_FILE:
            print(f"✅ Telethon credentials available")
            print(f"   API ID: {TELEGRAM_USER_API_ID}")
            print(f"   Session: {TELEGRAM_USER_SESSION_FILE}")
        else:
            print("❌ Missing Telethon credentials")
            
    except Exception as e:
        print(f"❌ Error checking credentials: {e}")
        
except ImportError as e:
    print(f"❌ Telethon not installed: {e}")

# 5. Test actual Telethon connection
print("\n" + "=" * 80)
print("5. TELETHON CONNECTION TEST")
print("=" * 80)

try:
    import asyncio
    from app.telethon_notifier import send_group_message
    
    print("Testing send_group_message function...")
    print("Attempting to send test message...")
    
    # This will try to send but might fail
    result = send_group_message("🧪 DEEP DIAGNOSTIC TEST\n\nTesting Telethon connection.\n\nTimestamp: Now")
    
    print(f"Result: {result}")
    print(f"Type: {type(result)}")
    
    if result is True:
        print("✅ Function returned True")
    elif result is False:
        print("❌ Function returned False")
    else:
        print(f"⚠️  Function returned unexpected value: {result}")
        
except Exception as e:
    print(f"❌ Error testing Telethon: {e}")
    import traceback
    traceback.print_exc()

# 6. Check notify.py behavior
print("\n" + "=" * 80)
print("6. NOTIFY.PY BEHAVIOR")
print("=" * 80)

try:
    from app.notify import send_telegram_alert
    from app.config_unified import TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN
    
    print(f"TELEGRAM_ENABLED: {TELEGRAM_ENABLED}")
    print(f"TELEGRAM_BOT_TOKEN set: {bool(TELEGRAM_BOT_TOKEN)}")
    
    if not TELEGRAM_ENABLED:
        print("⚠️  TELEGRAM_ENABLED is False - send_telegram_alert will return True without sending!")
        
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️  TELEGRAM_BOT_TOKEN not set - Bot API won't work")
        
except Exception as e:
    print(f"❌ Error checking notify: {e}")

# 7. Check signal_processor integration
print("\n" + "=" * 80)
print("7. SIGNAL_PROCESSOR INTEGRATION")
print("=" * 80)

try:
    import inspect
    from app import signal_processor
    
    # Find _send_alert method
    source = inspect.getsource(signal_processor.SignalProcessor._send_alert)
    
    # Check if it calls send_group_message
    if 'send_group_message' in source:
        print("✅ signal_processor calls send_group_message")
        
        # Check if it awaits or handles async properly
        if 'await send_group_message' in source:
            print("✅ Properly awaits send_group_message")
        else:
            print("⚠️  Does NOT await send_group_message (might be sync wrapper)")
            
        # Check error handling
        if 'try:' in source and 'send_group_message' in source:
            print("✅ Has error handling for send_group_message")
        else:
            print("⚠️  No error handling - failures might be silent")
    else:
        print("❌ signal_processor does NOT call send_group_message")
        
except Exception as e:
    print(f"❌ Error checking signal_processor: {e}")

# 8. Check for running Telethon clients
print("\n" + "=" * 80)
print("8. PROCESS CHECK")
print("=" * 80)

try:
    import subprocess
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    
    telethon_processes = [line for line in result.stdout.split('\n') if 'telethon' in line.lower() or 'telegram' in line.lower()]
    
    if telethon_processes:
        print(f"Found {len(telethon_processes)} Telethon-related processes:")
        for proc in telethon_processes:
            print(f"  {proc}")
    else:
        print("No Telethon-related processes found")
        
except Exception as e:
    print(f"⚠️  Could not check processes: {e}")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)

