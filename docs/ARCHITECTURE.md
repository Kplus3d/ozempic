# Ozempic — Architecture

Module-by-module design of the Ozempic STEP wall-thickness modifier. Every statement
here was read from the source in `backend/` and `frontend/src/`.

- **Runtime**: Python 3.10 (system `/usr/bin/python` on the Jetson), FastAPI, OpenCASCADE via the `OCP` bindings.
- **Port**: 8001.
- **Process model**: a single uvicorn worker running `main:app`, optionally wrapped by
  `supervisor.sh` and launched through `server.py` (memory-capped).

---

## 1. High-level data flow

```
                       ┌────────────────────────────────────────────┐
   Browser             │  FastAPI app  (backend/main.py)            │
   (React SPA)         │                                            │
      │                │  middleware: rate limit → security headers  │
      │  upload file   │                                            │
      ├── POST /api/validate ──► engine.validate_step_file()         │
      │                          (STEPControl_Reader + BRepCheck)   │
      │                │                                            │
      ├── POST /api/preview ───► preview.step_file_to_mesh_data()    │
      │                          (BRepMesh_IncrementalMesh)         │
      │                │                                            │
      ├── POST /api/process ───► engine.process_step_file()          │
      │   ?thickness=N           (BRepOffsetAPI_MakeThickSolid)     │
      │                │                │                           │
      │◄── STEP file (FileResponse + X-*-Volume headers) ──────────┤
      │                │                                            │
      └── GET /  ──────►  StaticFiles(../frontend/dist)             │
                       └────────────────────────────────────────────┘
                                        │
                         writes temp files to <repo>/temp_uploads/
```

The frontend calls **validate + preview automatically** on file selection, then
**process** only when the user clicks *Modify Thickness*. Results are shown from the
response headers plus the mesh data, and the modified file is downloaded as a blob.

---

## 2. `backend/main.py` — FastAPI application

**Purpose**: defines the app, its middleware, all HTTP routes, and static serving of
the built frontend.

### App & configuration

```python
app = FastAPI(title="Ozempic", version="1.1.0")
MAX_FILE_SIZE = 50 * 1024 * 1024      # 50 MB
FRONTEND_DIR  = <repo>/frontend/dist
TEMP_DIR      = <repo>/temp_uploads   # created at import via os.makedirs(..., exist_ok=True)
RATE_LIMIT    = 30                    # requests per window
RATE_WINDOW   = 60                    # seconds
```

### Middleware (in the order registered)

1. **CORS** (`CORSMiddleware`) — explicit origins only:
   `http://localhost:8001`, `http://localhost:5173`, `http://127.0.0.1:8001`.
   Methods `GET, POST, OPTIONS`.
2. **TrustedHostMiddleware** — `allowed_hosts=["*"]`.
3. **`rate_limit_middleware`** (`@app.middleware("http")`) — a sliding-window limiter
   keyed on `request.client.host`. Counters live in the module-level
   `rate_limit_counts = defaultdict(list)`. When an IP reaches 30 requests in 60 s it
   returns **429** with `Retry-After: 60`. Counts **every** request, including
   `/api/health`.
4. **`add_security_headers`** (`@app.middleware("http")`) — sets
   `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
   `X-XSS-Protection: 1; mode=block`,
   `Cache-Control: no-store, no-cache, must-revalidate`, `Pragma: no-cache`,
   `Referrer-Policy: strict-origin-when-cross-origin`, and
   `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'`
   (the `unsafe-inline` is required because the React UI uses inline styles).

### Temp-file lifecycle

Files are written to `temp_uploads/` with `tempfile.NamedTemporaryFile(delete=False, dir=TEMP_DIR)`.
`cleanup_temp_files()` is registered with `atexit` and empties the directory on
shutdown. Input files are additionally `os.unlink`ed in the route's `finally` block.
`/api/process` leaves the *output* file on disk for `FileResponse` to stream and relies
on the `atexit` sweep.

### Routes

| Method | Path | Handler | Request | Response |
|---|---|---|---|---|
| GET | `/api/health` | `health` | — | `{"status","service","version"}` |
| POST | `/api/login` | `login` | JSON `{username,password}` | `{token,username,role}` |
| GET | `/api/me` | `get_me` | `Authorization: Bearer` | `{username,role}` |
| POST | `/api/validate` | `validate` | multipart `file` | geometry summary JSON |
| POST | `/api/process` | `process` | multipart `file`, query `thickness` | STEP file download |
| POST | `/api/preview` | `preview` | multipart `file` | mesh JSON |
| GET | `/api/formats` | `supported_formats` | — | static format list |
| POST | `/api/batch-process` | `batch_process` | multipart `files[]`, query `thickness` | JSON results |
| GET | `/` | `serve_frontend` | — | `frontend/dist/index.html` |
| GET | `/{full_path:path}` | `serve_static` | — | static asset or SPA fallback |

