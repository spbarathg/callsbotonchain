#!/usr/bin/env python3
"""
Signal Aggregator Daemon - Runs in separate container
Monitors external Telegram groups for consensus signals
"""
import asyncio
import sys
import os
import signal as system_signal

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.signal_aggregator import start_monitoring

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_flag
    print(f"\n🛑 Received signal {sig}, shutting down gracefully...", flush=True)
    shutdown_flag = True


async def main():
    """Main entry point for Signal Aggregator daemon."""
    # Setup signal handlers
    system_signal.signal(system_signal.SIGINT, signal_handler)
    system_signal.signal(system_signal.SIGTERM, signal_handler)
    
    print("=" * 80, flush=True)
    print("🚀 SIGNAL AGGREGATOR DAEMON STARTING", flush=True)
    print("=" * 80, flush=True)
    print("Running in separate container for 100% isolation", flush=True)
    print("No database lock conflicts with main bot!", flush=True)
    print("=" * 80, flush=True)
    
    try:
        # Start monitoring (this runs indefinitely)
        await start_monitoring()
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received, shutting down...", flush=True)
    except Exception as e:
        print(f"❌ Error in Signal Aggregator: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        print("👋 Signal Aggregator daemon stopped", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!", flush=True)

