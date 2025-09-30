import os
import json
from datetime import datetime
from typing import Dict, Any, List
import sqlite3

from flask import Flask, jsonify, render_template, request
from flask import Response
import time
from app.toggles import get_toggles, set_toggles


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


def _pick_signals_db_path(preferred_path: str) -> str:
    """Return the best available signals DB path by checking several candidates
    and picking the one with the highest alerted_tokens row count.
    """
    candidates = [
        preferred_path,
        "/app/state/alerted_tokens.db",
        "/app/var/alerted_tokens.db",
        os.path.join("var", "alerted_tokens.db"),
    ]
    best_path = preferred_path
    best_count = -1
    for p in candidates:
        try:
            con = sqlite3.connect(p, timeout=3)
            cur = con.cursor()
            cur.execute("SELECT COUNT(1) FROM alerted_tokens")
            n = int(cur.fetchone()[0])
            cur.close(); con.close()
            if n > best_count:
                best_count = n; best_path = p
        except Exception:
            continue
    return best_path


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

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
        last_alert = alerts[-1] if alerts else None
        last_heartbeat = None
        cooldowns: int = 0
        for rec in process:
            if rec.get("type") == "heartbeat":
                last_heartbeat = rec
            if rec.get("type") == "cooldown":
                cooldowns += 1

        # Last N alerts short view
        recent_alerts = [
            {
                "token": a.get("token"),
                "symbol": a.get("symbol"),
                "score": a.get("final_score"),
                "conviction": a.get("conviction_type"),
                "market_cap": a.get("market_cap"),
                "liquidity": a.get("liquidity"),
                "vol24": a.get("volume_24h"),
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
        data = {
            "total_alerts": (signals_summary.get("total_alerts") if isinstance(signals_summary, dict) and signals_summary.get("total_alerts") is not None else total_alerts),
            "log_alerts_count": total_alerts,
            "cooldowns": cooldowns,
            "last_alert": last_alert,
            "last_heartbeat": last_heartbeat,
            "recent_alerts": recent_alerts,
            "tracking_count": len(last_tracking),
            "toggles": toggles,
            "signals_summary": signals_summary,
            "trading_summary": trading_summary,
            "gates_summary": gates_summary,
        }
        return jsonify(data)

    @app.get("/api/stream")
    def api_stream():
        def _gen():
            while True:
                try:
                    alerts = _read_jsonl(alerts_path, limit=500)
                    process = _read_jsonl(process_path, limit=1000)
                    tracking = _read_jsonl(tracking_path, limit=500)

                    total_alerts = len(alerts)
                    last_alert = alerts[-1] if alerts else None
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
                            "market_cap": a.get("market_cap"),
                            "liquidity": a.get("liquidity"),
                            "vol24": a.get("volume_24h"),
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
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                except Exception:
                    # keep the stream alive even if an iteration fails
                    yield "event: ping\ndata: {}\n\n"
                time.sleep(2)

        return Response(_gen(), mimetype="text/event-stream")

    @app.get("/api/logs")
    def api_logs():
        try:
            log_type = (request.args.get("type") or "combined").lower()
            limit = int(request.args.get("limit") or 300)
        except Exception:
            log_type = "combined"; limit = 300

        alerts = _read_jsonl(alerts_path, limit=max(500, limit))
        process = _read_jsonl(process_path, limit=max(500, limit))
        tracking = _read_jsonl(tracking_path, limit=max(500, limit))

        if log_type == "alerts":
            return jsonify({"ok": True, "rows": alerts[-limit:]})
        if log_type == "process":
            return jsonify({"ok": True, "rows": process[-limit:]})
        if log_type == "tracking":
            return jsonify({"ok": True, "rows": tracking[-limit:]})

        # combined view
        def _tag(rows, tag):
            out = []
            for r in rows:
                rr = dict(r); rr.setdefault("_type", tag); out.append(rr)
            return out
        combined = _tag(alerts, "alerts") + _tag(process, "process") + _tag(tracking, "tracking")
        combined.sort(key=lambda r: _coerce_ts(r.get("ts")), reverse=True)
        return jsonify({"ok": True, "rows": combined[:limit]})

    @app.get("/api/tracked")
    def api_tracked():
        try:
            limit = int(request.args.get("limit") or 200)
        except Exception:
            limit = 200
        rows: List[Dict[str, Any]] = []
        try:
            signals_db = _pick_signals_db_path(default_db)
            con = sqlite3.connect(signals_db, timeout=5)
            cur = con.cursor()
            try:
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
            except Exception:
                # Fallback for older schemas missing some columns; select a compatible subset
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
                })
            cur.close(); con.close()
        except Exception:
            rows = []
        return jsonify({"ok": True, "rows": rows})

    @app.post("/api/toggles")
    def api_set_toggles():
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception:
            body = {}
        updated = set_toggles({
            "signals_enabled": body.get("signals_enabled"),
            "trading_enabled": body.get("trading_enabled"),
        })
        return jsonify({"ok": True, "toggles": updated})

    @app.post("/api/sql")
    def api_sql():
        body = request.get_json(force=True, silent=True) or {}
        query = str(body.get("query") or "").strip()
        target = str(body.get("target") or "signals")  # signals | trading | custom
        allow_writes = bool(body.get("allow_writes"))
        custom_path = body.get("path")

        if not query:
            return jsonify({"ok": False, "error": "empty query"}), 400

        # Very basic safety: block writes unless allowed
        q_upper = query.lstrip().upper()
        is_write = q_upper.startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "REPLACE", "VACUUM", "ATTACH", "PRAGMA"))
        if is_write and not allow_writes:
            return jsonify({"ok": False, "error": "write queries require allow_writes=true"}), 403

        path = default_db if target == "signals" else trading_db if target == "trading" else str(custom_path or default_db)
        try:
            con = sqlite3.connect(path, timeout=10)
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute(query)
            if is_write:
                con.commit()
                rows = [{"rows_affected": cur.rowcount}]
                cols: List[str] = ["rows_affected"]
            else:
                cols = [d[0] for d in (cur.description or [])]
                fetched = cur.fetchall()
                rows = [
                    {cols[i]: val for i, val in enumerate(r)}
                    for r in fetched
                ]
            cur.close()
            con.close()
            return jsonify({"ok": True, "columns": cols, "rows": rows, "db": path})
        except Exception as e:
            try:
                con.close()  # type: ignore
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.get("/")
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
    except Exception:
        pass
    return data


if __name__ == "__main__":
    print("This module is not a standalone entrypoint. Use: python scripts/bot.py web [--host 0.0.0.0 --port 8080]")


