import asyncio
import json
import os
import signal

import websockets
from dotenv import load_dotenv

# Load .env so API key is available when running directly
load_dotenv()

CIELO_WS_URL = os.getenv("CIELO_WS_URL", "wss://feed-api.cielo.finance/api/v1/ws")
API_KEY = os.getenv("CIELO_API_KEY")


def _build_filter_from_env():
    """Build subscription filter from environment variables.
    CIELO_WS_MIN_USD (default 0) and CIELO_WS_TX_TYPES (comma-separated).
    """
    min_usd = 0
    try:
        min_usd = int(os.getenv("CIELO_WS_MIN_USD", "0") or "0")
    except Exception:
        min_usd = 0

    tx_types_env = os.getenv("CIELO_WS_TX_TYPES")
    tx_types = [t.strip() for t in tx_types_env.split(",") if t.strip()] if tx_types_env else []

    chains_env = os.getenv("CIELO_WS_CHAINS", "solana")
    chains = [c.strip() for c in chains_env.split(",") if c.strip()]

    tokens_env = os.getenv("CIELO_WS_TOKENS")
    tokens = [x.strip() for x in tokens_env.split(",") if x.strip()] if tokens_env else []

    f = {"chains": chains or ["solana"]}
    if tx_types:
        f["tx_types"] = tx_types
    if min_usd > 0:
        f["min_usd_value"] = min_usd
    if tokens:
        f["tokens"] = tokens
    return f


async def _subscribe(ws, mode="all"):
    """Send a subscribe message.
    modes: 'all' (no filter), 'env' (env-driven filter), 'chains' (solana only)
    """
    payload = {"type": "subscribe_feed"}
    if mode == "env":
        payload["filter"] = _build_filter_from_env()
    elif mode == "chains":
        payload["filter"] = {"chains": ["solana"]}
    # else 'all': no filter
    list_id_env = os.getenv("CIELO_WS_LIST_ID")
    if list_id_env:
        try:
            payload["list_id"] = int(list_id_env)
        except ValueError:
            pass
    # If user provided a wallet, subscribe to it first for a deterministic test
    test_wallet = os.getenv("CIELO_WS_WALLET")
    if test_wallet:
        wallet_cmd = {"type": "subscribe_wallet", "wallet": test_wallet}
        await ws.send(json.dumps(wallet_cmd))
        print("WS: sent subscribe_wallet:", wallet_cmd)

    await ws.send(json.dumps(payload))
    print("WS: sent subscribe (mode=", mode, "):", payload)


async def ws_feed():
    if not API_KEY:
        raise RuntimeError("CIELO_API_KEY not set")

    # Try multiple header variants to avoid 403s if the server expects a different auth header
    header_variants = [
        [("X-API-Key", API_KEY)],
        [("Authorization", f"Bearer {API_KEY}")],
    ]

    last_err = None
    for hv in header_variants:
        try:
            async with websockets.connect(CIELO_WS_URL, extra_headers=hv, ping_interval=20, ping_timeout=10) as ws:
                print("WS: connected with headers:", hv)
                # Subscribe to ALL events first (most permissive, matches docs)
                await _subscribe(ws, mode="all")
                idle = 0
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=15)
                        idle = 0
                    except asyncio.TimeoutError:
                        idle += 15
                        # escalate filters sequence: all -> chains -> env
                        mode = "chains" if (idle // 15) % 2 == 1 else "env"
                        print("WS: no events in", idle, "seconds; resubscribing (mode=", mode, ")…")
                        await _subscribe(ws, mode=mode)
                        continue
                    try:
                        data = json.loads(msg)
                    except Exception:
                        print("WS raw:", msg[:200])
                        continue
                    token = data.get("token_address") or data.get("mint") or data.get("token")
                    kind = data.get("type") or data.get("event")
                    usd = data.get("usd_value") or data.get("value_usd")
                    print(f"Feed item: kind={kind} token={token} usd={usd}")
        except Exception as e:
            last_err = e
            print("WS connect error with headers", hv, ":", e)
            # try next header variant
            continue
    # If we tried all headers and failed, raise the last
    if last_err:
        raise last_err


async def main():
    stop = asyncio.Event()

    def _handle(*_):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _handle)
        except NotImplementedError:
            pass

    while not stop.is_set():
        try:
            await ws_feed()
        except Exception as e:
            print("WS error, reconnecting in 5s:", e)
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass


if __name__ == "__main__":
    asyncio.run(main())


