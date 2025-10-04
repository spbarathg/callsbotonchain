"""
Enhanced API endpoints for comprehensive dashboard
Provides data for Overview, Performance, System, Configuration, and Paper Trading tabs
"""
import os
import json
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
import subprocess

# Import existing utilities
try:
    from app.budget import get_budget
except:
    get_budget = None

try:
    from app.toggles import get_toggles
except:
    def get_toggles():
        return {"signals_enabled": True, "trading_enabled": False}


def _get_db_path() -> str:
    """Get database path"""
    return os.getenv("CALLSBOT_DB_FILE", "var/alerted_tokens.db")


def _read_alerts_file(limit: int = 1000) -> List[Dict]:
    """Read alerts from JSONL file"""
    alerts = []
    alerts_path = "data/logs/alerts.jsonl"
    try:
        with open(alerts_path, 'r') as f:
            lines = f.readlines()
            for line in reversed(lines[-limit:]):
                try:
                    alerts.append(json.loads(line.strip()))
                except:
                    continue
    except:
        pass
    return alerts


def _read_process_log(limit: int = 1000) -> List[Dict]:
    """Read process log"""
    logs = []
    log_path = "data/logs/process.jsonl"
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            for line in reversed(lines[-limit:]):
                try:
                    logs.append(json.loads(line.strip()))
                except:
                    continue
    except:
        pass
    return logs


# ============================================================================
# OVERVIEW TAB ENDPOINTS
# ============================================================================

def get_smart_money_status() -> Dict[str, Any]:
    """Get smart money detection status and performance"""
    alerts = _read_alerts_file(200)
    
    # Filter recent (last 24h)
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = [a for a in alerts if a.get('ts', '') >= cutoff]
    
    # Count smart money
    smart_alerts = [a for a in recent if a.get('smart_money_detected') == True]
    
    # Calculate metrics
    total_recent = len(recent)
    smart_count = len(smart_alerts)
    smart_percentage = (smart_count / total_recent * 100) if total_recent > 0 else 0
    
    # Average score for smart money
    smart_scores = [a.get('final_score', 0) for a in smart_alerts]
    avg_score = sum(smart_scores) / len(smart_scores) if smart_scores else 0
    
    # Perfect scores (10/10)
    perfect_scores = len([s for s in smart_scores if s == 10])
    
    # Latest smart alert
    latest_smart = smart_alerts[0] if smart_alerts else None
    latest_time = None
    if latest_smart:
        try:
            ts = datetime.fromisoformat(latest_smart.get('ts', ''))
            latest_time = (datetime.now() - ts).total_seconds() / 60  # minutes ago
        except:
            pass
    
    # Get current cycle from process log
    logs = _read_process_log(50)
    current_cycle = "unknown"
    feed_items = 0
    for log in logs:
        if log.get('type') == 'feed_mode':
            current_cycle = log.get('mode', 'unknown')
            break
        if log.get('type') == 'heartbeat':
            current_cycle = log.get('cycle', 'unknown')
            feed_items = log.get('feed_items', 0)
            break
    
    return {
        "status": "active" if smart_count > 0 else "idle",
        "smart_alerts_24h": smart_count,
        "total_alerts_24h": total_recent,
        "percentage": round(smart_percentage, 1),
        "avg_score": round(avg_score, 1),
        "perfect_scores": perfect_scores,
        "latest_minutes_ago": round(latest_time, 1) if latest_time else None,
        "current_cycle": current_cycle,
        "feed_items": feed_items,
        "next_cycle_seconds": 60 if current_cycle != "unknown" else None
    }


def get_feed_health() -> Dict[str, Any]:
    """Get feed health and processing status"""
    logs = _read_process_log(100)
    
    # Get latest heartbeat
    latest_heartbeat = None
    for log in logs:
        if log.get('type') == 'heartbeat':
            latest_heartbeat = log
            break
    
    # Count recent cycles
    recent_cycles = []
    for log in logs:
        if log.get('type') == 'feed_mode':
            recent_cycles.append(log.get('mode'))
    
    # Calculate processing rate
    heartbeats = [l for l in logs if l.get('type') == 'heartbeat']
    total_items = sum(h.get('feed_items', 0) for h in heartbeats[:10])
    avg_items = total_items / 10 if len(heartbeats) >= 10 else 0
    
    # Check for errors
    errors = [l for l in logs if l.get('type') in ['error', 'token_stats_error', 'feed_error']]
    error_rate = len(errors) / len(logs) * 100 if logs else 0
    
    return {
        "status": "connected" if latest_heartbeat else "disconnected",
        "current_cycle": latest_heartbeat.get('cycle') if latest_heartbeat else "unknown",
        "feed_items": latest_heartbeat.get('feed_items', 0) if latest_heartbeat else 0,
        "alerts_sent": latest_heartbeat.get('alerts_sent', 0) if latest_heartbeat else 0,
        "processing_rate": round(avg_items, 1),
        "recent_cycles": recent_cycles[:10],
        "general_count": recent_cycles.count('general'),
        "smart_count": recent_cycles.count('smart_money'),
        "error_rate": round(error_rate, 1),
        "last_heartbeat_seconds": None  # TODO: calculate from timestamp
    }


