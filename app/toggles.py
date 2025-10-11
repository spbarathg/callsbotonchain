import json
import os
from typing import Dict, Any
from app.file_lock import file_lock


_DEFAULTS = {
    "signals_enabled": True,
    "trading_enabled": False,
}


def _path() -> str:
    env_base = os.getenv("CALLSBOT_VAR_DIR")
    base = env_base or os.path.join(os.path.dirname(os.path.dirname(__file__)), "var")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "toggles.json")


def _load_raw() -> Dict[str, Any]:
    try:
        with file_lock(_path()):
            try:
                with open(_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        return dict(_DEFAULTS)
                    return {**_DEFAULTS, **data}
            except FileNotFoundError:
                return dict(_DEFAULTS)
    except Exception:
        return dict(_DEFAULTS)


def _save_raw(data: Dict[str, Any]) -> None:
    try:
        p = _path()
        with file_lock(p):
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({**_DEFAULTS, **data}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
    except Exception:
        pass


def get_toggles() -> Dict[str, Any]:
    return _load_raw()


def set_toggles(updates: Dict[str, Any]) -> Dict[str, Any]:
    cur = _load_raw()
    cur.update({k: bool(v) for k, v in updates.items() if k in _DEFAULTS})
    _save_raw(cur)
    return cur


def signals_enabled() -> bool:
    return bool(_load_raw().get("signals_enabled", True))


def trading_enabled() -> bool:
    return bool(_load_raw().get("trading_enabled", False))
