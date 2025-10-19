"""
Telethon-based Telegram Group Notifier
Sends trading signals to a Telegram group using user account (not bot).

ULTIMATE FIX: Uses a single global client with proper async handling
to prevent SQLite session file locking issues.
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

# Global singleton client and lock for thread-safe access
_client_lock = threading.Lock()
_global_client = None
_client_initialized = False
IS_TESTING = "PYTEST_CURRENT_TEST" in os.environ


async def _get_client():  # -> Optional[TelegramClient] but can't annotate due to lazy import
    """
    Get or create a SINGLE global Telethon client.
    
    ULTIMATE FIX: Uses a single global client with proper locking,
    preventing multiple clients from trying to access the same session file.
    """
    global _global_client, _client_initialized
    
    if not TELETHON_ENABLED:
        return None
    
    # Use lock to ensure only one client is created
    with _client_lock:
        if not _client_initialized:
            # Lazy import Telethon only when actually needed
            from telethon import TelegramClient
            
            try:
                _global_client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
                await _global_client.connect()
                
                if not await _global_client.is_user_authorized():
                    print("❌ Telethon: Session not authorized. Run setup_telethon_session.py first.")
                    _global_client = None
                    return None
                
                # Verify access to target group
                try:
                    entity = await _global_client.get_entity(TARGET_CHAT_ID)
                    print(f"✅ Telethon: Global client initialized (session: {SESSION_FILE})")
                    print(f"✅ Telethon connected to: {entity.title}")
                except Exception as e:
                    print(f"❌ Telethon: Cannot access group {TARGET_CHAT_ID}: {e}")
                    await _global_client.disconnect()
                    _global_client = None
                    return None
                
                _client_initialized = True
                    
            except Exception as e:
                print(f"❌ Telethon client initialization failed: {e}")
                _global_client = None
                return None
    
    return _global_client


async def send_group_message_async(message: str) -> bool:
    """
    Send a message to the configured Telegram group.
    
    Args:
        message: The message text to send (supports HTML formatting)
    
    Returns:
        True if sent successfully, False otherwise
    """
    print(f"🔍 Telethon: send_group_message_async called (TELETHON_ENABLED={TELETHON_ENABLED})")
    
    if not TELETHON_ENABLED:
        if not IS_TESTING:
            print("⚠️  Telethon not enabled (missing credentials)")
        return False
    
    if not message or not message.strip():
        print("❌ Telethon: Empty message provided")
        return False
    
    print(f"🔍 Telethon: Attempting to send message to {TARGET_CHAT_ID}")
    
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
    
    ULTIMATE FIX: Uses a dedicated thread with its own event loop to avoid
    conflicts with Signal Aggregator or other async components.
    
    Args:
        message: The message text to send
    
    Returns:
        True if sent successfully, False otherwise
    """
    print(f"🔍 Telethon: send_group_message (sync wrapper) called")
    
    import queue
    
    result_queue = queue.Queue()
    
    def run_in_thread():
        """Run async code in a dedicated thread with its own event loop."""
        try:
            # Create a new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(send_group_message_async(message))
                result_queue.put(('success', result))
            finally:
                new_loop.close()
        except Exception as e:
            result_queue.put(('error', e))
    
    try:
        # Run async code in a separate thread to avoid event loop conflicts
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        thread.join(timeout=30)  # 30 second timeout
        
        if thread.is_alive():
            print("❌ Telethon: Send operation timed out")
            return False
        
        # Get result from queue
        try:
            status, value = result_queue.get_nowait()
            if status == 'success':
                return value
            else:
                print(f"❌ Telethon sync wrapper error: {value}")
                return False
        except queue.Empty:
            print("❌ Telethon: No result received from thread")
            return False
            
    except Exception as e:
        print(f"❌ Telethon thread creation error: {e}")
        return False


# Module initialization check (skip during tests to avoid noise)
if not IS_TESTING:
    if TELETHON_ENABLED:
        print(f"📱 Telethon notifier enabled for group {TARGET_CHAT_ID}")
    else:
        print("⚠️  Telethon notifier disabled (check environment variables)")

