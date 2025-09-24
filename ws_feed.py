import json
import threading
import time
from datetime import datetime

import websocket

from config import CIELO_API_KEY


def _on_open(ws):
    try:
        msg = {"type": "subscribe_feed", "chains": ["solana"]}
        ws.send(json.dumps(msg))
        print("WS: subscribed to feed (solana)")
    except Exception as e:
        print(f"WS open error: {e}")


def _on_message(ws, message):
    try:
        data = json.loads(message)
    except Exception:
        print("WS: non-JSON message", message[:200])
        return

    ts = datetime.now().strftime('%H:%M:%S')
    # Cielo WS usually pushes objects with token info / transaction data
    # Print a concise heartbeat line to prove visibility
    token = (
        data.get('token_address')
        or data.get('token')
        or data.get('mint')
    )
    usd = data.get('usd_value') or data.get('value_usd')
    kind = data.get('type') or data.get('event')
    print(f"[{ts}] WS event: kind={kind} token={token} usd={usd}")


def _on_error(ws, error):
    print("WS error:", error)


def _on_close(ws, code, reason):
    print(f"WS closed code={code} reason={reason}")


def run_ws_forever():
    # Use Cielo's documented WS endpoint
    url = "wss://feed-api.cielo.finance/api/v1/ws"
    headers = [f"X-API-Key: {CIELO_API_KEY}"]

    ws = websocket.WebSocketApp(
        url,
        header=headers,
        on_open=_on_open,
        on_message=_on_message,
        on_error=_on_error,
        on_close=_on_close,
    )

    # Keepalive loop with auto-reconnect
    while True:
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print("WS fatal error, retrying in 5s:", e)
            time.sleep(5)


if __name__ == "__main__":
    print("Starting Cielo WS client (Solana)…")
    run_ws_forever()


