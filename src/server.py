import os
import json
from datetime import datetime
from typing import Dict, Any, List
import sqlite3

from flask import Flask, jsonify, render_template, request
try:
    from flask_limiter import Limiter  # type: ignore
    from flask_limiter.util import get_remote_address  # type: ignore
except Exception:
    Limiter = None  # type: ignore

    def get_remote_address():  # type: ignore
        return ""
from app.logger_utils import write_jsonl
from app.secrets import hmac_sign
from hashlib import sha256

try:
    from src.risk.treasury import get_snapshot as get_treasury_snapshot
except Exception:
    class _TreasuryDummy:
        bankroll_usd = 0.0
        reserve_usd = 0.0
        
        def total(self) -> float:
            return 0.0

    def get_treasury_snapshot() -> '_TreasuryDummy':  # type: ignore
        return _TreasuryDummy()

from flask import Response
try:
    from src.api_enhanced import (
        get_smart_money_status,
        get_feed_health,
        get_budget_status,
        get_recent_activity,
        get_quick_stats,
        get_signal_quality,
        get_gate_performance,
        get_performance_trends,
        get_hourly_heatmap,
    )
    from src.api_system import (
        get_system_health,
        get_database_status,
        get_error_logs,
        get_lifecycle_tracking,
        get_current_config,
        update_toggle as _update_toggle_v2,
    )
    from src.paper_trading import get_paper_trading_engine
except Exception:
    # Soft-fallbacks if new modules are not present
    def get_smart_money_status():
        return {"status": "unavailable"}
    def get_feed_health():
        return {"status": "unavailable"}
    def get_budget_status():
        return {"status": "unavailable"}
    def get_recent_activity(limit: int = 20):
        return {"alerts": [], "count": 0}
    def get_quick_stats():
        return {}
    def get_signal_quality():
        return {}
    def get_gate_performance():
        return {}
    def get_performance_trends(days: int = 7):
        return {"trends": [], "days": days}
    def get_hourly_heatmap():
        return {"heatmap": [], "peak_hour": None, "peak_count": 0}
    def get_system_health():
        return {"error": "unavailable"}
    def get_database_status():
        return {"error": "unavailable"}
    def get_error_logs(limit: int = 50, level: str = "all"):
        return {"logs": [], "counts": {"error": 0, "warning": 0, "info": 0}}
    def get_lifecycle_tracking():
        return {"total_tracking": 0, "stages": {}, "movement": {}}
    def get_current_config():
        return {}
    def _update_toggle_v2(toggle_name: str, value: bool):
        return {"success": False, "error": "unavailable"}
    def get_paper_trading_engine():
        class _Dummy:  # type: ignore
            def start_session(self, *a, **k):
                return {"success": False, "error": "unavailable"}
            def stop_session(self):
                return {"success": False, "error": "unavailable"}
            def reset_session(self):
                return {"success": False, "error": "unavailable"}
            def get_portfolio_summary(self):
                return None
            def update_positions(self):
                return {"success": True}
            def run_backtest(self, *a, **k):
                return {"success": False, "error": "unavailable"}
        return _Dummy()
import time
from app.toggles import get_toggles, set_toggles
import socket
import math


def _read_jsonl(path: str, limit: int = 500) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        if limit > 0:
            records = records[-limit:]
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return records


def _coerce_ts(s: Any) -> float:
    try:
        if isinstance(s, (int, float)):
            return float(s)
        # Expect ISO timestamp
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _sanitize_json(obj: Any) -> Any:
    """Recursively convert NaN/Infinity to None so JSON is standard-compliant.
    This prevents client JSON.parse errors and keeps UI rendering reliable.
    """
    try:
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {k: _sanitize_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ _sanitize_json(v) for v in obj ]
        return obj
    except Exception:
        return obj


def _finite(value: Any) -> Any:
    """Return None for non-finite numerics (NaN/Inf), otherwise return the value unchanged."""
    try:
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
        return value
    except Exception:
        return value


