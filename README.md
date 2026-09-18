# Ozempic

A web app that analyses and modifies the **wall thickness** of STEP CAD parts — an
injection-moulding / part-manufacturability check. Upload a solid, pick a thickness,
get back a hollowed STEP file plus volume/surface metrics and an interactive 3D preview.

Internal R&D project — not currently distributed.

> New to the project? Start with [docs/SETUP.md](docs/SETUP.md) for install/run and
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.
> The authoritative HTTP reference is [docs/API.md](docs/API.md).

---

## Why it exists

Checking whether a part can actually be moulded at a given wall thickness normally
means opening a CAD package, manually shelling the solid, and eyeballing the result.
Ozempic turns that into one upload: it runs OpenCASCADE's `BRepOffsetAPI_MakeThickSolid`
on the largest solid in the file and reports exactly how much material the new wall
thickness removes. It was built to run on a small NVIDIA Jetson Orin Nano edge box
next to the shop floor, not on a workstation.

---

## Features

| Feature | Notes |
|---|---|
| STEP wall-thickness modification | Hollows the largest solid via `BRepOffsetAPI_MakeThickSolid` with an empty face list (uniform shell, no openings). |
| Geometry validation | Face/edge/vertex counts, volume, surface area, bounding box. |
| Interactive 3D preview | Server-side OpenCASCADE meshing → Three.js viewer (drag to rotate, scroll to zoom). |
| Multiple formats accepted by preview | `.step .stp .sldprt .sldasm .stl .obj .iges .igs` (see the honesty note below). |
| Batch processing | `POST /api/batch-process` handles many files in one request. |
| JWT login endpoints | `POST /api/login`, `GET /api/me` (see limitations — not yet enforced). |
| Single-page UI | React 19 + TypeScript + Vite, dark theme, no heavy UI framework. |
| OOM-safe deployment | `ulimit -v` + `RLIMIT_AS` + a self-terminating memory watchdog + supervisor restart loop. |

### Honesty note on accepted formats

`/api/preview` and the frontend *accept the extensions* for SolidWorks, STL, OBJ and
IGES, but the backend only ever parses the file with the **STEP** reader
(`step_file_to_mesh_data`). There is **no converter** in this codebase — a non-STEP
file will fail to parse and the preview silently degrades to an empty mesh with an
error string. Only real STEP/STP solids are fully supported end-to-end.
`/api/validate` hard-rejects anything that is not `.step`/`.stp`.

---

## Architecture at a glance

```
Browser (React + Three.js)
      │  multipart/form-data
      ▼
FastAPI (backend/main.py)  ──► engine.py     (validate + MakeThickSolid)
      │                                      
      │  serves built frontend from ../frontend/dist
      ▼
backend/server.py (memory caps) ◄── backend/supervisor.sh (ulimit + restart loop)
```

- **Backend**: FastAPI 0.104-era app (`app = FastAPI(title="Ozempic", version="1.1.0")`),
  served on **port 8001**. Heavy lifting in `engine.py` (thickness) and `preview.py` (meshing).
- **Frontend**: Vite + React + TypeScript in `frontend/`. In production the backend
  serves `frontend/dist` as static files; in dev, Vite proxies `/api` to port 8001.
- **Edge hardening**: `server.py` caps virtual memory, `supervisor.sh` restarts on exit.

### Directory tree

```
ozempic/
├── README.md                 # this file
├── LICENSE                   # proprietary, all rights reserved
├── .gitignore
├── API_DOCUMENTATION.md      # superseded → archived copy lives in docs/archive/
├── backend/
│   ├── main.py               # FastAPI app, routes, middleware, static serving
│   ├── engine.py             # STEP read/validate + MakeThickSolid thickness engine
│   ├── preview.py            # STEP → triangle mesh for the 3D viewer
│   ├── auth.py               # JWT create/verify, in-memory user store
│   ├── server.py             # production entrypoint: RLIMIT_AS + OOM watchdog
│   ├── supervisor.sh         # ulimit -v wrapper + auto-restart loop
│   ├── healthcheck.sh        # one-shot liveness check / restart helper
│   ├── requirements.txt      # Python deps (see SETUP for the pin caveats)
│   └── test_engine.py        # standalone engine smoke-test script (not pytest)
├── frontend/
│   ├── index.html
│   ├── package.json          # Vite + React 19 + three
│   ├── vite.config.ts        # /api → http://localhost:8001 proxy
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx           # upload → validate → preview → process → download
│       └── components/
│           ├── StepUploader.tsx      # drag & drop + client-side format/size checks
│           ├── ThicknessControl.tsx  # wall-thickness slider
│           └── Viewer3D.tsx          # Three.js mesh viewer
├── tests/
│   ├── test_core.py          # pytest suite (validation, thickness, preview, auth)
│   └── test_step.step        # 100×100×100 mm box fixture (volume 1,000,000 mm³)
└── docs/
    ├── ARCHITECTURE.md
    ├── SETUP.md
    ├── API.md
    └── archive/              # historical audit reports & improvement summaries
```

