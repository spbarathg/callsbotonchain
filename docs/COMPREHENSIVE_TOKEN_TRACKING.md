# Comprehensive Token Tracking System

**Status:** ✅ IMPLEMENTED  
**Date:** October 13, 2025  
**Version:** 1.0

## Overview

This document describes the comprehensive token tracking system that captures and displays detailed on-chain data for all alerted tokens.

---

## 📊 Data Points Tracked

The system now tracks ALL the following data points for each token:

### 1. **Contract Address (CA)**
- ✅ Tracked in: `alerted_tokens.token_address`
- Unique identifier for each token

### 2. **First Seen Timestamp**
- ✅ Tracked in: `alerted_tokens.alerted_at`
- Unix timestamp when token was first detected/alerted

### 3. **Liquidity Snapshots (Time Series)**
- ✅ Tracked in: `price_snapshots.liquidity_usd`, `price_snapshots.snapshot_at`
- Captures liquidity in SOL/USD over time
- Recorded every 30 seconds while tracking

### 4. **Transaction Snapshots**
- ✅ **NEW TABLE:** `transaction_snapshots`
- Captures detailed transaction data:
  - `tx_signature`: Solana transaction signature
  - `timestamp`: Unix timestamp of transaction
  - `from_wallet`: Sender wallet address
  - `to_wallet`: Receiver wallet address
  - `amount`: Token amount transacted
  - `amount_usd`: USD value of transaction
  - `tx_type`: Type (buy, sell, swap)
  - `dex`: DEX name where transaction occurred
  - `is_smart_money`: Whether wallet is smart money

### 5. **Wallet First Buys**
- ✅ **NEW TABLE:** `wallet_first_buys`
- Tracks first N buyers for each token:
  - `wallet_address`: Buyer wallet
  - `timestamp`: Time of first buy
  - `amount`: Token amount purchased
  - `amount_usd`: USD value of purchase
  - `price_usd`: Entry price per token
  - `is_smart_money`: Smart money detection
  - `wallet_pnl_history`: Historical P&L of wallet

### 6. **Price Time Series**
- ✅ Tracked in: `price_snapshots` + computed fields
- Key intervals tracked:
  - `t0`: Entry price (first seen)
  - `t+1m`: Price after 1 minute
  - `t+5m`: Price after 5 minutes
  - `t+15m`: Price after 15 minutes
  - `t+1h`: Price after 1 hour
  - `t+24h`: Price after 24 hours
  - `t_peak`: Peak price reached
  - `t_latest`: Most recent price

### 7. **Holders Count Time Series**
- ✅ Tracked in: `price_snapshots.holder_count`
- Captures holder count at each snapshot

### 8. **Token Metadata**
- ✅ Tracked in: `alerted_token_stats`
- Fields:
  - `token_name`: Token name
  - `token_symbol`: Token symbol
  - `token_age_minutes`: Age when alerted
  - `holder_count`: Number of holders
  - Plus security data (LP locked, mint revoked, etc.)

### 9. **Outcome Label**
- ✅ Computed field based on `max_gain_percent`
- Classifications:
  - `moonshot_10x+`: ≥900% gain
  - `strong_5x+`: ≥400% gain
  - `good_2x+`: ≥100% gain
  - `moderate_1.5x+`: ≥50% gain
  - `breakeven`: 0-50% gain
  - `loss`: <0% gain
  - `rug`: Detected rug pull
  - `pending`: Still tracking

---

## 🗄️ Database Schema

### New Tables Added (Migration 4)

#### `transaction_snapshots`
```sql
CREATE TABLE transaction_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address TEXT NOT NULL,
    tx_signature TEXT NOT NULL,
    timestamp REAL NOT NULL,
    from_wallet TEXT,
    to_wallet TEXT,
    amount REAL,
    amount_usd REAL,
    tx_type TEXT,
    dex TEXT,
    is_smart_money BOOLEAN DEFAULT 0,
    FOREIGN KEY (token_address) REFERENCES alerted_tokens(token_address)
);

-- Indexes for fast queries
CREATE INDEX idx_tx_snapshots_token ON transaction_snapshots(token_address);
CREATE INDEX idx_tx_snapshots_timestamp ON transaction_snapshots(timestamp);
CREATE INDEX idx_tx_snapshots_signature ON transaction_snapshots(tx_signature);
```

