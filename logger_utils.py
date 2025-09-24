import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


LOG_DIR = os.getenv("CALLSBOT_LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _log_path(name: str) -> str:
    return os.path.join(LOG_DIR, name)


def write_jsonl(filename: str, record: Dict[str, Any]) -> None:
    path = _log_path(filename)
    record = dict(record)
    record["ts"] = record.get("ts") or datetime.utcnow().isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_alert(event: Dict[str, Any]) -> None:
    write_jsonl("alerts.jsonl", event)


def log_tracking(event: Dict[str, Any]) -> None:
    write_jsonl("tracking.jsonl", event)