> Scratch CAD files (`*.step` at the repo root, `temp_uploads/`) are **git-ignored**.
> The one committed fixture is `tests/test_step.step`, which the tests require.

---

## Quick start

### 1. Backend

```bash
# OpenCASCADE Python bindings (OCP) provide the STEP engine.
pip install cadquery-ocp==7.9.3.0
pip install -r backend/requirements.txt

cd backend
python3 main.py          # dev: plain uvicorn on 0.0.0.0:8001
# or, production entrypoint with memory caps:
python3 server.py
```

The API is then at `http://localhost:8001`, interactive docs at
`http://localhost:8001/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # dev server on :5173, proxies /api → :8001
npm run build      # emits frontend/dist, which the backend serves at /
```

Once `frontend/dist` exists, the backend serves the UI directly from
`http://localhost:8001/`.

### 3. Try it

```bash
curl http://localhost:8001/api/health
# {"status":"ok","service":"ozempic","version":"1.1.0"}

curl -F "file=@tests/test_step.step" http://localhost:8001/api/validate
curl -F "file=@tests/test_step.step" -o out.step \
     "http://localhost:8001/api/process?thickness=2.0"
```

---

## Configuration / environment variables

One environment variable exists — the admin password:

| Variable | Purpose |
|---|---|
| `OZEMPIC_ADMIN_PASSWORD` | Password for the single `admin` account, read by `backend/auth.py` at import. **There is no default**: if it is unset, no password authenticates and `/api/login` always fails. Set it before starting the service. |

Everything else is a compile-time constant:

| Setting | Value | Where |
|---|---|---|
| Server port / host | `8001` / `0.0.0.0` | `backend/main.py`, `backend/server.py` |
| Max upload size | `50 MB` (`50 * 1024 * 1024`) | `backend/main.py` |
| Rate limit | `30` requests / `60` seconds per client IP | `backend/main.py` |
| CORS origins | `http://localhost:8001`, `http://localhost:5173`, `http://127.0.0.1:8001` | `backend/main.py` |
| Temp upload dir | `<repo>/temp_uploads` (created on import) | `backend/main.py` |
| JWT algorithm / expiry | `HS256` / 7 days (`60 * 24 * 7` minutes) | `backend/auth.py` |
| Memory cap (`RLIMIT_AS`) | `2.5 GB` | `backend/server.py` |
| Watchdog threshold | 90 % of the cap, checked every 30 s | `backend/server.py` |
| Supervisor memory cap | `2621440 KB` (2.5 GB) | `backend/supervisor.sh` |
| Healthcheck memory cap | `1572864 KB` (1.5 GB) | `backend/healthcheck.sh` |
| Log file | `/tmp/ozempic.log` | `backend/supervisor.sh` |

To change any of these you edit the constants (rebuild/redeploy) — they are not
runtime-tunable.

---

## Testing

The pytest suite lives in `tests/test_core.py` and needs its fixture
`tests/test_step.step` (tests *skip*, not fail, if it is missing).

```bash
cd ozempic
python3 -m pytest tests/test_core.py -v
```

Verified on the dev/Jetson box: **11 passed** (validation, thickness processing at
0.1–20 mm, preview mesh + bounds, JWT create/verify/authenticate). The fixture is a
100×100×100 mm box: 1 shape, 6 faces, 24 edges, 48 vertices, volume 1,000,000 mm³,
surface area 60,000 mm², and it meshes to 12 triangles.

`backend/test_engine.py` is a **standalone script** (not a pytest test) that generates
its own `test_box.solid.step` and exercises the engine directly:

```bash
cd backend && python3 test_engine.py
```

---

## Deployment (Jetson edge box)

Production runs on an NVIDIA **Jetson Orin Nano** (Ubuntu 22.04, arm64, JetPack R36 /
kernel `5.15.148-tegra`) with system Python 3.10.

