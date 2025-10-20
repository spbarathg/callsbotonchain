#!/bin/bash
# Start main bot with Signal Aggregator for multi-bot consensus scoring
# 
# This script runs:
# 1. Signal Aggregator daemon (monitors external Telegram groups)
# 2. Main bot (processes Cielo feed and sends alerts)
#
# Both processes share data via Redis for cross-process communication

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Starting Bot with Signal Aggregator${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    exit 1
fi

# Load environment
export $(grep -v '^#' .env | xargs)

# Check Redis
echo "Checking Redis..."
if command -v redis-cli &> /dev/null; then
    if ! redis-cli ping > /dev/null 2>&1; then
        echo -e "${RED}❌ Redis is not running!${NC}"
        echo "Signal Aggregator requires Redis for cross-process communication."
        echo ""
        echo "To start Redis:"
        echo "  - Linux: sudo systemctl start redis"
        echo "  - macOS: brew services start redis"
        echo "  - Manual: redis-server --daemonize yes"
        exit 1
    fi
    echo -e "${GREEN}✅ Redis is running${NC}"
else
    echo -e "${YELLOW}⚠️  redis-cli not found. Assuming Redis is running...${NC}"
fi

# Check if signal aggregator session exists
SESSION_FILE="${SIGNAL_AGGREGATOR_SESSION_FILE:-var/memecoin_session.session}"
if [ ! -f "$SESSION_FILE" ]; then
    echo -e "${YELLOW}⚠️  Signal Aggregator session not found: $SESSION_FILE${NC}"
    echo "Signal Aggregator will prompt for Telegram authorization on first run."
    echo ""
fi

# PIDs for cleanup
AGGREGATOR_PID=""
BOT_PID=""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    
    if [ ! -z "$BOT_PID" ]; then
        echo "Stopping main bot (PID: $BOT_PID)..."
        kill $BOT_PID 2>/dev/null || true
    fi
    
    if [ ! -z "$AGGREGATOR_PID" ]; then
        echo "Stopping signal aggregator (PID: $AGGREGATOR_PID)..."
        kill $AGGREGATOR_PID 2>/dev/null || true
    fi
    
    echo -e "${GREEN}✅ All processes stopped${NC}"
    exit 0
}

# Register cleanup on exit
trap cleanup SIGINT SIGTERM EXIT

# Start Signal Aggregator daemon
echo ""
echo -e "${BLUE}Starting Signal Aggregator daemon...${NC}"
python scripts/signal_aggregator_daemon.py > data/logs/signal_aggregator.log 2>&1 &
AGGREGATOR_PID=$!
echo -e "${GREEN}✅ Signal Aggregator started (PID: $AGGREGATOR_PID)${NC}"
echo "   Monitoring 13 Telegram groups for consensus signals"
echo "   Log: data/logs/signal_aggregator.log"

# Wait for aggregator to initialize
sleep 3

# Check if aggregator is still running
if ! kill -0 $AGGREGATOR_PID 2>/dev/null; then
    echo -e "${RED}❌ Signal Aggregator failed to start!${NC}"
    echo "Check data/logs/signal_aggregator.log for errors"
    exit 1
fi

# Start main bot
echo ""
echo -e "${BLUE}Starting main bot...${NC}"
python scripts/bot.py run > data/logs/bot.log 2>&1 &
BOT_PID=$!
echo -e "${GREEN}✅ Main bot started (PID: $BOT_PID)${NC}"
echo "   Processing Cielo feed with multi-bot consensus scoring"
echo "   Log: data/logs/bot.log"

# Display status
echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}✅ ALL SYSTEMS OPERATIONAL${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Running processes:"
echo "  - Signal Aggregator: PID $AGGREGATOR_PID (monitors external groups)"
echo "  - Main Bot:          PID $BOT_PID (processes feed + consensus)"
echo ""
echo "Data flow:"
echo "  1. External groups → Signal Aggregator → Redis"
echo "  2. Cielo feed → Main Bot → checks Redis → Alert"
echo ""
echo "Scoring bonuses when consensus detected:"
echo "  - 3+ groups: +2 score (strong validation)"
echo "  - 2 groups:  +1 score"
echo "  - 0 groups:  -1 score (solo signal)"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all processes${NC}"
echo ""

# Monitor logs in real-time (interleaved)
echo "=== LIVE LOGS (Ctrl+C to stop) ==="
tail -f data/logs/signal_aggregator.log data/logs/bot.log







