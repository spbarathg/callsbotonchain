# Token Tracking Status Report - October 14, 2025

## 📊 **TRACKING STATUS OVERVIEW**

### ✅ **WHAT'S BEING TRACKED**

| Data Point | Status | Table | Records | Notes |
|------------|--------|-------|---------|-------|
| **Contract Address (CA)** | ✅ **TRACKED** | `alerted_tokens` | 770 | Primary key for all tracking |
| **First Seen Timestamp** | ✅ **TRACKED** | `alerted_tokens.alerted_at` | 770 | UTC timestamp when first detected |
| **Liquidity Snapshots** | ✅ **TRACKED** | `price_snapshots.liquidity_usd` | 67,340 | Time series, ~87 snapshots/token |
| **Transaction Snapshots** | ⚠️ **PARTIAL** | `transaction_snapshots` | 55 | Only initial alert tx, not ongoing |
| **Wallet First Buys** | ⚠️ **PARTIAL** | `wallet_first_buys` | 55 | Only initial buyer, not first N |
| **Price Time Series** | ✅ **TRACKED** | `price_snapshots.price_usd` | 67,340 | t0, t+1m, t+5m, t+15m, t+1h, t+24h |
| **Holders Count** | ✅ **TRACKED** | `price_snapshots.holder_count` | 67,340 | Time series of holder counts |
| **Token Metadata** | ✅ **TRACKED** | `alerted_token_stats` | 770 | name, symbol, decimals, supply |
| **Outcome Label** | ✅ **TRACKED** | `alerted_token_stats.max_gain_percent` | 770 | Computed from performance |

---

## 📈 **DETAILED TRACKING ANALYSIS**

### 1. ✅ **Contract Address (CA)**
- **Table:** `alerted_tokens.token_address`
- **Status:** Fully tracked
- **Records:** 770 unique tokens
- **Example:** `56DTV25XtoYFSxW2Xe6MAz9vdReGt1UTgdFXkPwjpump`

### 2. ✅ **First Seen Timestamp**
- **Table:** `alerted_tokens.alerted_at`
- **Status:** Fully tracked
- **Format:** UTC timestamp (e.g., `2025-10-14 08:33:34`)
- **Example:** `1760375473.62351` (Unix timestamp)

### 3. ✅ **Liquidity Snapshots (Time Series)**
- **Table:** `price_snapshots`
- **Fields:** `snapshot_at`, `liquidity_usd`
- **Status:** Fully tracked
- **Records:** 67,340 snapshots across 770 tokens
- **Frequency:** Every 30 seconds while tracking
- **Average:** ~87 snapshots per token
- **Top tracked tokens:** 173 snapshots each (29FYsapBaEjW6nCTDNXR9HuScnc3uUfYymQ9Q4Rcbonk, etc.)

**Sample Data:**
```
Token: 29FYsapBaEjW6nCTDNXR9HuScnc3uUfYymQ9Q4Rcbonk
Snapshots: 173
Duration: ~86 minutes of tracking
```

### 4. ⚠️ **Transaction Snapshots** (PARTIAL TRACKING)
- **Table:** `transaction_snapshots`
- **Fields:** `tx_signature`, `timestamp`, `from_wallet`, `to_wallet`, `amount`, `amount_usd`, `tx_type`, `dex`, `is_smart_money`
- **Status:** ⚠️ **Only initial alert transaction tracked**
- **Records:** 55 transactions (only 1 per token)
- **Issue:** Not tracking ongoing transactions after alert

**Sample Data:**
```
Token: 56DTV25XtoYFSxW2Xe6MAz9vdReGt1UTgdFXkPwjpump
TX: 2MJLXjCVys56nyBM642CZ3qKPDfPzHqJNxBSAVSR15KpSmvvDemyhZPKn17rPUxvDeoXeGn3XkTVSAbu77nvwWCK
From: 5B52w1ZW9tuwUduueP5J7HXz5AcGfruGoX6YoAudvyxG
Amount: $2,003.08
Type: swap
DEX: PumpSwap
Smart Money: No
```