#### `wallet_first_buys`
```sql
CREATE TABLE wallet_first_buys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    timestamp REAL NOT NULL,
    amount REAL,
    amount_usd REAL,
    price_usd REAL,
    is_smart_money BOOLEAN DEFAULT 0,
    wallet_pnl_history REAL,
    UNIQUE(token_address, wallet_address),
    FOREIGN KEY (token_address) REFERENCES alerted_tokens(token_address)
);

-- Indexes
CREATE INDEX idx_wallet_buys_token ON wallet_first_buys(token_address);
CREATE INDEX idx_wallet_buys_timestamp ON wallet_first_buys(timestamp);
```

---

## 🔧 New Functions Added

### Storage Functions (`app/storage.py`)

#### `record_transaction_snapshot()`
Records a single transaction for a token.

```python
record_transaction_snapshot(
    token_address="ABC123...",
    tx_signature="sig123...",
    timestamp=1697234567.0,
    from_wallet="wallet1...",
    to_wallet="wallet2...",
    amount=1000.0,
    amount_usd=50.0,
    tx_type="buy",
    dex="Raydium",
    is_smart_money=True
)
```

#### `record_wallet_first_buy()`
Records the first buy from a wallet for a token.

```python
record_wallet_first_buy(
    token_address="ABC123...",
    wallet_address="wallet1...",
    timestamp=1697234567.0,
    amount=1000.0,
    amount_usd=50.0,
    price_usd=0.05,
    is_smart_money=True,
    wallet_pnl_history=15000.0
)
```

#### `get_token_comprehensive_data(token_address)`
Returns ALL tracking data for a token in a single call.

```python
data = get_token_comprehensive_data("ABC123...")
# Returns:
{
    "ca": "ABC123...",
    "first_seen_ts": 1697234567.0,
    "liquidity_snapshots": [...],
    "tx_snapshots": [...],
    "wallet_first_buys": [...],
    "price_time_series": {...},
    "holders_count_ts": [...],
    "token_meta": {...},
    "outcome_label": "moonshot_10x+"
}
```

#### `get_all_tracked_tokens_summary(limit=100)`
Returns summary of all tracked tokens (for website display).

---

## 🌐 API Endpoints

### Base URL: `/api/v2/`

#### 1. Get Token Detail
```
GET /api/v2/token/<token_address>
```
Returns comprehensive tracking data for a specific token.

**Response:**
```json
{
  "success": true,
  "token": {
    "ca": "ABC123...",
    "first_seen_ts": 1697234567.0,
    "liquidity_snapshots": [...],
    "tx_snapshots": [...],
    "wallet_first_buys": [...],
    "price_time_series": {...},
    "holders_count_ts": [...],
    "token_meta": {...},
    "outcome_label": "moonshot_10x+",
    "max_gain_percent": 1542.5
  }
}
```

#### 2. Get All Tracked Tokens
```
GET /api/v2/tokens?limit=100&offset=0
```
Returns paginated list of all tracked tokens.

**Response:**
```json
{
  "success": true,
  "tokens": [
    {
      "ca": "ABC123...",
      "alerted_at": 1697234567.0,
      "score": 8,
      "conviction": "High Confidence",
      "name": "MyToken",
      "symbol": "MTK",
      "entry_price": 0.00012,
      "peak_price": 0.00198,
      "current_price": 0.00145,
      "max_gain_pct": 1550.0,
      "outcome": "moonshot_10x+",
      "liquidity": 125000,
      "volume_24h": 85000,
      "tx_count": 342,
      "buyer_count": 87
    }
  ],
  "count": 42,
  "limit": 100,
  "offset": 0
}
```

#### 3. Get Token Transactions
```
GET /api/v2/token/<token_address>/transactions?limit=100
```
Returns transaction history for a token.

#### 4. Get Token Top Buyers
```
GET /api/v2/token/<token_address>/buyers?limit=50
```
Returns top buyers (by USD amount) for a token.

#### 5. Get Token Price History
```
GET /api/v2/token/<token_address>/price-history
```
Returns complete price snapshot history.

---

## 🎨 Website Features

### Enhanced Tracked Tokens Tab

