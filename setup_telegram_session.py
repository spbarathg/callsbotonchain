#!/usr/bin/env python3
"""
Interactive Telegram Session Setup Script
This script must be run interactively to authorize Telegram sessions.
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.abspath('.'))

async def setup_session():
    print('=' * 80)
    print('TELEGRAM SESSION SETUP')
    print('=' * 80)
    
    # Import credentials from .env
    try:
        from dotenv import load_dotenv
        load_dotenv('deployment/.env')
        load_dotenv('.env')
    except:
        pass
    
    API_ID = int(os.getenv('TELEGRAM_USER_API_ID', '0'))
    API_HASH = os.getenv('TELEGRAM_USER_API_HASH', '')
    
    if not API_ID or not API_HASH:
        print('❌ Error: TELEGRAM_USER_API_ID and TELEGRAM_USER_API_HASH must be set in deployment/.env')
        return
    
    print(f'API ID: {API_ID}')
    print(f'API Hash: {API_HASH[:8]}...')
    print('=' * 80)
    
    # Session file in the var directory
    SESSION_FILE = os.getenv('TELEGRAM_USER_SESSION_FILE', 'var/relay_user.session')
    
    from telethon import TelegramClient
    
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    
    print('\nConnecting to Telegram...')
    await client.connect()
    
    if not await client.is_user_authorized():
        print('\n⚠️  Not authorized. Starting authorization process...')
        print('\nYou will be prompted for:')
        print('  1. Your phone number (with country code, e.g., +1234567890)')
        print('  2. The code Telegram sends to your phone/app')
        print('  3. Your 2FA password (if enabled)')
        print('=' * 80)
        
        await client.start()
        
        print('\n✅ Authorization successful!')
        print(f'Session saved to: {SESSION_FILE}')
    else:
        print('\n✅ Already authorized!')
        me = await client.get_me()
        print(f'Logged in as: {me.first_name} (@{me.username})')
    
    await client.disconnect()
    print('\n✅ Setup complete! You can now start the containers.')
    print('=' * 80)

if __name__ == '__main__':
    asyncio.run(setup_session())







