"""
Token Classifier - Identify Memecoin Behavior Patterns
Classifies tokens as: FAST_MOVER, SLOW_GROWER, SUSTAINED, PUMP_DUMP
Adjusts exit strategy based on classification.
"""

import time
from typing import Dict, List, Optional, Tuple
from collections import deque
import statistics


class PriceHistory:
    """Track price history for pattern analysis"""
    
    def __init__(self, token_address: str, max_history: int = 100):
        self.token_address = token_address
        self.prices: deque = deque(maxlen=max_history)
        self.timestamps: deque = deque(maxlen=max_history)
        self.volumes: deque = deque(maxlen=max_history)
    
    def add_price(self, price: float, volume: float = 0):
        """Add a new price point"""
        self.prices.append(price)
        self.timestamps.append(time.time())
        self.volumes.append(volume)
    
    def get_velocity(self, hours: int = 24) -> Optional[float]:
        """Calculate price velocity (% change per hour)"""
        if len(self.prices) < 2:
            return None
        
        cutoff_time = time.time() - (hours * 3600)
        
        # Find first price point within time window
        start_price = None
        for i, ts in enumerate(self.timestamps):
            if ts >= cutoff_time:
                start_price = self.prices[i]
                break
        
        if start_price is None or start_price <= 0:
            return None
        
        end_price = self.prices[-1]
        elapsed_hours = (self.timestamps[-1] - self.timestamps[0]) / 3600
        
        if elapsed_hours <= 0:
            return None
        
        total_change_pct = ((end_price - start_price) / start_price) * 100
        velocity = total_change_pct / elapsed_hours
        
        return velocity
    
    def get_volatility(self) -> Optional[float]:
        """Calculate price volatility (standard deviation of returns)"""
        if len(self.prices) < 3:
            return None
        
        returns = []
        for i in range(1, len(self.prices)):
            if self.prices[i-1] > 0:
                ret = (self.prices[i] - self.prices[i-1]) / self.prices[i-1]
                returns.append(ret)
        
        if not returns:
            return None
        
        return statistics.stdev(returns)
    
    def get_volume_consistency(self) -> Optional[float]:
        """Calculate volume consistency (lower is more erratic)"""
        if len(self.volumes) < 3:
            return None
        
        volumes = [v for v in self.volumes if v > 0]
        if not volumes:
            return None
        
        avg_volume = statistics.mean(volumes)
        if avg_volume <= 0:
            return None
        
        # Coefficient of variation (lower = more consistent)
        std = statistics.stdev(volumes)
        cv = std / avg_volume
        
        # Return inverse (so higher = more consistent)
        consistency = 1.0 / (1.0 + cv)
        
        return consistency


