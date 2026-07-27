import asyncio
import json
import logging
import os
from datetime import datetime, timezone
import redis.asyncio as redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DepthTracker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs', 'depth_series')
os.makedirs(LOG_DIR, exist_ok=True)

class DepthTracker:
    def __init__(self):
        self.redis = redis.from_url(REDIS_URL)
        # mint -> { "launch_time": ts, "last_vsol": val, "last_vtoken": val, "last_bar_ts": ts }
        self.token_state = {}

    def _get_log_filepath(self, dt: datetime):
        date_str = dt.strftime("%Y-%m-%d")
        return os.path.join(LOG_DIR, f"{date_str}.jsonl")

    async def _process_event(self, event_data):
        event_type = event_data.get("event_type")
        mint = event_data.get("mint")
        receipt_time = event_data.get("receipt_time")
        raw_data = event_data.get("raw_data", {})
        
        dt = datetime.fromtimestamp(receipt_time, tz=timezone.utc)
        
        if event_type == "TokenCreated":
            # Initialize tracking state
            self.token_state[mint] = {
                "launch_time": receipt_time,
                "last_vsol": raw_data.get("vSolInBondingCurve", 30.0), # typical starting vSol
                "last_vtoken": raw_data.get("vTokensInBondingCurve", 1073000000.0),
                "last_bar_ts": receipt_time
            }
            # Log initial bar
            self._log_bar(mint, receipt_time, dt, self.token_state[mint]["last_vsol"], self.token_state[mint]["last_vtoken"])
            
        elif event_type == "Trade":
            if mint not in self.token_state:
                # We missed the creation event, maybe tracking started late
                self.token_state[mint] = {
                    "launch_time": receipt_time,
                    "last_vsol": raw_data.get("vSolInBondingCurve", 0),
                    "last_vtoken": raw_data.get("vTokensInBondingCurve", 0),
                    "last_bar_ts": receipt_time
                }
                
            state = self.token_state[mint]
            
            # Extract new bonding curve state
            vsol = raw_data.get("vSolInBondingCurve")
            vtoken = raw_data.get("vTokensInBondingCurve")
            
            if vsol is None or vtoken is None:
                return
                
            state["last_vsol"] = vsol
            state["last_vtoken"] = vtoken
            
            elapsed = receipt_time - state["launch_time"]
            
            # Determine bar resolution requirement
            # First 5 minutes: 1s bars
            # 5m to 4h: 1m bars
            # > 4h: Drop from tracking
            
            if elapsed > 14400: # 4 hours
                if mint in self.token_state:
                    del self.token_state[mint]
                return
                
            if elapsed <= 300: # First 5 mins
                bar_interval = 1.0
            else:
                bar_interval = 60.0
                
            if receipt_time - state["last_bar_ts"] >= bar_interval:
                # Time for a new bar
                state["last_bar_ts"] = receipt_time
                self._log_bar(mint, receipt_time, dt, vsol, vtoken)

    def _log_bar(self, mint, ts, dt, vsol, vtoken):
        bar_data = {
            "mint": mint,
            "ts": ts,
            "vsol": vsol,
            "vtoken": vtoken
        }
        log_file = self._get_log_filepath(dt)
        with open(log_file, "a") as f:
            f.write(json.dumps(bar_data) + "\n")

    async def run(self):
        stream_name = "unbiased_logger:events"
        group_name = "depth_group"
        consumer_name = "depth_worker_1"
        
        # Create consumer group if it doesn't exist
        try:
            await self.redis.xgroup_create(stream_name, group_name, mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
                
        logger.info("DepthTracker started. Claiming orphaned messages...")
        
        # XAUTOCLAIM orphaned messages (pending > 60s)
        try:
            claim_res = await self.redis.xautoclaim(stream_name, group_name, consumer_name, 60000, "0-0", count=100)
            if isinstance(claim_res, tuple) and len(claim_res) >= 2:
                messages = claim_res[1]
                for message_id, message_data in messages:
                    await self._process_stream_message(stream_name, group_name, message_id, message_data)
        except Exception as e:
            logger.error(f"Error during XAUTOCLAIM: {e}")

        logger.info("Listening for unbiased_logger:events...")
        
        while True:
            try:
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
            await self.redis.xack(stream_name, group_name, message_id)
        except json.JSONDecodeError:
            await self.redis.xack(stream_name, group_name, message_id)
        except Exception as e:
            logger.error(f"Error processing event {message_id}: {e}")
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
            "source": "depth_tracker"
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(dl_event) + "\n")

if __name__ == "__main__":
    tracker = DepthTracker()
    asyncio.run(tracker.run())
