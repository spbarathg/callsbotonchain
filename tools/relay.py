import asyncio
import os
from typing import Optional, List
from telethon import TelegramClient
from telethon.errors import RPCError


# Environment variables needed:
# - PHANES_USER_RELAY: 'true' to enable
# - TELEGRAM_API_ID: numeric API ID (from https://my.telegram.org)
# - TELEGRAM_API_HASH: API hash
# - TELEGRAM_PHONE: phone number for the user account (e.g., +15551234567)
# - TELEGRAM_TARGET_CHAT: chat id or @username of the channel/group to post the CA


_client: Optional[TelegramClient] = None


def relay_enabled() -> bool:
    return os.getenv("PHANES_USER_RELAY", "false").lower() == "true"


def _get_env(name: str) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None and v != "" else None


async def _ensure_client() -> Optional[TelegramClient]:
    global _client
    if _client:
        return _client

    if not relay_enabled():
        return None

    api_id = _get_env("TELEGRAM_API_ID")
    api_hash = _get_env("TELEGRAM_API_HASH")
    phone = _get_env("TELEGRAM_PHONE")

    if not api_id or not api_hash or not phone:
        print("Relay disabled: missing TELEGRAM_API_ID/API_HASH/PHONE")
        return None

    try:
        api_id_int = int(api_id)
    except ValueError:
        print("Relay disabled: TELEGRAM_API_ID must be integer")
        return None

    session_name = os.getenv("TELETHON_SESSION_NAME", "relay_user")
    _client = TelegramClient(session_name, api_id_int, api_hash)
    await _client.connect()
    if not await _client.is_user_authorized():
        try:
            await _client.send_code_request(phone)
            code = input("Enter the Telegram login code sent to your account: ")
            await _client.sign_in(phone=phone, code=code)
        except Exception as e:
            print("Relay authorization failed:", e)
            return None
    return _client


async def relay_contract_address(ca_text: str) -> bool:
    """Send a plain-text CA from a user account, so 3rd-party bots can ingest it."""
    if not relay_enabled():
        return False
    target = _get_env("TELEGRAM_TARGET_CHAT")
    if not target:
        print("Relay disabled: TELEGRAM_TARGET_CHAT not set")
        return False

    client = await _ensure_client()
    if not client:
        return False

    try:
        entity = await _resolve_target(client, target)
        await client.send_message(entity, ca_text)
        return True
    except RPCError as e:
        print("Relay send error:", e)
        return False
    except Exception as e:
        print("Relay unexpected error:", e)
        return False


def relay_contract_address_sync(ca_text: str) -> bool:
    return asyncio.get_event_loop().run_until_complete(relay_contract_address(ca_text))


async def _resolve_target(client: TelegramClient, target: str):
    """Resolve a chat target from username, invite link, title, or numeric id."""
    t = target.strip()
    # Numeric (including -100 channel ids)
    if t.lstrip("-").isdigit():
        return int(t)
    # t.me links
    if t.startswith("http") or t.startswith("t.me/") or "+" in t:
        try:
            return await client.get_entity(t)
        except Exception:
            pass
    # @username
    if t.startswith("@"):
        try:
            return await client.get_entity(t)
        except Exception:
            pass
    # Fallback: search dialogs by title (case-insensitive)
    try:
        dialogs = await client.get_dialogs(limit=500)
        norm = t.casefold()
        # exact match first
        for d in dialogs:
            if (d.name or "").casefold() == norm:
                return d.entity
        # startswith match
        for d in dialogs:
            if (d.name or "").casefold().startswith(norm):
                return d.entity
    except Exception:
        pass
    raise ValueError(f"Cannot resolve TELEGRAM_TARGET_CHAT='{target}'. Use @username, numeric id, or invite link.")


def list_chats_sync(limit: int = 200) -> None:
    asyncio.get_event_loop().run_until_complete(_list_chats(limit))


async def _list_chats(limit: int = 200) -> None:
    client = await _ensure_client()
    if not client:
        print("Relay disabled or not authorized.")
        return
    dialogs = await client.get_dialogs(limit=limit)
    print("Your recent chats (use @username or ID):")
    for d in dialogs:
        try:
            eid = getattr(d.entity, 'id', None)
            print(f"- {d.name}  | id={eid}")
        except Exception:
            pass


