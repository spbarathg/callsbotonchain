import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from threading import Lock


# Persist logs locally under data/logs by default (never committed)
LOG_DIR = os.getenv("CALLSBOT_LOG_DIR", os.path.join("data", "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

# Optional: mirror JSON logs to stdout for containers/process supervisors
LOG_STDOUT = (os.getenv("CALLSBOT_LOG_STDOUT", "false").strip().lower() == "true")

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
        if LOG_STDOUT:
            try:
                # Best-effort mirror to stdout for observability (container-friendly)
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                # Never fail the main process due to logging
                pass


def log_alert(event: Dict[str, Any]) -> None:
    write_jsonl("alerts.jsonl", event)


def log_tracking(event: Dict[str, Any]) -> None:
    write_jsonl("tracking.jsonl", event)


# Monitoring helpers
def log_process(event: Dict[str, Any]) -> None:
    """
    Write a process/health event to process.jsonl. Accepts any dict and adds ts.
    """
    write_jsonl("process.jsonl", event)


def log_heartbeat(pid: int, msg: str = "ok", extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Emit a lightweight heartbeat with optional counters for live monitoring.
    """
    evt: Dict[str, Any] = {"type": "heartbeat", "pid": pid, "msg": msg}
    if extra:
        evt.update(extra)
    write_jsonl("process.jsonl", evt)


def mirror_stdout_line(line: str) -> None:
    """Append a single line to stdout.log for watcher compatibility.

    This mirrors human-readable console lines into data/logs/stdout.log while keeping
    JSONL files for structured processing. Safe no-op on errors.
    """
    try:
        path = _log_path("stdout.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write((line or "").rstrip("\n") + "\n")
    except Exception:
        pass


