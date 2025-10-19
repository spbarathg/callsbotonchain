"""
Telethon-based Telegram Group Notifier
Sends trading signals to a Telegram group using user account (not bot).

PERMANENT FIX: Each thread gets its own event loop and Telethon client instance.
This prevents "event loop must not change" errors while still sharing the session file safely.
"""
import asyncio
import os
import threading
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

IS_TESTING = "PYTEST_CURRENT_TEST" in os.environ


async def _create_and_connect_client():
    """
    Create a NEW Telethon client for the current event loop.
    
    PERMANENT FIX: Each call creates a fresh client in the current event loop.
    This prevents "event loop must not change" errors. The session file is
    safely shared between clients (SQLite handles concurrent reads).
    """
    if not TELETHON_ENABLED:
        return None
    
    # Lazy import Telethon only when actually needed
    from telethon import TelegramClient
    
    try:
        # Create a NEW client for THIS event loop
        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            print("❌ Telethon: Session not authorized. Run setup_telethon_session.py first.")
            await client.disconnect()
            return None
        
        return client
            
    except Exception as e:
        print(f"❌ Telethon client initialization failed: {e}")
        return None


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
    
    client = None
    try:
        # Create a fresh client for THIS event loop
        client = await _create_and_connect_client()
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
    finally:
        # CRITICAL: Disconnect client after use to clean up event loop tasks
        if client is not None:
            try:
                await client.disconnect()
            except Exception as e:
                print(f"⚠️  Telethon: Error disconnecting client: {e}")


def send_group_message(message: str) -> bool:
    """
    Synchronous wrapper for send_group_message_async.
    
    PERMANENT FIX: Creates a fresh event loop for each call. Each client
    is created, used, and disconnected within the same event loop, preventing
    "event loop must not change" errors.
    
    Args:
        message: The message text to send
    
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Create a fresh event loop for this call
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(send_group_message_async(message))
            return result
        finally:
            # Clean up: close the loop and all pending tasks
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # Wait for all tasks to be cancelled
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass  # Ignore cleanup errors
            finally:
                loop.close()
            
    except Exception as e:
        print(f"❌ Telethon: Sync wrapper error: {e}")
        return False


# Module initialization check (skip during tests to avoid noise)
if not IS_TESTING:
    if TELETHON_ENABLED:
        print(f"📱 Telethon notifier enabled for group {TARGET_CHAT_ID}")
    else:
        print("⚠️  Telethon notifier disabled (check environment variables)")

