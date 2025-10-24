#!/bin/bash
echo "=== Recent Closed Positions (Last 10) ==="
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT 
    substr(token_address,1,8) as token,
    strategy,
    entry_price,
    qty,
    usd_size,
    datetime(open_at) as opened,
    peak_price,
    status
FROM positions 
WHERE status='closed'
ORDER BY id DESC 
LIMIT 10;
SQL

echo ""
echo "=== Sells with PnL (Last 10) ==="
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT 
    p.id,
    substr(p.token_address,1,8) as token,
    p.entry_price,
    f.price as exit_price,
    f.qty as qty_sold,
    f.usd as exit_usd,
    p.usd_size as entry_usd,
    ROUND((f.usd - p.usd_size), 4) as pnl_usd,
    ROUND(((f.usd - p.usd_size) / p.usd_size * 100), 2) as pnl_pct,
    datetime(f.timestamp) as sold_at
FROM positions p
JOIN fills f ON p.id = f.position_id
WHERE p.status='closed' AND f.side='sell'
ORDER BY p.id DESC
LIMIT 10;
SQL

