"""
Dependency Injection Container

Provides centralized dependency management and configuration.
Implements the Service Locator pattern for easier testing and modularity.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class AppConfig:
    """Centralized application configuration"""
    # Core settings
    dry_run: bool
    debug: bool
    high_confidence_score: int
    
    # API Keys
    cielo_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    solana_wallet_secret: str
    solana_rpc_url: str
    
    # Database paths
    storage_db_path: str
    trading_db_path: str
    
    # Feature flags
    use_cielo_stats: bool
    ml_enhancement_enabled: bool
    portfolio_enabled: bool
    
    # Risk gates
    min_liquidity_usd: float
    max_top10_concentration: float
    
    # Budget
    enable_budget: bool
    budget_max_per_minute: int
    budget_max_per_day: int
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables"""
        try:
            from app.config_unified import (
                DRY_RUN, DEBUG_PRELIM, HIGH_CONFIDENCE_SCORE,
                CIELO_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                SOLANA_WALLET_SECRET, SOLANA_RPC_URL,
                STORAGE_DB_FILE, TRADING_DB_PATH,
                USE_CIELO_STATS, ML_ENHANCEMENT_ENABLED, PORTFOLIO_ENABLED,
                MIN_LIQUIDITY_USD, MAX_TOP10_CONCENTRATION,
                ENABLE_BUDGET, BUDGET_MAX_PER_MINUTE, BUDGET_MAX_PER_DAY,
            )
            
            return cls(
                dry_run=DRY_RUN,
                debug=DEBUG_PRELIM,
                high_confidence_score=HIGH_CONFIDENCE_SCORE,
                cielo_api_key=CIELO_API_KEY,
                telegram_bot_token=TELEGRAM_BOT_TOKEN,
                telegram_chat_id=TELEGRAM_CHAT_ID,
                solana_wallet_secret=SOLANA_WALLET_SECRET,
                solana_rpc_url=SOLANA_RPC_URL,
                storage_db_path=STORAGE_DB_FILE,
                trading_db_path=TRADING_DB_PATH,
                use_cielo_stats=USE_CIELO_STATS,
                ml_enhancement_enabled=ML_ENHANCEMENT_ENABLED,
                portfolio_enabled=PORTFOLIO_ENABLED,
                min_liquidity_usd=MIN_LIQUIDITY_USD,
                max_top10_concentration=MAX_TOP10_CONCENTRATION,
                enable_budget=ENABLE_BUDGET,
                budget_max_per_minute=BUDGET_MAX_PER_MINUTE,
                budget_max_per_day=BUDGET_MAX_PER_DAY,
            )
        except ImportError:
            # Fallback to legacy config if unified config not available
            from config.config import (
                DRY_RUN, DEBUG_PRELIM, HIGH_CONFIDENCE_SCORE,
                CIELO_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                STORAGE_DB_FILE,
                USE_CIELO_STATS, MIN_LIQUIDITY_USD, MAX_TOP10_CONCENTRATION,
                ENABLE_BUDGET, BUDGET_MAX_PER_MINUTE, BUDGET_MAX_PER_DAY,
            )
            
            import os
            
            return cls(
                dry_run=str(DRY_RUN).lower() == 'true',
                debug=DEBUG_PRELIM,
                high_confidence_score=HIGH_CONFIDENCE_SCORE,
                cielo_api_key=CIELO_API_KEY,
                telegram_bot_token=TELEGRAM_BOT_TOKEN,
                telegram_chat_id=TELEGRAM_CHAT_ID,
                solana_wallet_secret=os.getenv("SOLANA_WALLET_SECRET", ""),
                solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
                storage_db_path=STORAGE_DB_FILE,
                trading_db_path=os.getenv("TRADING_DB_PATH", "var/trading.db"),
                use_cielo_stats=USE_CIELO_STATS,
                ml_enhancement_enabled=False,
                portfolio_enabled=False,
                min_liquidity_usd=MIN_LIQUIDITY_USD,
                max_top10_concentration=MAX_TOP10_CONCENTRATION,
                enable_budget=ENABLE_BUDGET,
                budget_max_per_minute=BUDGET_MAX_PER_MINUTE,
                budget_max_per_day=BUDGET_MAX_PER_DAY,
            )


class Container:
    """
    Dependency injection container.
    
    Manages application dependencies and provides them to components.
    Implements lazy initialization and singleton pattern.
    """
    
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.from_env()
        self._instances: Dict[str, Any] = {}
    
    def get_config(self) -> AppConfig:
        """Get application configuration"""
        return self.config
    
    def get_repository_factory(self):
        """Get repository factory (singleton)"""
        if "repository_factory" not in self._instances:
            from app.repositories import RepositoryFactory
            self._instances["repository_factory"] = RepositoryFactory(
                db_path=self.config.storage_db_path
            )
        return self._instances["repository_factory"]
    
    def get_alert_repository(self):
        """Get alert repository"""
        factory = self.get_repository_factory()
        return factory.create_alert_repository()
    
    def get_performance_repository(self):
        """Get performance repository"""
        factory = self.get_repository_factory()
        return factory.create_performance_repository()
    
    def get_activity_repository(self):
        """Get activity repository"""
        factory = self.get_repository_factory()
        return factory.create_activity_repository()
    
    def get_budget_manager(self):
        """Get budget manager (singleton)"""
        if "budget_manager" not in self._instances:
            from app.budget import get_budget
            self._instances["budget_manager"] = get_budget()
        return self._instances["budget_manager"]
    
    def get_signal_processor(self):
        """Get signal processor (singleton)"""
        if "signal_processor" not in self._instances:
            from app.signal_processor import SignalProcessor
            # Build config dict for signal processor
            config_dict = {
                "high_confidence_score": self.config.high_confidence_score,
                "min_liquidity_usd": self.config.min_liquidity_usd,
            }
            self._instances["signal_processor"] = SignalProcessor(config_dict)
        return self._instances["signal_processor"]
    
    def get_ml_scorer(self):
        """Get ML scorer if enabled"""
        if not self.config.ml_enhancement_enabled:
            return None
        
        if "ml_scorer" not in self._instances:
            try:
                from app.ml_scorer import get_ml_scorer
                self._instances["ml_scorer"] = get_ml_scorer()
            except ImportError:
                return None
        return self._instances["ml_scorer"]
    
    def get_http_client(self):
        """Get HTTP client (uses module-level singleton)"""
        from app.http_client import get_session
        return get_session()
    
    def reset(self):
        """Reset all singletons (for testing)"""
        self._instances.clear()


# Global container instance
_container: Optional[Container] = None


def get_container(config: Optional[AppConfig] = None) -> Container:
    """Get the global dependency injection container"""
    global _container
    if _container is None:
        _container = Container(config)
    return _container


def reset_container():
    """Reset the global container (for testing)"""
    global _container
    if _container:
        _container.reset()
    _container = None

