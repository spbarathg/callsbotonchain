import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
import redis.asyncio as redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SnapshotEngine")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs', 'features_T30')
os.makedirs(LOG_DIR, exist_ok=True)

class SnapshotEngine:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        # Store events per mint: mint -> list of trade events
        self.events_buffer = {}

    def _get_log_filepath(self, dt: datetime):
        date_str = dt.strftime("%Y-%m-%d")
        return os.path.join(LOG_DIR, f"{date_str}.jsonl")

    async def _compute_and_log_snapshot(self, creation_event):
        mint = creation_event["mint"]
        receipt_time = creation_event["receipt_time"]
        
        # Wait until exactly T+30s based on local receipt time
        now = datetime.now(timezone.utc).timestamp()
        target_time = receipt_time + 30.0
        wait_time = target_time - now
        
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            
        # The window is now closed. Compute features.
        actual_processing_time = datetime.now(timezone.utc).timestamp()
        
        # Get buffered trades for this token
        trades = self.events_buffer.get(mint, [])
        
        # Filter strictly to trades that arrived before T+30
        valid_trades = [t for t in trades if t["receipt_time"] <= target_time]
        
        # Free up memory
        if mint in self.events_buffer:
            del self.events_buffer[mint]
            
        # Feature computation (T+30s)
        dt = datetime.fromtimestamp(receipt_time, tz=timezone.utc)
        iso_year, iso_week, _ = dt.isocalendar()
        
        buy_trades = [t for t in valid_trades if t.get("raw_data", {}).get("txType") == "buy"]
        sell_trades = [t for t in valid_trades if t.get("raw_data", {}).get("txType") == "sell"]
        
        # Sum volume (Assuming raw_data has solAmount, adjust based on actual payload)
        buy_volume = sum(t.get("raw_data", {}).get("solAmount", 0) for t in buy_trades)
        sell_volume = sum(t.get("raw_data", {}).get("solAmount", 0) for t in sell_trades)
        
        unique_buyers = len(set(t.get("raw_data", {}).get("traderPublicKey") for t in buy_trades if t.get("raw_data", {}).get("traderPublicKey")))
        
        features = {
            "mint": mint,
            "launch_timestamp": receipt_time,
            "launch_day": dt.strftime("%Y-%m-%d"),
            "launch_week": f"{iso_year}-W{iso_week:02d}",
            "receipt_latency": actual_processing_time - target_time, # Should be near 0
            "is_antbot_participant": False,
            "t30_trade_count": len(valid_trades),
            "t30_buy_count": len(buy_trades),
            "t30_sell_count": len(sell_trades),
            "t30_buy_volume_sol": buy_volume,
            "t30_sell_volume_sol": sell_volume,
            "t30_unique_buyers": unique_buyers,
            "trade_source": "logs_reconstruction"
        }
        
        log_file = self._get_log_filepath(dt)
        with open(log_file, "a") as f:
            f.write(json.dumps(features) + "\n")
            
        logger.info(f"Snapshot written for {mint}. Trades in window: {len(valid_trades)}")

    async def _process_event(self, event_data):
        event_type = event_data.get("event_type")
        mint = event_data.get("mint")
        
        if event_type == "TokenCreated":
            self.events_buffer[mint] = []
            # Spawn a task that sleeps for 30s then computes
            asyncio.create_task(self._compute_and_log_snapshot(event_data))
        elif event_type == "Trade":
            if mint in self.events_buffer:
                self.events_buffer[mint].append(event_data)

    async def run(self):
        stream_name = "unbiased_logger:events"
        group_name = "snapshot_group"
        consumer_name = "snapshot_worker_1"
        
        # Create consumer group if it doesn't exist
        try:
            await self.redis.xgroup_create(stream_name, group_name, mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
                
        logger.info("SnapshotEngine started. Claiming orphaned messages...")
        
        # XAUTOCLAIM orphaned messages (pending > 60s)
        try:
            # redis-py xautoclaim syntax: xautoclaim(name, groupname, consumername, min_idle_time, start_id, count=100)
            claim_res = await self.redis.xautoclaim(stream_name, group_name, consumer_name, 60000, "0-0", count=100)
            # claim_res returns (next_start_id, [messages], [deleted_message_ids]) depending on redis-py version
            # Usually (next_entry_id, messages)
            if isinstance(claim_res, tuple) and len(claim_res) >= 2:
                messages = claim_res[1]
                for message_id, message_data in messages:
                    await self._process_stream_message(stream_name, group_name, message_id, message_data)
        except Exception as e:
            logger.error(f"Error during XAUTOCLAIM: {e}")

        logger.info("Listening for unbiased_logger:events...")
        
        while True:
            try:
                # Read from Consumer Group ('>' means undelivered messages)
                results = await self.redis.xreadgroup(group_name, consumer_name, {stream_name: ">"}, count=100, block=1000)
                
                for stream, messages in results:
                    for message_id, message_data in messages:
                        await self._process_stream_message(stream_name, group_name, message_id, message_data)
                            
            except Exception as e:
                logger.error(f"Error reading stream: {e}")
                await asyncio.sleep(1)

    async def _process_stream_message(self, stream_name, group_name, message_id, message_data):
        payload_str = message_data.get(b"payload", b"{}").decode('utf-8')
        try:
            event_data = json.loads(payload_str)
            await self._process_event(event_data)
            # Acknowledge on success
            await self.redis.xack(stream_name, group_name, message_id)
        except json.JSONDecodeError:
            await self.redis.xack(stream_name, group_name, message_id)
        except Exception as e:
            logger.error(f"Error processing event {message_id}: {e}")
            # Check delivery count to handle poison messages
            pending_info = await self.redis.xpending_range(stream_name, group_name, message_id, message_id, 1)
            if pending_info and len(pending_info) > 0:
                delivery_count = pending_info[0].get('delivery_count', 0)
                if delivery_count > 3:
                    logger.error(f"Poison message detected {message_id}. Moving to dead letter log.")
                    await self._log_dead_letter(message_id, payload_str, str(e))
                    await self.redis.xack(stream_name, group_name, message_id)

    async def _log_dead_letter(self, message_id, payload_str, error_msg):
        log_dir = os.path.join(os.path.dirname(__file__), 'logs', 'system_events')
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"{date_str}_dead_letters.jsonl")
        dl_event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "message_id": message_id.decode('utf-8') if isinstance(message_id, bytes) else str(message_id),
            "payload": payload_str,
            "error": error_msg,
            "source": "snapshot_engine"
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(dl_event) + "\n")

if __name__ == "__main__":
    engine = SnapshotEngine()
    asyncio.run(engine.run())
