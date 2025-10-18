#!/usr/bin/env python3
"""
Setup Telethon Session for User Bot
This script creates and authorizes a Telethon session file for sending Telegram messages.
"""
import os
import sys
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


async def setup_session():
    """Setup Telethon session interactively."""
    
    # Load config from environment or use defaults
    api_id = os.getenv('TELEGRAM_USER_API_ID', '21297486')
    api_hash = os.getenv('TELEGRAM_USER_API_HASH', 'cef5c0cdae62a9d8e3208177a9c29ee3')
    session_file = os.getenv('TELEGRAM_USER_SESSION_FILE', 'var/memecoin_session')
    
    # Ensure var directory exists
    os.makedirs('var', exist_ok=True)
    
    print("=" * 60)
    print("🔧 Telethon Session Setup")
    print("=" * 60)
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:10]}...")
    print(f"Session File: {session_file}.session")
    print("=" * 60)
    print()
    
    # Get phone number
    phone = input("Enter your phone number (with country code, e.g., +919876543210): ").strip()
    
    if not phone.startswith('+'):
        print("❌ Phone number must start with + and country code")
        return False
    
    print(f"\n📱 Connecting to Telegram with phone: {phone}")
    
    # Create client
    client = TelegramClient(session_file, api_id, api_hash)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            print("📲 Sending verification code to your Telegram...")
            await client.send_code_request(phone)
            
            # Get verification code
            code = input("\nEnter the verification code you received: ").strip()
            
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                # 2FA is enabled
                password = input("\n🔐 2FA is enabled. Enter your password: ").strip()
                await client.sign_in(password=password)
        
        # Verify we're authorized
        if await client.is_user_authorized():
            me = await client.get_me()
            print("\n✅ Successfully authorized!")
            print(f"   Name: {me.first_name} {me.last_name or ''}")
            print(f"   Username: @{me.username or 'N/A'}")
            print(f"   Phone: {me.phone}")
            print(f"\n✅ Session saved to: {session_file}.session")
            
            # Test group access
            group_id = os.getenv('TELEGRAM_GROUP_CHAT_ID', '-1003153567866')
            try:
                entity = await client.get_entity(int(group_id))
                print(f"\n✅ Can access group: {entity.title}")
                print(f"   Group ID: {group_id}")
            except Exception as e:
                print(f"\n⚠️  Warning: Cannot access group {group_id}")
                print(f"   Error: {e}")
                print("   Make sure your account is a member of this group!")
            
            await client.disconnect()
            return True
        else:
            print("❌ Authorization failed")
            await client.disconnect()
            return False
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        await client.disconnect()
        return False


def main():
    """Main entry point."""
    try:
        success = asyncio.run(setup_session())
        
        if success:
            print("\n" + "=" * 60)
            print("✅ Setup Complete!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Upload session to server:")
            print("   scp var/memecoin_session.session root@64.227.157.221:/opt/callsbotonchain/var/")
            print("\n2. Restart worker on server:")
            print("   ssh root@64.227.157.221 \"cd /opt/callsbotonchain/deployment && docker compose restart worker\"")
            print("\n3. Verify in logs:")
            print("   ssh root@64.227.157.221 \"docker logs callsbot-worker --tail 20 | grep -i telethon\"")
            print("=" * 60)
            sys.exit(0)
        else:
            print("\n❌ Setup failed. Please try again.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