**What's Missing:**
- ❌ Ongoing buy/sell transactions after alert
- ❌ Full transaction history
- ❌ Transaction volume over time

### 5. ⚠️ **Wallet First Buys** (PARTIAL TRACKING)
- **Table:** `wallet_first_buys`
- **Fields:** `wallet_address`, `timestamp`, `amount`, `amount_usd`, `price_usd`, `is_smart_money`, `wallet_pnl_history`
- **Status:** ⚠️ **Only initial buyer tracked**
- **Records:** 55 wallets (only 1 per token)
- **Issue:** Not tracking first N buyers (e.g., first 10-20 buyers)

**Sample Data:**
```
Token: JCBKQBPvnjr7emdQGCNM8wtE8AZjyvJgh7JMvkfYxypm
Wallet: GKT2j5gPqY2ZKfhaGB5cn5bTHLSKTUrULe8wG1QwmLpt
Amount: $1,385.22
Price: $0.00669672
Smart Money: Yes
PnL History: NULL (not tracked)
```

**What's Missing:**
- ❌ First 10-20 buyers for each token
- ❌ Wallet PnL history (always NULL)
- ❌ Buyer wallet analysis

### 6. ✅ **Price Time Series**
- **Table:** `price_snapshots`
- **Fields:** `snapshot_at`, `price_usd`
- **Status:** Fully tracked
- **Records:** 67,340 price snapshots
- **Intervals Tracked:**
  - `t0`: Entry price (first_price_usd)
  - `t+1m`: Price after 1 minute
  - `t+5m`: Price after 5 minutes
  - `t+15m`: Price after 15 minutes
  - `t+1h`: Price after 1 hour (price_change_1h)
  - `t+24h`: Price after 24 hours (price_change_24h)
  - `t_peak`: Peak price reached (peak_price_usd)
  - `t_latest`: Most recent price (last_price_usd)

**Sample Data:**
```
Token: Wasabi-Chan (わさび)
Entry Price: $0.0000920084
Peak Price: $0.0000108400
Current Price: (tracked in snapshots)
Max Gain: -88.22% (actually a loss)
```

### 7. ✅ **Holders Count Time Series**
- **Table:** `price_snapshots.holder_count`
- **Status:** Fully tracked
- **Records:** 67,340 holder count snapshots
- **Frequency:** Every 30 seconds (same as price snapshots)

### 8. ✅ **Token Metadata**
- **Table:** `alerted_token_stats`
- **Fields:** `token_name`, `token_symbol`, `token_age_minutes`, `holder_count`, `unique_traders_15m`
- **Status:** Fully tracked
- **Records:** 770 tokens

**Sample Data:**
```
Token: Wasabi-Chan
Symbol: わさび
Holders: (tracked in snapshots)
Age: (tracked as token_age_minutes)
```

### 9. ✅ **Outcome Label**
- **Computed from:** `alerted_token_stats.max_gain_percent`
- **Status:** Fully tracked
- **Classification:**
  - `moonshot_10x+`: max_gain_percent >= 1000%
  - `winner_2x+`: max_gain_percent >= 100%
  - `winner`: max_gain_percent > 0%
  - `loser`: max_gain_percent <= 0%

**Sample Data:**
```
Token: Wasabi-Chan
Max Gain: -88.22%
Outcome: loser

Token: kayloni
Max Gain: -31.98%
Outcome: loser

Token: 索拉纳 (Sorana)
Max Gain: -59.79%
Outcome: loser
```

---

## 🔍 **GAPS & MISSING DATA**

### ❌ **Critical Gaps:**

1. **Transaction History Not Tracked**
   - Only initial alert transaction is recorded
   - Missing: Ongoing buy/sell activity after alert
   - Impact: Cannot analyze trading patterns, volume spikes, whale activity

2. **First N Buyers Not Tracked**
   - Only initial buyer is recorded
   - Missing: First 10-20 buyers for pattern analysis
   - Impact: Cannot identify early buyer patterns, smart money clustering

