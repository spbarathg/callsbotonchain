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
WALLET_SECRET = os.getenv("TS_WALLET_SECRET", "")  # base58 privkey or JSON array of bytes
SLIPPAGE_BPS = _get_int("TS_SLIPPAGE_BPS", 150)  # 1.50%

# Base asset for accounting (default USDC)
USDC_MINT = os.getenv("TS_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
BASE_MINT = os.getenv("TS_BASE_MINT", USDC_MINT)

# Risk and sizing
MAX_CONCURRENT = _get_int("TS_MAX_CONCURRENT", 3)
BANKROLL_USD = _get_float("TS_BANKROLL_USD", 500)
CORE_SIZE_USD = _get_float("TS_CORE_SIZE_USD", 60)
SCOUT_SIZE_USD = _get_float("TS_SCOUT_SIZE_USD", 30)

# Stops/Trails
CORE_STOP_PCT = _get_float("TS_CORE_STOP_PCT", 12.0)  # hard stop
SCOUT_STOP_PCT = _get_float("TS_SCOUT_STOP_PCT", 8.0)
TRAIL_DEFAULT_PCT = _get_float("TS_TRAIL_DEFAULT_PCT", 22.0)
TRAIL_TIGHT_PCT = _get_float("TS_TRAIL_TIGHT_PCT", 16.0)
TRAIL_WIDE_PCT = _get_float("TS_TRAIL_WIDE_PCT", 25.0)

# Entry gates (mirror bot)
MIN_LP_USD = _get_float("TS_MIN_LP_USD", 15000)
RATIO_MIN = _get_float("TS_RATIO_MIN", 0.45)
MCAP_MAX = _get_float("TS_MCAP_MAX", 1_500_000)
MOMENTUM_1H_GATE = _get_float("TS_MOMENTUM_1H_GATE", 20.0)

# Paths
BOT_STDOUT_LOG = os.getenv("TS_BOT_STDOUT_LOG", "data/logs/stdout.log")
DB_PATH = os.getenv("TS_DB_PATH", "var/trading.db")

# Logging
LOG_JSON_PATH = os.getenv("TS_LOG_JSON", "data/logs/trading.jsonl")
LOG_TEXT_PATH = os.getenv("TS_LOG_TEXT", "data/logs/trading.log")

# Mode
DRY_RUN = _get_bool("TS_DRY_RUN", True)