`/`, `/{full_path:path}` and the `/static/assets` mount are registered **only if
`FRONTEND_DIR` exists** — i.e. only after `npm run build`. `GET /{full_path:path}`
serves a real file if it exists, otherwise falls back to `index.html` (SPA routing).

Notes on individual handlers:

- **`process`** reads the upload via `await request.form()` (not a `UploadFile`
  parameter) and takes `thickness` as a **query parameter** defaulting to `2.0`. It
  validates `0 < thickness <= 500` (different from batch-process). It writes the output
  as `<name>_modified.step` inside `TEMP_DIR` and returns it with
  `FileResponse(..., media_type='application/octet-stream')`, filename
  `ozempic_<name>_modified.step`, and the `X-Processing-Info`, `X-Input-Volume`,
  `X-Output-Volume`, `X-Volume-Change` headers.
- **`validate`** only accepts `.step`/`.stp` (case-insensitive via
  `filename.lower().endswith(('.step', '.stp'))`); anything else is a 400.
- **`preview`** accepts `.step .stp .sldprt .sldasm .stl .obj .iges .igs` by
  extension, but always calls the STEP path. On failure it still returns
  `success: true` with an empty mesh and an `errors` list.
- **`batch_process`** takes `files: list[UploadFile]` and `thickness` (query, default
  `2.0`, must be `0.1..50.0`). Each successful result includes the output file
  **hex-encoded** in `output_data`; both the temp input and output are unlinked
  afterwards. A per-file exception is caught and reported as `success: false`.
