#!/usr/bin/env python3
"""Detailed rejection analysis with step-by-step checks"""
import sys
sys.path.insert(0, '/opt/callsbotonchain')

from app.analyze_token import get_token_stats, score_token
from app.config_unified import (
    MIN_LIQUIDITY_USD, MIN_VOLUME_24H_USD, VOL_TO_MCAP_RATIO_MIN,
    MAX_MARKET_CAP_FOR_DEFAULT_ALERT, HIGH_CONFIDENCE_SCORE,
    NUANCED_SCORE_REDUCTION
)

token_address = 'CigZ6CQpM4Vk8Fo92XAEQGLWtauXYNe5LEVt849Gdoge'

print('\n' + '='*60)
print(f'DETAILED ANALYSIS: {token_address[:12]}...')
print('='*60)

stats = get_token_stats(token_address)
if not stats:
    print('Could not fetch stats')
    sys.exit(1)

score, details = score_token(stats, False, token_address)

# Extract values
liq_usd = stats.get('liquidity_usd', 0)
volume_24h = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0
mcap = stats.get('market_cap_usd', 0) or 0
vol_mcap_ratio = (volume_24h / mcap * 100) if mcap else 0

print(f'\nToken Metrics:')
print(f'  Score: {score}/10')
print(f'  Liquidity: ${liq_usd:,.0f}')
print(f'  Volume 24h: ${volume_24h:,.0f}')
print(f'  Market Cap: ${mcap:,.0f}')
print(f'  Vol/MCap: {vol_mcap_ratio:.1f}%')

print(f'\n🔍 JUNIOR STRICT CHECK (step-by-step):')

# Check 1: Liquidity
print(f'\n1. Liquidity Check:')
print(f'   Required: ${MIN_LIQUIDITY_USD:,.0f}')
print(f'   Actual: ${liq_usd:,.0f}')
print(f'   Result: {"✅ PASS" if liq_usd >= MIN_LIQUIDITY_USD else "❌ FAIL"}')

# Check 2: Volume
print(f'\n2. Volume Check:')
print(f'   Required: ${MIN_VOLUME_24H_USD:,.0f}')
print(f'   Actual: ${volume_24h:,.0f}')
volume_pass = volume_24h >= MIN_VOLUME_24H_USD
print(f'   Result: {"✅ PASS" if volume_pass else "❌ FAIL ⚠️"}')
if not volume_pass:
    print(f'   ❌ THIS IS WHY IT\'S FAILING!')
    print(f'   Gap: ${MIN_VOLUME_24H_USD - volume_24h:,.0f} short')

# Check 3: Market Cap
print(f'\n3. Market Cap Check:')
print(f'   Max: ${MAX_MARKET_CAP_FOR_DEFAULT_ALERT:,.0f}')
print(f'   Actual: ${mcap:,.0f}')
print(f'   Result: {"✅ PASS" if mcap <= MAX_MARKET_CAP_FOR_DEFAULT_ALERT else "❌ FAIL"}')

# Check 4: Vol/MCap Ratio
print(f'\n4. Vol/MCap Ratio Check:')
print(f'   Required: {VOL_TO_MCAP_RATIO_MIN*100:.0f}%')
print(f'   Actual: {vol_mcap_ratio:.1f}%')
ratio_req = VOL_TO_MCAP_RATIO_MIN
ratio = volume_24h / mcap if mcap else 0
print(f'   Result: {"✅ PASS" if ratio >= ratio_req else "❌ FAIL"}')

# Check 5: Score
print(f'\n5. Score Check:')
print(f'   Required (Strict): {HIGH_CONFIDENCE_SCORE}')
print(f'   Required (Nuanced): {HIGH_CONFIDENCE_SCORE - NUANCED_SCORE_REDUCTION}')
print(f'   Actual: {score}')
print(f'   Strict Result: {"✅ PASS" if score >= HIGH_CONFIDENCE_SCORE else "❌ FAIL"}')
print(f'   Nuanced Result: {"✅ PASS" if score >= (HIGH_CONFIDENCE_SCORE - NUANCED_SCORE_REDUCTION) else "❌ FAIL"}')

print('\n' + '='*60)
print('CONCLUSION:')
if not volume_pass:
    print(f'❌ Token rejected due to LOW VOLUME')
    print(f'   Volume is ${volume_24h:,.0f}, need ${MIN_VOLUME_24H_USD:,.0f}')
    print(f'   This is {((MIN_VOLUME_24H_USD - volume_24h) / volume_24h * 100):.0f}% below threshold')
    print(f'\n💡 RECOMMENDATION: Lower MIN_VOLUME_24H_USD from $8,000 to $5,000')
    print(f'   This would catch earlier micro-cap signals')
else:
    print('❌ Token rejected for other reasons (check above)')
print('='*60)

