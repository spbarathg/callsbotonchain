import json
import os
from typing import Dict, Any
from contextlib import contextmanager


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
        with _lock_file(_path()):
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
        with _lock_file(p):
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


# --------- Cross-process lock helper ---------
@contextmanager
def _lock_file(path: str):
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    f = open(lock_path, "a+b")
    locked = False
    try:
        try:
            import fcntl  # type: ignore
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                locked = True
            except Exception:
                locked = False
        except ImportError:
            try:
                import msvcrt  # type: ignore
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                locked = True
            except Exception:
                locked = False
        yield
    finally:
        try:
            if locked:
                try:
                    import fcntl  # type: ignore
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    try:
                        import msvcrt  # type: ignore
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            f.close()
        except Exception:
            pass









