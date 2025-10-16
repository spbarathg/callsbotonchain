#!/usr/bin/env python3
"""Analyze why tokens are being rejected"""
import sys
sys.path.insert(0, '/opt/callsbotonchain')

from app.analyze_token import get_token_stats, score_token, check_senior_strict, check_junior_strict, check_junior_nuanced

token1 = 'fRfKGCriduzDwSudCwpL7ySCEiboNuryhZDVJtr1a1C'
token2 = 'CigZ6CQpM4Vk8Fo92XAEQGLWtauXYNe5LEVt849Gdoge'

for token_address in [token1, token2]:
    print('\n' + '='*60)
    print(f'Analyzing {token_address[:12]}...')
    print('='*60)
    stats = get_token_stats(token_address)
    if not stats:
        print('Could not fetch stats')
        continue
    
    score, details = score_token(stats, False, token_address)
    print(f'Score: {score}/10')
    print(f'Liquidity: ${stats.get("liquidity_usd", 0):,.0f}')
    print(f'Market Cap: ${stats.get("market_cap_usd", 0):,.0f}')
    
    volume = stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0
    print(f'Volume 24h: ${volume:,.0f}')
    
    mcap = stats.get('market_cap_usd', 0)
    liq = stats.get('liquidity_usd', 0)
    if mcap and volume:
        vol_mcap = (volume / mcap) * 100
        print(f'Vol/MCap: {vol_mcap:.1f}% (min: 15%)')
    
    if liq and volume:
        vol_liq = (volume / liq) * 100
        print(f'Vol/Liq: {vol_liq:.1f}% (min: 20%)')
    
    senior_ok = check_senior_strict(stats, token_address)
    junior_strict_ok = check_junior_strict(stats, score)
    junior_nuanced_ok = check_junior_nuanced(stats, score)
    
    print('\nGate Results:')
    print(f'  Senior Strict: {"✅ PASS" if senior_ok else "❌ FAIL"}')
    print(f'  Junior Strict: {"✅ PASS" if junior_strict_ok else "❌ FAIL"}')
    print(f'  Junior Nuanced: {"✅ PASS" if junior_nuanced_ok else "❌ FAIL"}')
    
    security = stats.get('security', {}) or {}
    holders = stats.get('holders', {}) or {}
    lp_locked = security.get('lp_locked') or security.get('is_lp_locked')
    mint_revoked = security.get('mint_revoked') or security.get('is_mint_revoked')
    
    print('\nSecurity Details:')
    print(f'  LP Locked: {lp_locked}')
    print(f'  Mint Revoked: {mint_revoked}')
    print(f'  Holders: {holders.get("holder_count", 0)} (min: 50)')
    print(f'  Top10: {holders.get("top10_concentration", 0):.1f}% (max: 30%)')
    print(f'  Bundlers: {holders.get("bundlers_percent", 0):.1f}% (max: 25%)')
    print(f'  Insiders: {holders.get("insiders_percent", 0):.1f}% (max: 35%)')

print('\n' + '='*60)
print('Analysis complete')
print('='*60)

