import os
import pathlib
import json
import time
import sys

# Ensure project root is importable when running this script directly
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main() -> None:
    # Configure admin key for this process
    os.environ["CALLSBOT_SQL_KEY"] = os.environ.get("CALLSBOT_SQL_KEY", "secret123")

    from src.server import create_app

    app = create_app()
    client = app.test_client()

    # 1) toggles without header -> 403
    r1 = client.post("/api/toggles", json={"signals_enabled": True})
    print("toggles no hdr:", r1.status_code, r1.json)

    # 2) toggles wrong header -> 403
    r2 = client.post(
        "/api/toggles",
        headers={"X-Callsbot-Admin-Key": "wrong"},
        json={"signals_enabled": False},
    )
    print("toggles wrong hdr:", r2.status_code, r2.json)

    # 3) toggles correct header -> 200 and audited
    correct_key = os.environ.get("CALLSBOT_SQL_KEY", "")
    r3 = client.post(
        "/api/toggles",
        headers={"X-Callsbot-Admin-Key": correct_key},
        json={"signals_enabled": True, "trading_enabled": False},
    )
    print("toggles ok:", r3.status_code, r3.json)

    # 4) sql without header -> 403
    r4 = client.post("/api/sql", json={"query": "SELECT 1"})
    print("sql no hdr:", r4.status_code, r4.json)

    # 5) sql wrong header -> 403
    r5 = client.post(
        "/api/sql",
        headers={"X-Callsbot-Admin-Key": "wrong"},
        json={"query": "SELECT 1"},
    )
    print("sql wrong hdr:", r5.status_code, r5.json)

    # 6) sql with header (readonly ok) -> 200
    r6 = client.post(
        "/api/sql",
        headers={"X-Callsbot-Admin-Key": correct_key},
        json={"query": "SELECT 1 AS one"},
    )
    print("sql ok:", r6.status_code, r6.json)

    # 7) sql forbidden write op -> 403
    r7 = client.post(
        "/api/sql",
        headers={"X-Callsbot-Admin-Key": correct_key},
        json={"query": "INSERT INTO x VALUES (1)"},
    )
    print("sql write:", r7.status_code, r7.json)

    # 8) metrics reachable locally on localhost-only bind
    metrics_status = None
    metrics_len = None
    try:
        from prometheus_client import start_http_server
        start_http_server(port=9123, addr="127.0.0.1")
        import requests
        time.sleep(0.2)
        mr = requests.get("http://127.0.0.1:9123/metrics", timeout=2)
        metrics_status = mr.status_code
        metrics_len = len(mr.text or "")
    except Exception as e:
        print("metrics local error:", str(e))
    print("metrics local:", metrics_status, metrics_len)

    # 9) admin audit log tail
    try:
        audit_path = pathlib.Path("data/logs/admin_audit.jsonl")
        if audit_path.exists():
            tail = audit_path.read_text(encoding="utf-8").splitlines()[-3:]
            print("audit tail:\n" + "\n".join(tail))
        else:
            print("audit file missing")
    except Exception as e:
        print("audit read failed:", str(e))

    # 10) verify secret redaction
    try:
        from app.logger_utils import write_jsonl
        write_jsonl(
            "process.jsonl",
            {
                "event": "test_redact",
                "Authorization": "Bearer topsecret",
                "headers": {"X-API-Key": "abc12345", "X-Callsbot-Admin-Key": correct_key},
            },
        )
    except Exception as e:
        print("redaction write failed:", str(e))
    try:
        proc_path = pathlib.Path("data/logs/process.jsonl")
        tail = proc_path.read_text(encoding="utf-8").splitlines()[-2:]
        print("process tail:\n" + "\n".join(tail))
    except Exception as e:
        print("process read failed:", str(e))


if __name__ == "__main__":
    main()


