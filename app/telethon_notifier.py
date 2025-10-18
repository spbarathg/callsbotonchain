"""
Telethon-based Telegram Group Notifier
Sends trading signals to a Telegram group using user account (not bot).
"""
import asyncio
import os
from typing import TYPE_CHECKING
from app.config_unified import (
    TELEGRAM_USER_API_ID as API_ID,
    TELEGRAM_USER_API_HASH as API_HASH,
    TELEGRAM_USER_SESSION_FILE as SESSION_FILE,
    TELEGRAM_GROUP_CHAT_ID as TARGET_CHAT_ID,
    TELETHON_ENABLED,
)

# Lazy imports for Telethon (expensive imports, only load when needed)
if TYPE_CHECKING:
    pass

# Global client instance (initialized on first use)
_client = None  # Telethon client instance (lazy)
_client_lock = asyncio.Lock()
IS_TESTING = "PYTEST_CURRENT_TEST" in os.environ


async def _get_client():  # -> Optional[TelegramClient] but can't annotate due to lazy import
    """Get or create the Telethon client (singleton pattern)."""
    global _client
    
    if not TELETHON_ENABLED:
        return None
    
    # Lazy import Telethon only when actually needed
    from telethon import TelegramClient
    
    async with _client_lock:
        if _client is None:
            try:
                _client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
                await _client.connect()
                
                if not await _client.is_user_authorized():
                    print("❌ Telethon: Session not authorized. Run setup_telethon_session.py first.")
                    _client = None
                    return None
                
                # Verify access to target group
                try:
                    entity = await _client.get_entity(TARGET_CHAT_ID)
                    print(f"✅ Telethon connected to: {entity.title}")
                except Exception as e:
                    print(f"❌ Telethon: Cannot access group {TARGET_CHAT_ID}: {e}")
                    await _client.disconnect()
                    _client = None
                    return None
                    
            except Exception as e:
                print(f"❌ Telethon client initialization failed: {e}")
                _client = None
                return None
        
        return _client


async def send_group_message_async(message: str) -> bool:
    """
    Send a message to the configured Telegram group.
    
    Args:
        message: The message text to send (supports HTML formatting)
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not TELETHON_ENABLED:
        if not IS_TESTING:
            print("⚠️  Telethon not enabled (missing credentials)")
        return False
    
    if not message or not message.strip():
        print("❌ Telethon: Empty message provided")
        return False
    
    # Lazy import Telethon errors only when actually needed
    from telethon.errors import FloodWaitError, ChatWriteForbiddenError
    
    try:
        client = await _get_client()
        if client is None:
            return False
        
        # Send message with HTML parsing
        await client.send_message(
            TARGET_CHAT_ID,
            message,
            parse_mode='html',
            link_preview=False  # Disable link previews for cleaner messages
        )
        
        print(f"✅ Telethon: Message sent to group {TARGET_CHAT_ID}")
        return True
        
    except FloodWaitError as e:
        print(f"⚠️  Telethon: Rate limited, need to wait {e.seconds} seconds")
        return False
    except ChatWriteForbiddenError:
        print(f"❌ Telethon: No permission to send messages to {TARGET_CHAT_ID}")
        return False
    except Exception as e:
        print(f"❌ Telethon: Failed to send message: {e}")
        return False


def send_group_message(message: str) -> bool:
    """
    Synchronous wrapper for send_group_message_async.
    
    Args:
        message: The message text to send
    
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Try to get existing event loop, otherwise create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is already running, we need to use nest_asyncio or run_until_complete won't work
                # Instead, create a new event loop in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, send_group_message_async(message))
                    return future.result(timeout=30)
            else:
                # Loop exists but not running, safe to use run_until_complete
                return loop.run_until_complete(send_group_message_async(message))
        except RuntimeError:
            # No event loop exists, create one with asyncio.run
            return asyncio.run(send_group_message_async(message))
    except Exception as e:
        print(f"❌ Telethon sync wrapper error: {e}")
        return False


# Module initialization check (skip during tests to avoid noise)
if not IS_TESTING:
    if TELETHON_ENABLED:
        print(f"📱 Telethon notifier enabled for group {TARGET_CHAT_ID}")
    else:
        print("⚠️  Telethon notifier disabled (check environment variables)")

