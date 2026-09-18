# Ozempic — Setup & Deployment

Exact install/run steps for the development machine and for the deployment target — an
NVIDIA **Jetson Orin Nano** edge box (Ubuntu 22.04, arm64, JetPack R36, kernel
`5.15.148-tegra`, system Python 3.10).

---

## 0. What you actually need (read this first)

`backend/requirements.txt` is **incomplete**. Its full committed contents are:

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
```

It does **not** list the OpenCASCADE bindings (`OCP`), **NumPy** or **PyJWT**, all of
which the code imports at runtime:

| Imported in | Package | Why |
|---|---|---|
| `engine.py`, `preview.py` | `cadquery-ocp` (provides `OCP`) | STEP read/write, meshing, MakeThickSolid |
| `OCP.*` transitively | `numpy` | OCP wheels depend on it |
| `auth.py` | `PyJWT` | `import jwt` for token encode/decode |

You must install those three explicitly. Also be aware the committed pins are **older
than what is actually running on the deployment machine** — see the table below.

### Version reality check

| Package | `requirements.txt` pin | Installed on the Jetson (`/usr/bin/python` 3.10.12) |
|---|---|---|
| `fastapi` | `0.104.1` | `0.136.1` |
| `uvicorn` | `0.24.0` (`[standard]`) | `0.46.0` |
| `python-multipart` | `0.0.6` | `0.0.27` |
| `cadquery-ocp` | *(absent)* | `7.9.3.0` |
| `cadquery-ocp-proxy` | *(absent)* | `7.9.3.0` |
| `numpy` | *(absent)* | `2.2.6` |
| `PyJWT` | *(absent)* | `2.3.0` |
| `pydantic` | *(absent)* | `2.13.3` |
| `starlette` | *(absent)* | `1.0.0` |

**Note on NumPy**: the codebase does not pin `<2.0`; nothing in the source constrains
NumPy. The deployed interpreter has **NumPy 2.2.6**. If you intend to reproduce the
production environment, install the *installed* versions above rather than the stale
`requirements.txt` pins, or refresh the pins before relying on them.

---

## 1. Development machine (x86_64 or arm64 Linux/macOS)

### 1.1 System prerequisites

- Python **3.10+** (3.10 verified; the deployment uses 3.10.12).
- Node.js **18+** with npm (for the Vite/React frontend).
- A working C toolchain is not needed — the OCP wheels ship prebuilt binaries.

### 1.2 Clone / unpack

```bash
git clone <your-remote> ozempic      # or copy the bundle directory to the machine
cd ozempic
```

### 1.3 Python environment

Create a virtualenv to keep OCP isolated:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# OCP wheels (this is the STEP/OpenCASCADE engine)
pip install cadquery-ocp==7.9.3.0

# The three required deps, then the committed pins last so they can't silently
# downgrade anything that matters:
pip install PyJWT numpy
pip install -r backend/requirements.txt
```

> If you install `-r backend/requirements.txt` first and it pulls a different
> NumPy/Pydantic, don't worry — nothing in the source depends on a specific NumPy
> major version. But do make sure `import jwt`, `import OCP` and `import numpy` all
> succeed before running.

Verify:

```bash
python -c "import OCP, numpy, jwt, fastapi, uvicorn; print('deps ok')"
```

### 1.4 Run the backend (dev)

```bash
cd backend
python3 main.py            # uvicorn on 0.0.0.0:8001
```

- API: <http://localhost:8001>
- Swagger UI: <http://localhost:8001/docs>
- Health: <http://localhost:8001/api/health>

For the memory-capped production-style process use `python3 server.py` instead (sets
`RLIMIT_AS` and the OOM watchdog — see §3).

`temp_uploads/` is created automatically at import, one level up from `backend/`.

### 1.5 Frontend (dev)

```bash
cd frontend
npm install
npm run dev                # Vite dev server on :5173, proxies /api → :8001
```

Open <http://localhost:5173>. CORS already allows this origin.

### 1.6 Build the frontend for production

```bash
cd frontend
npm run build              # tsc && vite build → frontend/dist
```

Once `frontend/dist` exists, the backend serves the SPA at
<http://localhost:8001/> and mounts its assets at `/static/assets`. Until then `GET /`
returns 404.

### 1.7 Tests

```bash
cd ozempic
python3 -m pytest tests/test_core.py -v
# expected: 11 passed
```

Standalone engine smoke test (creates its own box STEP file):

```bash
cd backend && python3 test_engine.py
```

---

## 2. Deployment target — Jetson Orin Nano

Verified platform: Ubuntu 22.04.5 LTS, arm64, kernel `5.15.148-tegra`, JetPack
**R36 rev 4.7**, system Python **3.10.12**, deployed at **`~/ozempic`** (paths in
the shell scripts are hard-coded to this location).

### 2.1 Dependencies

