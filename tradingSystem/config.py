import os


def _get_float(name: str, default: float) -> float:
	try:
		return float(os.getenv(name, str(default)))
	except Exception:
		return default


def _get_int(name: str, default: int) -> int:
	try:
		return int(os.getenv(name, str(default)))
	except Exception:
		return default


def _get_bool(name: str, default: bool) -> bool:
	val = os.getenv(name)
	if val is None:
		return default
	return val.strip().lower() in ("1", "true", "yes", "on")


# Wallet/Execution
RPC_URL = os.getenv("TS_RPC_URL", "https://api.mainnet-beta.solana.com")
JITO_URL = os.getenv("TS_JITO_URL", "")
PRIORITY_FEE_MICROLAMPORTS = _get_int("TS_PRIORITY_FEE_MICROLAMPORTS", 8000)
JITO_TIP_SOL = _get_float("TS_JITO_TIP_SOL", 0.0006)
# SECURITY WARNING: Do NOT store real private keys in plaintext environment variables in production.
# Use a proper secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager, Google Secret Manager)
# and inject the secret securely at runtime. Local/dev only: base58 privkey or JSON array of bytes.
WALLET_SECRET = os.getenv("TS_WALLET_SECRET", "")  # base58 privkey or JSON array of bytes
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 150)  # 1.50%

# Base asset for accounting (default USDC)
USDC_MINT = os.getenv("TS_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
BASE_MINT = os.getenv("TS_BASE_MINT", USDC_MINT)

# Risk and sizing (optimized for $500 bankroll)
MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 5)  # Allow 5 positions for better utilization
BANKROLL_USD = _get_float("TS_BANKROLL_USD", 500)
CORE_SIZE_USD = _get_float("TS_CORE_SIZE_USD", 70)  # Smart Money signals - highest conviction
SCOUT_SIZE_USD = _get_float("TS_SCOUT_SIZE_USD", 40)  # High velocity plays
STRICT_SIZE_USD = _get_float("TS_STRICT_SIZE_USD", 50)  # High Confidence (Strict) - good but not smart
NUANCED_SIZE_USD = _get_float("TS_NUANCED_SIZE_USD", 25)  # Nuanced - smallest, riskiest

# Stops/Trails (optimized for memecoin volatility)
CORE_STOP_PCT = _get_float("TS_CORE_STOP_PCT", 15.0)  # Wider stop for runner (smart money)
SCOUT_STOP_PCT = _get_float("TS_SCOUT_STOP_PCT", 10.0)  # Tighter for velocity plays
STRICT_STOP_PCT = _get_float("TS_STRICT_STOP_PCT", 12.0)  # Balanced for strict
NUANCED_STOP_PCT = _get_float("TS_NUANCED_STOP_PCT", 8.0)  # Tightest for nuanced
TRAIL_DEFAULT_PCT = _get_float("TS_TRAIL_DEFAULT_PCT", 22.0)
TRAIL_TIGHT_PCT = _get_float("TS_TRAIL_TIGHT_PCT", 16.0)
TRAIL_WIDE_PCT = _get_float("TS_TRAIL_WIDE_PCT", 25.0)

# Entry gates for runner (Smart Money - strictest)
MIN_LP_USD = _get_float("TS_MIN_LP_USD", 15000)
RATIO_MIN = _get_float("TS_RATIO_MIN", 0.45)
MCAP_MAX = _get_float("TS_MCAP_MAX", 1_500_000)
MOMENTUM_1H_GATE = _get_float("TS_MOMENTUM_1H_GATE", 20.0)

# Entry gates for strict (High Confidence without smart money - slightly relaxed)
STRICT_MIN_LP_USD = _get_float("TS_STRICT_MIN_LP_USD", 10000)
STRICT_RATIO_MIN = _get_float("TS_STRICT_RATIO_MIN", 0.35)
STRICT_MCAP_MAX = _get_float("TS_STRICT_MCAP_MAX", 2_000_000)

# Entry gates for nuanced (Lowest confidence - strictest to compensate)
NUANCED_MIN_LP_USD = _get_float("TS_NUANCED_MIN_LP_USD", 12000)
NUANCED_RATIO_MIN = _get_float("TS_NUANCED_RATIO_MIN", 0.55)
NUANCED_MCAP_MAX = _get_float("TS_NUANCED_MCAP_MAX", 1_000_000)

# Paths
BOT_STDOUT_LOG = os.getenv("TS_BOT_STDOUT_LOG", "data/logs/stdout.log")
DB_PATH = os.getenv("TS_DB_PATH", "var/trading.db")

# Logging
LOG_JSON_PATH = os.getenv("TS_LOG_JSON", "data/logs/trading.jsonl")
LOG_TEXT_PATH = os.getenv("TS_LOG_TEXT", "data/logs/trading.log")

# Mode
DRY_RUN = _get_bool("TS_DRY_RUN", True)


