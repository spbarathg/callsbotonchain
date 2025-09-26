import os
import re
from pathlib import Path

# Import the project notifier
try:
    from app.notify import send_telegram_alert
except Exception:  # pragma: no cover - cron-only path
    def send_telegram_alert(msg: str):
        print(msg)
        return True


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = PROJECT_ROOT / "logs"
VAR_DIR = PROJECT_ROOT / "var"
ENV_FILE = PROJECT_ROOT / ".env"
STATE_FILE = VAR_DIR / "summary_state.txt"


def _read_env_threshold(default_threshold: int = 6) -> int:
    try:
        text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return default_threshold

    for line in text.splitlines():
        if line.strip().startswith("HIGH_CONFIDENCE_SCORE="):
            try:
                return int(line.split("=", 1)[1].strip())
            except Exception:
                return default_threshold
    return default_threshold


def _count_passed_initial(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    needle = "FETCHING DETAILED STATS"
    count = 0
    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if needle in line:
                count += 1
    return count


def _count_blocked(log_path: Path, threshold: int) -> int:
    if not log_path.exists():
        return 0
    # Matches e.g. "FINAL: 7/10" and captures 7
    pattern = re.compile(r"FINAL:\s*(\d+)/10")
    blocked = 0
    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                try:
                    score = int(m.group(1))
                except Exception:
                    continue
                if score < threshold:
                    blocked += 1
    return blocked


def _count_alerts(alerts_path: Path) -> int:
    if not alerts_path.exists():
        return 0
    count = 0
    with alerts_path.open("r", encoding="utf-8", errors="ignore") as f:
        for _ in f:
            count += 1
    return count


def _read_prev_state(state_file: Path) -> tuple[int, int, int]:
    try:
        text = state_file.read_text(encoding="utf-8").strip()
        p, b, s = text.split()
        return int(p), int(b), int(s)
    except Exception:
        return 0, 0, 0


def _write_state(state_file: Path, p: int, b: int, s: int) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(f"{p} {b} {s}", encoding="utf-8")


def build_message(delta_passed: int, delta_blocked: int, delta_sent: int,
                  total_passed: int, total_blocked: int, total_sent: int) -> str:
    lines = [
        "⏱️ Signals (last 1 min)",
        f"🟢 Passed initial filter: {delta_passed}",
        f"🚫 Blocked after scoring: {delta_blocked}",
        f"📣 Alerts sent: {delta_sent}",
        "",
        "Totals",
        f"🟢 Passed: {total_passed}",
        f"🚫 Blocked: {total_blocked}",
        f"📣 Alerts: {total_sent}",
    ]
    return "\n".join(lines)


def main() -> int:
    threshold = _read_env_threshold(6)
    stdout_log = LOGS_DIR / "stdout.log"
    alerts_log = LOGS_DIR / "alerts.jsonl"

    total_passed = _count_passed_initial(stdout_log)
    total_blocked = _count_blocked(stdout_log, threshold)
    total_sent = _count_alerts(alerts_log)

    prev_passed, prev_blocked, prev_sent = _read_prev_state(STATE_FILE)

    delta_passed = max(total_passed - prev_passed, 0)
    delta_blocked = max(total_blocked - prev_blocked, 0)
    delta_sent = max(total_sent - prev_sent, 0)

    _write_state(STATE_FILE, total_passed, total_blocked, total_sent)

    message = build_message(
        delta_passed, delta_blocked, delta_sent,
        total_passed, total_blocked, total_sent,
    )

    try:
        send_telegram_alert(message)
    except Exception:
        # Fail silently under cron; still exit 0 so cron doesn't spam mail
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