Use the **system** Python (`/usr/bin/python`, i.e. 3.10) — that is what `server.py` and
the shell scripts invoke. On aarch64, OCP wheels install into the user site
(`~/.local/lib/python3.10/site-packages`):

```bash
/usr/bin/python -m pip install --user cadquery-ocp==7.9.3.0
/usr/bin/python -m pip install --user PyJWT numpy
/usr/bin/python -m pip install --user -r ~/ozempic/backend/requirements.txt
```

Verify with the system interpreter:

```bash
/usr/bin/python -c "import OCP, numpy, jwt, fastapi; print('runtime ok')"
```

### 2.2 Build the frontend

```bash
cd ~/ozempic/frontend && npm install && npm run build
```

### 2.3 Auto-start on boot (crontab)

The box runs the supervisor from crontab (export `OZEMPIC_ADMIN_PASSWORD` first if you
want `/api/login` to work; the supervisor inherits the environment of the cron job):

```bash
crontab -l
# @reboot nohup bash ~/ozempic/backend/supervisor.sh >> /tmp/ozempic-supervisor.log 2>&1 &
```

To install/reinstall it:

```bash
( crontab -l 2>/dev/null; \
  echo '@reboot nohup bash ~/ozempic/backend/supervisor.sh >> /tmp/ozempic-supervisor.log 2>&1 &' ) | crontab -
```

Make the scripts executable:

```bash
chmod +x ~/ozempic/backend/supervisor.sh ~/ozempic/backend/healthcheck.sh
```

### 2.4 Start / stop / inspect

```bash
# start now without rebooting
nohup bash ~/ozempic/backend/supervisor.sh >> /tmp/ozempic-supervisor.log 2>&1 &

# health
curl -s http://localhost:8001/api/health

# logs
tail -f /tmp/ozempic.log                 # server + supervisor loop
tail -f /tmp/ozempic-supervisor.log      # crontab redirect

# manual one-shot recovery (does NOT use the supervisor lock)
bash ~/ozempic/backend/healthcheck.sh

# stop everything
pkill -f supervisor.sh; pkill -f "server.py"
```

Runtime state lives in `~/.ozempic/`:
- `supervisor.lock` — supervisor PID (single-instance guard)
- `server.pid` — current server PID

### 2.5 Memory behavior (why this box needs care)

- `supervisor.sh` launches the server under `ulimit -v 2621440` (**2.5 GB** virtual).
- `server.py` additionally sets `RLIMIT_AS` to **2.5 GB**, writes `oom_score_adj=-999`,
  and runs a watchdog that `os._exit(137)`s if RSS ≥ 90 % of the cap.
- `healthcheck.sh` (manual only) uses a tighter **1.5 GB** `ulimit -v`.
- If the server dies with code 137, that is the watchdog — the supervisor restarts it
  after 3 s. Process smaller/simpler parts if this recurs.

---

## 3. Two ways to run the backend, summarized

| Entrypoint | Command | Memory cap | Use |
|---|---|---|---|
| Dev | `python3 backend/main.py` | none | local development |
| Production | `python3 backend/server.py` | 2.5 GB `RLIMIT_AS` + watchdog | Jetson |
| Supervised | `bash backend/supervisor.sh` | supervisor `ulimit -v` + auto-restart | boot / long-running |

Only `server.py` and `supervisor.sh` are used in production; `main.py`'s
`__main__` block is the plain dev server.

---

## 4. Upgrade procedure

```bash
cd ~/ozempic
git pull                       # (once the repo has a remote/commit history)
cd frontend && npm install && npm run build && cd ..
# restart under the supervisor
pkill -f "server.py"
# supervisor.sh will relaunch it automatically; or start it if it isn't running:
pgrep -f supervisor.sh || nohup bash backend/supervisor.sh >> /tmp/ozempic-supervisor.log 2>&1 &
```

Always rebuild `frontend/dist` after frontend changes — the backend serves the built
files, not the TypeScript sources.

---

## 5. Troubleshooting checklist

| Check | Command |
|---|---|
| Is it listening? | `ss -ltnp \| grep 8001` |
| Health | `curl -s http://localhost:8001/api/health` |
| Which interpreter runs it? | `ls -l /proc/$(pgrep -f server.py)/exe` → should be `python3.10` |
| Deps present? | `/usr/bin/python -c "import OCP, numpy, jwt, fastapi"` |
| Logs | `tail -100 /tmp/ozempic.log` |
| Supervisor alive? | `pgrep -f supervisor.sh; cat ~/.ozempic/supervisor.lock` |
| Crontab entry | `crontab -l \| grep ozempic` |

Common failures: missing `PyJWT` (not in requirements.txt), missing `frontend/dist`
(404 at `/`), a second supervisor already holding the lock (exits silently by design),
and rate-limit 429s if you poll `/api/health` faster than ~every 2 s.