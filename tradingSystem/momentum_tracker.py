"""
MOMENTUM INTELLIGENCE SYSTEM
Tracks token velocity and strength in first 5 minutes to predict winners vs losers
"""
import time
from typing import Dict, Tuple, Optional


class MomentumTracker:
    """Tracks early price momentum to detect scams and optimize exits"""
    
    def __init__(self):
        # token -> {'entry_price': float, 'entry_time': float, 'samples': [(timestamp, price)]}
        self._momentum_data: Dict[str, Dict] = {}
        
        # Momentum thresholds (calibrated from real trading data)
        self.SCAM_THRESHOLD_60S = -15.0  # If -15% in 60s → instant exit
        self.STRONG_MOMENTUM_5MIN = 20.0  # +20% in 5min = strong token
        self.MODERATE_MOMENTUM_5MIN = 5.0  # +5% in 5min = moderate
        # Anything below = weak token
    
    def init_position(self, token: str, entry_price: float, entry_time: float):
        """Initialize momentum tracking for a new position"""
        self._momentum_data[token] = {
            'entry_price': entry_price,
            'entry_time': entry_time,
            'samples': [(entry_time, entry_price)],
            'scam_checked': False,
            'momentum_score': None,
            'momentum_calculated': False
        }
    
    def add_price_sample(self, token: str, price: float):
        """Add a price sample for momentum calculation"""
        if token not in self._momentum_data:
            return
        
        data = self._momentum_data[token]
        current_time = time.time()
        data['samples'].append((current_time, price))
        
        # Keep only last 10 minutes of samples
        cutoff_time = current_time - 600
        data['samples'] = [(t, p) for t, p in data['samples'] if t > cutoff_time]
    
    def check_scam(self, token: str, current_price: float) -> Tuple[bool, str]:
        """
        Check if token shows scam signature in first 60 seconds
        Returns: (is_scam, reason)
        """
        if token not in self._momentum_data:
            return False, ""
        
        data = self._momentum_data[token]
        
        # Only check once in first 60 seconds
        if data['scam_checked']:
            return False, ""
        
        entry_time = data['entry_time']
        entry_price = data['entry_price']
        time_elapsed = time.time() - entry_time
        
        # Check within first 60 seconds
        if time_elapsed <= 60:
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
            
            if price_change_pct <= self.SCAM_THRESHOLD_60S:
                # SCAM DETECTED!
                data['scam_checked'] = True
                return True, f"Price dropped {price_change_pct:.1f}% in first {time_elapsed:.0f}s (scam signature)"
        elif time_elapsed > 60:
            # Past 60 seconds, mark as checked
            data['scam_checked'] = True
        
        return False, ""
    
    def calculate_momentum(self, token: str, current_price: float) -> Optional[str]:
        """
        Calculate momentum strength after 5 minutes
        Returns: 'strong', 'moderate', or 'weak'
        """
        if token not in self._momentum_data:
            return None
        
        data = self._momentum_data[token]
        
        # Only calculate once after 5 minutes
        if data['momentum_calculated']:
            return data['momentum_score']
        
        entry_time = data['entry_time']
        entry_price = data['entry_price']
        time_elapsed = time.time() - entry_time
        
        # Calculate after 5 minutes
        if time_elapsed >= 300:  # 5 minutes
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
            
            if price_change_pct >= self.STRONG_MOMENTUM_5MIN:
                momentum = 'strong'
            elif price_change_pct >= self.MODERATE_MOMENTUM_5MIN:
                momentum = 'moderate'
            else:
                momentum = 'weak'
            
            data['momentum_score'] = momentum
            data['momentum_calculated'] = True
            
            return momentum
        
        return None
    
    def get_momentum_exit_threshold(self, token: str) -> Optional[float]:
        """
        Get the profit exit threshold based on momentum
        Returns profit percentage where bot should exit
        """
        if token not in self._momentum_data:
            return None
        
        data = self._momentum_data[token]
        momentum = data.get('momentum_score')
        
        if momentum is None:
            return None
        
        # Momentum-based exit strategy:
        # - Strong tokens: Hold for 100%+ moonshot potential
        # - Moderate tokens: Exit at +40% to capture profit before reversal
        # - Weak tokens: Exit at +30% or use tight trailing stop
        if momentum == 'strong':
            return None  # No early exit, hold for moonshot
        elif momentum == 'moderate':
            return 40.0  # Exit at +40%
        else:  # weak
            return 30.0  # Exit at +30%
    
    def get_adaptive_trailing_stop(self, token: str) -> Optional[float]:
        """
        Get adaptive trailing stop percentage based on momentum
        """
        if token not in self._momentum_data:
            return None
        
        data = self._momentum_data[token]
        momentum = data.get('momentum_score')
        
        if momentum is None:
            return None  # Use default trail
        
        # Adaptive trailing stops:
        # - Strong tokens: 40% trail (let it breathe)
        # - Moderate tokens: 35% trail (standard)
        # - Weak tokens: 25% trail (tight, quick exit)
        if momentum == 'strong':
            return 40.0
        elif momentum == 'moderate':
            return 35.0
        else:  # weak
            return 25.0
    
    def cleanup(self, token: str):
        """Remove tracking data for closed position"""
        if token in self._momentum_data:
            del self._momentum_data[token]
    
    def get_position_age(self, token: str) -> Optional[float]:
        """Get position age in seconds"""
        if token not in self._momentum_data:
            return None
        
        entry_time = self._momentum_data[token]['entry_time']
        return time.time() - entry_time

