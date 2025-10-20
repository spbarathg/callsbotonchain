"""
CLI for Conservative Paper Trading System
Implements CAPITAL_MANAGEMENT_STRATEGY.md principles
"""
import sys
import os
import time
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingSystem.paper_trader_conservative import ConservativePaperTrader
from tradingSystem.config_conservative import print_config_summary, BANKROLL_USD


def print_portfolio_status(trader: ConservativePaperTrader):
    """Print current portfolio status"""
    stats = trader.get_stats()
    
    print("\n" + "="*70)
    print("CONSERVATIVE PAPER TRADING - PORTFOLIO STATUS")
    print("="*70)
    
    # Capital overview
    print(f"\n💰 CAPITAL OVERVIEW:")
    print(f"├─ Starting Capital:    ${stats['starting_capital']:,.2f}")
    print(f"├─ Current Capital:     ${stats['current_capital']:,.2f}")
    print(f"├─ Cash Reserve:        ${stats['current_capital']:,.2f} ({stats['cash_reserve_pct']:.1f}%) ", end="")
    if stats['cash_reserve_pct'] >= 50:
        print("✅")
    elif stats['cash_reserve_pct'] >= 40:
        print("⚠️")
    else:
        print("🚨")
    
    print(f"├─ Deployed Capital:    ${stats['deployed_capital']:,.2f} ({stats['deployed_pct']:.1f}%) ", end="")
    if stats['deployed_pct'] <= 50:
        print("✅")
    elif stats['deployed_pct'] <= 60:
        print("⚠️")
    else:
        print("🚨")
    
    print(f"├─ Total Value:         ${stats['total_value']:,.2f}")
    print(f"└─ Total Return:        {stats['roi_pct']:+.1f}%", end="")
    if stats['roi_pct'] > 0:
        print(" 🟢")
    else:
        print(" 🔴")
    
    # Performance
    print(f"\n📊 PERFORMANCE:")
    print(f"├─ Total Trades:        {stats['total_trades']}")
    print(f"├─ Wins:                {stats['wins']}")
    print(f"├─ Losses:              {stats['losses']}")
    print(f"├─ Win Rate:            {stats['win_rate']:.1f}%")
    print(f"└─ Total P&L:           ${stats['total_pnl']:+,.2f}")
    
    # Risk management
    print(f"\n🛡️  RISK MANAGEMENT:")
    print(f"├─ Open Positions:      {stats['open_positions']}/6")
    print(f"├─ Daily P&L:           ${stats['daily_pnl']:+,.2f} (limit: -${abs(trader.circuit_breaker.daily_pnl):.2f if trader.circuit_breaker.daily_pnl < 0 else 0:.2f}/-$100)")
    print(f"├─ Weekly P&L:          ${stats['weekly_pnl']:+,.2f}")
    print(f"├─ Consecutive Losses:  {stats['consecutive_losses']}/3")
    print(f"├─ Circuit Breaker:     ", end="")
    if stats['circuit_breaker_tripped']:
        print(f"🚨 TRIPPED - {stats['circuit_breaker_reason']}")
    else:
        print("✅ OK")
    print(f"└─ Recovery Mode:       ", end="")
    if stats['recovery_mode']:
        print("⚠️  ACTIVE (positions reduced by 50%)")
    else:
        print("✅ OFF")
    
    # Open positions
    if trader.positions:
        print(f"\n📈 OPEN POSITIONS:")
        for i, (token, pos) in enumerate(trader.positions.items(), 1):
            tier_emoji = "🚀" if pos.risk_tier.tier_name == "MOONSHOT" else "💎" if pos.risk_tier.tier_name == "AGGRESSIVE" else "📊"
            print(f"{i}. {tier_emoji} {token[:12]}... ({pos.risk_tier.tier_name})")
            print(f"   ├─ Entry: ${pos.entry_price:.8f} @ {pos.entry_time[:16]}")
            print(f"   ├─ Size: ${pos.usd_invested:.2f} ({pos.usd_invested/stats['total_value']*100:.1f}%)")
            if pos.current_price > 0:
                print(f"   ├─ Current: ${pos.current_price:.8f}")
                print(f"   ├─ P&L: ${pos.unrealized_pnl_usd:+.2f} ({pos.unrealized_pnl_pct:+.1f}%)")
                print(f"   ├─ Peak: ${pos.peak_price:.8f} ({(pos.peak_price/pos.entry_price-1)*100:+.1f}%)")
            print(f"   ├─ Stop: -{pos.stop_loss_pct}% | Trail: -{pos.trail_pct}%")
            print(f"   └─ Target: {pos.risk_tier.take_profit_min_multiplier:.0f}x")
    
    print("\n" + "="*70)


def print_help():
    """Print help"""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     CONSERVATIVE PAPER TRADING CLI                            ║
╚═══════════════════════════════════════════════════════════════╝

Commands:
  config            Show current configuration
  status            Show portfolio status
  open <token>      Open a position (test mode)
  help              Show this help
  exit              Exit CLI

""")


def main():
    """Main CLI loop"""
    # Print config on startup
    print_config_summary()
    
    # Create trader
    print(f"\n🤖 Initializing Conservative Paper Trader with ${BANKROLL_USD:,.2f}...")
    trader = ConservativePaperTrader(starting_capital=BANKROLL_USD)
    
    # Show initial status
    print_portfolio_status(trader)
    
    # Interactive loop
    print("\n💡 Type 'help' for commands, 'exit' to quit")
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "exit" or cmd == "quit":
                print("👋 Goodbye!")
                break
            
            elif cmd == "help":
                print_help()
            
            elif cmd == "config":
                print_config_summary()
            
            elif cmd == "status":
                print_portfolio_status(trader)
            
            elif cmd.startswith("open "):
                token = cmd.split()[1] if len(cmd.split()) > 1 else "TestToken"
                print(f"\n🔍 Simulating position open for {token}...")
                
                # Create test signal data
                signal_data = {
                    'token_address': token,
                    'price': 0.00001,
                    'first_market_cap_usd': 75000,  # Tier 2 (Aggressive)
                    'liquidity_usd': 35000,
                    'volume_24h_usd': 50000,
                    'final_score': 8,
                    'conviction_type': 'High Confidence'
                }
                
                # Try to open
                pos_id = trader.open_position(token, signal_data)
                
                if pos_id:
                    print(f"✅ Position opened! ID: {pos_id}")
                    print_portfolio_status(trader)
                else:
                    print(f"❌ Failed to open position")
                    can_trade, reason = trader.can_trade(signal_data)
                    if not can_trade:
                        print(f"   Reason: {reason}")
            
            elif cmd == "":
                continue
            
            else:
                print(f"❌ Unknown command: {cmd}")
                print("💡 Type 'help' for available commands")
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()




