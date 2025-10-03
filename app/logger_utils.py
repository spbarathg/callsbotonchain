import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from hashlib import sha256
import urllib.request
import urllib.error
from threading import Lock


# Persist logs locally under data/logs by default (never committed)
LOG_DIR = os.getenv("CALLSBOT_LOG_DIR", os.path.join("data", "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

# Optional: mirror JSON logs to stdout for containers/process supervisors
LOG_STDOUT = (os.getenv("CALLSBOT_LOG_STDOUT", "false").strip().lower() == "true")

_log_lock = Lock()


def _log_path(name: str) -> str:
    return os.path.join(LOG_DIR, name)


def mask_secret(value: Optional[str], *, show: int = 4) -> str:
    """Return a masked representation of a secret with an optional fingerprint.

    Example: abcdefgh -> ****f3a1 (keeps last N and adds sha256 tail)
    """
    try:
        s = str(value or "")
        if not s:
            return ""
        tail = s[-max(0, int(show)):] if show > 0 else ""
        fp = sha256(s.encode("utf-8")).hexdigest()[:4]
        return ("*" * max(4, len(s) - len(tail))) + tail + ":" + fp
    except Exception:
        return "***"


def _sanitize_obj(obj: Any) -> Any:
    """Deep-copy sanitize of objects for logging: redact sensitive keys and headers.
    - Redacts auth/secret material but PRESERVES on-chain token addresses.
    - Redacted keys (case-insensitive): authorization, x-api-key, x-callsbot-admin-key,
      api_key, apikey, password, secret, and any key that ends with "_token" EXCEPT
      plain "token" and "token_address" which are legitimate data fields for the app.
    - Applies recursively to dicts/lists
    """
    try:
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                lk = str(k).lower()
                # Determine if key should be redacted
                redact = False
                if lk in ("authorization", "x-api-key", "x-callsbot-admin-key", "api_key", "apikey", "password", "secret"):
                    redact = True
                if ("authorization" in lk) or ("api-key" in lk) or ("admin-key" in lk):
                    redact = True
                # Generic *_token secrets, but do NOT redact plain 'token' fields or 'token_address'
                if (lk.endswith("_token") or lk.endswith("-token")) and lk not in ("token", "token_address"):
                    redact = True
                if redact:
                    out[k] = mask_secret(str(v) if v is not None else "")
                else:
                    out[k] = _sanitize_obj(v)
            return out
        if isinstance(obj, list):
            return [_sanitize_obj(x) for x in obj]
        return obj
    except Exception:
        return "<sanitization_error>"


def write_jsonl(filename: str, record: Dict[str, Any]) -> None:
    path = _log_path(filename)
    rec = dict(record)
    # Inject defaults for structured logs
    rec.setdefault("level", "info")
    rec.setdefault("component", filename.replace(".jsonl", ""))
    record = _sanitize_obj(rec)
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


def alert_critical(message: str) -> None:
    """Best-effort critical alert via webhook if configured.
    Supports Slack-compatible webhook in env CALLSBOT_SLACK_WEBHOOK.
    """
    url = os.getenv("CALLSBOT_SLACK_WEBHOOK")
    if not url:
        return
    try:
        payload = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
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


