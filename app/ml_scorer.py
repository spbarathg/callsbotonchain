"""
ML-Enhanced Signal Scoring
Uses trained ML models to boost/penalize signal scores based on predicted outcomes
"""
import os
import joblib
import numpy as np
from typing import Dict, Optional, Tuple


class MLScorer:
    """ML-enhanced signal scoring system"""
    
    def __init__(self):
        self.gain_model = None
        self.winner_model = None
        self.features = None
        # Gate on either ML_SCORING_ENABLED or ML_ENHANCEMENT_ENABLED for flexibility
        self.enabled = (
            os.getenv("ML_SCORING_ENABLED", "false").lower() == "true" or
            os.getenv("ML_ENHANCEMENT_ENABLED", "false").lower() == "true"
        )
        
        if self.enabled:
            self._load_models()
    
    def _load_models(self):
        """Load trained models from disk"""
        try:
            model_dir = 'var/models'
            self.gain_model = joblib.load(f'{model_dir}/gain_predictor.pkl')
            self.winner_model = joblib.load(f'{model_dir}/winner_classifier.pkl')
            self.features = joblib.load(f'{model_dir}/features.pkl')
            
            # Soft-validate features: warn but do not hard-disable
            if not isinstance(self.features, list) or len(self.features) < 10:
                self._log_warn("ML features metadata looks unusual; continuing with caution")
            
            self._log_info("ML models loaded successfully")
        except FileNotFoundError:
            self._log_warn("ML models not found. Run: python scripts/ml/train_model.py")
            self.enabled = False
        except Exception as e:
            self._log_warn(f"Failed to load ML models: {e}")
            self.enabled = False
    
    @staticmethod
    def _log_info(msg: str) -> None:
        """Log info message"""
        try:
            from app.logger_utils import log_process
            log_process({"type": "ml_scorer_info", "message": msg})
        except Exception:
            print(f"✅ {msg}")
    
    @staticmethod
    def _log_warn(msg: str) -> None:
        """Log warning message"""
        try:
            from app.logger_utils import log_process
            log_process({"type": "ml_scorer_warning", "message": msg})
        except Exception:
            print(f"⚠️  {msg}")
    
    def is_available(self) -> bool:
        """Check if ML scoring is available"""
        return self.enabled and self.gain_model is not None
    
    def predict_gain(self, stats: Dict, score: int, smart_money: bool, 
                    conviction_type: str) -> Optional[float]:
        """
        Predict expected gain percentage
        
        Returns:
            Predicted gain % (e.g., 150.0 for 2.5x), or None if unavailable
        """
        if not self.is_available():
            return None
        
        try:
            X = self._extract_features(stats, score, smart_money, conviction_type)
            predicted_gain = self.gain_model.predict([X])[0]
            return float(predicted_gain)
        except Exception as e:
            print(f"⚠️  ML prediction error: {e}")
            return None
    
    def predict_winner_probability(self, stats: Dict, score: int, 
                                   smart_money: bool, conviction_type: str) -> Optional[float]:
        """
        Predict probability of 2x+ gain
        
        Returns:
            Probability [0.0-1.0], or None if unavailable
        """
        if not self.is_available():
            return None
        
        try:
            X = self._extract_features(stats, score, smart_money, conviction_type)
            prob = self.winner_model.predict_proba([X])[0][1]  # Prob of class 1 (winner)
            return float(prob)
        except Exception as e:
            print(f"⚠️  ML prediction error: {e}")
            return None
    
    def _extract_features(self, stats: Dict, score: int, smart_money: bool, 
                         conviction_type: str) -> list:
        """
        Extract feature vector matching training format
        
        Must match feature_engineer.get_feature_list() exactly!
        """
        # Extract raw values
        liquidity = stats.get('liquidity_usd', 0) or 0
        volume = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0
        mcap = stats.get('market_cap_usd', 0) or 0
        
        # Avoid division by zero
        liquidity_safe = max(liquidity, 1)
        mcap_safe = max(mcap, 1)
        
        # Build feature vector matching feature_engineer.get_feature_list()
        features = [
            # Core score features
            score,                # final_score
            score,                # prelim_score (fallback: use same)
            0,                    # score_gap (unknown online)
            int(smart_money),     # smart_money_detected
            
            # Market metrics (log-transformed)
            np.log1p(liquidity),  # log_liquidity
            np.log1p(volume),     # log_volume
            np.log1p(mcap),       # log_mcap
            
            # Ratios
            volume / mcap_safe,       # vol_to_mcap_ratio
            volume / liquidity_safe,  # vol_to_liq_ratio
            liquidity / mcap_safe,    # liq_to_mcap_ratio
            
            # Conviction flags
            int('Smart Money' in conviction_type),
            int('Strict' in conviction_type),
            int('Nuanced' in conviction_type),
            int('High Confidence' in conviction_type),
            
            # Market cap tiers
            int(mcap < 100_000),
            int(100_000 <= mcap < 1_000_000),
            
            # Liquidity quality tiers
            int(liquidity >= 50_000),
            int(15_000 <= liquidity < 50_000),
            int(liquidity < 15_000),
        ]
        
        return features
    
    def enhance_score(self, base_score: int, stats: Dict, smart_money: bool,
                     conviction_type: str) -> Tuple[int, str]:
        """
        Enhance base score with ML predictions
        
        Args:
            base_score: Rule-based score (0-10)
            stats: Token statistics
            smart_money: Smart money detected flag
            conviction_type: Conviction type string
        
        Returns:
            (enhanced_score, reason_string)
        """
        if not self.is_available():
            return base_score, "ML not available"
        
        try:
            predicted_gain = self.predict_gain(stats, base_score, smart_money, conviction_type)
            winner_prob = self.predict_winner_probability(stats, base_score, smart_money, conviction_type)
            
            if predicted_gain is None or winner_prob is None:
                return base_score, "ML prediction failed"
            
            # Calculate ML bonus/penalty
            ml_bonus = 0
            reasons = []
            
            # Boost for high predicted gains
            if predicted_gain > 200:  # Predicted 3x+
                ml_bonus += 2
                reasons.append(f"High gain pred: {predicted_gain:.0f}%")
            elif predicted_gain > 150:  # Predicted 2.5x+
                ml_bonus += 1
                reasons.append(f"Good gain pred: {predicted_gain:.0f}%")
            elif predicted_gain > 80:  # Predicted 1.8x+
                ml_bonus += 1
                reasons.append(f"Decent gain pred: {predicted_gain:.0f}%")
            
            # Boost for high winner probability
            if winner_prob > 0.65:  # >65% chance of 2x
                ml_bonus += 1
                reasons.append(f"High win prob: {winner_prob:.0%}")
            elif winner_prob > 0.50:  # >50% chance
                reasons.append(f"Good win prob: {winner_prob:.0%}")
            
            # Penalty for poor predictions
            if predicted_gain < 20 and winner_prob < 0.25:
                ml_bonus -= 2
                reasons.append(f"Low confidence: {predicted_gain:.0f}%, {winner_prob:.0%}")
            elif predicted_gain < 40 and winner_prob < 0.35:
                ml_bonus -= 1
                reasons.append(f"Weak signal: {predicted_gain:.0f}%, {winner_prob:.0%}")
            
            # Apply bonus (cap at 0-10 range)
            enhanced_score = max(0, min(10, base_score + ml_bonus))
            
            if ml_bonus != 0:
                reason_str = " | ".join(reasons)
            else:
                reason_str = f"Neutral: {predicted_gain:.0f}%, {winner_prob:.0%}"
            
            return enhanced_score, reason_str
            
        except Exception as e:
            print(f"⚠️  ML enhance_score error: {e}")
            return base_score, f"ML error: {str(e)[:50]}"


# Global singleton
_ml_scorer = None

def get_ml_scorer() -> MLScorer:
    """Get or create global ML scorer instance"""
    global _ml_scorer
    if _ml_scorer is None:
        _ml_scorer = MLScorer()
    return _ml_scorer

