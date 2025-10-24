#!/bin/bash
echo "=== Recent Sells with PnL (Last 10) ==="
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT 
    p.id,
    substr(p.token_address,1,8) as token,
    ROUND(p.entry_price, 8) as entry,
    ROUND(f.price, 8) as exit,
    ROUND(f.qty, 2) as qty,
    ROUND(p.usd_size, 4) as entry_usd,
    ROUND(f.usd, 4) as exit_usd,
    ROUND((f.usd - p.usd_size), 4) as pnl_usd,
    ROUND(((f.usd - p.usd_size) / p.usd_size * 100), 2) as pnl_pct,
    datetime(f.at) as sold_at
FROM positions p
JOIN fills f ON p.id = f.position_id
WHERE p.status='closed' AND f.side='sell'
ORDER BY p.id DESC
LIMIT 10;
SQL

echo ""
echo "=== Current Open Positions ==="
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT 
    id,
    substr(token_address,1,8) as token,
    ROUND(entry_price, 8) as entry,
    ROUND(peak_price, 8) as peak,
    ROUND(qty, 2) as qty,
    ROUND(usd_size, 4) as size_usd,
    datetime(open_at) as opened,
    ROUND((peak_price - entry_price) / entry_price * 100, 2) as max_gain_pct
FROM positions 
WHERE status='open'
ORDER BY id DESC;
SQL

