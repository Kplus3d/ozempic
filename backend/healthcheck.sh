#!/usr/bin/env bash
# Check if Ozempic server is alive; restart if not
LOG="/tmp/ozempic-healthcheck.log"

if ! curl -s --connect-timeout 2 http://127.0.0.1:8001/api/health > /dev/null 2>&1; then
    echo "[$(date)] Server not responding, restarting..." >> "$LOG"
    pkill -f "server.py" 2>/dev/null || true
    sleep 2
    (
        ulimit -v 1572864 2>/dev/null || true
        echo -999 > /proc/self/oom_score_adj 2>/dev/null || true
        exec /usr/bin/python ~/ozempic/backend/server.py
    ) &
    echo "[$(date)] Restart attempt complete" >> "$LOG"
else
    echo "[$(date)] OK" >> "$LOG"
fi
