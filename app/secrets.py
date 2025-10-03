import os
import hmac
import hashlib
from typing import Optional


def get_env_secret(name: str) -> Optional[str]:
    val = os.getenv(name)
    if val is None or val == "":
        return None
    return val


def require_secret(name: str) -> str:
    val = get_env_secret(name)
    if not val:
        raise RuntimeError(f"Missing required secret: {name}")
    return val


def hmac_sign(message: str, *, key_env: str = "CALLSBOT_HMAC_KEY") -> str:
    key = get_env_secret(key_env) or ""
    digest = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest
