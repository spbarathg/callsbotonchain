"""
WATCH LIST MONITOR
Background task to continuously track prices and identify entry opportunities

Runs in separate thread to avoid blocking main trading loop
"""
import threading
import time
from typing import Optional
from .watch_list_manager import get_watch_list_manager


class WatchListMonitor:
    """Background monitor for watch list"""
    
    def __init__(self, trader):
        self.trader = trader
        self.watch_manager = get_watch_list_manager()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Pending recommendations (for main loop to process)
        self.pending_entries = []
        self.pending_reentries = []
        self.lock = threading.Lock()
    
    def start(self):
        """Start background monitoring"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print("[WATCH_MONITOR] 🚀 Started background price monitoring", flush=True)
    
    def stop(self):
        """Stop background monitoring"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[WATCH_MONITOR] 🛑 Stopped background monitoring", flush=True)
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        iteration = 0
        while self.running:
            try:
                iteration += 1
                # DEBUG: Log every iteration to prove the loop is running
                if iteration % 6 == 0:  # Every 30s (6 iterations * 5s)
                    watchlist_size = len(self.watch_manager.watch_list)
                    print(f"[WATCH_MONITOR_DEBUG] Iteration {iteration} | Watchlist size: {watchlist_size} | "
                          f"Total checks: {self.watch_manager.price_checks}", flush=True)
                
                # Update all prices and get recommendations
                recommendations = self.watch_manager.update_prices()
                
                # Store recommendations for main loop
                with self.lock:
                    self.pending_entries.extend(recommendations["enter"])
                    self.pending_reentries.extend(recommendations["reenter"])
                
                # Log activity
                if recommendations["enter"] or recommendations["reenter"]:
                    print(f"[WATCH_MONITOR] 🎯 Found {len(recommendations['enter'])} new entries, "
                          f"{len(recommendations['reenter'])} re-entries", flush=True)
                
                # Cleanup old signals every 100 iterations
                if self.watch_manager.price_checks % 100 == 0 and self.watch_manager.price_checks > 0:
                    self.watch_manager.cleanup_old_signals()
                
                # Sleep briefly (actual interval is per-token in watch_manager)
                time.sleep(5)
                
            except Exception as e:
                print(f"[WATCH_MONITOR] ⚠️ Error in monitor loop: {e}", flush=True)
                import traceback
                traceback.print_exc()
                time.sleep(10)
    
    def get_pending_recommendations(self):
        """Get and clear pending recommendations"""
        with self.lock:
            entries = self.pending_entries.copy()
            reentries = self.pending_reentries.copy()
            self.pending_entries.clear()
            self.pending_reentries.clear()
        return entries, reentries
    
    def get_summary(self) -> str:
        """Get watch list summary"""
        return self.watch_manager.get_watch_summary()


# Global instance
_monitor: Optional[WatchListMonitor] = None


def get_watch_list_monitor(trader) -> WatchListMonitor:
    """Get or create global watch list monitor"""
    global _monitor
    if _monitor is None:
        _monitor = WatchListMonitor(trader)
    return _monitor


