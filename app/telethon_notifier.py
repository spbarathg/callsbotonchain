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

# Thread-local storage for Telethon clients (one per thread/event loop)
import threading
_thread_local = threading.local()
IS_TESTING = "PYTEST_CURRENT_TEST" in os.environ


async def initialize_client_async() -> bool:
    """
    Pre-initialize the Telethon client to avoid database lock issues.
    
    This should be called BEFORE starting the Signal Aggregator to ensure
    the notifier client is initialized first, preventing SQLite lock contention.
    
    Returns:
        True if initialized successfully, False otherwise
    """
    if not TELETHON_ENABLED:
        return False
    
    try:
        client = await _get_client()
        return client is not None
    except Exception as e:
        print(f"❌ Telethon: Pre-initialization failed: {e}")
        return False


def initialize_client() -> bool:
    """
    Synchronous wrapper for initialize_client_async.
    
    Pre-initializes the Telethon notifier client to prevent database lock issues
    when Signal Aggregator is running.
    
    Returns:
        True if initialized successfully, False otherwise
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(initialize_client_async())
            return result
        finally:
            # Don't close the loop - keep it for future use
            pass
    except Exception as e:
        print(f"❌ Telethon: Client initialization error: {e}")
        return False


async def _get_client():  # -> Optional[TelegramClient] but can't annotate due to lazy import
    """
    Get or create a Telethon client for the current event loop.
    
    FIXED: Uses thread-local storage to ensure each event loop has its own
    client instance, preventing "event loop must not change" errors.
    """
    if not TELETHON_ENABLED:
        return None
    
    # Get or create client for this thread
    if not hasattr(_thread_local, 'client'):
        _thread_local.client = None
    
    if _thread_local.client is None:
        # Lazy import Telethon only when actually needed
        from telethon import TelegramClient
        
        try:
            client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                print("❌ Telethon: Session not authorized. Run setup_telethon_session.py first.")
                return None
            
            # Verify access to target group
            try:
                entity = await client.get_entity(TARGET_CHAT_ID)
                print(f"✅ Telethon connected to: {entity.title}")
            except Exception as e:
                print(f"❌ Telethon: Cannot access group {TARGET_CHAT_ID}: {e}")
                await client.disconnect()
                return None
            
            _thread_local.client = client
                
        except Exception as e:
            print(f"❌ Telethon client initialization failed: {e}")
            return None
    
    return _thread_local.client


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
    
    FIXED: Properly handles event loop conflicts by using a dedicated thread
    with its own event loop instead of asyncio.run() which conflicts with
    Signal Aggregator's event loop.
    
    Args:
        message: The message text to send
    
    Returns:
        True if sent successfully, False otherwise
    """
    import threading
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

