"""
Multi-Bot Signal Aggregator

Monitors signal groups on Telegram to detect consensus signals.
When multiple groups alert on the same token, it's a strong validation signal.

Quality Control:
- Only counts signals from tokens that meet basic quality thresholds
- Validates token exists and has minimum liquidity/volume
- Filters out spam/scam addresses
"""
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Global signal cache: {token_address: [(timestamp, group_name), ...]}
_signal_cache: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)
_validated_tokens: Dict[str, bool] = {}  # Cache of validated tokens
_cache_lock = asyncio.Lock()

# Signal groups to monitor (all treated equally)
MONITORED_CHANNELS = [
    '@MooDengPresidentCallers',
    '@Bot_NovaX',
    '@Ranma_Calls_Solana',
    '@MarksGems',
    '@Alphakollswithins',
    '@mattprintalphacalls',
    '@ReVoX_Academy',
    '@pfultimate',
    '@pumpfunvolumeby4AM',
    '@SouthParkCall',
    '@batman_gem',
    '@wifechangingcallss',
    '@SAVANNAHCALLS'
]


def extract_token_address(text: str) -> Optional[str]:
    """
    Extract Solana token address from message text.
    Handles various formats from different signal groups.
    """
    if not text:
        return None
    
    # Common false positives to exclude
    EXCLUDED = {
        'pump', 'SOL', 'USDC', 'USDT', 'BONK', 'WIF', 'JUP', 
        'So11111111111111111111111111111111111111112',  # Wrapped SOL
        'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',  # USDC
    }
    
    # Multiple patterns to catch different formats
    patterns = [
        # Standard formats
        r'(?:CA|Contract|Token|Address)[\s:]+([1-9A-HJ-NP-Za-km-z]{32,44})',
        # With emoji/symbols
        r'💎\s*([1-9A-HJ-NP-Za-km-z]{32,44})',
        r'🔥\s*([1-9A-HJ-NP-Za-km-z]{32,44})',
        r'📢\s*([1-9A-HJ-NP-Za-km-z]{32,44})',
        # Code blocks
        r'`([1-9A-HJ-NP-Za-km-z]{32,44})`',
        # URLs (dexscreener, birdeye, etc)
        r'dexscreener\.com/solana/([1-9A-HJ-NP-Za-km-z]{32,44})',
        r'birdeye\.so/token/([1-9A-HJ-NP-Za-km-z]{32,44})',
        r'pump\.fun/([1-9A-HJ-NP-Za-km-z]{32,44})',
        # General base58 (last resort)
        r'\b([1-9A-HJ-NP-Za-km-z]{32,44})\b',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for address in matches:
            # Validate length and not in exclusion list
            if 32 <= len(address) <= 44 and address not in EXCLUDED:
                # Additional validation: must start with valid base58 chars
                if address[0] in '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz':
                    return address
    
    return None


async def validate_token_quality(token_address: str) -> bool:
    """
    Validate token meets minimum quality standards.
    Returns True if token is worth considering, False otherwise.
    """
    # Check cache first
    if token_address in _validated_tokens:
        return _validated_tokens[token_address]
    
    try:
        from app.http_client import request_json
        
        # Quick check via DexScreener (free, fast)
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        result = request_json("GET", url, timeout=5)
        
        if result.get("status_code") != 200:
            _validated_tokens[token_address] = False
            return False
        
        data = result.get("json") or {}
        pairs = data.get("pairs") or []
        
        if not pairs:
            _validated_tokens[token_address] = False
            return False
        
        # Get best pair
        best_pair = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        
        # Quality thresholds (STRICT - filter bogus signals)
        liquidity = float((best_pair.get("liquidity") or {}).get("usd") or 0)
        volume_24h = float((best_pair.get("volume") or {}).get("h24") or 0)
        
        # Minimum quality bar
        MIN_LIQUIDITY = 10000  # $10k minimum (filters most scams)
        MIN_VOLUME = 5000      # $5k minimum (filters dead tokens)
        
        is_valid = liquidity >= MIN_LIQUIDITY and volume_24h >= MIN_VOLUME
        
        # Cache result
        _validated_tokens[token_address] = is_valid
        
        if not is_valid:
            print(f"⚠️  Signal Aggregator: Rejected {token_address[:8]}... "
                  f"(liq: ${liquidity:,.0f}, vol: ${volume_24h:,.0f})")
        
        return is_valid
        
    except Exception as e:
        print(f"❌ Signal Aggregator: Validation error for {token_address[:8]}...: {e}")
        return False


async def record_signal(token_address: str, group_name: str = "unknown") -> None:
    """Record a signal from a group (with quality validation)."""
    # Validate token quality first
    is_valid = await validate_token_quality(token_address)
    
    if not is_valid:
        return  # Silently reject low-quality signals
    
    async with _cache_lock:
        now = datetime.now()
        
        if token_address not in _signal_cache:
            _signal_cache[token_address] = []
        
        # Add signal with group name
        _signal_cache[token_address].append((now, group_name))
        
        # Clean old signals (>1 hour)
        _signal_cache[token_address] = [
            (ts, grp) for ts, grp in _signal_cache[token_address]
            if now - ts < timedelta(hours=1)
        ]


def get_signal_count(token_address: str) -> int:
    """Get number of validated group signals in last hour."""
    now = datetime.now()
    
    if token_address not in _signal_cache:
        return 0
    
    # Count recent signals from unique groups
    recent_signals = [
        (ts, grp) for ts, grp in _signal_cache[token_address]
        if now - ts < timedelta(hours=1)
    ]
    
    # Count unique groups (avoid double-counting if same group posts twice)
    unique_groups = set(grp for ts, grp in recent_signals)
    
    return len(unique_groups)


def cleanup_old_signals() -> None:
    """Remove signals older than 1 hour."""
    now = datetime.now()
    
    for token_address in list(_signal_cache.keys()):
        _signal_cache[token_address] = [
            (ts, grp) for ts, grp in _signal_cache[token_address]
            if now - ts < timedelta(hours=1)
        ]
        
        # Remove empty entries
        if not _signal_cache[token_address]:
            del _signal_cache[token_address]
    
    # Also cleanup validation cache (keep last 1000 entries)
    if len(_validated_tokens) > 1000:
        # Keep most recent 500
        keys_to_remove = list(_validated_tokens.keys())[:-500]
        for key in keys_to_remove:
            del _validated_tokens[key]


async def start_monitoring():
    """
    Start monitoring bot channels (run in background).
    This should be called once when the bot starts.
    """
    if not MONITORED_CHANNELS:
        print("⚠️  Signal Aggregator: No channels configured to monitor")
        return
    
    try:
        from telethon import TelegramClient, events
        from app.config_unified import (
            TELEGRAM_USER_API_ID,
            TELEGRAM_USER_API_HASH,
            TELETHON_ENABLED
        )
        import os
        
        if not TELETHON_ENABLED:
            print("⚠️  Signal Aggregator: Telethon not enabled")
            return
        
        # Use separate session file for monitoring to avoid conflicts with alert sender
        SIGNAL_AGGREGATOR_SESSION_FILE = os.getenv("SIGNAL_AGGREGATOR_SESSION_FILE", "var/memecoin_session.session")
        
        print(f"✅ Signal Aggregator: Starting to monitor {len(MONITORED_CHANNELS)} channels...")
        print(f"   Using session: {SIGNAL_AGGREGATOR_SESSION_FILE}")
        
        async with TelegramClient(
            SIGNAL_AGGREGATOR_SESSION_FILE,
            TELEGRAM_USER_API_ID,
            TELEGRAM_USER_API_HASH
        ) as client:
            
            @client.on(events.NewMessage(chats=MONITORED_CHANNELS))
            async def handler(event):
                """Handle new messages from monitored channels."""
                try:
                    message_text = event.message.text or ""
                    
                    # Get group name
                    try:
                        chat = await event.get_chat()
                        group_name = chat.username or chat.title or "unknown"
                    except Exception:
                        group_name = "unknown"
                    
                    # Log all messages (for debugging)
                    print(f"📨 Signal Aggregator: New message from @{group_name}")
                    if message_text:
                        # Show first 100 chars of message
                        preview = message_text[:100].replace('\n', ' ')
                        print(f"   Message preview: {preview}...")
                    
                    # Extract token address
                    token_address = extract_token_address(message_text)
                    
                    if token_address:
                        print(f"🔍 Signal Aggregator: Extracted token {token_address[:8]}... from @{group_name}")
                        await record_signal(token_address, group_name)
                        signal_count = get_signal_count(token_address)
                        
                        if signal_count > 0:  # Only log if validated
                            print(f"✅ Signal Aggregator: {group_name} → {token_address[:8]}... "
                                  f"(total groups: {signal_count})")
                    else:
                        print(f"   No token address found in message")
                
                except Exception as e:
                    print(f"❌ Signal Aggregator: Error processing message: {e}")
            
            # Cleanup task (every 5 minutes)
            async def cleanup_task():
                while True:
                    await asyncio.sleep(300)  # 5 minutes
                    cleanup_old_signals()
            
            # Start cleanup task
            asyncio.create_task(cleanup_task())
            
            print("✅ Signal Aggregator: Monitoring active")
            
            # Keep running
            await client.run_until_disconnected()
    
    except Exception as e:
        print(f"❌ Signal Aggregator: Failed to start monitoring: {e}")


# Synchronous wrapper for use in scoring
def get_other_bot_signals(token_address: str) -> int:
    """
    Get number of other bot signals for this token (synchronous).
    Safe to call from scoring logic.
    """
    return get_signal_count(token_address)