def get_budget_status() -> Dict[str, Any]:
    """Get API budget usage status"""
    if get_budget is None:
        return {"status": "unavailable"}
    
    try:
        budget = get_budget()
        
        # Get current usage
        daily_max = int(os.getenv("BUDGET_PER_DAY_MAX", "10000"))
        minute_max = int(os.getenv("BUDGET_PER_MINUTE_MAX", "15"))
        
        # Load budget file
        budget_file = "var/credits_budget.json"
        day_count = 0
        minute_count = 0
        try:
            with open(budget_file, 'r') as f:
                data = json.load(f)
                day_count = data.get('day_count', 0)
                minute_count = data.get('minute_count', 0)
        except:
            pass
        
        daily_percent = (day_count / daily_max * 100) if daily_max > 0 else 0
        minute_percent = (minute_count / minute_max * 100) if minute_max > 0 else 0
        
        # Calculate reset time (rough estimate)
        now = datetime.now()
        tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
        reset_seconds = (tomorrow - now).total_seconds()
        reset_hours = int(reset_seconds // 3600)
        reset_minutes = int((reset_seconds % 3600) // 60)
        
        return {
            "status": "healthy" if daily_percent < 80 else "warning" if daily_percent < 95 else "critical",
            "daily_used": day_count,
            "daily_max": daily_max,
            "daily_percent": round(daily_percent, 1),
            "minute_used": minute_count,
            "minute_max": minute_max,
            "minute_percent": round(minute_percent, 1),
            "reset_hours": reset_hours,
            "reset_minutes": reset_minutes,
            "zero_miss_mode": os.getenv("BUDGET_FEED_COST", "1") == "0"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_recent_activity(limit: int = 20) -> Dict[str, Any]:
    """Get recent alerts with details"""
    alerts = _read_alerts_file(limit)
    
    formatted_alerts = []
    for alert in alerts:
        try:
            ts = datetime.fromisoformat(alert.get('ts', ''))
            minutes_ago = (datetime.now() - ts).total_seconds() / 60
        except:
            minutes_ago = None
        
        token = alert.get('token', '')
        is_pump_bonk = token.endswith('pump') or token.endswith('bonk')
        
        formatted_alerts.append({
            "token": token[:16] + "..." if len(token) > 16 else token,
            "token_full": token,
            "score": alert.get('final_score'),
            "conviction": alert.get('conviction_type', ''),
            "smart_money": alert.get('smart_money_detected', False),
            "minutes_ago": round(minutes_ago, 0) if minutes_ago else None,
            "timestamp": alert.get('ts'),
            "is_tradeable": is_pump_bonk,
            "symbol": alert.get('symbol', '')
        })
    
    return {
        "alerts": formatted_alerts,
        "count": len(formatted_alerts)
    }


def get_quick_stats() -> Dict[str, Any]:
    """Get quick overview statistics"""
    # Get total from DB
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM alerted_tokens")
        total_alerts = c.fetchone()[0]
        conn.close()
    except:
        total_alerts = 0
    
    # Get 24h from file
    alerts = _read_alerts_file(500)
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = [a for a in alerts if a.get('ts', '') >= cutoff]
    alerts_24h = len(recent)
    
    # Get tracking count
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM alerted_token_stats")
        tracking_count = c.fetchone()[0]
        conn.close()
    except:
        tracking_count = 0
    
    # Success rate (tokens that 2x'd)
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM alerted_token_stats 
            WHERE (peak_price_usd / first_price_usd) >= 2.0
            AND first_price_usd > 0
        """)
        success_count = c.fetchone()[0]
        success_rate = (success_count / tracking_count * 100) if tracking_count > 0 else 0
        conn.close()
    except:
        success_rate = 0
    
    # Get toggles
    toggles = get_toggles()
    
    return {
        "total_alerts": total_alerts,
        "alerts_24h": alerts_24h,
        "tracking_count": tracking_count,
        "success_rate": round(success_rate, 1),
        "signals_enabled": toggles.get("signals_enabled", True),
        "trading_enabled": toggles.get("trading_enabled", False)
    }


# ============================================================================
# PERFORMANCE TAB ENDPOINTS
# ============================================================================

def get_signal_quality() -> Dict[str, Any]:
    """Get signal quality breakdown"""
    alerts = _read_alerts_file(500)
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = [a for a in alerts if a.get('ts', '') >= cutoff]
    
    # Conviction breakdown
    conviction_counts = defaultdict(int)
    for alert in recent:
        conv = alert.get('conviction_type', 'Unknown')
        conviction_counts[conv] += 1
    
    # Score distribution
    score_ranges = {
        "perfect": 0,      # 10
        "excellent": 0,    # 8-9
        "good": 0,         # 6-7
        "marginal": 0      # 4-5
    }
    
    scores = []
    for alert in recent:
        score = alert.get('final_score', 0)
        scores.append(score)
        if score == 10:
            score_ranges["perfect"] += 1
        elif score >= 8:
            score_ranges["excellent"] += 1
        elif score >= 6:
            score_ranges["good"] += 1
        else:
            score_ranges["marginal"] += 1
    
    avg_score = sum(scores) / len(scores) if scores else 0
    
    return {
        "conviction_breakdown": dict(conviction_counts),
        "score_distribution": score_ranges,
        "avg_score": round(avg_score, 1),
        "total_signals": len(recent)
    }


def get_gate_performance() -> Dict[str, Any]:
    """Get gate pass/fail statistics"""
    logs = _read_process_log(1000)
    
    # Count gate outcomes
    prelim_pass = 0
    prelim_fail = 0
    strict_pass = 0
    nuanced_pass = 0
    final_fail = 0
    
    for log in logs:
        log_type = log.get('type', '')
        if 'prelim' in log_type.lower() or 'preliminary' in log_type.lower():
            if 'pass' in log_type.lower():
                prelim_pass += 1
            elif 'fail' in log_type.lower() or 'reject' in log_type.lower():
                prelim_fail += 1
        elif 'strict' in log_type.lower():
            if 'pass' in log_type.lower():
                strict_pass += 1
        elif 'nuanced' in log_type.lower():
            if 'pass' in log_type.lower():
                nuanced_pass += 1
    
    # Get current settings
    settings = {
        "high_confidence_score": int(os.getenv("HIGH_CONFIDENCE_SCORE", "5")),
        "min_liquidity": int(os.getenv("MIN_LIQUIDITY_USD", "5000")),
        "vol_mcap_ratio": float(os.getenv("VOL_TO_MCAP_RATIO_MIN", "0.15"))
    }
    
    total_prelim = prelim_pass + prelim_fail
    prelim_pass_rate = (prelim_pass / total_prelim * 100) if total_prelim > 0 else 0
    
    return {
        "prelim_pass": prelim_pass,
        "prelim_fail": prelim_fail,
        "prelim_pass_rate": round(prelim_pass_rate, 1),
        "strict_pass": strict_pass,
        "nuanced_pass": nuanced_pass,
        "settings": settings
    }


def get_performance_trends(days: int = 7) -> Dict[str, Any]:
    """Get performance trends over time"""
    alerts = _read_alerts_file(2000)
    
    # Group by day
    daily_stats = defaultdict(lambda: {"alerts": 0, "smart": 0, "scores": []})
    
    for alert in alerts:
        try:
            ts = datetime.fromisoformat(alert.get('ts', ''))
            date = ts.strftime('%Y-%m-%d')
            
            daily_stats[date]["alerts"] += 1
            if alert.get('smart_money_detected'):
                daily_stats[date]["smart"] += 1
            daily_stats[date]["scores"].append(alert.get('final_score', 0))
        except:
            continue
    
    # Format for last N days
    trends = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        stats = daily_stats.get(date, {"alerts": 0, "smart": 0, "scores": []})
        
        smart_pct = (stats["smart"] / stats["alerts"] * 100) if stats["alerts"] > 0 else 0
        avg_score = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
        
        trends.append({
            "date": date,
            "alerts": stats["alerts"],
            "smart_percentage": round(smart_pct, 1),
            "avg_score": round(avg_score, 1)
        })
    
    return {
        "trends": list(reversed(trends)),
        "days": days
    }


def get_hourly_heatmap() -> Dict[str, Any]:
    """Get hourly alert distribution for last 24h"""
    alerts = _read_alerts_file(500)
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = [a for a in alerts if a.get('ts', '') >= cutoff]
    
    # Count by hour
    hourly_counts = defaultdict(int)
    for alert in recent:
        try:
            ts = datetime.fromisoformat(alert.get('ts', ''))
            hour = ts.strftime('%H:00')
            hourly_counts[hour] += 1
        except:
            continue
    
    # Format for all 24 hours
    heatmap = []
    for hour in range(24):
        hour_str = f"{hour:02d}:00"
        count = hourly_counts.get(hour_str, 0)
        heatmap.append({
            "hour": hour_str,
            "count": count
        })
    
    # Find peak
    peak_hour = max(heatmap, key=lambda x: x['count']) if heatmap else None
    
    return {
        "heatmap": heatmap,
        "peak_hour": peak_hour['hour'] if peak_hour else None,
        "peak_count": peak_hour['count'] if peak_hour else 0
    }


# More endpoints to follow in next file...
# This is Part 1 of the backend implementation

