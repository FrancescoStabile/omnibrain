#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# OmniBrain — run backend + frontend in one shot
# Usage:  ./run.sh          (starts both)
#         ./run.sh stop     (kills both)
# ─────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=7432
FRONTEND_PORT=3000
PIDFILE_BACK="$ROOT/.pid-backend"
PIDFILE_FRONT="$ROOT/.pid-frontend"
LOG_BACK="$ROOT/.log-backend.txt"
LOG_FRONT="$ROOT/.log-frontend.txt"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${CYAN}Shutting down OmniBrain...${NC}"
    # Kill backend
    if [[ -f "$PIDFILE_BACK" ]]; then
        kill "$(cat "$PIDFILE_BACK")" 2>/dev/null || true
        rm -f "$PIDFILE_BACK"
    fi
    # Kill frontend
    if [[ -f "$PIDFILE_FRONT" ]]; then
        kill "$(cat "$PIDFILE_FRONT")" 2>/dev/null || true
        rm -f "$PIDFILE_FRONT"
    fi
    # Belt-and-suspenders: kill by port
    lsof -t -i :"$BACKEND_PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
    lsof -t -i :"$FRONTEND_PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
    echo -e "${GREEN}Done.${NC}"
}

# ── Stop mode ──
if [[ "${1:-}" == "stop" ]]; then
    cleanup
    exit 0
fi

# ── Pre-flight: kill anything on our ports ──
lsof -t -i :"$BACKEND_PORT" -i :"$FRONTEND_PORT" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
sleep 2

trap cleanup EXIT INT TERM

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         🧠  OmniBrain  🧠            ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

# ── Check venv ──
if [[ ! -f "$ROOT/.venv/bin/python" ]]; then
    echo -e "${RED}ERROR: .venv not found. Run: python -m venv .venv && pip install -e .${NC}"
    exit 1
fi

# ── Check .env ──
if [[ ! -f "$ROOT/.env" ]]; then
    echo -e "${RED}ERROR: .env not found. Create one with at least DEEPSEEK_API_KEY=...${NC}"
    exit 1
fi

# ── Start Backend ──
echo -e "${CYAN}Starting backend on port ${BACKEND_PORT}...${NC}"
cd "$ROOT"
.venv/bin/python -m omnibrain api --host 127.0.0.1 --port "$BACKEND_PORT" > "$LOG_BACK" 2>&1 &
echo $! > "$PIDFILE_BACK"

# Wait for backend to be ready
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend ready${NC}"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo -e "${RED}✗ Backend failed to start. Check $LOG_BACK${NC}"
        exit 1
    fi
    sleep 0.5
done

# ── Read auth token for frontend ──
AUTH_TOKEN_FILE="${HOME}/.omnibrain/auth_token"
if [[ -f "$AUTH_TOKEN_FILE" ]]; then
    export OMNIBRAIN_API_KEY="$(cat "$AUTH_TOKEN_FILE")"
fi

# ── Start Frontend ──
echo -e "${CYAN}Starting frontend on port ${FRONTEND_PORT}...${NC}"
cd "$ROOT/web"
node_modules/.bin/next dev --turbopack -p "$FRONTEND_PORT" > "$LOG_FRONT" 2>&1 &
echo $! > "$PIDFILE_FRONT"

# Wait for frontend (use bash TCP probe — Next.js compiles lazily)
for i in $(seq 1 60); do
    if (echo > /dev/tcp/127.0.0.1/"$FRONTEND_PORT") 2>/dev/null; then
        echo -e "${GREEN}✓ Frontend ready${NC}"
        break
    fi
    if [[ $i -eq 60 ]]; then
        echo -e "${RED}✗ Frontend failed to start. Check $LOG_FRONT${NC}"
        cat "$LOG_FRONT"
        exit 1
    fi
    sleep 0.5
done

echo ""
echo -e "${BOLD}${GREEN}  OmniBrain is running!${NC}"
echo -e "  ${CYAN}App:${NC}      http://localhost:${FRONTEND_PORT}"
echo -e "  ${CYAN}API:${NC}      http://127.0.0.1:${BACKEND_PORT}/api/v1/status"
echo -e "  ${CYAN}Logs:${NC}     tail -f $LOG_BACK"
echo -e "  ${CYAN}Stop:${NC}     Ctrl+C  or  ./run.sh stop"
echo ""

# Keep alive — show backend logs
tail -f "$LOG_BACK"