- Error messages are "sanitised": if the exception text contains `OCP` (or the code
  can't classify it) the client gets a generic message instead of the raw traceback.

### `__main__`

```python
uvicorn.run(app, host="0.0.0.0", port=8001)
```

---

## 3. `backend/engine.py` — the STEP / thickness engine

Two public functions plus two private helpers. All OpenCASCADE APIs are imported lazily
inside functions, so the module imports cleanly without OCP present.

### `StepGeometryInfo` (dataclass)

Fields: `valid, num_shapes, num_faces, num_edges, num_vertices, volume, surface_area,
bounding_box, errors`.

### `validate_step_file(path) -> StepGeometryInfo`

1. Checks the file exists.
2. Reads the first 256 bytes and requires `"step"` or `"begin_file"` in the lowercased
   ASCII header — a cheap signature check before invoking OpenCASCADE.
3. `STEPControl_Reader().ReadFile(path)`; requires `IFSelect_RetDone`.
4. `reader.TransferRoots()`, then iterates `reader.Shape(i)` for
   `i in 1..NbRootsForTransfer()`, collecting non-null shapes.
5. For each shape: `BRepCheck_Analyzer(shape).IsValid()` (appends an error if invalid);
   `TopExp_Explorer` counts faces, edges and vertices.
6. Volume via `BRepGProp.VolumeProperties_s(shape, GProp_GProps())` → `Mass()`;
   surface area via `BRepGProp.SurfaceProperties_s(...)` → `Mass()`.
7. Bounding box via `Bnd_Box()` + `BRepBndLib.Add_s(shape, bbox)`, read with
   `bbox.Get()` → `(xmin, ymin, zmin, xmax, ymax, zmax)`, rounded to 4 dp. The result
   contains only `min`/`max` (no `center`/`size`).
8. Wraps everything in try/except; failures land in `info.errors` and `valid` stays
   `False`.

### `process_step_file(input_path, target_wall_thickness, output_path) -> dict`

The core operation. Steps:

1. **Validate**: file exists, `thickness > 0`, `thickness <= 500`.
2. **Read** with `STEPControl_Reader`, `TransferRoots()`, collect all non-null shapes.
3. **Find solids**: `TopExp_Explorer(shape, TopAbs_SOLID)`. If none, fall back to
   shells (`TopAbs_SHELL`), and if still none, use the raw shapes.
4. **Pick the largest solid** by comparing `_compute_volume()` across candidates.
   Records `input_volume` and `input_faces` for the chosen solid.
5. **Hollow it**:
   ```python
   face_list = TopTools_ListOfShape()          # EMPTY → uniform shell, no openings
   thick_solid = BRepOffsetAPI_MakeThickSolid()
   thick_solid.MakeThickSolidByJoin(largest, face_list, -target_wall_thickness, 1e-4)
   thick_solid.Build()
   ```
   The negative offset means material is removed inward; the empty opening list means
   there is no hole in the shell. `IsDone()` must be true and `Shape()` must return a
   non-null shape.
6. **Verify change**: computes `output_volume` and `output_faces`; if
   `abs(output_volume - largest_vol) < 1e-6` it errors with the "Volume unchanged…"
   message (catches non-watertight solids and too-thick walls).
7. **Write** with `STEPControl_Writer().Transfer(shape, STEPControl_AsIs)` and
   `Write(output_path)`; verifies the output file exists.
8. Appends a warning if `output_faces < 4` ("the part may have collapsed").
9. Returns the result dict: `status`, paths, `wall_thickness`, `input_volume`,
   `output_volume`, `volume_change`, `input_faces`, `output_faces`, `hollow_mode`,
   `warnings`, `errors`.

### Helpers

- `_compute_volume(shape)` → `GProp_GProps` + `BRepGProp.VolumeProperties_s`; returns
  `0.0` on failure.
- `_count_faces(shape)` → `TopExp_Explorer` over `TopAbs_FACE`.

---

## 4. `backend/preview.py` — STEP → mesh

Single function `step_file_to_mesh_data(step_file_path, max_triangles=5000) -> dict`.

1. `STEPControl_Reader()` → `ReadFile` (must be `IFSelect_RetDone`) → `TransferRoots()`
   → `reader.OneShape()`.
2. Computes volume and surface area **before meshing** (noted in the source as "more
   reliable"): `BRepGProp.VolumeProperties_s` / `SurfaceProperties_s`.
3. `BRepMesh_IncrementalMesh(shape, 0.001, False, 0.5, False)` then `Perform()`; must be
   `IsDone()`.
4. Walks faces with `TopExp_Explorer(shape, TopAbs_FACE)`. For each face it takes
   `face_shape.TShape()` and calls **`tshape.ActiveTriangulation()`** — the OCP 7.9-safe
   path (no `topods`/"TopoDS_Face cast", see §7).
5. Per triangulation: appends `InternalNodes`-style `triangulation.Node(i)` (1-based)
   as `[x, y, z]`, and for each `triangulation.Triangle(i)` reads
   `tri.Value(1..3)`, offsetting indices by the base vertex index (`v - 1`).
6. Truncates to `max_triangles` (default 5000) **by faces** after collection.
7. Builds a flat `indices` list and the bounding box with `Bnd_Box` + `BRepBndLib.Add_s`,
   returning `min`, `max`, `center`, `size`.
8. Returns `{success, vertices, indices, triangles, faces, volume, surface_area,
   bounding_box}`. Note `triangles == faces == len(faces)` (both count triangles). On
   any exception it returns `success: False` plus an `error` string and an empty mesh.

`/api/preview` maps this to the HTTP response and always sets `success: true` for the
client, moving the internal error into `errors: [mesh_data['error']]`.

---

## 5. `backend/auth.py` — authentication

- `SECRET_KEY = secrets.token_hex(32)` — generated **at import time**, so every process
  restart invalidates all previously issued tokens.
- `ALGORITHM = "HS256"`, `TOKEN_EXPIRE_MINUTES = 60 * 24 * 7` (7 days).
- `ADMIN_PASSWORD = os.environ.get("OZEMPIC_ADMIN_PASSWORD", "")` — read at import.
- `USERS_DB`: one in-memory user, `admin`, with `hashlib.sha256(ADMIN_PASSWORD)`
  (unsalted) and role `admin`. If the environment variable is unset the hash is of the
  empty string, so no password authenticates — the service fails closed rather than
  shipping a default credential.
- `create_token(username, role="user")` — payload `{sub, role, exp, iat}`, encoded with
  `jwt.encode` (PyJWT).
- `verify_token(token)` — `jwt.decode`; maps `ExpiredSignatureError` →
  401 "Token has expired" and `InvalidTokenError` → 401 "Invalid token".
- `get_current_user(credentials=Depends(security))` — `security = HTTPBearer()`; checks
  `sub` is in `USERS_DB`; returns `{username, role}`.
- `authenticate_user(username, password)` — constant-time-ish compare of the SHA-256
  digest; returns `None` on failure.
- `require_admin(...)` — 403 "Admin access required" unless role is `admin`.
  **Defined but never imported by any route.**

**Important**: no route in `main.py` depends on `get_current_user` or `require_admin`.
Auth is present but not enforced on any data endpoint. `main.py` only *imports*
`authenticate_user`, `create_token`, `get_current_user` for the login/me endpoints.

---

## 6. `backend/server.py` — production entrypoint & memory limits

`#!/usr/bin/env python3`. Imports `app` from `main` and starts uvicorn; before that it
applies several host-protection measures (all wrapped in `try/except` so the server
still starts if a step is denied):

1. `os.nice(10)` — lowers CPU scheduling priority.
2. Writes `-999` to `/proc/<pid>/oom_score_adj` — makes the kernel much less likely to
   OOM-kill this process.
3. **`resource.setrlimit(resource.RLIMIT_AS, (limit, limit))` with `limit = 2.5 GiB`**
   (`int(2.5 * 1024 * 1024 * 1024)`). This is the hard address-space cap.
4. Starts a **daemon `memory_watchdog` thread** that, every 30 s, reads `VmRSS` from
   `/proc/<pid>/status` and calls `os._exit(137)` if RSS exceeds **90 % of the limit**.
   This is a deliberate self-kill so the supervisor can restart a clean process before
   the box thrashes.
5. Prints the PID and `RLIMIT_NOFILE`, installs SIGINT/SIGTERM handlers that
   `sys.exit(0)`, then `uvicorn.run(app, host="0.0.0.0", port=8001)`.

(The task brief said "~1.5 GB"; the code actually sets **2.5 GB** here. 1.5 GB appears
only in `healthcheck.sh`.)

---

## 7. Shell scripts

### `backend/supervisor.sh`

Bash, run from the crontab `@reboot` line. Sequence:

1. Constants: `MAX_MEM_KB=2621440` (2.5 GB), `LOG=/tmp/ozempic.log`,
   `PID_DIR=~/.ozempic`, `LOCK_FILE=$PID_DIR/supervisor.lock`, `PORT=8001`.
2. **Single-instance lock**: if `supervisor.lock` names a live PID, exit 0; else write
   `$$`.
3. **Main loop** (`while true`):
   - If `curl -s --connect-timeout 2 http://127.0.0.1:8001/api/health` succeeds *and*
     `$PID_DIR/server.pid` is alive, `sleep 5` and loop (monitor, don't spawn).
   - Otherwise launch the server detached:
     ```bash
     (
       ulimit -v $MAX_MEM_KB 2>/dev/null || true
       echo -999 > /proc/self/oom_score_adj 2>/dev/null || true
       exec /usr/bin/python ~/ozempic/backend/server.py >> "$LOG" 2>&1
     ) &>/dev/null &
     ```
     record `$!` in `$PID_DIR/server.pid`, `disown`.
   - `wait $SERVER_PID`, log the exit code, increment `RESTARTS`, `sleep 3`, loop.

Paths are hard-coded to `~/ozempic`; move the deploy and you must edit the
script.

### `backend/healthcheck.sh`

One-shot liveness check, **not** referenced by the crontab. If
`curl http://127.0.0.1:8001/api/health` fails it `pkill -f "server.py"`, sleeps 2 s,
and relaunches the server with `ulimit -v 1572864` (1.5 GB) and `oom_score_adj=-999`,
logging to `/tmp/ozempic-healthcheck.log`. It does not use the lock file, so running it
alongside the supervisor can race.

---

## 8. `frontend/` — Vite + React + TypeScript

- **Stack** (`package.json`): `react`/`react-dom` `^19.0.0`, `three` `^0.170.0`,
  `@react-three/fiber` `^9.0.0`, `@react-three/drei` `^10.0.0`; dev tooling
  `vite ^5.1.0`, `typescript ^5.3.0`, `@vitejs/plugin-react ^4.3.0`.
  (`fiber`/`drei` are declared but the viewer uses the raw `three` API.)
- **Scripts**: `dev` = `vite`, `build` = `tsc && vite build`, `preview` = `vite preview`.
- **`vite.config.ts`**: proxies `/api` → `http://localhost:8001` for dev.
- **`index.html`**: dark base styles, mounts `#root`, loads `/src/main.tsx`.
- **`main.tsx`**: `ReactDOM.createRoot(...).render(<React.StrictMode><App/></React.StrictMode>)`.
- **`App.tsx`**: the whole flow. Holds `file`, `fileInfo`, `meshData`, `thickness`
  (default 2.0), `processing`, `progress`, `error`, `success`, `previewLoading`,
  `previewError`, `processingInfo`.
  - `handleFileSelected`: POSTs `/api/validate` then `/api/preview` (both with the
    same `FormData`), populating the info panel and the 3D view.
  - `handleProcess`: uses **`XMLHttpRequest`** (for upload progress) to
    `POST /api/process?thickness=<value>`, downloads the blob as
    `<base>_ozempic_modified.step`, and reads the `X-Input-Volume` /
    `X-Output-Volume` / `X-Volume-Change` headers for the results panel.
  - `handleReset` clears all state. Renders two columns (controls | preview) and a footer.
- **`components/StepUploader.tsx`**: exports `MAX_FILE_SIZE` (50 MB), `supportedFormats`,
  `isValidFormat`, `formatLabel`, `supportedFormatsList`, `formatFileSize`, `isValidSize`,
  and the drag-and-drop `StepUploader`. Validates extension and size client-side before
  calling up. File input `accept=".step,.stp,.sldprt,.sldasm,.stl,.obj,.iges,.igs"`.
- **`components/ThicknessControl.tsx`**: a range slider (defaults `min 0.1`, `max 50`,
  `step 0.1`); `App.tsx` renders it with `min={0.1} max={20} step={0.1}`.
- **`components/Viewer3D.tsx`**: raw `three`. Builds a `THREE.BufferGeometry` from the
  API `vertices`/`indices`, `computeVertexNormals()`, `MeshPhongMaterial` (double-sided,
  0.9 opacity), ambient + two directional lights, a `GridHelper`, custom mouse
  drag-to-rotate (`quaternion` multiplication) and wheel zoom, a resize handler, and a
  `requestAnimationFrame` render loop. Camera is refit to `150/maxDim` scale from the
  bounding box. Cleanup disposes the renderer and removes the resize listener.

---

## 9. Tests

- **`tests/test_core.py`** — pytest; inserts `../backend` onto `sys.path` and imports
  `engine`, `preview`, `auth`. Classes: `TestValidation` (valid + invalid file),
  `TestThicknessProcessing` (default 2.0 mm, a sweep 0.1–20 mm asserting monotonic
  volume decrease, and an extreme 20 mm case), `TestPreviewGeneration` (12 triangles,
  volume, bounds), `TestAuthentication` (token create/verify/authenticate/expiry).
  Skips if `tests/test_step.step` is missing. Verified: **11 passed**.
- **`tests/test_step.step`** — a 100×100×100 mm box produced by OpenCASCADE 7.9
  (header `STEP; FILE_SCHEMA AUTOMOTIVE_DESIGN`), volume 1,000,000 mm³, area 60,000 mm².
- **`backend/test_engine.py`** — a standalone script that writes its own
  `test_box.solid.step` (100×100×50) via `BRepPrimAPI_MakeBox` and runs validate + a
  thickness sweep. Not collected by pytest.

---

## 10. OCP / OpenCASCADE 7.9 specifics (verified in this repo)

The installed bindings are **`cadquery-ocp` 7.9.3.0**. The code encodes three
compatibility facts, all corroborated by the source and the audit notes:

1. **Face triangulation**: use `face_shape.TShape().ActiveTriangulation()` rather than a
   `TopoDS_Face` cast. `preview.py`'s header comment says *"Uses OCP 7.9 compatible API
   (no topods casting needed)"*; the `topods` module is gone in 7.9.
2. **`BRepBndLib` lives in the top-level `OCP` namespace** — `from OCP.BRepBndLib import BRepBndLib`
   in `engine.py` and `preview.py` (not `OCP.Bnd`/`OCP.BRepBndLib` sub-namespaces from older layouts).
3. **`_s` static-method suffixes** are required for the property calculators:
   `BRepGProp.VolumeProperties_s(shape, props)` and
   `BRepGProp.SurfaceProperties_s(shape, props)` — the un-suffixed overloads are not
   exposed the same way and historically returned 0.0 here.

Plus standard 7.9 usage: `IFSelect_RetDone` as the reader status sentinel,
`STEPControl_StepModelType.STEPControl_AsIs` on write, `TopTools_ListOfShape()` for the
(empty) opening-face list, and the absence of `HasShape()` on
`BRepOffsetAPI_MakeThickSolid` (the code compensates with a try/except around `Shape()`).

---

## 11. Known architectural limitations

- Single uvicorn worker, in-process state (rate-limit counters, JWT key). No shared
  cache/db → cannot scale horizontally and loses tokens/counters on restart.
- Auth module present but not wired into the data routes.
- `requirements.txt` under-specifies runtime deps (missing OCP, NumPy, PyJWT).
- The engine deliberately handles only the largest solid; assemblies/batch-face
  thickness are out of scope.
- The frontend viewer renders only the *input* mesh; there is no preview of the
  modified (hollowed) result.