import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from threading import Lock


LOG_DIR = os.getenv("CALLSBOT_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_log_lock = Lock()


def _log_path(name: str) -> str:
    return os.path.join(LOG_DIR, name)


def write_jsonl(filename: str, record: Dict[str, Any]) -> None:
    path = _log_path(filename)
    record = dict(record)
    record["ts"] = record.get("ts") or datetime.utcnow().isoformat()
    line = json.dumps(record, ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    # Atomic-ish append: single os.write call under a lock to avoid partial interleaving
    with _log_lock:
        fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)


def log_alert(event: Dict[str, Any]) -> None:
    write_jsonl("alerts.jsonl", event)


def log_tracking(event: Dict[str, Any]) -> None:
    write_jsonl("tracking.jsonl", event)


