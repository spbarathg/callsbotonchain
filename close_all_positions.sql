-- Close all open positions
UPDATE positions SET status='closed', closed_at=datetime('now') WHERE status='open';
SELECT 'Closed positions count:', changes();

