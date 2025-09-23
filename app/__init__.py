import os


def _load_env_file() -> None:
    # Load simple KEY=VALUE pairs from a project-level .env file if present.
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env_path = os.path.join(base_dir, ".env")
        if not os.path.isfile(env_path):
            # Try current working directory as fallback
            env_path = ".env"
            if not os.path.isfile(env_path):
                return
        
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"\'")
                # Do not overwrite existing environment variables
                if key and (key not in os.environ):
                    os.environ[key] = val
    except Exception as e:
        # Log environment loading errors for debugging
        import logging
        logging.warning("Failed to load .env file: %s", e)


# Load .env before other modules import environment values
_load_env_file()


__all__ = []
