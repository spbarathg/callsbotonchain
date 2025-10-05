# Developer Setup Guide

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git

### Local Development Setup

1. **Clone and Setup**
```bash
git clone <repository-url>
cd callsbotonchain
cp .env.example .env
# Edit .env with your API keys
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
```

3. **Run Tests**
```bash
pytest tests/
```

4. **Start Local Development**
```bash
# Start all services
docker-compose up -d

# Or run individual components
python scripts/bot.py run
python src/server.py
python scripts/track_performance.py
```

## 🏗️ Architecture Overview

### Core Components

**`scripts/bot.py`** - Main worker process
- Fetches signals from Cielo API
- Analyzes and scores tokens
- Sends alerts via Telegram
- Entry point: `python scripts/bot.py run`

**`app/`** - Core application modules
- `analyze_token.py` - Token scoring and analysis
- `fetch_feed.py` - API integration
- `storage.py` - Database operations
- `budget.py` - API rate limiting
- `logger_utils.py` - Structured logging

**`tradingSystem/`** - Trading engine
- `cli.py` - Trading CLI interface
- `trader.py` - Trade execution
- `strategy.py` - Trading strategies
- `broker.py` - Exchange interface

**`src/`** - Web interface
- `server.py` - Flask API server
- `api_enhanced.py` - Enhanced API endpoints
- `paper_trading.py` - Paper trading simulator

## 🔧 Development Workflow

### Making Changes

1. **Code Changes**
   - Follow existing patterns for error handling
   - Add type hints to new functions
   - Use structured logging: `log_process({"type": "event", "data": value})`

2. **Testing**
   - Run tests: `pytest tests/`
   - Check specific module: `pytest tests/test_analyze_token.py`

3. **Deployment**
   - Build containers: `docker-compose build`
   - Deploy: `docker-compose up -d`
   - Check logs: `docker logs callsbot-worker`

### Debugging

**Check Container Health**
```bash
docker ps
docker logs callsbot-worker --tail 50
```

**Check API Status**
```bash
curl http://localhost/api/v2/quick-stats | jq
```

**Check Database**
```bash
sqlite3 var/alerted_tokens.db "SELECT COUNT(*) FROM alerted_tokens;"
```

## 📁 File Structure

```
callsbotonchain/
├── app/                    # Core modules
│   ├── analyze_token.py    # Token analysis
│   ├── fetch_feed.py       # API integration
│   ├── storage.py          # Database
│   └── logger_utils.py     # Logging
├── scripts/                # Executables
│   ├── bot.py              # Main worker
│   └── track_performance.py # Tracker
├── tradingSystem/          # Trading
│   ├── cli.py              # Trading CLI
│   ├── trader.py           # Execution
│   └── strategy.py         # Strategies
├── src/                    # Web UI
│   ├── server.py           # Flask server
│   └── api_enhanced.py     # API endpoints
├── tests/                  # Test suite
├── docs/                   # Documentation
├── config.py               # Configuration
└── docker-compose.yml      # Orchestration
```

## 🐛 Common Issues

### Import Errors
```python
# Fix: Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
```

### Database Errors
```bash
# Fix: Check permissions
chown -R appuser:appuser var/
```

### API Rate Limits
```python
# Fix: Check budget status
from app.budget import get_budget
budget = get_budget()
print(f"Daily used: {budget.daily_used}/{budget.daily_max}")
```

## 📊 Monitoring

**Local Monitoring**
```bash
python monitoring/monitor_bot.py
```

**Check Metrics**
```bash
curl http://localhost:9108/metrics
```

**View Logs**
```bash
tail -f data/logs/process.jsonl | jq
```

## 🔒 Security Notes

- API keys are sanitized in logs
- Database files should have proper permissions
- Use environment variables for secrets
- Never commit `.env` files

## 📚 Additional Resources

- [Production Safety](docs/PRODUCTION_SAFETY.md)
- [Trading Deployment](docs/TRADING_DEPLOYMENT.md)
- [Health Monitoring](ops/HEALTH_CHECK.md)
- [Troubleshooting](ops/TROUBLESHOOTING.md)
