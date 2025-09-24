import asyncio
import json
import os
import signal

import websockets

CIELO_WS_URL = os.getenv("CIELO_WS_URL", "wss://feed-api.cielo.finance/api/v1/ws")
API_KEY = os.getenv("CIELO_API_KEY")


async def _subscribe(ws):
    """Try subscribe payloads in order of permissiveness."""
    payloads = [
        {"type": "subscribe_feed", "filter": {"tx_types": ["transfer", "swap"], "chains": ["solana"], "min_usd_value": 1000}},
        {"type": "subscribe_feed", "filter": {"chains": ["solana"]}},
        {"type": "subscribe_feed"},
    ]
    for i, p in enumerate(payloads, 1):
        try:
            await ws.send(json.dumps(p))
            print(f"WS: sent subscribe variant #{i}: {p}")
            return
        except Exception as e:
            print("WS subscribe error:", e)


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
                await _subscribe(ws)
                while True:
                    msg = await ws.recv()
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


