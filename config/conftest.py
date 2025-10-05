import os
import sys

# Avoid importing external pytest plugins that may not be compatible in this environment
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


def _ensure_repo_on_path() -> None:
    root = os.path.abspath(os.path.dirname(__file__) or os.getcwd())
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_repo_on_path()