#### Summary Cards
- **Total Tracked**: Count of all tracked tokens
- **Moonshots (10x+)**: Tokens with ≥900% gain
- **Winners (2x+)**: Tokens with ≥100% gain
- **Losers**: Tokens with negative performance

#### Tracked Tokens Table
Enhanced table with:
- Token address (clickable)
- Alert time
- Score & conviction
- Price progression (entry → current → peak)
- Peak multiple
- Liquidity & volume
- Outcome classification
- **NEW:** "View" button for detailed modal

#### Token Detail Modal
Clicking "View" opens a comprehensive modal showing:

**Token Info Section:**
- Contract address
- Name & symbol
- Score & conviction
- Smart money detection
- Outcome label (color-coded)

**Price Timeline Section:**
- Entry price (t0)
- Price at +1m, +5m, +15m, +1h, +24h
- Peak price (highlighted)
- Latest price
- Max gain percentage

**Activity Stats Section:**
- Transaction count
- Unique buyer count
- Liquidity snapshots count
- Price snapshots count

**Top Buyers Table:**
- Wallet addresses
- Amount purchased (USD)
- Entry price
- Smart money indicator
- Historical PnL

**Recent Transactions Table:**
- Transaction type
- Amount (USD)
- DEX used
- Timestamp
- Smart money indicator

---

## 📝 Usage Examples

### Recording a Transaction
```python
from app.storage import record_transaction_snapshot

record_transaction_snapshot(
    token_address="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
    tx_signature="3kNx7...abc123",
    timestamp=time.time(),
    from_wallet="Abc1...xyz",
    to_wallet="Def2...uvw",
    amount=1000.0,
    amount_usd=50.0,
    tx_type="buy",
    dex="Raydium",
    is_smart_money=False
)
```

### Recording First Buys
```python
from app.storage import record_wallet_first_buy

record_wallet_first_buy(
    token_address="DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
    wallet_address="Abc1...xyz",
    timestamp=time.time(),
    amount=1000.0,
    amount_usd=50.0,
    price_usd=0.05,
    is_smart_money=True,
    wallet_pnl_history=25000.0
)
```

### Querying via API
```bash
# Get comprehensive data for a token
curl http://localhost/api/v2/token/DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK

# Get all tracked tokens
curl http://localhost/api/v2/tokens?limit=50

# Get transaction history
curl http://localhost/api/v2/token/DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK/transactions

# Get top buyers
curl http://localhost/api/v2/token/DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK/buyers
```

### Viewing on Website
1. Navigate to website (e.g., `http://localhost` or `http://64.227.157.221`)
2. Click on **"Tracked"** tab
3. Browse tracked tokens with summary stats
4. Click **"View"** button on any token to see comprehensive details
5. Modal shows:
   - Full price timeline
   - Top buyers
   - Recent transactions
   - All metadata

---

## 🚀 Deployment Steps

### 1. Apply Database Migration
```bash
cd /opt/callsbotonchain
python3 -c "from app.storage import init_db; init_db()"
```

The migration system will automatically:
- Create `transaction_snapshots` table
- Create `wallet_first_buys` table
- Add necessary indexes
- Skip if already applied

### 2. Restart Services
```bash
# Restart the web dashboard
docker-compose restart api

# Or if running standalone
systemctl restart callsbot-api
```

### 3. Verify
```bash
# Check tables exist
sqlite3 /opt/callsbotonchain/deployment/var/alerted_tokens.db "SELECT name FROM sqlite_master WHERE type='table';"

# Should show:
# - transaction_snapshots
# - wallet_first_buys
# - price_snapshots
# - alerted_tokens
# - alerted_token_stats

# Test API endpoint
curl http://localhost/api/v2/tokens?limit=5
```

---

## 📈 Data Collection Integration

### In Signal Processing (`scripts/bot.py`)
When a token is alerted, you can now also record:

