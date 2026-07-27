import asyncio
import websockets
import json
import time
import logging
import os
import base64
import struct
import redis.asyncio as redis
from datetime import datetime, timezone
from solders.pubkey import Pubkey

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("StreamClient")

# Configuration
PUMP_PORTAL_WS = "wss://pumpportal.fun/api/data"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Transform HTTPS RPC URL to WSS
rpc_url = os.getenv("TS_RPC_URL", "https://api.mainnet-beta.solana.com")
HELIUS_RPC_WS = rpc_url.replace("https://", "wss://")

HEARTBEAT_INTERVAL = 30
DISCONNECT_THRESHOLD = 60

PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TRADE_EVENT_DISCRIMINATOR = bytes([189, 219, 127, 211, 78, 230, 97, 238])

class StreamClient:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        self.active_tokens = set()
        self.last_message_time = time.time()
        self.is_connected = False
        self.disconnect_time = None
        self.redis_queue = asyncio.Queue(maxsize=10000)
        self.unknown_trades_buffer = {} # mint -> list of (timestamp, trade_event)

    def _enqueue_event(self, event):
        """Puts event in asyncio.Queue, dropping oldest if full to prevent OOM."""
        if self.redis_queue.full():
            try:
                self.redis_queue.get_nowait()
                logger.warning("queue_full_dropped_oldest: Redis publisher is lagging. Dropped oldest event.")
            except asyncio.QueueEmpty:
                pass
        self.redis_queue.put_nowait(event)

    async def _redis_publisher(self):
        """Batch flushes the local asyncio.Queue to Redis using pipelines."""
        while True:
            try:
                batch = []
                # Block for the first item
                item = await self.redis_queue.get()
                batch.append(item)
                
                # Drain the rest of the queue instantly (up to 500 per pipeline)
                while len(batch) < 500 and not self.redis_queue.empty():
                    batch.append(self.redis_queue.get_nowait())
                
                pipeline = self.redis.pipeline()
                for event in batch:
                    pipeline.xadd("unbiased_logger:events", {"payload": json.dumps(event)})
                
                await pipeline.execute()
                
                for _ in batch:
                    self.redis_queue.task_done()
                    
                await asyncio.sleep(0.05) # Small delay to allow batching to accumulate efficiently
            except Exception as e:
                logger.error(f"Redis publisher error: {e}. Restarting publisher...")
                await asyncio.sleep(1)

    async def _prune_unknown_trades(self):
        """Prunes trades older than 15s from the unknown_trades_buffer."""
        while True:
            await asyncio.sleep(5)
            now = time.time()
            evicted_count = 0
            for mint in list(self.unknown_trades_buffer.keys()):
                valid_trades = []
                for ts, trade in self.unknown_trades_buffer[mint]:
                    if now - ts <= 15:
                        valid_trades.append((ts, trade))
                    else:
                        evicted_count += 1
                if valid_trades:
                    self.unknown_trades_buffer[mint] = valid_trades
                else:
                    del self.unknown_trades_buffer[mint]
            
            if evicted_count > 0:
                logger.warning(f"unmatched_trade_evictions_total: {evicted_count} trades pruned without matching a TokenCreated event.")

    async def _send_gap_sentinel(self, start_time, end_time):
        """Logs an explicit gap sentinel to exclude downtime from backtesting."""
        sentinel_event = {
            "type": "gap_sentinel",
            "start_time_iso": datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
            "end_time_iso": datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat(),
            "duration_seconds": end_time - start_time,
            "start_ts": start_time,
            "end_ts": end_time
        }
        
        # Write to JSONL
        log_dir = os.path.join(os.path.dirname(__file__), 'logs', 'system_events')
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"{date_str}_gaps.jsonl")
        
        with open(log_file, "a") as f:
            f.write(json.dumps(sentinel_event) + "\n")
            
        await self.redis.xadd("unbiased_logger:system_events", {"payload": json.dumps(sentinel_event)})
        logger.warning(f"GAP SENTINEL LOGGED: Downtime from {sentinel_event['start_time_iso']} to {sentinel_event['end_time_iso']}")

    async def listen_pumpportal(self):
        """Listens ONLY for new token creations from PumpPortal (free stream)"""
        while True:
            try:
                logger.info(f"Connecting to PumpPortal {PUMP_PORTAL_WS}...")
                async with websockets.connect(PUMP_PORTAL_WS) as ws:
                    self.ws = ws
                    if self.disconnect_time:
                        await self._send_gap_sentinel(self.disconnect_time, time.time())
                        self.disconnect_time = None
                        
                    self.is_connected = True
                    self.last_message_time = time.time()
                    
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    
                    async for message in ws:
                        self.last_message_time = time.time()
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue
                            
                        receipt_time = time.time()
                        if "mint" in data and data.get("txType") == "create":
                            token_mint = data["mint"]
                            
                            if not token_mint.endswith("pump"):
                                continue
                                
                            self.active_tokens.add(token_mint)
                            
                            event = {
                                "event_type": "TokenCreated",
                                "receipt_time": receipt_time,
                                "mint": token_mint,
                                "raw_data": data
                            }
                            self._enqueue_event(event)
                            logger.info(f"TokenCreated: {token_mint}")
                            
                            # Flush any buffered trades for this mint (fixes race condition where snipes arrive before TokenCreated)
                            if token_mint in self.unknown_trades_buffer:
                                recovered_count = len(self.unknown_trades_buffer[token_mint])
                                logger.info(f"recovered_sniper_trades: Flushed {recovered_count} early trades for {token_mint}")
                                for ts, trade in self.unknown_trades_buffer[token_mint]:
                                    self._enqueue_event(trade)
                                del self.unknown_trades_buffer[token_mint]
                            
            except Exception as e:
                logger.error(f"PumpPortal WS error: {e}")
            finally:
                if self.is_connected:
                    self.disconnect_time = time.time()
                    self.is_connected = False
                await asyncio.sleep(5)

    async def listen_helius(self):
        """Listens for logsSubscribe on Helius to manually reconstruct trades for free"""
        while True:
            try:
                logger.info(f"Connecting to Helius WSS...")
                async with websockets.connect(HELIUS_RPC_WS) as ws:
                    req = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "logsSubscribe",
                        "params": [
                            {"mentions": [PROGRAM_ID]},
                            {"commitment": "confirmed"}
                        ]
                    }
                    await ws.send(json.dumps(req))
                    
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue
                            
                        receipt_time = time.time()
                        
                        if "params" in data and "result" in data["params"]:
                            result = data["params"]["result"]["value"]
                            if "logs" not in result:
                                continue
                                
                            logs = result["logs"]
                            signature = result.get("signature", "unknown")
                            
                            for log in logs:
                                if "Program data: " in log:
                                    b64_data = log.split("Program data: ")[1].strip()
                                    try:
                                        bin_data = base64.b64decode(b64_data)
                                    except Exception:
                                        continue
                                        
                                    if bin_data[:8] == TRADE_EVENT_DISCRIMINATOR:
                                        try:
                                            offset = 8
                                            mint_bytes = bin_data[offset:offset+32]
                                            offset += 32
                                            mint = str(Pubkey.from_bytes(mint_bytes))
                                            
                                            is_known = mint in self.active_tokens
                                                
                                            sol_amount = struct.unpack("<Q", bin_data[offset:offset+8])[0]
                                            offset += 8
                                            token_amount = struct.unpack("<Q", bin_data[offset:offset+8])[0]
                                            offset += 8
                                            is_buy = struct.unpack("<?", bin_data[offset:offset+1])[0]
                                            offset += 1
                                            user_bytes = bin_data[offset:offset+32]
                                            offset += 32
                                            user = str(Pubkey.from_bytes(user_bytes))
                                            
                                            # Reconstruct exact PumpPortal format
                                            trade_data = {
                                                "signature": signature,
                                                "mint": mint,
                                                "traderPublicKey": user,
                                                "txType": "buy" if is_buy else "sell",
                                                "tokenAmount": token_amount / 1e6,
                                                "solAmount": sol_amount / 1e9
                                            }
                                            
                                            event = {
                                                "event_type": "Trade",
                                                "receipt_time": receipt_time,
                                                "mint": mint,
                                                "raw_data": trade_data
                                            }
                                            
                                            if is_known:
                                                self._enqueue_event(event)
                                            else:
                                                if mint not in self.unknown_trades_buffer:
                                                    self.unknown_trades_buffer[mint] = []
                                                self.unknown_trades_buffer[mint].append((receipt_time, event))
                                            
                                        except Exception as e:
                                            logger.error(f"Failed to unpack TradeEvent: {e}")
                                            
            except Exception as e:
                logger.error(f"Helius WS error: {e}")
            finally:
                await asyncio.sleep(5)

    async def _heartbeat_monitor(self):
        while True:
            await asyncio.sleep(10)
            if self.is_connected and (time.time() - self.last_message_time > DISCONNECT_THRESHOLD):
                logger.error("Heartbeat missed. Connection assumed dead.")
                if hasattr(self, 'ws') and self.ws:
                    await self.ws.close()

    async def run(self):
        asyncio.create_task(self._heartbeat_monitor())
        # Run all asynchronous tasks safely
        await asyncio.gather(
            self.listen_pumpportal(), 
            self.listen_helius(),
            self._prune_unknown_trades(),
            self._redis_publisher()
        )

if __name__ == "__main__":
    client = StreamClient()
    asyncio.run(client.run())
