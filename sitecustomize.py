import os

# Ensure pytest does not auto-load third-party plugins that may not be compatible
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
