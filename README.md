# CallsBotOnChain

Automated cryptocurrency signal detection and trading bot for Solana tokens.

## 🚀 Quick Links

- **Documentation**: See [`docs/`](docs/) folder
- **Operations**: See [`ops/`](ops/) folder  
- **Monitoring**: See [`monitoring/`](monitoring/) folder
- **Current Status**: See [`docs/STATUS.md`](docs/STATUS.md)

## 📁 Repository Structure

```
callsbotonchain/
├── app/                    # Core application modules
│   ├── analyze_token.py    # Token analysis and scoring
│   ├── fetch_feed.py       # Cielo API integration
│   ├── storage.py          # Database operations
│   ├── budget.py           # API budget management
│   └── ...                 # Other app modules
│
├── scripts/                # Executable scripts
│   └── bot.py              # Main worker script
│
├── tradingSystem/          # Trading system (Jupiter V6)
│   ├── cli.py              # Trading CLI
│   ├── trader.py           # Trade engine
│   ├── broker.py           # Exchange interface
│   ├── strategy.py         # Trading strategies
│   └── ...                 # Other trading modules
│
├── src/                    # Web interface
│   ├── server.py           # Flask API server
│   ├── templates/          # HTML templates
│   └── static/             # CSS, JS assets
│
├── docs/                   # Documentation
│   ├── STATUS.md           # Current operational status
│   ├── README.md           # Documentation index
│   ├── PRODUCTION_SAFETY.md
│   ├── TRADING_DEPLOYMENT.md
│   └── TRADING_MONITORING.md
│
├── ops/                    # Operations guides
│   ├── README.md           # Ops documentation index
│   ├── HEALTH_CHECK.md     # Health monitoring
│   ├── ANALYSIS_GUIDE.md   # Performance analysis
│   └── TROUBLESHOOTING.md  # Issue resolution
│
├── monitoring/             # Local monitoring system
│   ├── monitor_bot.py      # Main monitor script
│   ├── analyze_metrics.py  # Analysis tool
│   └── MONITORING_SYSTEM.md # Monitoring guide
│
├── tests/                  # Test suite
├── tools/                  # Utility scripts
├── analytics/              # Generated monitoring data (gitignored)
├── var/                    # Runtime data (gitignored)
├── data/                   # Logs and backups (gitignored)
│
├── config.py               # Configuration settings
├── conftest.py             # Test configuration
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # Docker orchestration
├── Dockerfile              # Container definition
└── README.md               # This file
```

## 🎯 What This Bot Does

### Signal Detection
- Monitors Solana token launches via Cielo Finance API
- Detects smart money activity and high-conviction signals
- Scores tokens based on liquidity, volume, momentum, and more
- Generates 500+ alerts per day with 67% smart money detection

### Tracking
- Monitors all alerted tokens for price movements
- Tracks peak multiples, drawdowns, and performance
- Stores historical data for analysis and optimization

### Trading (Optional)
- Executes trades via Jupiter Aggregator V6
- 4 strategies: Runner (smart money), Scout (velocity), Strict, Nuanced
- Risk-managed position sizing and stop losses
- Currently in dry-run mode (paper trading)

### Dashboard
- Real-time web UI at http://64.227.157.221/
- 7 tabs: Overview, Performance, System, Config, Paper Trade, Logs, Tracked
- Interactive controls for toggles and settings
- Paper trading simulator with backtesting

## 🚀 Getting Started

### For Operators

**Daily Health Check:**
```bash
# On server
docker ps
curl http://127.0.0.1/api/v2/quick-stats | jq
```

**See Full Guide**: [`ops/HEALTH_CHECK.md`](ops/HEALTH_CHECK.md)

### For Developers

**Setup Local Environment:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Start local monitoring
python monitoring/monitor_bot.py
```

**See Development Guide**: [`docs/README.md`](docs/README.md)

### For Analysis

**Start Local Monitoring:**
```bash
python monitoring/monitor_bot.py
```

**Analyze Performance:**
```bash
python monitoring/analyze_metrics.py
```

**See Monitoring Guide**: [`monitoring/MONITORING_SYSTEM.md`](monitoring/MONITORING_SYSTEM.md)

## 📊 Current Status

**As of October 4, 2025:**

- ✅ All containers healthy (worker, web, trader, proxy)
- ✅ 241 total alerts, 67% smart money detection
- ✅ Average signal score: 6.6/10
- ✅ Budget: 13% used, zero-miss mode active
- ✅ Resources: 38% disk, 50% memory
- ✅ Zero restarts, 100% uptime

**See Detailed Status**: [`docs/STATUS.md`](docs/STATUS.md)

## 🔧 Configuration

**Key Settings** (in `.env` and `config.py`):
- `HIGH_CONFIDENCE_SCORE=5` - Minimum score for alerts
- `MIN_LIQUIDITY_USD=5000` - Minimum liquidity requirement
- `BUDGET_PER_DAY_MAX=10000` - Daily API call limit
- `TRACK_INTERVAL_MIN=15` - Tracking frequency

**See Configuration Guide**: [`docs/STATUS.md`](docs/STATUS.md#key-runtime-essentials)

## 🐛 Troubleshooting

**Common Issues:**
- No alerts? Check [`ops/TROUBLESHOOTING.md`](ops/TROUBLESHOOTING.md#3-no-alerts-being-generated)
- Budget exhausted? See [`ops/TROUBLESHOOTING.md`](ops/TROUBLESHOOTING.md#2-high-budget-usage--api-exhaustion)
- Database errors? Check [`ops/TROUBLESHOOTING.md`](ops/TROUBLESHOOTING.md#4-database-errors--permission-issues)

## 📚 Documentation Index

### Operations
- [`ops/HEALTH_CHECK.md`](ops/HEALTH_CHECK.md) - Health monitoring procedures
- [`ops/ANALYSIS_GUIDE.md`](ops/ANALYSIS_GUIDE.md) - Performance analysis
- [`ops/TROUBLESHOOTING.md`](ops/TROUBLESHOOTING.md) - Issue resolution

### System Documentation
- [`docs/STATUS.md`](docs/STATUS.md) - Current operational status
- [`docs/PRODUCTION_SAFETY.md`](docs/PRODUCTION_SAFETY.md) - System stability
- [`docs/TRADING_DEPLOYMENT.md`](docs/TRADING_DEPLOYMENT.md) - Trading setup
- [`docs/TRADING_MONITORING.md`](docs/TRADING_MONITORING.md) - Trading monitoring

### Monitoring
- [`monitoring/MONITORING_SYSTEM.md`](monitoring/MONITORING_SYSTEM.md) - Local monitoring guide

## 🔗 External Resources

- **Dashboard**: http://64.227.157.221/
- **Cielo Finance API**: https://feed-api.cielo.finance/
- **Jupiter Aggregator**: https://station.jup.ag/
- **Server**: SSH root@64.227.157.221

## 📝 License

Proprietary - All rights reserved

## 🤝 Contributing

This is a private project. For questions or issues, contact the operator.

---

**Last Updated**: October 4, 2025  
**Version**: 2.0  
**Status**: Production

