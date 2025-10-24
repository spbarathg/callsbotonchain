#!/bin/bash
echo "=== Positions WITHOUT Sell Fills ==="
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT 
    p.id,
    substr(p.token_address,1,8) as token,
    p.status,
    ROUND(p.entry_price, 8) as entry,
    ROUND(p.peak_price, 8) as peak,
    ROUND(p.usd_size, 4) as size_usd,
    datetime(p.open_at) as opened,
    (SELECT COUNT(*) FROM fills WHERE position_id = p.id AND side='sell') as sell_count
FROM positions p
WHERE p.status='closed' AND p.id NOT IN (SELECT position_id FROM fills WHERE side='sell')
ORDER BY p.id DESC
LIMIT 10;
SQL

echo ""
echo "=== All Fills for Recent Closed Positions ==="
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT 
    p.id,
    substr(p.token_address,1,8) as token,
    f.side,
    ROUND(f.price, 8) as price,
    ROUND(f.qty, 2) as qty,
    ROUND(f.usd, 4) as usd,
    datetime(f.at) as time
FROM positions p
LEFT JOIN fills f ON p.id = f.position_id
WHERE p.status='closed' AND p.id >= 145
ORDER BY p.id DESC, f.side;
SQL

