#!/bin/bash
# Trading System Startup Script
# Starts both the signal bot and trading system with proper synchronization

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Trading System Startup${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found!${NC}"
    echo "Creating from env.example..."
    if [ -f "env.example" ]; then
        cp env.example .env
        echo -e "${GREEN}✅ Created .env file${NC}"
        echo -e "${YELLOW}⚠️  Please edit .env and set your API keys and wallet secret${NC}"
        exit 1
    else
        echo -e "${RED}❌ env.example not found!${NC}"
        exit 1
    fi
fi

# Load environment
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ Loading environment from .env${NC}"
    export $(grep -v '^#' .env | xargs)
fi

# Check Python
if ! command -v python &> /dev/null; then
    echo -e "${RED}❌ Python not found!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python found: $(python --version)${NC}"

# Check Redis
echo ""
echo "Checking Redis..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Redis is running${NC}"
    else
        echo -e "${YELLOW}⚠️  Redis is not running${NC}"
        echo "Starting Redis..."
        if command -v redis-server &> /dev/null; then
            redis-server --daemonize yes
            sleep 2
            if redis-cli ping > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Redis started${NC}"
            else
                echo -e "${RED}❌ Failed to start Redis${NC}"
                exit 1
            fi
        else
            echo -e "${RED}❌ redis-server not found. Please install Redis.${NC}"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}⚠️  redis-cli not found. Assuming Redis is running elsewhere...${NC}"
fi

# Run verification script
echo ""
echo -e "${BLUE}Running system verification...${NC}"
if python scripts/verify_trading_system.py; then
    echo -e "${GREEN}✅ System verification passed${NC}"
else
    echo -e "${RED}❌ System verification failed${NC}"
    echo "Fix the issues above before starting the trading system."
    exit 1
fi

# Ask user for mode
echo ""
echo -e "${BLUE}Select startup mode:${NC}"
echo "1) Bot only (generate signals)"
echo "2) Trading system only (execute trades from existing signals)"
echo "3) Both bot and trading system (full stack)"
echo "4) Dry run test (both, but no real trades)"
echo -n "Enter choice [1-4]: "
read -r choice

case $choice in
    1)
        echo -e "${GREEN}Starting signal bot only...${NC}"
        python scripts/bot.py run
        ;;
    2)
        echo -e "${GREEN}Starting trading system only...${NC}"
        python scripts/bot.py trade
        ;;
    3)
        echo -e "${YELLOW}⚠️  Starting full stack (bot + trading system)${NC}"
        echo ""
        
        # Check if live trading
        if [ "${TS_DRY_RUN}" = "false" ]; then
            echo -e "${RED}═══════════════════════════════════════${NC}"
            echo -e "${RED}WARNING: LIVE TRADING IS ENABLED${NC}"
            echo -e "${RED}This will execute REAL trades with REAL money!${NC}"
            echo -e "${RED}═══════════════════════════════════════${NC}"
            echo ""
            echo -n "Type 'I UNDERSTAND' to continue: "
            read -r confirmation
            if [ "$confirmation" != "I UNDERSTAND" ]; then
                echo "Aborted."
                exit 1
            fi
        else
            echo -e "${GREEN}Dry run mode enabled - safe testing${NC}"
        fi
        
        # Start bot in background
        echo "Starting signal bot..."
        python scripts/bot.py run > data/logs/bot.log 2>&1 &
        BOT_PID=$!
        echo -e "${GREEN}✅ Bot started (PID: $BOT_PID)${NC}"
        
        # Wait for bot to initialize
        echo "Waiting for bot to initialize..."
        sleep 5
        
        # Start trading system
        echo "Starting trading system..."
        python scripts/bot.py trade
        
        # Cleanup on exit
        echo "Stopping bot..."
        kill $BOT_PID 2>/dev/null || true
        ;;
    4)
        echo -e "${GREEN}Starting in DRY RUN mode...${NC}"
        export TS_DRY_RUN=true
        export DRY_RUN=true
        
        # Start bot in background
        echo "Starting signal bot (dry run)..."
        python scripts/bot.py run > data/logs/bot.log 2>&1 &
        BOT_PID=$!
        echo -e "${GREEN}✅ Bot started (PID: $BOT_PID)${NC}"
        
        # Wait for bot to initialize
        echo "Waiting for bot to initialize..."
        sleep 5
        
        # Start trading system in dry run
        echo "Starting trading system (dry run)..."
        python scripts/bot.py trade
        
        # Cleanup on exit
        echo "Stopping bot..."
        kill $BOT_PID 2>/dev/null || true
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

