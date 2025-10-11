"""
Domain Models with Validation

Provides type-safe, validated data models for the application.
Uses dataclasses with validation to prevent NaN/Infinity and ensure data integrity.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import math


def _validate_finite(value: Optional[float], field_name: str = "value") -> Optional[float]:
    """Validate that a float is finite (not NaN or Infinity)"""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _validate_positive(value: Optional[float], field_name: str = "value") -> Optional[float]:
    """Validate that a value is positive"""
    validated = _validate_finite(value, field_name)
    if validated is not None and validated < 0:
        return None
    return validated


@dataclass
class TokenStats:
    """Validated token statistics from API"""
    # Required fields
    token_address: str
    
    # Price and market data
    price_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    
    # Volume data
    volume_24h_usd: Optional[float] = None
    unique_buyers_24h: Optional[int] = None
    unique_sellers_24h: Optional[int] = None
    
    # Price changes
    change_1h: Optional[float] = None
    change_24h: Optional[float] = None
    
    # Metadata
    name: Optional[str] = None
    symbol: Optional[str] = None
    
    # Security info
    is_mint_revoked: Optional[bool] = None
    is_lp_locked: Optional[bool] = None
    is_honeypot: Optional[bool] = None
    
    # Holder info
    top_10_concentration_percent: Optional[float] = None
    bundlers_percent: Optional[float] = None
    insiders_percent: Optional[float] = None
    holder_count: Optional[int] = None
    
    # Source tracking
    source: str = "unknown"
    fetched_at: float = field(default_factory=lambda: datetime.now().timestamp())
    
    # Raw data for extensions
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate all numeric fields after initialization"""
        # Validate and clean numeric fields
        self.price_usd = _validate_positive(self.price_usd, "price_usd")
        self.market_cap_usd = _validate_positive(self.market_cap_usd, "market_cap_usd")
        self.liquidity_usd = _validate_positive(self.liquidity_usd, "liquidity_usd")
        self.volume_24h_usd = _validate_positive(self.volume_24h_usd, "volume_24h_usd")
        
        # Change percentages can be negative
        self.change_1h = _validate_finite(self.change_1h, "change_1h")
        self.change_24h = _validate_finite(self.change_24h, "change_24h")
        
        # Validate concentrations (0-100%)
        if self.top_10_concentration_percent is not None:
            self.top_10_concentration_percent = _validate_finite(
                self.top_10_concentration_percent, 
                "top_10_concentration_percent"
            )
            if self.top_10_concentration_percent is not None:
                self.top_10_concentration_percent = max(0, min(100, self.top_10_concentration_percent))
        
        if self.bundlers_percent is not None:
            self.bundlers_percent = _validate_finite(self.bundlers_percent, "bundlers_percent")
            if self.bundlers_percent is not None:
                self.bundlers_percent = max(0, min(100, self.bundlers_percent))
        
        if self.insiders_percent is not None:
            self.insiders_percent = _validate_finite(self.insiders_percent, "insiders_percent")
            if self.insiders_percent is not None:
                self.insiders_percent = max(0, min(100, self.insiders_percent))
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any], source: str = "unknown") -> Optional["TokenStats"]:
        """Create TokenStats from API response, handling various schemas"""
        if not data or not isinstance(data, dict):
            return None
        
        try:
            # Extract token address
            token_address = data.get("token_address") or data.get("address") or data.get("mint")
            if not token_address:
                return None
            
            # Extract nested structures with fallbacks
            security = data.get("security", {}) or {}
            liquidity = data.get("liquidity", {}) or {}
            holders = data.get("holders", {}) or {}
            volume = data.get("volume", {}) or {}
            volume_24h = volume.get("24h", {}) or {}
            change = data.get("change", {}) or {}
            
            return cls(
                token_address=token_address,
                price_usd=data.get("price_usd"),
                market_cap_usd=data.get("market_cap_usd"),
                liquidity_usd=data.get("liquidity_usd") or liquidity.get("usd"),
                volume_24h_usd=volume_24h.get("volume_usd"),
                unique_buyers_24h=volume_24h.get("unique_buyers"),
                unique_sellers_24h=volume_24h.get("unique_sellers"),
                change_1h=change.get("1h"),
                change_24h=change.get("24h"),
                name=data.get("name"),
                symbol=data.get("symbol"),
                is_mint_revoked=security.get("is_mint_revoked"),
                is_lp_locked=(
                    liquidity.get("is_lp_locked") or
                    liquidity.get("is_lp_burned") or
                    (liquidity.get("lock_status") in ("locked", "burned"))
                ),
                is_honeypot=security.get("is_honeypot"),
                top_10_concentration_percent=(
                    holders.get("top_10_concentration_percent") or
                    holders.get("top10_percent")
                ),
                bundlers_percent=holders.get("bundlers_percent"),
                insiders_percent=holders.get("insiders_percent"),
                holder_count=holders.get("holder_count") or holders.get("holders"),
                source=source,
                raw_data=data
            )
        except Exception as e:
            # Log error but don't crash
            try:
                from app.logger_utils import log_process
                log_process({"type": "token_stats_parse_error", "error": str(e)})
            except Exception:
                pass
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API"""
        return {
            "token_address": self.token_address,
            "price_usd": self.price_usd,
            "market_cap_usd": self.market_cap_usd,
            "liquidity_usd": self.liquidity_usd,
            "volume_24h_usd": self.volume_24h_usd,
            "change_1h": self.change_1h,
            "change_24h": self.change_24h,
            "name": self.name,
            "symbol": self.symbol,
            "source": self.source,
        }


@dataclass
class TokenAlert:
    """Represents a token alert event"""
    token_address: str
    timestamp: float
    final_score: int
    preliminary_score: int
    conviction_type: str
    smart_money_detected: bool
    
    # Token info at alert time
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    
    # Market data at alert
    price_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    
    # Alert metadata
    telegram_sent: bool = False
    group_sent: bool = False
    redis_pushed: bool = False
    
    def __post_init__(self):
        """Validate fields"""
        self.price_usd = _validate_positive(self.price_usd)
        self.market_cap_usd = _validate_positive(self.market_cap_usd)
        self.liquidity_usd = _validate_positive(self.liquidity_usd)
        self.volume_24h_usd = _validate_positive(self.volume_24h_usd)
        
        # Validate scores
        self.final_score = max(0, min(10, self.final_score))
        self.preliminary_score = max(0, min(10, self.preliminary_score))


@dataclass
class FeedTransaction:
    """Represents a transaction from the feed"""
    token0_address: Optional[str] = None
    token1_address: Optional[str] = None
    token0_amount_usd: Optional[float] = None
    token1_amount_usd: Optional[float] = None
    usd_value: Optional[float] = None
    tx_type: Optional[str] = None
    dex: Optional[str] = None
    timestamp: Optional[float] = None
    smart_money: bool = False
    is_synthetic: bool = False
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and compute derived fields"""
        self.token0_amount_usd = _validate_positive(self.token0_amount_usd)
        self.token1_amount_usd = _validate_positive(self.token1_amount_usd)
        
        # Compute usd_value if not provided
        if self.usd_value is None:
            candidates = [
                self.token0_amount_usd,
                self.token1_amount_usd,
            ]
            valid_candidates = [c for c in candidates if c is not None and c > 0]
            if valid_candidates:
                self.usd_value = max(valid_candidates)
        else:
            self.usd_value = _validate_positive(self.usd_value)
    
    def get_candidate_token(self) -> Optional[str]:
        """Get the candidate token address (non-SOL token)"""
        sol_mint = "So11111111111111111111111111111111111111112"
        
        if self.token0_address == sol_mint and self.token1_address:
            return self.token1_address
        if self.token1_address == sol_mint and self.token0_address:
            return self.token0_address
        
        # Neither is SOL, choose token with higher USD value
        if (self.token1_amount_usd or 0) >= (self.token0_amount_usd or 0):
            return self.token1_address
        return self.token0_address


@dataclass
class TradingPosition:
    """Represents an open trading position"""
    position_id: int
    token_address: str
    strategy: str
    entry_price: float
    quantity: float
    usd_size: float
    entry_time: float
    peak_price: float
    trail_pct: float
    
    def current_pnl_pct(self, current_price: float) -> float:
        """Calculate current PnL percentage"""
        if self.entry_price <= 0:
            return 0.0
        return ((current_price - self.entry_price) / self.entry_price) * 100
    
    def stop_price(self, stop_pct: float) -> float:
        """Calculate stop loss price from entry"""
        return self.entry_price * (1.0 - stop_pct / 100.0)
    
    def trail_price(self) -> float:
        """Calculate trailing stop price from peak"""
        return self.peak_price * (1.0 - self.trail_pct / 100.0)


@dataclass
class ProcessResult:
    """Result of processing a feed item"""
    status: str  # 'alert_sent', 'skipped', 'error'
    token_address: Optional[str] = None
    final_score: Optional[int] = None
    preliminary_score: Optional[int] = None
    api_calls_saved: int = 0
    error_message: Optional[str] = None
    
    @property
    def is_alert(self) -> bool:
        return self.status == "alert_sent"
    
    @property
    def is_error(self) -> bool:
        return self.status == "error"