class TokenClassifier:
    """
    Classify tokens by behavior pattern to optimize exit strategy
    
    Categories:
    - PUMP_DUMP: Fast pump, erratic volume → tight trailing stops
    - FAST_MOVER: Rapid gains, moderate volume → standard strategy
    - SLOW_GROWER: Steady growth, consistent volume → loose trailing stops
    - SUSTAINED: Strong momentum + consistent volume → hold longer
    """
    
    def __init__(self):
        self.price_histories: Dict[str, PriceHistory] = {}
        self.classifications: Dict[str, str] = {}
        self.classification_time: Dict[str, float] = {}
    
    def track_price(self, token_address: str, price: float, volume: float = 0):
        """Track a price point for a token"""
        if token_address not in self.price_histories:
            self.price_histories[token_address] = PriceHistory(token_address)
        
        self.price_histories[token_address].add_price(price, volume)
    
    def classify_token(self, token_address: str, holder_concentration: Optional[float] = None) -> Optional[str]:
        """
        Classify token behavior pattern
        
        Args:
            token_address: Token mint address
            holder_concentration: Top 10 holder concentration (0-100%)
        
        Returns:
            Classification string or None if insufficient data
        """
        if token_address not in self.price_histories:
            return None
        
        history = self.price_histories[token_address]
        
        # Need at least 10 data points
        if len(history.prices) < 10:
            return None
        
        # Get metrics
        velocity_24h = history.get_velocity(hours=24)
        velocity_1h = history.get_velocity(hours=1)
        volatility = history.get_volatility()
        volume_consistency = history.get_volume_consistency()
        
        if velocity_24h is None or volatility is None:
            return None
        
        # Classification logic
        classification = "FAST_MOVER"  # Default
        
        # 1. PUMP_DUMP: Fast pump + high volatility + erratic volume
        if velocity_1h and velocity_1h > 200:  # >200% per hour
            if volatility > 0.3:  # High volatility
                if volume_consistency and volume_consistency < 0.3:  # Erratic volume
                    classification = "PUMP_DUMP"
        
        # 2. SLOW_GROWER: Steady growth + low volatility + consistent volume
        elif velocity_24h < 50:  # <50% per day (moderate)
            if volatility < 0.15:  # Low volatility
                if volume_consistency and volume_consistency > 0.7:  # Consistent volume
                    classification = "SLOW_GROWER"
        
        # 3. SUSTAINED: Strong momentum + low volatility + consistent volume
        elif velocity_24h > 100:  # >100% per day
            if volatility < 0.2:  # Moderate-low volatility
                if volume_consistency and volume_consistency > 0.6:  # Good consistency
                    classification = "SUSTAINED"
        
        # 4. Consider holder concentration (if available)
        if holder_concentration and holder_concentration > 80:
            # Very concentrated = likely pump and dump
            classification = "PUMP_DUMP"
        
        # Cache classification
        self.classifications[token_address] = classification
        self.classification_time[token_address] = time.time()
        
        return classification
    
    def get_classification(self, token_address: str, max_age_seconds: int = 3600) -> Optional[str]:
        """Get cached classification (if recent)"""
        if token_address not in self.classifications:
            return None
        
        # Check age
        age = time.time() - self.classification_time.get(token_address, 0)
        if age > max_age_seconds:
            return None
        
        return self.classifications[token_address]
    
    def get_recommended_trail_pct(self, token_address: str) -> Optional[float]:
        """
        Get recommended trailing stop percentage based on classification
        
        Returns:
            Trailing stop percentage (10-40%) or None if no classification
        """
        classification = self.get_classification(token_address)
        
        if classification is None:
            return None
        
        # Different strategies per classification
        trail_pct_map = {
            "PUMP_DUMP": 12.0,      # Tight trail (lock gains fast)
            "FAST_MOVER": 15.0,     # Standard trail
            "SLOW_GROWER": 25.0,    # Loose trail (let it run)
            "SUSTAINED": 20.0,      # Moderate trail
        }
        
        return trail_pct_map.get(classification, 15.0)
    
    def should_hold_longer(self, token_address: str) -> bool:
        """
        Determine if token should be held longer based on classification
        
        Returns:
            True if token shows sustained/slow growth patterns
        """
        classification = self.get_classification(token_address)
        
        return classification in ["SUSTAINED", "SLOW_GROWER"]
    
    def should_exit_faster(self, token_address: str) -> bool:
        """
        Determine if token should be exited faster based on classification
        
        Returns:
            True if token shows pump/dump patterns
        """
        classification = self.get_classification(token_address)
        
        return classification == "PUMP_DUMP"
    
    def get_stats(self, token_address: str) -> Dict:
        """Get classification stats for a token"""
        if token_address not in self.price_histories:
            return {}
        
        history = self.price_histories[token_address]
        classification = self.get_classification(token_address)
        
        return {
            "token": token_address[:8] + "...",
            "classification": classification or "UNKNOWN",
            "data_points": len(history.prices),
            "velocity_24h": history.get_velocity(hours=24),
            "velocity_1h": history.get_velocity(hours=1),
            "volatility": history.get_volatility(),
            "volume_consistency": history.get_volume_consistency(),
            "recommended_trail": self.get_recommended_trail_pct(token_address),
        }


# Global classifier instance
_classifier = None

def get_classifier() -> TokenClassifier:
    """Get global token classifier instance"""
    global _classifier
    if _classifier is None:
        _classifier = TokenClassifier()
    return _classifier



