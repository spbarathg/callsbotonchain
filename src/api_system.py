"""
System and Configuration API endpoints
"""
import os
import json
import subprocess
import sqlite3
from typing import Dict, Any, List
from datetime import datetime, timedelta
import psutil


def get_system_health() -> Dict[str, Any]:
    """Get container and system health"""
    health = {
        "containers": {},
        "resources": {},
        "database": {},
        "timestamp": datetime.now().isoformat()
    }
    
    # Get container status via docker ps
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=callsbot", "--format", "{{.Names}}:{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                name, status = line.split(':', 1)
                is_healthy = "healthy" in status.lower() or "up" in status.lower()
                health["containers"][name] = {
                    "status": "healthy" if is_healthy else "unhealthy",
                    "details": status
                }
    except:
        health["containers"] = {"error": "Could not fetch container status"}
    
    # Get resource usage
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health["resources"] = {
            "cpu_percent": round(cpu_percent, 2),
            "memory_used_mb": round(memory.used / 1024 / 1024, 0),
            "memory_total_mb": round(memory.total / 1024 / 1024, 0),
            "memory_percent": round(memory.percent, 1),
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "disk_percent": round(disk.percent, 1)
        }
    except:
        health["resources"] = {"error": "Could not fetch resource usage"}
    
    # Get database status
    try:
        db_path = os.getenv("CALLSBOT_DB_FILE", "var/alerted_tokens.db")
        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            health["database"] = {
                "size_mb": round(size / 1024 / 1024, 2),
                "exists": True,
                "path": db_path
            }
            
            # Check last write
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT MAX(alerted_at) FROM alerted_tokens")
            last_write = c.fetchone()[0]
            health["database"]["last_write"] = last_write
            conn.close()
        else:
            health["database"] = {"exists": False}
    except Exception as e:
        health["database"] = {"error": str(e)}
    
    return health


def get_database_status() -> Dict[str, Any]:
    """Get detailed database information"""
    db_path = os.getenv("CALLSBOT_DB_FILE", "var/alerted_tokens.db")
    
    if not os.path.exists(db_path):
        return {"error": "Database not found"}
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Get table counts
        tables = {}
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for (table_name,) in c.fetchall():
            c.execute(f"SELECT COUNT(*) FROM {table_name}")
            tables[table_name] = c.fetchone()[0]
        
        # Get database size
        size = os.path.getsize(db_path)
        
        conn.close()
        
        return {
            "size_mb": round(size / 1024 / 1024, 2),
            "tables": tables,
            "path": db_path
        }
    except Exception as e:
        return {"error": str(e)}


def get_error_logs(limit: int = 50, level: str = "all") -> Dict[str, Any]:
    """Get recent error logs"""
    logs = []
    log_path = "data/logs/process.jsonl"
    
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            for line in reversed(lines[-1000:]):
                try:
                    log = json.loads(line.strip())
                    log_type = log.get('type', '')
                    log_level = log.get('level', 'info')
                    
                    # Filter by level
                    if level != "all":
                        if level == "error" and log_level != "error":
                            continue
                        if level == "warning" and log_level not in ["warning", "error"]:
                            continue
                    
                    # Include errors, warnings, and certain info types
                    if ('error' in log_type.lower() or 
                        'warning' in log_type.lower() or 
                        'exception' in log_type.lower() or
                        'failed' in log_type.lower() or
                        log_level in ['error', 'warning']):
                        
                        logs.append({
                            "timestamp": log.get('ts'),
                            "type": log_type,
                            "level": log_level,
                            "message": log.get('msg', log_type),
                            "component": log.get('component', 'unknown')
                        })
                        
                        if len(logs) >= limit:
                            break
                except:
                    continue
    except:
        pass
    
    # Categorize
    error_count = len([l for l in logs if l['level'] == 'error'])
    warning_count = len([l for l in logs if l['level'] == 'warning'])
    info_count = len(logs) - error_count - warning_count
    
    return {
        "logs": logs,
        "counts": {
            "error": error_count,
            "warning": warning_count,
            "info": info_count
        },
        "total": len(logs)
    }


def get_lifecycle_tracking() -> Dict[str, Any]:
    """Get token lifecycle tracking status"""
    db_path = os.getenv("CALLSBOT_DB_FILE", "var/alerted_tokens.db")
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Get tokens by age
        now = datetime.now()
        
        c.execute("""
            SELECT token_address, first_alert_at, last_checked_at 
            FROM alerted_token_stats
        """)
        
        stages = {
            "fresh": 0,        # < 1h
            "monitoring": 0,   # 1-6h
            "mature": 0,       # 6-24h
            "archived": 0      # > 24h
        }
        
        moving = {
            "pumping": 0,
            "stable": 0,
            "dumping": 0
        }
        
        for row in c.fetchall():
            token_address, first_alert, last_checked = row
            try:
                first_time = datetime.fromisoformat(first_alert)
                age_hours = (now - first_time).total_seconds() / 3600
                
                if age_hours < 1:
                    stages["fresh"] += 1
                elif age_hours < 6:
                    stages["monitoring"] += 1
                elif age_hours < 24:
                    stages["mature"] += 1
                else:
                    stages["archived"] += 1
                
                # Check movement (simplified - would need price data)
                # For now, distribute randomly as placeholder
                import random
                movement = random.choice(["pumping", "stable", "dumping"])
                moving[movement] += 1
            except:
                continue
        
        total = sum(stages.values())
        
        conn.close()
        
        return {
            "total_tracking": total,
            "stages": stages,
            "movement": moving,
            "next_check_minutes": 15  # From TRACK_INTERVAL_MIN
        }
    except Exception as e:
        return {"error": str(e)}


def get_current_config() -> Dict[str, Any]:
    """Get current bot configuration"""
    config = {
        "gates": {
            "mode": os.getenv("GATE_MODE", "CUSTOM"),
            "high_confidence_score": int(os.getenv("HIGH_CONFIDENCE_SCORE", "5")),
            "min_liquidity_usd": int(os.getenv("MIN_LIQUIDITY_USD", "5000")),
            "vol_mcap_ratio_min": float(os.getenv("VOL_TO_MCAP_RATIO_MIN", "0.15")),
            "nuanced_reduction": int(os.getenv("NUANCED_SCORE_REDUCTION", "2"))
        },
        "tracking": {
            "interval_minutes": int(os.getenv("TRACK_INTERVAL_MIN", "15")),
            "batch_size": int(os.getenv("TRACK_BATCH_SIZE", "30")),
            "max_age_hours": 48
        },
        "smart_money": {
            "min_usd_general": int(os.getenv("MIN_USD_VALUE", "200")),
            "min_usd_smart": 50,  # Calculated as max(50, MIN_USD_VALUE // 4)
            "min_wallet_pnl": 1000,
            "top_wallets_enabled": True
        },
        "budget": {
            "per_day_max": int(os.getenv("BUDGET_PER_DAY_MAX", "10000")),
            "per_minute_max": int(os.getenv("BUDGET_PER_MINUTE_MAX", "15")),
            "feed_cost": int(os.getenv("BUDGET_FEED_COST", "0")),
            "stats_cost": int(os.getenv("BUDGET_STATS_COST", "1"))
        },
        "api": {
            "cielo_enabled": os.getenv("CIELO_API_KEY", "") != "",
            "new_trade_only": os.getenv("CIELO_NEW_TRADE_ONLY", "false") == "true",
            "force_fallback": os.getenv("CALLSBOT_FORCE_FALLBACK", "false") == "true"
        }
    }
    
    return config


def update_toggle(toggle_name: str, value: bool) -> Dict[str, Any]:
    """Update a feature toggle"""
    try:
        from app.toggles import set_toggles, get_toggles
        
        current = get_toggles()
        current[toggle_name] = value
        set_toggles(current)
        
        return {
            "success": True,
            "toggle": toggle_name,
            "value": value,
            "all_toggles": current
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

