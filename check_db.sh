#!/bin/bash
sqlite3 /opt/callsbotonchain/deployment/var/trading.db <<'SQL'
SELECT id, substr(token_address,1,8) as token, entry_price, peak_price, status 
FROM positions 
WHERE status='open'
ORDER BY id DESC 
LIMIT 10;
SQL