3. **Wallet PnL History Not Tracked**
   - `wallet_pnl_history` field is always NULL
   - Missing: Historical performance of buyer wallets
   - Impact: Cannot identify consistently profitable wallets

---

## 📝 **RECOMMENDATIONS**

### 🔧 **To Fix Transaction Tracking:**

Add to `scripts/track_performance.py`:

```python
from app.storage import record_transaction_snapshot

# In tracking loop, fetch recent transactions
def track_token_transactions(token_address):
    """Fetch and record recent transactions for a token."""
    try:
        # Fetch from API (e.g., Birdeye, Helius)
        transactions = fetch_recent_transactions(token_address, limit=50)
        
        for tx in transactions:
            record_transaction_snapshot(
                token_address=token_address,
                tx_signature=tx['signature'],
                timestamp=tx['timestamp'],
                from_wallet=tx['from'],
                to_wallet=tx['to'],
                amount=tx['amount'],
                amount_usd=tx['amount_usd'],
                tx_type=tx['type'],  # buy, sell, swap
                dex=tx['dex'],
                is_smart_money=is_smart_wallet(tx['from'])
            )
    except Exception as e:
        log_error(f"Failed to track transactions for {token_address}: {e}")
```

### 🔧 **To Fix First N Buyers Tracking:**

Add to `scripts/bot.py` after alert:

```python
from app.storage import record_wallet_first_buy

# After alerting, fetch first 20 buyers
def record_early_buyers(token_address, price_usd):
    """Record first N buyers for a token."""
    try:
        # Fetch from API
        early_buyers = fetch_first_buyers(token_address, limit=20)
        
        for buyer in early_buyers:
            record_wallet_first_buy(
                token_address=token_address,
                wallet_address=buyer['wallet'],
                timestamp=buyer['timestamp'],
                amount=buyer['amount'],
                amount_usd=buyer['amount_usd'],
                price_usd=price_usd,
                is_smart_money=is_smart_wallet(buyer['wallet']),
                wallet_pnl_history=get_wallet_pnl(buyer['wallet'])
            )
    except Exception as e:
        log_error(f"Failed to record early buyers for {token_address}: {e}")
```

### 🔧 **To Fix Wallet PnL Tracking:**

Add wallet PnL lookup function:

```python
def get_wallet_pnl(wallet_address):
    """Get historical PnL for a wallet."""
    try:
        # Fetch from smart money API or on-chain data
        wallet_data = fetch_wallet_performance(wallet_address)
        return wallet_data.get('total_pnl_usd', 0.0)
    except Exception:
        return None
```

---

## 📊 **CURRENT TRACKING STATISTICS**

```
Total Tokens Tracked: 770
Total Price Snapshots: 67,340
Total Transaction Snapshots: 55 (only initial alerts)
Total Wallet First Buys: 55 (only initial buyers)

Average Snapshots per Token: 87.5
Average Tracking Duration: ~44 minutes per token
Snapshot Frequency: Every 30 seconds

Win Rate: 58.44% (450/770 winners)
Moonshots (10x+): 12 tokens
Mega Winner: 1,462x (Polyagent)
```

---

## ✅ **SUMMARY**

### **What's Working Well:**
- ✅ Contract addresses tracked
- ✅ First seen timestamps tracked
- ✅ Liquidity snapshots (time series) tracked
- ✅ Price time series tracked (all intervals)
- ✅ Holder counts tracked (time series)
- ✅ Token metadata tracked
- ✅ Outcome labels computed

### **What Needs Improvement:**
- ⚠️ Transaction snapshots (only initial, not ongoing)
- ⚠️ Wallet first buys (only 1 buyer, not first N)
- ⚠️ Wallet PnL history (always NULL)

### **Impact:**
The current tracking is **sufficient for basic performance analysis** but **insufficient for deep pattern analysis** (e.g., identifying smart money clustering, transaction volume patterns, early buyer behavior).

---

**Report Generated:** 2025-10-14 15:00 IST  
**Database:** `/opt/callsbotonchain/deployment/var/alerted_tokens.db`  
**Total Records:** 770 tokens, 67,340 snapshots, 55 transactions, 55 wallets

