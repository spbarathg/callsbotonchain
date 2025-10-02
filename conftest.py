import os
import sys


def _ensure_repo_on_path() -> None:
    root = os.path.abspath(os.path.dirname(__file__) or os.getcwd())
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_repo_on_path()