```python
from app.storage import record_transaction_snapshot, record_wallet_first_buy

# After alerting a token, record initial transaction that triggered it
if feed_transaction:
    record_transaction_snapshot(
        token_address=token_address,
        tx_signature=feed_transaction.get('signature'),
        timestamp=feed_transaction.get('timestamp'),
        from_wallet=feed_transaction.get('from_wallet'),
        to_wallet=feed_transaction.get('to_wallet'),
        amount=feed_transaction.get('amount'),
        amount_usd=feed_transaction.get('usd_value'),
        tx_type=feed_transaction.get('type'),
        dex=feed_transaction.get('dex'),
        is_smart_money=feed_transaction.get('smart_money', False)
    )

# Record first buyer if known
if buyer_wallet:
    record_wallet_first_buy(
        token_address=token_address,
        wallet_address=buyer_wallet,
        timestamp=time.time(),
        amount=buy_amount,
        amount_usd=buy_amount_usd,
        price_usd=current_price,
        is_smart_money=is_smart_money_wallet,
        wallet_pnl_history=get_wallet_pnl(buyer_wallet)
    )
```

### In Tracking Script (`scripts/track_performance.py`)
The tracking script automatically records:
- Price snapshots every 30 seconds
- Liquidity updates
- Holder counts

To extend it with transaction tracking, add:
```python
# Fetch recent transactions from chain
transactions = fetch_token_transactions(token_address)
for tx in transactions:
    record_transaction_snapshot(
        token_address=token_address,
        tx_signature=tx['signature'],
        ...
    )
```

---

## 🔍 Query Examples

### SQL Queries

#### Get All Data for Analysis
```sql
-- Export comprehensive token data
SELECT 
    a.token_address as ca,
    a.alerted_at as first_seen_ts,
    s.token_name,
    s.token_symbol,
    s.first_price_usd,
    s.peak_price_usd,
    s.max_gain_percent,
    s.outcome_label,
    (SELECT COUNT(*) FROM transaction_snapshots WHERE token_address = a.token_address) as tx_count,
    (SELECT COUNT(*) FROM wallet_first_buys WHERE token_address = a.token_address) as buyer_count
FROM alerted_tokens a
LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
ORDER BY s.max_gain_percent DESC;
```

#### Top Smart Money Wallets
```sql
SELECT 
    wallet_address,
    COUNT(*) as tokens_bought,
    SUM(amount_usd) as total_spent,
    AVG(wallet_pnl_history) as avg_pnl
FROM wallet_first_buys
WHERE is_smart_money = 1
GROUP BY wallet_address
ORDER BY tokens_bought DESC
LIMIT 20;
```

#### Transaction Volume by DEX
```sql
SELECT 
    dex,
    COUNT(*) as tx_count,
    SUM(amount_usd) as total_volume
FROM transaction_snapshots
GROUP BY dex
ORDER BY total_volume DESC;
```

---

## 🎯 Next Steps & Enhancements

### Recommended Additions:

1. **Real-time Transaction Monitoring**
   - Integrate with Solana RPC to capture transactions in real-time
   - Use websocket subscriptions for immediate updates

2. **Smart Money Analytics**
   - Build profiles of top-performing wallets
   - Track wallet follow patterns
   - Calculate smart money consensus scores

3. **Advanced Visualization**
   - Add price charts using Chart.js or similar
   - Liquidity flow visualizations
   - Transaction network graphs

4. **Export Functionality**
   - CSV export for all token data
   - JSON export for ML training
   - Historical data archiving

5. **Alerting System**
   - Alert when smart money buys a tracked token
   - Alert on unusual transaction volumes
   - Alert on liquidity changes

---

## 🐛 Troubleshooting

### Migration Not Applied
```bash
# Check current schema version
sqlite3 var/alerted_tokens.db "SELECT * FROM schema_migrations;"

# Manually apply migration
python3 -c "
from app.migrations import get_signals_migrations
runner = get_signals_migrations()
version, applied = runner.run()
print(f'Version: {version}, Applied: {applied}')
"
```

### API Returns Empty Data
- Ensure tokens have been alerted and tracked
- Check that `track_performance.py` is running
- Verify database path is correct

### Website Not Showing New Features
- Clear browser cache (Ctrl+Shift+R)
- Check browser console for JavaScript errors
- Verify API endpoints are accessible

---

## 📚 Related Documentation

- **Database Schema:** `app/migrations.py` (Migration 4)
- **Storage Functions:** `app/storage.py`
- **API Endpoints:** `src/api_enhanced.py`, `src/server.py`
- **Website Frontend:** `src/templates/index.html`
- **Current Setup:** `docs/quickstart/CURRENT_SETUP.md`

---

**Last Updated:** October 13, 2025  
**Maintained By:** AI Assistant  
**Status:** Production Ready ✅

