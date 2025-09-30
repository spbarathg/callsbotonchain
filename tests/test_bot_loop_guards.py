from scripts.bot import acquire_singleton_lock, _release_singleton_lock, PROJECT_ROOT
import os


def test_singleton_lock_reacquire_same_process(tmp_path):
    # Use temp lock path by pointing var dir under tmp
    var_dir = tmp_path / "var"
    os.makedirs(var_dir, exist_ok=True)
    lock_path = os.path.join(PROJECT_ROOT, "var", "bot.lock")
    try:
        # Ensure no stale lock
        if os.path.exists(lock_path):
            try: os.remove(lock_path)
            except Exception: pass
        ok1 = acquire_singleton_lock()
        ok2 = acquire_singleton_lock()
        assert ok1 is True
        assert ok2 is True
    finally:
        try:
            _release_singleton_lock(lock_path)
        except Exception:
            pass