def _sanitize_alert_row(alert: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(alert, dict):
        return alert  # type: ignore
    # Ensure alert rows have finite numeric values for UI rendering
    try:
        row = dict(alert)
        for k in (
            "market_cap",
            "liquidity",
            "volume_24h",
            "price",
            "change_1h",
            "change_24h",
        ):
            if k in row:
                row[k] = _finite(row.get(k))
        return row
    except Exception:
        return alert  # type: ignore


def _safe_json_dumps(obj: Any) -> str:
    """Serialize to JSON ensuring there are no NaN/Infinity values.
    Tries strict dumps; if it fails, falls back to aggressive sanitation and string replacement.
    """
    try:
        return json.dumps(_sanitize_json(obj), allow_nan=False)
    except Exception:
        try:
            s = json.dumps(_sanitize_json(obj))
        except Exception:
            s = json.dumps(obj, default=lambda _o: None)
        # Last-resort cleanup for any remaining NaN/Infinity sequences
        for bad in ("NaN", "Infinity", "-Infinity"):
            s = s.replace(bad, "null")
        return s


def _pick_signals_db_path(preferred_path: str) -> str:
    """Return a good signals DB path by checking candidates.

    Heuristic:
    - Prefer the database with the HIGHEST alerted_tokens row count
    - Break ties by most recent mtime
    - Always include the env-provided preferred_path first
    """
    candidates = [
        preferred_path,
        "/app/state/alerted_tokens.db",
        "/app/var/alerted_tokens.db",
        os.path.join("var", "alerted_tokens.db"),
    ]
    best_path = preferred_path
    best_mtime = -1.0
    best_count = -1
    for p in candidates:
        try:
            st = os.stat(p)
            mtime = float(getattr(st, "st_mtime", 0.0) or 0.0)
        except Exception:
            mtime = -1.0
        count = -1
        try:
            con = sqlite3.connect(p, timeout=2)
            cur = con.cursor()
            cur.execute("SELECT COUNT(1) FROM alerted_tokens")
            count = int(cur.fetchone()[0])
            cur.close(); con.close()
        except Exception:
            pass
        # Prefer highest row count; break ties by newer mtime
        more_rows = count > best_count
        newer_tie = (count == best_count) and (mtime > best_mtime)
        if more_rows or newer_tie:
            best_path = p; best_mtime = mtime; best_count = count
    return best_path


def _window_to_sqlite_clause(window: str) -> str:
    """Return a SQLite datetime WHERE clause for first_alert_at based on a simple window string.
    Examples: '90m', '2h', '1d'. Defaults to 3 hours if unparsable.
    """
    try:
        w = (window or "").strip().lower()
        if w.endswith("m"):
            n = int(w[:-1] or "0")
            return f"first_alert_at >= datetime('now','-{n} minute')"
        if w.endswith("h"):
            n = int(w[:-1] or "0")
            return f"first_alert_at >= datetime('now','-{n} hour')"
        if w.endswith("d"):
            n = int(w[:-1] or "0")
            return f"first_alert_at >= datetime('now','-{n} day')"
    except Exception:
        pass
    return "first_alert_at >= datetime('now','-3 hour')"


def _paper_metrics(db_path: str, *, window: str, stop_pct: float, trail_retention: float,
                   cap_multiple: float, strict_only: bool = True,
                   max_mcap_usd: float | None = None) -> Dict[str, Any]:
    """Compute paper-trading expectancy using a simple trailing/stop model over a window.
    Model: ret = min(cap_multiple, trail_retention * peak/first) - 1; ret floored at -stop_pct.
    Filters: optional strict_only via conviction_type; optional max_mcap_usd via first_market_cap_usd when available.
    """
    out: Dict[str, Any] = {}
    where = _window_to_sqlite_clause(window)
    try:
        con = sqlite3.connect(db_path, timeout=10)
        cur = con.cursor()
        # Build base selection with optional joins/filters
        sel = [
            "SELECT",
            "  t.conviction_type AS conv,",
            "  s.first_price_usd AS f,",
            "  s.peak_price_usd AS p,",
            "  s.first_market_cap_usd AS fmcap",
            "FROM alerted_token_stats s",
            "LEFT JOIN alerted_tokens t ON t.token_address = s.token_address",
            f"WHERE {where} AND s.first_price_usd > 0",
        ]
        if strict_only:
            sel.append("AND (t.conviction_type LIKE 'High Confidence (Strict)%')")
        if max_mcap_usd is not None:
            sel.append("AND (s.first_market_cap_usd IS NULL OR s.first_market_cap_usd <= ?)")
        query = "\n".join(sel)
        params: tuple[Any, ...] = (max_mcap_usd,) if max_mcap_usd is not None else tuple()
        cur.execute(query, params)
        rows = cur.fetchall() or []
        n = 0
        wins = 0
        sum_ret = 0.0
        win_sum = 0.0
        loss_sum = 0.0
        for _conv, f, p, _fmcap in rows:
            try:
                f_val = float(f or 0)
                p_val = float(p or 0)
                if f_val <= 0:
                    continue
                # Trailing realization from peak
                mul_trail = trail_retention * (p_val / f_val) if p_val > 0 else 1.0
                eff_mul = min(max(mul_trail, 0.0), float(cap_multiple))
                ret = eff_mul - 1.0
                if ret < -float(stop_pct):
                    ret = -float(stop_pct)
                n += 1
                sum_ret += ret
                if ret >= 0:
                    wins += 1
                    win_sum += ret
                else:
                    loss_sum += abs(ret)
            except Exception:
                continue
        out["n"] = n
        out["win_rate"] = (float(wins) / float(n)) if n else None
        out["avg_ret"] = (sum_ret / float(n)) if n else None
        out["avg_win"] = (win_sum / float(wins)) if wins else None
        losses = n - wins
        out["avg_loss"] = (loss_sum / float(losses)) if losses > 0 else None
        con.close()
    except Exception as e:
        out = {"error": str(e)}
    return out


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    # Optional rate limiting for admin endpoints
    limiter = None
    try:
        if os.getenv("CALLSBOT_RATE_LIMIT_ENABLED", "true").strip().lower() == "true" and Limiter is not None:
            limiter = Limiter(get_remote_address, app=app, default_limits=[])
    except Exception:
        limiter = None
    # Security: enforce secure cookies and SameSite
    try:
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    except Exception:
        pass
    
    # Basic Authentication
    def check_auth(username: str, password: str) -> bool:
        """Check if username/password combination is valid."""
        expected_user = os.getenv("DASHBOARD_USERNAME", "admin")
        expected_pass = os.getenv("DASHBOARD_PASSWORD", "")
        # If no password is set, disable authentication
        if not expected_pass:
            return True
        return username == expected_user and password == expected_pass
    
    def authenticate():
        """Send 401 response that enables basic auth."""
        return Response(
            'Authentication required. Please login.',
            401,
            {'WWW-Authenticate': 'Basic realm="CallsBot Dashboard"'}
        )
    
    def requires_auth(f):  # type: ignore
        """Decorator to require authentication for routes."""
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):  # type: ignore
            # Skip auth if disabled
            if os.getenv("DASHBOARD_AUTH_ENABLED", "true").strip().lower() != "true":
                return f(*args, **kwargs)
            
            auth = request.authorization
            if not auth or not check_auth(auth.username, auth.password):
                return authenticate()
            return f(*args, **kwargs)
        return decorated
    
    def _no_cache(resp):  # type: ignore
        try:
            resp.headers["Cache-Control"] = "no-store, max-age=0"
        except Exception as e:
            try:
                print(f"_no_cache: failed to set headers: {e}")
            except Exception:
                pass
        return resp

    log_dir = os.getenv("CALLSBOT_LOG_DIR", os.path.join("data", "logs"))
    alerts_path = os.path.join(log_dir, "alerts.jsonl")
    process_path = os.path.join(log_dir, "process.jsonl")
    tracking_path = os.path.join(log_dir, "tracking.jsonl")
    default_db = os.getenv("CALLSBOT_DB_FILE", os.path.join("var", "alerted_tokens.db"))
    trading_db = os.getenv("TS_DB_PATH", os.path.join("var", "trading.db"))

    @app.get("/api/stats")
    def api_stats():
        alerts = _read_jsonl(alerts_path, limit=500)
        process = _read_jsonl(process_path, limit=1000)
        tracking = _read_jsonl(tracking_path, limit=500)

        # Totals
        # Keep both: log_count (from alerts.jsonl slice) and db_count (from signals_summary)
        total_alerts = len(alerts)
        last_alert = _sanitize_alert_row(alerts[-1]) if alerts else None
        last_heartbeat = None
        cooldowns: int = 0
        for rec in process:
            if rec.get("type") == "heartbeat":
                last_heartbeat = rec
            if rec.get("type") == "cooldown":
                cooldowns += 1

        # Treasury snapshot
        try:
            treas = get_treasury_snapshot()
            treasury = {"bankroll_usd": treas.bankroll_usd, "reserve_usd": treas.reserve_usd, "total_usd": treas.total()}
        except Exception as e:
            try:
                print(f"api_stats: treasury snapshot error: {e}")
            except Exception:
                pass
            treasury = {"bankroll_usd": 0.0, "reserve_usd": 0.0, "total_usd": 0.0}

        # Last N alerts short view
        recent_alerts = [
            {
                "token": a.get("token"),
                "symbol": a.get("symbol"),
                "score": a.get("final_score"),
                "conviction": a.get("conviction_type"),
                "market_cap": _finite(a.get("market_cap")),
                "liquidity": _finite(a.get("liquidity")),
                "vol24": _finite(a.get("volume_24h")),
                "ts": a.get("ts"),
            }
            for a in alerts[-20:]
        ][::-1]

        # Tracking summary (last values per token)
        last_tracking: Dict[str, Dict[str, Any]] = {}
        for t in tracking:
            tok = t.get("token")
            if not tok:
                continue
            prev = last_tracking.get(tok)
            if not prev or _coerce_ts(t.get("ts")) > _coerce_ts(prev.get("ts")):
                last_tracking[tok] = t

        toggles = get_toggles()
        # Choose best available signals DB (env, state, var) based on row counts
        signals_db = _pick_signals_db_path(default_db)

        # Derived summaries
        signals_summary = _signals_metrics(signals_db)
        trading_summary = _trading_metrics(trading_db)
        gates_summary = _gates_summary(alerts_path)
        # Lightweight API error-rate from recent process logs
        
        def _api_error_pct(proc_rows: List[Dict[str, Any]]) -> float | None:
            try:
                window = proc_rows[-500:] if len(proc_rows) > 500 else proc_rows
                err_types = {
                    "token_stats_error",
                    "token_stats_unavailable",
                    "token_stats_rate_limited",
                    "token_stats_denied_variants",
                }
                count_err = sum(1 for r in window if (r.get("type") in err_types))
                # Treat not_found as a non-error attempt
                count_total = sum(1 for r in window if str(r.get("type", "")).startswith("token_stats_"))
                if count_total <= 0:
                    return None
                return round((100.0 * float(count_err) / float(count_total)), 1)
            except Exception:
                return None

        # Simple cache hit% derived from process logs (hits / (hits+misses))
        def _cache_hit_pct(proc_rows: List[Dict[str, Any]]) -> float | None:
            try:
                window = proc_rows[-1000:] if len(proc_rows) > 1000 else proc_rows
                hits = sum(1 for r in window if r.get("type") == "stats_cache_hit")
                misses = sum(1 for r in window if r.get("type") == "stats_cache_miss")
                total = hits + misses
                if total <= 0:
                    return None
                return round(100.0 * float(hits) / float(total), 1)
            except Exception:
                return None

        metrics = {
            "api_error_pct": _api_error_pct(process),
            "cache_hit_pct": _cache_hit_pct(process),
        }

        data = {
            "total_alerts": (signals_summary.get("total_alerts") if isinstance(signals_summary, dict) and signals_summary.get("total_alerts") is not None else total_alerts),
            "log_alerts_count": total_alerts,
            "cooldowns": cooldowns,
            "last_alert": last_alert,
            "last_heartbeat": last_heartbeat,
            "treasury": treasury,
            "recent_alerts": recent_alerts,
            "tracking_count": len(last_tracking),
            "toggles": toggles,
            "signals_summary": signals_summary,
            "trading_summary": trading_summary,
            "gates_summary": gates_summary,
            "kill_switch": bool(os.getenv("KILL_SWITCH", "false").strip().lower() == "true"),
            "metrics": metrics,
        }
        return _no_cache(jsonify(_sanitize_json(data)))

    # ---------------- v2 Enhanced API (read-only) ----------------
    @app.get("/api/v2/smart-money-status")
    def api_v2_smart_money_status():
        return _no_cache(jsonify(_sanitize_json(get_smart_money_status())))

    @app.get("/api/v2/feed-health")
    def api_v2_feed_health():
        return _no_cache(jsonify(_sanitize_json(get_feed_health())))

    @app.get("/api/v2/budget-status")
    def api_v2_budget_status():
        return _no_cache(jsonify(_sanitize_json(get_budget_status())))

    @app.get("/api/v2/recent-activity")
    def api_v2_recent_activity():
        try:
            limit = int(request.args.get("limit") or 20)
        except Exception:
            limit = 20
        return _no_cache(jsonify(_sanitize_json(get_recent_activity(limit=limit))))

    @app.get("/api/v2/quick-stats")
    def api_v2_quick_stats():
        return _no_cache(jsonify(_sanitize_json(get_quick_stats())))

    # Performance
    @app.get("/api/v2/signal-quality")
    def api_v2_signal_quality():
        return _no_cache(jsonify(_sanitize_json(get_signal_quality())))

    @app.get("/api/v2/gate-performance")
    def api_v2_gate_performance():
        return _no_cache(jsonify(_sanitize_json(get_gate_performance())))

    @app.get("/api/v2/performance-trends")
    def api_v2_performance_trends():
        try:
            days = int(request.args.get("days") or 7)
        except Exception:
            days = 7
        return _no_cache(jsonify(_sanitize_json(get_performance_trends(days=days))))

    @app.get("/api/v2/hourly-heatmap")
    def api_v2_hourly_heatmap():
        return _no_cache(jsonify(_sanitize_json(get_hourly_heatmap())))

    # System
    @app.get("/api/v2/system-health")
    def api_v2_system_health():
        return _no_cache(jsonify(_sanitize_json(get_system_health())))

    @app.get("/api/v2/database-status")
    def api_v2_database_status():
        return _no_cache(jsonify(_sanitize_json(get_database_status())))

    @app.get("/api/v2/error-logs")
    def api_v2_error_logs():
        try:
            limit = int(request.args.get("limit") or 50)
        except Exception:
            limit = 50
        level = (request.args.get("level") or "all").lower()
        return _no_cache(jsonify(_sanitize_json(get_error_logs(limit=limit, level=level))))

    @app.get("/api/v2/lifecycle-tracking")
    def api_v2_lifecycle_tracking():
        return _no_cache(jsonify(_sanitize_json(get_lifecycle_tracking())))

    @app.get("/api/v2/current-config")
    def api_v2_current_config():
        return _no_cache(jsonify(_sanitize_json(get_current_config())))

    @app.post("/api/v2/update-toggle")
    def api_v2_update_toggle():
        body = request.get_json(force=True, silent=True) or {}
        name = str(body.get("name") or "").strip()
        val = bool(body.get("value"))
        if not name:
            return jsonify({"success": False, "error": "name required"}), 400
        return _no_cache(jsonify(_sanitize_json(_update_toggle_v2(name, val))))

    # Paper trading
    @app.post("/api/v2/paper/start")
    def api_v2_paper_start():
        body = request.get_json(force=True, silent=True) or {}
        capital = float(body.get("capital") or 1000.0)
        strategy = str(body.get("strategy") or "smart_money_only")
        sizing = str(body.get("position_sizing") or "fixed_50")
        max_conc = int(body.get("max_concurrent") or 5)
        eng = get_paper_trading_engine()
        return _no_cache(jsonify(_sanitize_json(eng.start_session(capital, strategy, sizing, max_conc))))

    @app.post("/api/v2/paper/stop")
    def api_v2_paper_stop():
        eng = get_paper_trading_engine()
        return _no_cache(jsonify(_sanitize_json(eng.stop_session())))

    @app.post("/api/v2/paper/reset")
    def api_v2_paper_reset():
        eng = get_paper_trading_engine()
        return _no_cache(jsonify(_sanitize_json(eng.reset_session())))

    @app.get("/api/v2/paper/portfolio")
    def api_v2_paper_portfolio():
        eng = get_paper_trading_engine()
        # update positions before returning
        try:
            eng.update_positions()
        except Exception:
            pass
        return _no_cache(jsonify(_sanitize_json({"portfolio": eng.get_portfolio_summary()})))

    @app.post("/api/v2/paper/backtest")
    def api_v2_paper_backtest():
        body = request.get_json(force=True, silent=True) or {}
        days = int(body.get("days") or 7)
        capital = float(body.get("capital") or 1000.0)
        strategy = str(body.get("strategy") or "smart_money_only")
        eng = get_paper_trading_engine()
        return _no_cache(jsonify(_sanitize_json(eng.run_backtest(days, capital, strategy))))

    @app.get("/healthz")
    def healthz():
        ok = True
        checks: Dict[str, Any] = {}
        # DB check (signals DB read-only)
        try:
            signals_db = _pick_signals_db_path(default_db)
            ro_uri = f"file:{signals_db}?mode=ro"
            con = sqlite3.connect(ro_uri, timeout=2, uri=True)
            cur = con.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close(); con.close()
            checks["db"] = {"ok": True, "path": signals_db}
        except Exception as e:
            ok = False
            checks["db"] = {"ok": False, "error": str(e)}
        # Redis check (optional)
        try:
            redis_url = os.getenv("REDIS_URL") or os.getenv("CALLSBOT_REDIS_URL")
            if redis_url:
                try:
                    import redis  # type: ignore
                    r = redis.from_url(redis_url, decode_responses=False)
                    r.ping()
                    checks["redis"] = {"ok": True}
                except Exception as e:
                    ok = False
                    checks["redis"] = {"ok": False, "error": str(e)}
            else:
                checks["redis"] = {"ok": True, "skipped": True}
        except Exception:
            checks["redis"] = {"ok": True, "skipped": True}
        # Last heartbeat recency
        try:
            process = _read_jsonl(process_path, limit=200)
            last_hb = None
            for rec in reversed(process):
                if rec.get("type") == "heartbeat":
                    last_hb = rec; break
            checks["heartbeat"] = {"ok": bool(last_hb), "last": last_hb}
        except Exception:
            checks["heartbeat"] = {"ok": False}
        status = 200 if ok else 503
        return jsonify({"ok": ok, "hostname": socket.gethostname(), "checks": checks}), status

    @app.get("/api/stream")
    def api_stream():
        def _gen():
            while True:
                try:
                    alerts = _read_jsonl(alerts_path, limit=500)
                    process = _read_jsonl(process_path, limit=1000)
                    tracking = _read_jsonl(tracking_path, limit=500)

                    total_alerts = len(alerts)
                    last_alert = _sanitize_alert_row(alerts[-1]) if alerts else None
                    last_heartbeat = None
                    cooldowns: int = 0
                    for rec in process:
                        if rec.get("type") == "heartbeat":
                            last_heartbeat = rec
                        if rec.get("type") == "cooldown":
                            cooldowns += 1

                    recent_alerts = [
                        {
                            "token": a.get("token"),
                            "symbol": (a.get("symbol") or a.get("name") or None),
                            "score": a.get("final_score"),
                            "conviction": a.get("conviction_type"),
                            "market_cap": _finite(a.get("market_cap")),
                            "liquidity": _finite(a.get("liquidity")),
                            "vol24": _finite(a.get("volume_24h")),
                            "ts": a.get("ts"),
                        }
                        for a in alerts[-20:]
                    ][::-1]

                    last_tracking: Dict[str, Dict[str, Any]] = {}
                    for t in tracking:
                        tok = t.get("token")
                        if not tok:
                            continue
                        prev = last_tracking.get(tok)
                        if not prev or _coerce_ts(t.get("ts")) > _coerce_ts(prev.get("ts")):
                            last_tracking[tok] = t

                    toggles = get_toggles()
                    signals_db = _pick_signals_db_path(default_db)
                    signals_summary = _signals_metrics(signals_db)
                    trading_summary = _trading_metrics(trading_db)
                    gates_summary = _gates_summary(alerts_path)
                    # Rolling API error-rate as part of stream payload
                    
                    def _api_error_pct_stream(proc_rows: List[Dict[str, Any]]) -> float | None:
                        try:
                            window = proc_rows[-500:] if len(proc_rows) > 500 else proc_rows
                            err_types = {
                                "token_stats_error",
                                "token_stats_unavailable",
                                "token_stats_rate_limited",
                                "token_stats_denied_variants",
                            }
                            count_err = sum(1 for r in window if (r.get("type") in err_types))
                            count_total = sum(1 for r in window if str(r.get("type", "")).startswith("token_stats_"))
                            if count_total <= 0:
                                return None
                            return round((100.0 * float(count_err) / float(count_total)), 1)
                        except Exception:
                            return None

                    payload = {
                        "total_alerts": total_alerts,
                        "cooldowns": cooldowns,
                        "last_alert": last_alert,
                        "last_heartbeat": last_heartbeat,
                        "recent_alerts": recent_alerts,
                        "tracking_count": len(last_tracking),
                        "toggles": toggles,
                        "signals_summary": signals_summary,
                        "trading_summary": trading_summary,
                        "gates_summary": gates_summary,
                        "metrics": {"api_error_pct": _api_error_pct_stream(process)},
                    }
                    yield f"data: {_safe_json_dumps(payload)}\n\n"
                except Exception as e:
                    # keep the stream alive even if an iteration fails
                    try:
                        print(f"api_stream: iteration error: {e}")
                    except Exception:
                        pass
                    yield "event: ping\ndata: {}\n\n"
                time.sleep(2)

        resp = Response(_gen(), mimetype="text/event-stream")
        try:
            resp.headers["Cache-Control"] = "no-store, no-transform"
            resp.headers["Connection"] = "keep-alive"
            resp.headers["X-Accel-Buffering"] = "no"
            resp.headers["Content-Type"] = "text/event-stream; charset=utf-8"
        except Exception as e:
            try:
                print(f"api_stream: failed to set headers: {e}")
            except Exception:
                pass
        return resp

    @app.get("/api/logs")
    def api_logs():
        try:
            log_type = (request.args.get("type") or "combined").lower()
            limit = int(request.args.get("limit") or 300)
        except Exception as e:
            try:
                print(f"api_logs: bad request args: {e}")
            except Exception:
                pass
            log_type = "combined"; limit = 300

        alerts = _read_jsonl(alerts_path, limit=max(500, limit))
        process = _read_jsonl(process_path, limit=max(500, limit))
        tracking = _read_jsonl(tracking_path, limit=max(500, limit))

        def _san_list(rows):
            try:
                return [_sanitize_json(r) for r in rows]
            except Exception:
                return rows

        if log_type == "alerts":
            return _no_cache(jsonify({"ok": True, "rows": _san_list(alerts[-limit:])}))
        if log_type == "process":
            return _no_cache(jsonify({"ok": True, "rows": _san_list(process[-limit:])}))
        if log_type == "tracking":
            return _no_cache(jsonify({"ok": True, "rows": _san_list(tracking[-limit:])}))

        # combined view
        def _tag(rows, tag):
            out = []
            for r in rows:
                rr = dict(r); rr.setdefault("_type", tag); out.append(rr)
            return out
        combined = _tag(alerts, "alerts") + _tag(process, "process") + _tag(tracking, "tracking")
        combined.sort(key=lambda r: _coerce_ts(r.get("ts")), reverse=True)
        return _no_cache(jsonify({"ok": True, "rows": _san_list(combined[:limit])}))

    @app.get("/api/tracked")
    def api_tracked():
        try:
            limit = int(request.args.get("limit") or 200)
        except Exception:
            limit = 200
        rows: List[Dict[str, Any]] = []
        source: str = "db"
        try:
            signals_db = _pick_signals_db_path(default_db)
            con = sqlite3.connect(signals_db, timeout=5)
            cur = con.cursor()
            # Detect optional columns for broad compatibility across historical DBs
            has_conviction_col: bool = False
            try:
                cur.execute("PRAGMA table_info('alerted_tokens')")
                cols = {str(r[1]) for r in (cur.fetchall() or [])}
                has_conviction_col = ("conviction_type" in cols)
            except Exception:
                has_conviction_col = False
            # If stats table doesn't exist yet, return alerts-only rows
            try:
                cur.execute("SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='alerted_token_stats'")
                has_stats = int((cur.fetchone() or [0])[0]) == 1
            except Exception as e:
                try:
                    print(f"api_tracked: has_stats detect error: {e}")
                except Exception:
                    pass
                has_stats = False
            if not has_stats:
                # Older schemas may not have conviction_type; substitute NULL when absent
                if has_conviction_col:
                    cur.execute(
                        """
                        SELECT t.token_address,
                               t.alerted_at,
                               t.final_score,
                               t.conviction_type
                        FROM alerted_tokens t
                        ORDER BY datetime(t.alerted_at) DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )
                else:
                    cur.execute(
                        """
                        SELECT t.token_address,
                               t.alerted_at,
                               t.final_score,
                               NULL AS conviction_type
                        FROM alerted_tokens t
                        ORDER BY datetime(t.alerted_at) DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )
                for r in cur.fetchall() or []:
                    rows.append({
                        "token": r[0],
                        "alerted_at": r[1],
                        "final_score": r[2],
                        "conviction": r[3],
                        "first_price": None,
                        "last_price": None,
                        "peak_price": None,
                        "first_mcap": None,
                        "last_mcap": None,
                        "peak_mcap": None,
                        "last_liq": None,
                        "last_vol24": None,
                        "peak_drawdown_pct": None,
                        "outcome": None,
                        "peak_multiple": None,
                        "last_multiple": None,
                    })
                # Do not early-return; let unified return append source
                cur.close(); con.close()
                return _no_cache(jsonify({"ok": True, "rows": rows, "source": "db_alerts_only"}))
            try:
                if has_conviction_col:
                    cur.execute(
                        """
                        SELECT t.token_address,
                               t.alerted_at,
                               t.final_score,
                               t.conviction_type,
                               s.first_price_usd,
                               NULLIF(s.last_price_usd,0),
                               NULLIF(s.peak_price_usd,0),
                               s.first_market_cap_usd,
                               NULLIF(s.last_market_cap_usd,0),
                               NULLIF(s.peak_market_cap_usd,0),
                               NULLIF(s.last_liquidity_usd,0),
                               NULLIF(s.last_volume_24h_usd,0),
                               s.peak_drawdown_pct,
                               s.outcome
                        FROM alerted_tokens t
                        LEFT JOIN alerted_token_stats s ON s.token_address = t.token_address
                        ORDER BY datetime(COALESCE(s.last_checked_at, t.alerted_at)) DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )
                else:
                    cur.execute(
                        """
                        SELECT t.token_address,
                               t.alerted_at,
                               t.final_score,
                               NULL AS conviction_type,
                               s.first_price_usd,
                               NULLIF(s.last_price_usd,0),
                               NULLIF(s.peak_price_usd,0),
                               s.first_market_cap_usd,
                               NULLIF(s.last_market_cap_usd,0),
                               NULLIF(s.peak_market_cap_usd,0),
                               NULLIF(s.last_liquidity_usd,0),
                               NULLIF(s.last_volume_24h_usd,0),
                               s.peak_drawdown_pct,
                               s.outcome
                        FROM alerted_tokens t
                        LEFT JOIN alerted_token_stats s ON s.token_address = t.token_address
                        ORDER BY datetime(COALESCE(s.last_checked_at, t.alerted_at)) DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )
            except Exception as e:
                # Fallback for older schemas missing some columns; select a compatible subset
                try:
                    print(f"api_tracked: main select failed, using fallback: {e}")
                except Exception:
                    pass
                cur.execute(
                    """
                    SELECT t.token_address,
                           t.alerted_at,
                           t.final_score,
                           t.conviction_type,
                           s.first_price_usd,
                           NULLIF(s.last_price_usd,0),
                           NULLIF(s.peak_price_usd,0),
                           NULL AS first_market_cap_usd,
                           NULL AS last_market_cap_usd,
                           NULL AS peak_market_cap_usd,
                           NULL AS last_liquidity_usd,
                           NULL AS last_volume_24h_usd,
                           NULL AS peak_drawdown_pct,
                           NULL AS outcome
                    FROM alerted_tokens t
                    LEFT JOIN alerted_token_stats s ON s.token_address = t.token_address
                    ORDER BY datetime(t.alerted_at) DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
            for r in cur.fetchall() or []:
                first_price = float(r[4] or 0)
                last_price = float(r[5] or 0)
                peak_price = float(r[6] or 0)
                peak_multiple = (peak_price / first_price) if (first_price > 0 and peak_price > 0) else None
                last_multiple = (last_price / first_price) if (first_price > 0 and last_price > 0) else None
                rows.append({
                    "token": r[0],
                    "alerted_at": r[1],
                    "final_score": r[2],
                    "conviction": r[3],
                    "first_price": r[4],
                    "last_price": r[5],
                    "peak_price": r[6],
                    "first_mcap": r[7],
                    "last_mcap": r[8],
                    "peak_mcap": r[9],
                    "last_liq": r[10],
                    "last_vol24": r[11],
                    "peak_drawdown_pct": r[12],
                    "outcome": r[13],
                    "peak_multiple": peak_multiple,
                    "last_multiple": last_multiple,
                })
            cur.close(); con.close()
        except Exception as e:
            try:
                print(f"api_tracked: db error: {e}")
            except Exception:
                pass
            rows = []

        # Logs-based fallback if DB returns empty or errored
        if not rows:
            try:
                alerts = _read_jsonl(alerts_path, limit=max(1000, limit * 5))
                tracking = _read_jsonl(tracking_path, limit=max(2000, limit * 50))
                # Group tracking by token for quick lookups
                by_token: Dict[str, List[Dict[str, Any]]] = {}
                for t in tracking:
                    tok = t.get("token")
                    if not tok:
                        continue
                    by_token.setdefault(tok, []).append(t)
                # Sort per-token by ts ascending
                for tok, lst in by_token.items():
                    lst.sort(key=lambda r: _coerce_ts(r.get("ts")))

                # Take most recent alerts first
                recent_alerts = [a for a in reversed(alerts) if a.get("token")][:limit]
                rows = []
                for a in recent_alerts:
                    tok = a.get("token")
                    if not tok:
                        continue
                    alerted_ts = _coerce_ts(a.get("ts"))
                    tlist = by_token.get(tok) or []
                    # First/last snapshots around alert time
                    first_rec = None
                    last_rec = tlist[-1] if tlist else None
                    for rec in tlist:
                        if _coerce_ts(rec.get("ts")) >= alerted_ts:
                            first_rec = rec
                            break
                    # Compute metrics
                    
                    def _val(rec: Dict[str, Any], key: str) -> Any:
                        return None if not rec else rec.get(key)

                    first_price = _finite(_val(first_rec, "price"))
                    last_price = _finite(_val(last_rec, "price"))
                    peak_price = None
                    if tlist:
                        # Prefer provided peak_price else max price
                        peaks = [r.get("peak_price") for r in tlist if r.get("peak_price")]
                        if peaks:
                            try:
                                peak_price = max(float(x) for x in peaks if x is not None)
                            except Exception:
                                peak_price = None
                        if peak_price is None:
                            try:
                                prices = [float(r.get("price") or 0) for r in tlist]
                                peak_price = max(prices) if prices else None
                            except Exception:
                                peak_price = None

                    # If first price is missing/zero, fall back to last/peak so UI shows numbers
                    try:
                        if float(first_price or 0) <= 0:
                            first_price = last_price or peak_price
                    except Exception:
                        if not first_price:
                            first_price = last_price or peak_price

                    first_mcap = _finite(_val(first_rec, "market_cap"))
                    last_mcap = _finite(_val(last_rec, "market_cap"))
                    peak_mcap = None
                    if tlist:
                        try:
                            # prefer provided peak_mcap else max mcap
                            peaks_m = [r.get("peak_mcap") for r in tlist if r.get("peak_mcap")]
                            if peaks_m:
                                peak_mcap = max(float(x) for x in peaks_m if x is not None)
                            else:
                                mcaps = [float(r.get("market_cap") or 0) for r in tlist]
                                peak_mcap = max(mcaps) if mcaps else None
                        except Exception:
                            peak_mcap = None

                    last_liq = _finite(_val(last_rec, "liquidity"))
                    last_vol24 = _finite(_val(last_rec, "vol24"))

                    peak_multiple = None
                    last_multiple = None
                    try:
                        fp = float(first_price or 0)
                        lp = float(last_price or 0)
                        pp = float(peak_price or 0)
                        if fp > 0 and pp > 0:
                            peak_multiple = pp / fp
                        if fp > 0 and lp > 0:
                            last_multiple = lp / fp
                    except Exception:
                        pass

                    rows.append({
                        "token": tok,
                        "alerted_at": a.get("ts"),
                        "final_score": a.get("final_score"),
                        "conviction": a.get("conviction_type"),
                        "first_price": first_price,
                        "last_price": last_price,
                        "peak_price": peak_price,
                        "first_mcap": first_mcap,
                        "last_mcap": last_mcap,
                        "peak_mcap": peak_mcap,
                        "last_liq": last_liq,
                        "last_vol24": last_vol24,
                        "peak_drawdown_pct": None,
                        "outcome": None,
                        "peak_multiple": peak_multiple,
                        "last_multiple": last_multiple,
                    })
                source = "logs_enriched"
            except Exception as e:
                try:
                    print(f"api_tracked: logs fallback error: {e}")
                except Exception:
                    pass
                rows = []
                source = "unknown"

        return _no_cache(jsonify({"ok": True, "rows": rows, "source": source}))

    def _client_ip() -> str:
        try:
            fwd = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            return fwd or (request.remote_addr or "")
        except Exception:
            return ""

    def _admin_ip_allowed() -> bool:
        try:
            allow = (os.getenv("CALLSBOT_ADMIN_IP_ALLOWLIST") or "").strip()
            if not allow:
                return True  # If unset, do not block by IP; rely on key
            client = _client_ip()
            allowed = [x.strip() for x in allow.split(",") if x.strip()]
            return client in allowed
        except Exception:
            return False

    def _key_fingerprint(key: str) -> str:
        try:
            if not key:
                return ""
            return sha256(key.encode("utf-8")).hexdigest()[:12]
        except Exception:
            return ""

    def _admin_audit(endpoint: str, ok: bool, payload: dict | None = None) -> None:
        try:
            req_key = (request.headers.get("X-Callsbot-Admin-Key") or "").strip()
            rec = {
                "endpoint": endpoint,
                "ok": bool(ok),
                "ip": _client_ip(),
                "key_fp": _key_fingerprint(req_key),
                "payload": payload or {},
            }
            try:
                rec_signature = hmac_sign(json.dumps(rec, ensure_ascii=False, sort_keys=True))
                rec["sig"] = rec_signature
            except Exception:
                pass
            # JSONL audit trail
            try:
                write_jsonl("admin_audit.jsonl", rec)
            except Exception:
                pass
            # SQLite audit trail (separate admin db)
            try:
                admin_db = os.getenv("CALLSBOT_ADMIN_DB_FILE", os.path.join("var", "admin.db"))
                os.makedirs(os.path.dirname(admin_db) or ".", exist_ok=True)
                con = sqlite3.connect(admin_db, timeout=5)
                cur = con.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_actions (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      ts TEXT DEFAULT (datetime('now')),
                      endpoint TEXT,
                      ip TEXT,
                      key_fp TEXT,
                      ok INTEGER,
                      payload TEXT,
                      sig TEXT
                    )
                    """
                )
                cur.execute(
                    "INSERT INTO admin_actions(endpoint, ip, key_fp, ok, payload, sig) VALUES (?,?,?,?,?,?)",
                    (rec.get("endpoint"), rec.get("ip"), rec.get("key_fp"), 1 if rec.get("ok") else 0, json.dumps(rec.get("payload") or {}), rec.get("sig")),
                )
                con.commit(); cur.close(); con.close()
            except Exception:
                try:
                    con.close()  # type: ignore
                except Exception:
                    pass
        except Exception:
            pass

    def _cors_ok() -> bool:
        # CORS is disabled by default; allow only configured origins
        allow = (os.getenv("CALLSBOT_CORS_ORIGINS") or "").strip()
        if not allow:
            return False
        origin = (request.headers.get("Origin") or "").strip()
        if not origin:
            return False
        allowed = [o.strip() for o in allow.split(",") if o.strip()]
        return origin in allowed

    @app.after_request
    def _set_security_headers(resp):  # type: ignore
        try:
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Referrer-Policy", "no-referrer")
            # HSTS (assumes TLS termination at proxy)
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
            # CORS: only when explicitly allowed
            if _cors_ok():
                origin = request.headers.get("Origin")
                # Ensure Vary includes Origin without breaking existing values
                try:
                    vary_parts = list(filter(None, [resp.headers.get("Vary"), "Origin"]))
                    resp.headers["Vary"] = ", ".join(sorted(set(vary_parts)))
                except Exception:
                    resp.headers["Vary"] = "Origin"
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Callsbot-Admin-Key"
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        except Exception:
            pass
        return resp

    @app.before_request
    def _limit_request_size_and_https():  # type: ignore
        try:
            # Request size limit to 1MB
            cl = request.content_length or 0
            max_bytes = int(os.getenv("CALLSBOT_MAX_REQUEST_BYTES", "1048576"))
            if cl and cl > max_bytes:
                return jsonify({"ok": False, "error": "payload too large"}), 413
            # Optionally enforce HTTPS by rejecting if X-Forwarded-Proto != https
            # Default disabled so plain HTTP works; set CALLSBOT_REQUIRE_HTTPS=true to enforce
            if os.getenv("CALLSBOT_REQUIRE_HTTPS", "false").lower() == "true":
                xf = (request.headers.get("X-Forwarded-Proto") or request.scheme or "").lower()
                if xf != "https":
                    return jsonify({"ok": False, "error": "https required"}), 400
        except Exception:
            pass

    @app.post("/api/toggles")
    def api_set_toggles():
        # Require admin key (same pattern as /api/sql)
        admin_key = os.getenv("CALLSBOT_SQL_KEY", "").strip()
        req_key = (request.headers.get("X-Callsbot-Admin-Key") or "").strip()
        if (not admin_key) or (req_key != admin_key) or (not _admin_ip_allowed()):
            _admin_audit("/api/toggles", False, {"reason": "forbidden"})
            return jsonify({"ok": False, "error": "forbidden"}), 403
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            _admin_audit("/api/toggles", False, {"reason": "bad_json", "error": str(e)})
            return jsonify({"ok": False, "error": "invalid json"}), 400
        # Validate types if provided
        for key in ("signals_enabled", "trading_enabled"):
            if key in body and not isinstance(body.get(key), bool):
                _admin_audit("/api/toggles", False, {"reason": "bad_type", "key": key})
                return jsonify({"ok": False, "error": f"{key} must be a boolean"}), 400
        updated = set_toggles({
            "signals_enabled": body.get("signals_enabled"),
            "trading_enabled": body.get("trading_enabled"),
        })
        _admin_audit("/api/toggles", True, {"toggles": updated})
        return jsonify({"ok": True, "toggles": updated})

    # Optional SQL allowlist for safer admin queries
    _SQL_ALLOWLIST = {
        "alerts_24h": "SELECT COUNT(1) AS alerts_24h FROM alerted_tokens WHERE alerted_at >= datetime('now','-1 day')",
        "recent_open_positions": "SELECT id, token_address, open_at FROM positions WHERE status='open' ORDER BY datetime(open_at) DESC LIMIT 50",
    }

    if 'limiter' in locals() and limiter is not None:
        _sql_decorator = limiter.limit(os.getenv("CALLSBOT_SQL_RATELIMIT", "20/minute"))
        _toggles_decorator = limiter.limit(os.getenv("CALLSBOT_TOGGLES_RATELIMIT", "10/minute"))
    else:
        
        def _sql_decorator(f):
            return f

        def _toggles_decorator(f):
            return f

    @_sql_decorator
    @app.post("/api/sql")
    def api_sql():
        # Require admin key header (default deny when not set)
        admin_key = os.getenv("CALLSBOT_SQL_KEY", "").strip()
        req_key = (request.headers.get("X-Callsbot-Admin-Key") or "").strip()
        if (not admin_key) or (req_key != admin_key) or (not _admin_ip_allowed()):
            _admin_audit("/api/sql", False, {"reason": "forbidden"})
            return jsonify({"ok": False, "error": "forbidden"}), 403
        body = request.get_json(force=True, silent=True) or {}
        query_val = body.get("query")
        query = (str(query_val) if isinstance(query_val, (str, bytes)) else "").strip()
        preset = (body.get("preset") or "").strip()
        if preset:
            query = _SQL_ALLOWLIST.get(preset) or ""
        target = str(body.get("target") or "signals").strip().lower()  # signals | trading | custom
        custom_path = body.get("path")

        if not query:
            return jsonify({"ok": False, "error": "empty query"}), 400

        # Enforce read-only: allow only SELECT/PRAGMA/EXPLAIN (and WITH ... SELECT) and reject known write ops
        q_upper = query.lstrip().upper()
        forbidden_tokens = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH", "DETACH", "VACUUM", "REPLACE", "CREATE", "TRUNCATE")
        if any(tok in q_upper for tok in forbidden_tokens):
            _admin_audit("/api/sql", False, {"reason": "write_op_detected", "query": query[:200]})
            return jsonify({"ok": False, "error": "write queries are not allowed"}), 403
        allowed_starts = ("SELECT", "PRAGMA", "EXPLAIN", "WITH")
        if not q_upper.startswith(allowed_starts):
            _admin_audit("/api/sql", False, {"reason": "disallowed_statement", "query": query[:200]})
            return jsonify({"ok": False, "error": "only SELECT/PRAGMA/EXPLAIN are allowed"}), 403
        # If WITH, ensure it is used for a SELECT query
        if q_upper.startswith("WITH") and (" SELECT " not in f" {q_upper} "):
            _admin_audit("/api/sql", False, {"reason": "with_without_select", "query": query[:200]})
            return jsonify({"ok": False, "error": "WITH must be used with SELECT"}), 403

        path = default_db if target == "signals" else trading_db if target == "trading" else (str(custom_path) if custom_path else default_db)
        # Open read-only connection via URI
        try:
            ro_uri = f"file:{path}?mode=ro"
            con = sqlite3.connect(ro_uri, timeout=10, uri=True)
            cur = con.cursor()
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute(query)
            cols = [d[0] for d in (cur.description or [])]
            fetched = cur.fetchall() or []
            rows = [
                {cols[i]: val for i, val in enumerate(r)} if cols else {}
                for r in fetched
            ]
            cur.close(); con.close()
            _admin_audit("/api/sql", True, {"query": query[:200], "target": target, "db": path})
            return jsonify({"ok": True, "columns": cols, "rows": rows, "db": path})
        except Exception as e:
            try:
                con.close()  # type: ignore
            except Exception:
                pass
            _admin_audit("/api/sql", False, {"reason": "db_error", "error": str(e)[:200]})
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.post("/api/paper")
    def api_paper():
        body = request.get_json(force=True, silent=True) or {}
        window = str(body.get("window") or "3h")
        stop_pct = float(body.get("stop_pct") or 0.25)
        trail_ret = float(body.get("trail_retention") or 0.70)
        cap_mul = float(body.get("cap_multiple") or 2.0)
        strict_only = bool(body.get("strict_only") if body.get("strict_only") is not None else True)
        max_mcap = body.get("max_mcap_usd")
        try:
            max_mcap_val = float(max_mcap) if (max_mcap is not None and max_mcap != "") else None
        except Exception as e:
            try:
                print(f"api_paper: bad max_mcap: {e}")
            except Exception:
                pass
            max_mcap_val = None

        signals_db = _pick_signals_db_path(default_db)
        metrics = _paper_metrics(
            signals_db,
            window=window,
            stop_pct=stop_pct,
            trail_retention=trail_ret,
            cap_multiple=cap_mul,
            strict_only=strict_only,
            max_mcap_usd=max_mcap_val,
        )
        return jsonify({"ok": True, "window": window, "params": {
            "stop_pct": stop_pct,
            "trail_retention": trail_ret,
            "cap_multiple": cap_mul,
            "strict_only": strict_only,
            "max_mcap_usd": max_mcap_val,
        }, "metrics": metrics})

    @app.get("/")
    @requires_auth
    def index():
        return render_template("index.html")

    return app


