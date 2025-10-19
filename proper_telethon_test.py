#!/usr/bin/env python3
"""
Proper Telethon Test - Uses existing client infrastructure
"""
import sys
import asyncio
sys.path.insert(0, '/app')

print("=" * 80)
print("🧪 PROPER TELETHON TEST")
print("=" * 80)

# Import the async function
from app.telethon_notifier import send_group_message_async

async def main():
    print("\nSending test message via Telethon...")
    
    message = """🧪 **PROPER TELETHON TEST**

This test uses the bot's existing Telethon client.

**Time:** Now
**Status:** ✅ Testing

If you see this, Telethon is working! 🚀"""
    
    result = await send_group_message_async(message)
    
    print(f"\n{'=' * 80}")
    if result:
        print("✅ MESSAGE SENT SUCCESSFULLY!")
        print("Result: True")
    else:
        print("❌ MESSAGE FAILED!")
        print("Result: False")
    print("=" * 80)
    
    return result

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

