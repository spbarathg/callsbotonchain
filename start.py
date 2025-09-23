#!/usr/bin/env python3
"""Simple bot starter."""

import subprocess
import sys

if __name__ == "__main__":
    try:
        subprocess.run([sys.executable, "-m", "app.main"], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
