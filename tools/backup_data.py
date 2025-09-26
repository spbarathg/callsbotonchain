import os
import shutil
import sqlite3
import csv
from datetime import datetime, timezone


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def copy_file(src: str, dst: str) -> bool:
    try:
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            return True
    except Exception:
        pass
    return False


def export_db_csv(db_path: str, out_csv: str) -> None:
    # Allow running as a script by fixing sys.path
    import sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from tools.export_stats import export_db_summary
    export_db_summary(db_path, out_csv)


def export_jsonl_to_csv(jsonl_path: str, out_csv: str) -> bool:
    try:
        import sys
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from tools.export_stats import export_jsonl
        export_jsonl(jsonl_path, out_csv)
        return True
    except Exception:
        return False


def main() -> None:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    os.chdir(project_root)

    # Inputs/outputs
    db_path = os.getenv("CALLSBOT_DB_FILE", os.path.join("var", "alerted_tokens.db"))
    # Align default with app.logger_utils which defaults to data/logs
    log_dir = os.getenv("CALLSBOT_LOG_DIR", os.path.join("data", "logs"))

    ts = utc_ts()
    base_dir = os.path.join("data", "backups", ts)
    ensure_dir(base_dir)

    # 1) Copy raw state
    copied_db = copy_file(db_path, os.path.join(base_dir, os.path.basename(db_path)))
    copy_file(os.path.join("var", "relay_user.session"), os.path.join(base_dir, "relay_user.session"))
    # Logs
    copy_file(os.path.join(log_dir, "alerts.jsonl"), os.path.join(base_dir, "alerts.jsonl"))
    copy_file(os.path.join(log_dir, "tracking.jsonl"), os.path.join(base_dir, "tracking.jsonl"))
    copy_file(os.path.join(log_dir, "stdout.log"), os.path.join(base_dir, "stdout.log"))

    # 2) Structured exports
    if copied_db:
        ensure_dir(os.path.join(base_dir, "exports"))
        export_db_csv(db_path, os.path.join(base_dir, "exports", f"db_{ts}.csv"))
    # Export alerts/tracking CSVs if logs present
    export_jsonl_to_csv(os.path.join(log_dir, "alerts.jsonl"), os.path.join(base_dir, "exports", f"alerts_{ts}.csv"))
    export_jsonl_to_csv(os.path.join(log_dir, "tracking.jsonl"), os.path.join(base_dir, "exports", f"tracking_{ts}.csv"))

    # 3) Summary file
    summary_path = os.path.join(base_dir, "SUMMARY.txt")
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Backup at {ts} UTC\n")
            f.write(f"DB: {db_path} -> {'ok' if copied_db else 'missing'}\n")
            f.write(f"Logs dir: {log_dir}\n")
    except Exception:
        pass

    print(f"✅ Backup completed: {base_dir}")


if __name__ == "__main__":
    main()