- **Boot / auto-start**: a crontab `@reboot` entry launches the supervisor:
  ```
  @reboot nohup bash ~/ozempic/backend/supervisor.sh >> /tmp/ozempic-supervisor.log 2>&1 &
  ```
- **Supervisor** (`backend/supervisor.sh`): takes a lock
  (`~/.ozempic/supervisor.lock`), polls `/api/health`, and runs the server in a
  loop: `ulimit -v 2621440`, `oom_score_adj=-999`, then
  `exec /usr/bin/python ~/ozempic/backend/server.py`. If the server exits it
  restarts after 3 s.
- **Memory**: `server.py` sets `RLIMIT_AS` to 2.5 GB and a daemon thread reads
  `VmRSS` every 30 s, calling `os._exit(137)` if RSS exceeds 90 % of the cap. Typical
  steady-state RSS is a few hundred MB; OCP STEP workloads are the spike risk.
- **Health**: `http://localhost:8001/api/health`.
- **Logs**: `/tmp/ozempic.log` (server + supervisor) and
  `/tmp/ozempic-supervisor.log` (crontab redirect).
- **Note**: `backend/healthcheck.sh` exists as a manual one-shot liveness check
  (it `pkill -f server.py`s and restarts with a 1.5 GB cap); it is **not** scheduled
  in the crontab.

See [docs/SETUP.md](docs/SETUP.md) for the full step-by-step on both the dev machine
and the Jetson.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Server not reachable on 8001 | Check `curl http://localhost:8001/api/health`; look at `/tmp/ozempic.log`. Restart: `bash backend/healthcheck.sh`, or kill the supervisor and re-run it. |
| `429 Rate limit exceeded` | 30 req/min per IP. `/api/health` is also counted — don't poll faster than ~every 2 s. Wait 60 s. |
| `File too large. Maximum size is 50MB` | Upload exceeds the 50 MB cap; the frontend rejects it earlier too. |
| `Processing failed — check geometry` / `Volume unchanged` | The solid isn't watertight, or the wall thickness is too large for the part. Try a smaller thickness. |
| `MakeThickSolid failed to produce a shape` | Same class of geometry problem — shelling failed. |
| Preview is empty / "3D preview generation failed" | The file isn't really a STEP solid (SolidWorks/STL/OBJ/IGES are not converted — see the honesty note). Thickness modification may still work if it parses. |
| Login token stops working after a restart | Expected: `SECRET_KEY` is regenerated with `secrets.token_hex(32)` at every process start, so all issued tokens are invalidated by a restart. |
| Server dies with exit code 137 | The OOM watchdog fired (RSS ≥ 90 % of the 2.5 GB cap). The supervisor restarts it; process a smaller/simpler file. |
| `ImportError: No module named 'jwt'` | `PyJWT` is required by `backend/auth.py` but is **not** listed in `backend/requirements.txt` — install it explicitly. |
| Frontend 404s at `/` | `frontend/dist` was never built (`npm run build`), so the backend doesn't mount the UI. |

---

## Known limitations

- **No enforced authentication.** `auth.py` and the `/api/login`, `/api/me` endpoints
  exist, but no data endpoint (`/api/validate`, `/api/process`, `/api/preview`,
  `/api/batch-process`) requires a token. There is also no frontend login page, and
  `require_admin` is defined but never used.
- **`requirements.txt` is incomplete/out of sync.** It pins only
  `fastapi`, `uvicorn[standard]` and `python-multipart`, and does not pin
  **OCP**, **NumPy** or **PyJWT**, all of which are required at runtime. The pins
  themselves do not match the versions actually installed on the deployment box. See
  [docs/SETUP.md](docs/SETUP.md).
- **Single hard-coded user** (`admin`) stored in memory with an unsalted SHA-256 hash.
- **Single-solid focus.** The engine hollows only the *largest* solid; assemblies and
  multi-solid parts are not fully handled.
- **No non-STEP conversion.** Despite the accepted extensions, SolidWorks/STL/OBJ/IGES
  are parsed as STEP and will generally fail.
- **No persistence** of processed files or history; temp files are cleaned on exit and
  input files are unlinked right after processing.
- **State is in-process.** Rate-limit counters and JWT signing key live in memory, so
  they reset on restart and don't survive a multi-worker deployment.
- **Frontend slider caps at 20 mm** (`App.tsx` passes `max={20}`), even though the API
  accepts more (see `docs/API.md` for per-endpoint ranges).
- **No CI, no Docker, no git history** — the project has not been committed yet.

---

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
© 2026. All rights reserved.