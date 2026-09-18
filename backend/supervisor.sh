#!/usr/bin/env bash
# Ozempic supervisor - memory capped, auto-restart loop

MAX_MEM_KB=2621440  # 2.5GB in KB
LOG="/tmp/ozempic.log"
PID_DIR="~/.ozempic"
LOCK_FILE="~/.ozempic/supervisor.lock"
PORT=8001

mkdir -p "$PID_DIR"

# Prevent duplicate supervisors
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date)] Another supervisor already running (PID $OLD_PID). Exiting." >> "$LOG"
        exit 0
    fi
    rm -f "$LOCK_FILE"
fi
echo $$ > "$LOCK_FILE"

echo "[$(date)] Ozempic supervisor starting (PID $$)..." >> "$LOG"
RESTARTS=0

while true; do
    # Check if server is already running
    if curl -s --connect-timeout 2 http://127.0.0.1:$PORT/api/health > /dev/null 2>&1; then
        echo "[$(date)] Server already responding on port $PORT (healthy)" >> "$LOG"
        # Verify it's our server
        if [ -f "$PID_DIR/server.pid" ]; then
            OWN_PID=$(cat "$PID_DIR/server.pid")
            if kill -0 "$OWN_PID" 2>/dev/null; then
                # Our server is alive — just poll, don't use wait (can't wait on non-child)
                echo "[$(date)] Monitoring server PID $OWN_PID..." >> "$LOG"
                sleep 5
                continue
            else
                # Our PID is gone — fall through to restart
                echo "[$(date)] Previous server PID $OWN_PID is dead, restarting..." >> "$LOG"
            fi
        fi
    fi

    echo "[$(date)] Launching server.py (attempt $((RESTARTS + 1)))" >> "$LOG"

    # Start server detached from terminal
    (
        ulimit -v $MAX_MEM_KB 2>/dev/null || true
        echo -999 > /proc/self/oom_score_adj 2>/dev/null || true
        exec /usr/bin/python ~/ozempic/backend/server.py >> "$LOG" 2>&1
    ) &>/dev/null &

    SERVER_PID=$!
    echo $SERVER_PID > "$PID_DIR/server.pid"
    disown $SERVER_PID 2>/dev/null

    echo "[$(date)] Server PID: $SERVER_PID" >> "$LOG"

    # Wait for this server to exit (it IS a child, so wait works)
    wait $SERVER_PID 2>/dev/null
    EXIT_CODE=$?

    echo "[$(date)] Server exited (code: $EXIT_CODE), restarting in 3s..." >> "$LOG"
    RESTARTS=$((RESTARTS + 1))
    sleep 3
done
