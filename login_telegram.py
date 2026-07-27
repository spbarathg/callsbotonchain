import os
import sys
import asyncio
from dotenv import load_dotenv

# Ensure we're in the right directory and load the environment variables
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(".env")

try:
    from telethon import TelegramClient
except ImportError:
    print("Telethon is not installed! Run: pip install telethon")
    sys.exit(1)

# Grab the credentials from your .env
API_ID = os.getenv("ATM_TELETHON_API_ID") or os.getenv("TELEGRAM_USER_API_ID")
API_HASH = os.getenv("ATM_TELETHON_API_HASH") or os.getenv("TELEGRAM_USER_API_HASH")

if not API_ID or not API_HASH:
    print("❌ ERROR: TELEGRAM_USER_API_ID or TELEGRAM_USER_API_HASH is missing from your .env file!")
    sys.exit(1)

# Ensure the var folder exists
os.makedirs("var", exist_ok=True)
SESSION_FILE = "var/atm_ingest.session"

async def main():
    print(f"🚀 Initializing Telegram login sequence...")
    print(f"📦 Session file will be saved to: {SESSION_FILE}")
    
    # Initialize the client (IPv6 disabled to match your setup)
    client = TelegramClient(SESSION_FILE, int(API_ID), API_HASH, use_ipv6=False)
    
    # This will prompt you for your phone number and the login code
    await client.start()
    
    print("\n✅ SUCCESS! You are successfully logged into Telegram!")
    print(f"✅ The session file '{SESSION_FILE}' has been generated.")
    print("👉 You can now restart your docker containers.")

if __name__ == "__main__":
    asyncio.run(main())