def _signals_metrics(db_path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        con = sqlite3.connect(db_path, timeout=5)
        cur = con.cursor()
        # Totals
        cur.execute("SELECT COUNT(1) FROM alerted_tokens")
        out["total_alerts"] = int(cur.fetchone()[0])
        # 24h alerts
        cur.execute("SELECT COUNT(1) FROM alerted_tokens WHERE alerted_at >= datetime('now','-1 day')")
        out["alerts_24h"] = int(cur.fetchone()[0])
        # Success rates (>=2x and >=5x), denominator considers rows with valid first_price
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN first_price_usd>0 AND peak_price_usd/first_price_usd >= 2.0 THEN 1 ELSE 0 END) AS ge2x,
              SUM(CASE WHEN first_price_usd>0 AND peak_price_usd/first_price_usd >= 5.0 THEN 1 ELSE 0 END) AS ge5x,
              SUM(CASE WHEN first_price_usd>0 THEN 1 ELSE 0 END) AS denom_pos,
              SUM(CASE WHEN first_price_usd>0 AND peak_price_usd/first_price_usd < 2.0 THEN 1 ELSE 0 END) AS lt2x
            FROM alerted_token_stats
            """
        )
        row = cur.fetchone()
        ge2x, ge5x, denom_pos, lt2x = (row or (0, 0, 0, 0))
        denom_pos = float(denom_pos or 0)
        out["rate_ge_2x"] = (float(ge2x) / denom_pos) if denom_pos else 0.0
        out["rate_ge_5x"] = (float(ge5x) / denom_pos) if denom_pos else 0.0
        out["sub_2x_rate"] = (float(lt2x) / denom_pos) if denom_pos else 0.0
        # Rug rate
        cur.execute("SELECT SUM(CASE WHEN outcome='rug' THEN 1 ELSE 0 END), COUNT(1) FROM alerted_token_stats")
        r = cur.fetchone(); rugs, n = (r or (0, 0))
        out["rug_rate"] = (float(rugs) / float(n)) if n else 0.0
        # Median time to peak price (seconds)
        cur.execute(
            """
            SELECT time_to_peak_price_s FROM (
              SELECT CAST((JULIANDAY(peak_price_at)-JULIANDAY(first_alert_at))*86400 AS INTEGER) AS time_to_peak_price_s
              FROM alerted_token_stats
              WHERE peak_price_at IS NOT NULL AND first_alert_at IS NOT NULL
            )
            WHERE time_to_peak_price_s >= 0
            ORDER BY time_to_peak_price_s
            LIMIT 1 OFFSET (
              SELECT (COUNT(1)-1)/2 FROM (
                SELECT 1 FROM alerted_token_stats WHERE peak_price_at IS NOT NULL AND first_alert_at IS NOT NULL
              )
            )
            """
        )
        row = cur.fetchone()
        out["median_ttp_price_s"] = int(row[0]) if row and row[0] is not None else None
        # Average peak multiple
        cur.execute("SELECT AVG(CASE WHEN first_price_usd>0 THEN peak_price_usd/first_price_usd END) FROM alerted_token_stats")
        row = cur.fetchone(); out["avg_peak_multiple"] = float(row[0]) if row and row[0] is not None else None

        # 1-hour performance snapshot (PnL style using last vs first)
        cur.execute(
            """
            SELECT
              COUNT(1) as n,
              AVG(last_price_usd/first_price_usd) as avg_mul,
              SUM(CASE WHEN last_price_usd/first_price_usd > 1.0 THEN 1 ELSE 0 END) as winners
            FROM alerted_token_stats
            WHERE first_alert_at >= datetime('now','-1 hour')
              AND first_price_usd > 0 AND last_price_usd IS NOT NULL
            """
        )
        row = cur.fetchone() or (0, None, 0)
        n1h = int(row[0] or 0)
        avg_mul_1h = float(row[1]) if row[1] is not None else None
        winners_1h = int(row[2] or 0)
        out["alerts_1h"] = n1h
        out["avg_return_1h_multiple"] = avg_mul_1h
        out["avg_return_1h_pct"] = ((avg_mul_1h - 1.0) * 100.0) if (avg_mul_1h is not None) else None
        out["win_rate_1h"] = (float(winners_1h) / float(n1h)) if n1h else None
        # Daily counts (last 14 days)
        cur.execute(
            """
            SELECT DATE(alerted_at), COUNT(1)
            FROM alerted_tokens
            WHERE alerted_at >= DATE('now','-14 day')
            GROUP BY DATE(alerted_at)
            ORDER BY DATE(alerted_at)
            """
        )
        out["daily"] = [{"date": d, "count": int(c)} for d, c in (cur.fetchall() or [])]
        cur.close(); con.close()
    except Exception as e:
        try:
            print(f"_signals_metrics: metrics error: {e}")
        except Exception:
            pass
    return out


def _trading_metrics(db_path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        con = sqlite3.connect(db_path, timeout=5)
        cur = con.cursor()
        # Position counts
        cur.execute("SELECT COUNT(1) FROM positions WHERE status='open'")
        out["open_positions"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(1) FROM positions WHERE status='closed'")
        out["closed_positions"] = int(cur.fetchone()[0])
        # Total USD at entry for open positions
        cur.execute("SELECT COALESCE(SUM(usd_size),0) FROM positions WHERE status='open'")
        row = cur.fetchone(); out["open_usd_total"] = float(row[0] or 0)
        # Realized PnL approximate for closed: sum(sell.usd) - sum(buy.usd)
        cur.execute(
            """
            WITH sums AS (
              SELECT p.id as pid,
                     SUM(CASE WHEN f.side='buy' THEN COALESCE(f.usd,0) ELSE 0 END) AS buy_usd,
                     SUM(CASE WHEN f.side='sell' THEN COALESCE(f.usd,0) ELSE 0 END) AS sell_usd
              FROM positions p
              LEFT JOIN fills f ON f.position_id = p.id
              WHERE p.status='closed'
              GROUP BY p.id
            )
            SELECT COALESCE(SUM(sell_usd - buy_usd),0) FROM sums
            """
        )
        row = cur.fetchone(); out["realized_pnl_total"] = float(row[0] or 0)
        # Recent closed positions with pnl
        cur.execute(
            """
            WITH sums AS (
              SELECT p.id as pid,
                     p.token_address,
                     p.strategy,
                     p.open_at,
                     SUM(CASE WHEN f.side='buy' THEN COALESCE(f.usd,0) ELSE 0 END) AS buy_usd,
                     SUM(CASE WHEN f.side='sell' THEN COALESCE(f.usd,0) ELSE 0 END) AS sell_usd
              FROM positions p
              LEFT JOIN fills f ON f.position_id = p.id
              WHERE p.status='closed'
              GROUP BY p.id
            )
            SELECT token_address, strategy, open_at, (sell_usd - buy_usd) as pnl_usd
            FROM sums
            ORDER BY datetime(open_at) DESC
            LIMIT 20
            """
        )
        out["recent_closed"] = [
            {"token": t, "strategy": s, "open_at": oa, "pnl_usd": float(p)}
            for (t, s, oa, p) in (cur.fetchall() or [])
        ]
        # Open positions listing
        cur.execute(
            """
            SELECT id, token_address, strategy, entry_price, qty, usd_size, open_at, peak_price, trail_pct
            FROM positions WHERE status='open' ORDER BY datetime(open_at) DESC
            """
        )
        out["open_list"] = [
            {
                "id": int(r[0]), "token": r[1], "strategy": r[2], "entry_price": float(r[3] or 0),
                "qty": float(r[4] or 0), "usd_size": float(r[5] or 0), "open_at": r[6],
                "peak_price": float(r[7] or 0), "trail_pct": float(r[8] or 0),
            }
            for r in (cur.fetchall() or [])
        ]
        cur.close(); con.close()
    except Exception as e:
        try:
            print(f"_trading_metrics: metrics error: {e}")
        except Exception:
            pass
    return out


def _gates_summary(alerts_path: str) -> Dict[str, Any]:
    data = {"strict_pass": 0, "nuanced_pass": 0, "fails": 0}
    try:
        alerts = _read_jsonl(alerts_path, limit=2000)
        for a in alerts:
            gates = (a.get("gates") or {}).get("passes") or {}
            passed = all([
                (gates.get("liquidity") is not False),
                (gates.get("volume_24h") is not False),
                (gates.get("vol_to_mcap") is not False),
                (gates.get("mcap_micro") is not False),
                (gates.get("top10_concentration") is not False),
            ])
            if passed:
                if (a.get("conviction_type") or "").lower().startswith("high confidence"):
                    data["strict_pass"] += 1
                else:
                    data["nuanced_pass"] += 1
            else:
                data["fails"] += 1
    except Exception as e:
        try:
            print(f"_gates_summary: error: {e}")
        except Exception:
            pass
    return data


if __name__ == "__main__":
    print("This module is not a standalone entrypoint. Use: python scripts/bot.py web [--host 0.0.0.0 --port 8080]")


