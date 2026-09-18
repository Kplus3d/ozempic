#!/usr/bin/env python3
"""
Ozempic - STEP File Wall Thickness Modifier
Lightweight server with OOM protection and security
"""

import os
import signal
import sys
import uvicorn
from main import app

# Try to lower OOM score and set memory limit
try:
    os.nice(10)
except Exception:
    pass

# Set OOM score
try:
    with open(f"/proc/{os.getpid()}/oom_score_adj", "w") as f:
        f.write("-999")
except Exception:
    pass

# Set memory limit (2.5 GB) with graceful self-termination check
try:
    import resource

    limit = int(2.5 * 1024 * 1024 * 1024)  # 2.5 GB in bytes
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    print(f"Set virtual memory limit to {limit // (1024*1024*1024)}GB")

    # Add periodic memory watchdog (checks every 30s, self-terminates at 90% of limit)
    import threading

    def memory_watchdog():
        try:
            thresh = int(limit * 0.9)  # 90% of limit
            while True:
                try:
                    with open(f"/proc/{os.getpid()}/status") as f:
                        for line in f:
                            if line.startswith("VmRSS:"):
                                rss_kb = int(line.split()[1])
                                rss_bytes = rss_kb * 1024
                                if rss_bytes > thresh:
                                    print(f"[OOM watchdog] RSS {rss_bytes // (1024*1024)}MB > {thresh // (1024*1024)}MB threshold — self-terminating")
                                    os._exit(137)  # SIGKILL code
                                break
                except Exception:
                    pass
                time.sleep(30)
        except Exception:
            pass

    import time
    t = threading.Thread(target=memory_watchdog, daemon=True)
    t.start()
except Exception as e:
    print(f"Memory limit setup error: {e}")
    pass

print("Starting Ozempic on port 8001...")
print(f"Current PID: {os.getpid()}")
print(f"Open file descriptors limit: {resource.getrlimit(resource.RLIMIT_NOFILE)}")

# Handle graceful shutdown
def signal_handler(sig, frame):
    print("\nShutting down Ozempic...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
