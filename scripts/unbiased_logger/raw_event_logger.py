import os
import sys
import json
import time
import logging
import sqlite3
import asyncio
import redis
import zstandard as zstd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("RawEventLogger")

# Load environment variables
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
STREAM_KEY = "unbiased_logger:events"
GROUP_NAME = "raw_logger_group"
CONSUMER_NAME = "raw_logger_1"

# Directory setup
BASE_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs", "raw_data")
os.makedirs(BASE_LOG_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_LOG_DIR, "active_state.db")


class RawEventLogger:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True
        )
        self._init_redis_group()
        self.conn = self._init_db()
        self.current_date_str = None
        self.event_dict_path = os.path.join(BASE_LOG_DIR, "event_dictionary.json")
        self.event_dictionary = self._load_event_dict()
        
    def _load_event_dict(self):
        if os.path.exists(self.event_dict_path):
            with open(self.event_dict_path, "r") as f:
                return json.load(f)
        return {}

    def _get_event_id(self, event_type_str):
        if event_type_str not in self.event_dictionary:
            new_id = len(self.event_dictionary) + 1
            self.event_dictionary[event_type_str] = new_id
            with open(self.event_dict_path, "w") as f:
                json.dump(self.event_dictionary, f, indent=2)
        return self.event_dictionary[event_type_str]
        
    def _init_redis_group(self):
        try:
            self.redis_client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
            logger.info(f"Created consumer group {GROUP_NAME}")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" in str(e):
                logger.info(f"Consumer group {GROUP_NAME} already exists")
            else:
                raise e

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Create active_tokens table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_tokens (
                mint TEXT PRIMARY KEY,
                creator TEXT,
                launch_epoch INTEGER,
                last_trade_epoch INTEGER,
                next_buy_rank INTEGER DEFAULT 1,
                next_sell_rank INTEGER DEFAULT 1,
                expires_epoch INTEGER
            )
        ''')
        
        # Create logger_metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logger_metadata (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER,
                last_processed_stream_id TEXT,
                boot_time INTEGER,
                rotation_date TEXT
            )
        ''')
        
        # Insert default metadata if not exists
        cursor.execute('''
            INSERT OR IGNORE INTO logger_metadata 
            (id, schema_version, last_processed_stream_id, boot_time, rotation_date)
            VALUES (1, 1, '0-0', ?, ?)
        ''', (int(time.time()), datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        
        conn.commit()
        return conn

    def _get_metadata(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM logger_metadata WHERE id = 1')
        return cursor.fetchone()

    def _update_metadata(self, last_id, rotation_date):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE logger_metadata 
            SET last_processed_stream_id = ?, rotation_date = ?
            WHERE id = 1
        ''', (last_id, rotation_date))
        self.conn.commit()
        
    def _get_dir_for_epoch(self, epoch_time):
        dt = datetime.fromtimestamp(epoch_time, tz=timezone.utc)
        dir_path = os.path.join(BASE_LOG_DIR, str(dt.year), f"{dt.month:02d}", f"{dt.day:02d}", f"{dt.hour:02d}")
        
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            # Drop schema hash metadata.json
            metadata_file = os.path.join(dir_path, "metadata.json")
            if not os.path.exists(metadata_file):
                with open(metadata_file, "w") as f:
                    json.dump({
                        "schema_version": 2,
                        "logger_version": "1.0.2",
                        "build_commit": os.getenv("GIT_COMMIT", "unknown"),
                        "compression": "zstd"
                    }, f, indent=2)
                    
        return dir_path, dt.strftime("%Y-%m-%d-%H")

    def _compress_old_csvs(self, old_date_str):
        logger.info(f"Starting ZSTD compression for {old_date_str}")
        try:
            dt = datetime.strptime(old_date_str, "%Y-%m-%d-%H")
            dir_path = os.path.join(BASE_LOG_DIR, str(dt.year), f"{dt.month:02d}", f"{dt.day:02d}", f"{dt.hour:02d}")
            
            if not os.path.exists(dir_path):
                return

            cctx = zstd.ZstdCompressor(level=10)
            
            for filename in ["events.csv", "trades.csv"]:
                filepath = os.path.join(dir_path, filename)
                if os.path.exists(filepath):
                    out_filepath = filepath + ".zst"
                    with open(filepath, 'rb') as f_in:
                        with open(out_filepath, 'wb') as f_out:
                            cctx.copy_stream(f_in, f_out)
                    os.remove(filepath)
                    logger.info(f"Compressed {filename} to {filename}.zst")
        except Exception as e:
            logger.error(f"Error compressing logs for {old_date_str}: {e}")

    def _log_event(self, event_type, stream_id, payload_json, epoch_time):
        dir_path, _ = self._get_dir_for_epoch(epoch_time)
        events_file = os.path.join(dir_path, "events.csv")
        
        write_header = not os.path.exists(events_file)
        with open(events_file, "a") as f:
            if write_header:
                f.write("event_type,stream_id,payload_json\n")
            # Replace newlines in json payload to keep it single-line in CSV
            safe_payload = payload_json.replace('\n', ' ')
            # Properly escape double quotes and wrap in quotes for valid CSV
            escaped_payload = safe_payload.replace('"', '""')
            f.write(f'{event_type},{stream_id},"{escaped_payload}"\n')

    def _log_trade(self, trade_data, epoch_time, dir_path):
        trades_file = os.path.join(dir_path, "trades.csv")
        
        write_header = not os.path.exists(trades_file)
        with open(trades_file, "a") as f:
            if write_header:
                f.write("timestamp,signature,mint,wallet,side,token_amount,sol_amount,entry_rank,exit_rank,is_creator\n")
            
            f.write(f"{trade_data['timestamp']},{trade_data['signature']},{trade_data['mint']},"
                    f"{trade_data['wallet']},{trade_data['side']},{trade_data['token_amount']},"
                    f"{trade_data['sol_amount']},{trade_data['entry_rank']},{trade_data['exit_rank']},"
                    f"{trade_data['is_creator']}\n")

    def process_events(self):
        metadata = self._get_metadata()
        last_id = metadata['last_processed_stream_id']
        current_rotation_date = metadata['rotation_date']
        
        logger.info(f"Resuming from stream ID {last_id}")

        while True:
            try:
                # Read from stream
                messages = self.redis_client.xreadgroup(
                    GROUP_NAME, CONSUMER_NAME, {STREAM_KEY: ">"}, count=100, block=2000
                )
                
                if not messages:
                    # Perform cleanup of expired tokens every idle cycle
                    self._cleanup_expired_tokens()
                    continue

                cursor = self.conn.cursor()
                
                for stream, msg_list in messages:
                    for msg_id, msg_data in msg_list:
                        try:
                            # 1. Parse Event
                            payload_str = msg_data.get("payload", "{}")
                            try:
                                payload = json.loads(payload_str)
                            except:
                                payload = {}
                                
                            event_type_str = payload.get("event_type", "Unknown")
                            event_type_id = self._get_event_id(event_type_str)
                            receipt_time = float(payload.get("receipt_time", time.time()))
                            epoch_time = int(receipt_time)
                            
                            # Minimal provenance for Trade events
                            if event_type_str == "Trade":
                                sig = payload.get("raw_data", {}).get("signature", "unknown")
                                payload_str = json.dumps({"signature": sig})
                            
                            # Log raw event immediately
                            self._log_event(event_type_id, msg_id, payload_str, epoch_time)
                            
                            dir_path, event_date_str = self._get_dir_for_epoch(epoch_time)
                            
                            # Handle Rotation
                            if event_date_str != current_rotation_date:
                                # Spawn compression in background thread or just do it
                                self._compress_old_csvs(current_rotation_date)
                                current_rotation_date = event_date_str

                            # 2. Process logic based on event type
                            if event_type_str == "TokenCreated":
                                mint = payload.get("mint")
                                creator = payload.get("raw_data", {}).get("user") # Wait, PumpPortal TokenCreated has user? Actually we'll just extract from raw_data if possible.
                                # The TokenCreated from pumpportal has traderPublicKey or user. Let's safely extract.
                                if not creator:
                                    creator = payload.get("raw_data", {}).get("traderPublicKey", "unknown")
                                
                                # Set expires_epoch to 2 hours from now
                                expires_epoch = epoch_time + (2 * 3600)
                                
                                cursor.execute('''
                                    INSERT OR REPLACE INTO active_tokens 
                                    (mint, creator, launch_epoch, last_trade_epoch, next_buy_rank, next_sell_rank, expires_epoch)
                                    VALUES (?, ?, ?, ?, 1, 1, ?)
                                ''', (mint, creator, epoch_time, epoch_time, expires_epoch))
                                
                            elif event_type_str == "Trade":
                                mint = payload.get("mint")
                                
                                # Check if token is active
                                cursor.execute('SELECT * FROM active_tokens WHERE mint = ?', (mint,))
                                token_row = cursor.fetchone()
                                
                                if token_row:
                                    # We are tracking this token
                                    creator = token_row['creator']
                                    raw_data = payload.get("raw_data", {})
                                    
                                    signature = raw_data.get("signature", "unknown")
                                    wallet = raw_data.get("traderPublicKey", "unknown")
                                    is_buy = 1 if raw_data.get("txType") == "buy" else 0
                                    token_amount = raw_data.get("tokenAmount", 0)
                                    sol_amount = raw_data.get("solAmount", 0)
                                    
                                    is_creator = 1 if wallet == creator else 0
                                    
                                    # Ranks
                                    entry_rank = 0
                                    exit_rank = 0
                                    next_buy_rank = token_row['next_buy_rank']
                                    next_sell_rank = token_row['next_sell_rank']
                                    
                                    if is_buy:
                                        entry_rank = next_buy_rank
                                        next_buy_rank += 1
                                    else:
                                        exit_rank = next_sell_rank
                                        next_sell_rank += 1
                                        
                                    # Update state
                                    # Extend expiry if needed: age > 2h AND last_trade > 15m ago.
                                    # Meaning: expiration pushes forward to at least (now + 15m) if age is > 2h
                                    # Actually, just set expires_epoch = MAX(launch_epoch + 2h, current_time + 15m)
                                    launch_epoch = token_row['launch_epoch']
                                    new_expires_epoch = max(launch_epoch + (2 * 3600), epoch_time + (15 * 60))
                                    
                                    cursor.execute('''
                                        UPDATE active_tokens 
                                        SET last_trade_epoch = ?, next_buy_rank = ?, next_sell_rank = ?, expires_epoch = ?
                                        WHERE mint = ?
                                    ''', (epoch_time, next_buy_rank, next_sell_rank, new_expires_epoch, mint))
                                    
                                    # Log normalized trade
                                    trade_row = {
                                        "timestamp": epoch_time,
                                        "signature": signature,
                                        "mint": mint,
                                        "wallet": wallet,
                                        "side": is_buy,
                                        "token_amount": token_amount,
                                        "sol_amount": sol_amount,
                                        "entry_rank": entry_rank,
                                        "exit_rank": exit_rank,
                                        "is_creator": is_creator
                                    }
                                    self._log_trade(trade_row, epoch_time, dir_path)

                            # Ack the message
                            self.redis_client.xack(STREAM_KEY, GROUP_NAME, msg_id)
                            last_id = msg_id
                            
                        except Exception as e:
                            logger.error(f"Error processing message {msg_id}: {e}")
                            
                # Commit all state updates for this batch
                self._update_metadata(last_id, current_rotation_date)
                
            except redis.exceptions.ConnectionError:
                logger.error("Redis connection lost. Retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in loop: {e}")
                time.sleep(1)

    def _cleanup_expired_tokens(self):
        """Drops tokens that have aged out of the tracking window."""
        current_time = int(time.time())
        cursor = self.conn.cursor()
        
        cursor.execute('DELETE FROM active_tokens WHERE expires_epoch < ?', (current_time,))
        deleted = cursor.rowcount
        if deleted > 0:
            self.conn.commit()
            logger.info(f"Cleaned up {deleted} expired tokens from active tracking.")

if __name__ == "__main__":
    logger.info("Starting Raw Event Logger...")
    while True:
        try:
            worker = RawEventLogger()
            worker.process_events()
        except Exception as e:
            logger.error(f"Fatal error, restarting worker: {e}")
            time.sleep(5)
