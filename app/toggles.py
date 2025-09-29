import json
import os
from typing import Dict, Any


_DEFAULTS = {
    "signals_enabled": True,
    "trading_enabled": False,
}


def _path() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "var")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "toggles.json")


def _load_raw() -> Dict[str, Any]:
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
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump({**_DEFAULTS, **data}, f, ensure_ascii=False, indent=2)
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





