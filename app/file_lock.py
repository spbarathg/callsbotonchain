"""
Cross-platform file locking utility.

Provides a unified context manager for advisory file locks
that work on both POSIX (fcntl) and Windows (msvcrt) systems.
"""
import os
import threading
from contextlib import contextmanager
from typing import Generator


# Thread-local storage for nested lock detection
_thread_locks = threading.local()


@contextmanager
def file_lock(path: str) -> Generator[None, None, None]:
    """
    Cross-platform advisory file lock using a sidecar .lock file.
    
    Works on both POSIX (fcntl) and Windows (msvcrt) systems.
    Thread-safe and supports nested locking within the same thread.
    
    Args:
        path: Path to the file or resource to lock
    
    Usage:
        with file_lock("var/data.json"):
            # Critical section - only one process can be here
            with open("var/data.json", "r") as f:
                data = json.load(f)
    
    Note:
        - Creates a .lock file adjacent to the target
        - Lock is advisory (not enforced by OS)
        - Automatically released on context exit
    """
    lock_path = f"{path}.lock"
    
    # Thread-local lock tracking for nested locks
    if not hasattr(_thread_locks, 'held'):
        _thread_locks.held = set()
    
    # If this thread already holds the lock, allow re-entry
    if lock_path in _thread_locks.held:
        yield
        return
    
    # Ensure directory exists
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except Exception:
        pass
    
    # Open lock file in binary append mode
    f = open(lock_path, "a+b")
    
    # Ensure at least 1 byte exists for Windows region locking
    try:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"\0")
            f.flush()
    except Exception:
        pass
    
    locked = False
    try:
        # Try POSIX flock first (preferred on Unix systems)
        try:
            import fcntl  # type: ignore
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                # Lock is held by another process
                try:
                    f.seek(0)
                    owner = f.read(64).decode("utf-8", errors="ignore").strip()
                    raise RuntimeError(f"Lock held by: {owner}")
                except Exception:
                    raise RuntimeError("Lock held by another process")
        except ImportError:
            # Windows: use msvcrt locking on the first byte
            import msvcrt  # type: ignore
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError:
                # Lock is held by another process
                try:
                    f.seek(0)
                    owner = f.read(64).decode("utf-8", errors="ignore").strip()
                    raise RuntimeError(f"Lock held by: {owner}")
                except Exception:
                    raise RuntimeError("Lock held by another process")
        
        # Write PID and hostname for debugging (fixed-length header)
        if locked:
            try:
                f.seek(0)
                ident = f"{os.getpid()}@{os.uname().nodename if hasattr(os, 'uname') else 'host'}"
                pid_bytes = ident.encode("utf-8")
                f.write(pid_bytes[:64].ljust(64, b" "))
                f.flush()
            except Exception:
                pass
        
        # Mark as held by this thread
        _thread_locks.held.add(lock_path)
        
        # Yield control to the critical section
        yield
        
    finally:
        # Remove from thread-local tracking
        try:
            _thread_locks.held.discard(lock_path)
        except Exception:
            pass
        
        # Release the lock
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
        
        # Close the file
        try:
            f.close()
        except Exception:
            pass


def is_locked(path: str) -> bool:
    """
    Check if a file is currently locked without blocking.
    
    Args:
        path: Path to check
        
    Returns:
        True if locked by another process, False otherwise
    """
    lock_path = f"{path}.lock"
    
    try:
        with open(lock_path, "a+b") as f:
            # Ensure at least 1 byte exists
            try:
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    return False  # No lock file = not locked
            except Exception:
                pass
            
            # Try to acquire non-blocking
            try:
                import fcntl  # type: ignore
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # We got the lock, so it wasn't locked
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    return False
                except BlockingIOError:
                    return True
            except ImportError:
                import msvcrt  # type: ignore
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    # We got the lock, so it wasn't locked
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    return False
                except OSError:
                    return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

