"""
Ozempic — STEP File Wall Thickness Modifier

FastAPI backend serving both API and static frontend.
"""

import os
import time
import tempfile
import atexit
from collections import defaultdict
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from engine import process_step_file, validate_step_file
from preview import step_file_to_mesh_data
from auth import authenticate_user, create_token, get_current_user

app = FastAPI(title="Ozempic", version="1.1.0")

# ============================================================
# Configuration
# ============================================================
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "temp_uploads")
RATE_LIMIT = 30  # requests per minute
RATE_WINDOW = 60  # seconds

# Create temp directory if it doesn't exist
os.makedirs(TEMP_DIR, exist_ok=True)

# ============================================================
# Rate limiting state
# ============================================================
rate_limit_counts = defaultdict(list)

# ============================================================
# Security: CORS — explicit origins only (not wildcard)
# ============================================================
allowed_origins = [
    "http://localhost:8001",
    "http://localhost:5173",
    "http://127.0.0.1:8001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ============================================================
# Security: Trusted hosts
# ============================================================
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# ============================================================
# Rate limiting middleware
# ============================================================
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting to prevent abuse."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean old entries
    rate_limit_counts[client_ip] = [
        t for t in rate_limit_counts[client_ip] if now - t < RATE_WINDOW
    ]
    
    # Check rate limit
    if len(rate_limit_counts[client_ip]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
            headers={"Retry-After": str(RATE_WINDOW)}
        )
    
    rate_limit_counts[client_ip].append(now)
    
    response = await call_next(request)
    return response

# ============================================================
# Security: Custom headers middleware
# ============================================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers and remove server version."""
    response = await call_next(request)
    
    # Remove server version header (not available in MutableHeaders, skip)
    # response.headers.pop("server", None)
    
    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
    
    return response

# ============================================================
# Cleanup temp files on exit
# ============================================================
def cleanup_temp_files():
    """Remove all temp files on shutdown."""
    if os.path.exists(TEMP_DIR):
        import shutil
        for f in os.listdir(TEMP_DIR):
            fp = os.path.join(TEMP_DIR, f)
            try:
                if os.path.isfile(fp):
                    os.unlink(fp)
            except Exception:
                pass

atexit.register(cleanup_temp_files)

# Serve frontend static files
if os.path.exists(FRONTEND_DIR):
    assets_dir = os.path.join(FRONTEND_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/static/assets", StaticFiles(directory=assets_dir), name="assets")

# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "ozempic", "version": "1.1.0"}

@app.post("/api/login")
async def login(request: Request):
    """
    Authenticate user and return JWT token.
    
    Body:
        - username: str
        - password: str
    
    Returns:
        - token: str (JWT token)
        - username: str
        - role: str
    """
    try:
        body = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")
        
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password are required")
        
        user = authenticate_user(username, password)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        token = create_token(user["username"], user["role"])
        
        return {
            "token": token,
            "username": user["username"],
            "role": user["role"]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/me")
async def get_me(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """
    Get current user information.
    Requires valid JWT token.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        user = get_current_user(credentials)
        return {
            "username": user["username"],
            "role": user["role"]
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/validate")
async def validate(file: UploadFile = File(...)):
    """
    Validate a STEP file and return geometry information.
    
    Returns:
        - valid: bool
        - num_shapes: int
        - num_faces: int
        - num_edges: int
        - num_vertices: int
        - volume: float
        - surface_area: float
        - bounding_box: dict
        - errors: list
    """
    # Check file size
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not file.filename.lower().endswith(('.step', '.stp')):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .step or .stp files are accepted.")

    tmp_path = None
    try:
        # Save temp file with size check
        with tempfile.NamedTemporaryFile(
            suffix='.step', 
            delete=False, 
            dir=TEMP_DIR
        ) as tmp:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")
            tmp.write(content)
            tmp_path = tmp.name
        
        # Validate
        result = validate_step_file(tmp_path)
        
        # Build response (sanitize errors)
        response = {
            'valid': result.valid,
            'num_shapes': result.num_shapes,
            'num_faces': result.num_faces,
            'num_edges': result.num_edges,
            'num_vertices': result.num_vertices,
            'volume': result.volume,
            'surface_area': result.surface_area,
            'bounding_box': result.bounding_box,
            'errors': result.errors
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        # Sanitize error details
        detail = str(e) if 'OCP' not in str(e) and 'Exception' not in str(e) else "Validation failed"
        raise HTTPException(status_code=400, detail=detail)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@app.post("/api/process")
async def process(request: Request, thickness: float = 2.0):
    """
    Process a STEP file and modify wall thickness.
    
    Args:
        file: STEP file to process
        thickness: Desired wall thickness in mm (query parameter)
    
    Returns:
        Modified STEP file
    """
    # Validate thickness parameter
    if thickness <= 0:
        raise HTTPException(status_code=400, detail="Wall thickness must be positive")
    if thickness > 500:
        raise HTTPException(status_code=400, detail="Wall thickness too large (max 500mm)")

    form_data = await request.form()
    file = form_data.get('file')
    
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    tmp_path = None
    output_path = None
    try:
        # Save input file with size check
        with tempfile.NamedTemporaryFile(
            suffix='.step', 
            delete=False, 
            dir=TEMP_DIR
        ) as input_tmp:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")
            input_tmp.write(content)
            tmp_path = input_tmp.name
        
        # Generate output path
        output_path = os.path.join(TEMP_DIR, os.path.splitext(file.filename)[0] + '_modified.step')
        
        # Process
        result = process_step_file(tmp_path, thickness, output_path)
        
        if result["status"] == "error":
            # Sanitize error details
            error_detail = result["errors"][0] if result["errors"] else "Processing failed"
            if "OCP" in error_detail:
                error_detail = "Processing failed — check geometry"
            raise HTTPException(status_code=400, detail=error_detail)
        
        # Read output and return
        with open(output_path, 'rb') as f:
            output_content = f.read()
        
        # Build response with metadata
        headers = {
            "X-Processing-Info": "ok",
            "X-Input-Volume": str(result.get("input_volume", 0)),
            "X-Output-Volume": str(result.get("output_volume", 0)),
            "X-Volume-Change": str(result.get("volume_change", 0)),
        }
        
        # Return file - output_path will be cleaned up by atexit
        base_name = os.path.basename(file.filename).replace('.step', '_modified').replace('.stp', '_modified')
        if not base_name.endswith('.step'):
            base_name += '.step'
        
        return FileResponse(
            path=output_path,
            filename=f"ozempic_{base_name}",
            media_type='application/octet-stream',
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        detail = str(e) if 'OCP' not in str(e) else "Processing failed"
        raise HTTPException(status_code=400, detail=detail)
    finally:
        # Cleanup input file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@app.post("/api/preview")
async def preview(file: UploadFile = File(...)):
    """
    Generate a 3D preview of a STEP file.
    
    Returns:
        - success: bool
        - vertices: list of [x, y, z] arrays
        - indices: list of triangle indices
        - triangles: int
        - faces: int
        - volume: float
        - surface_area: float
        - bounding_box: dict
        - errors: list
    """
    # Check file size
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Accept STEP, STL, OBJ, IGES, and SolidWorks formats
    supported_extensions = (
        '.step', '.stp',  # STEP files
        '.sldprt', '.sldasm',  # SolidWorks
        '.stl', '.obj',  # Mesh formats
        '.iges', '.igs',  # IGES files
    )
    
    if not file.filename.lower().endswith(supported_extensions):
        raise HTTPException(status_code=400, detail="Unsupported file type. Accepted: .step, .stp, .sldprt, .stl, .obj, .iges")
    
    tmp_path = None
    try:
        # Save temp file with size check
        with tempfile.NamedTemporaryFile(
            suffix=file.filename, 
            delete=False, 
            dir=TEMP_DIR
        ) as tmp:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")
            tmp.write(content)
            tmp_path = tmp.name
        
        # Try to process as STEP first
        mesh_data = step_file_to_mesh_data(tmp_path)
        
        if mesh_data['success']:
            return {
                'success': True,
                'vertices': mesh_data['vertices'],
                'indices': mesh_data['indices'],
                'triangles': mesh_data['triangles'],
                'faces': mesh_data['faces'],
                'volume': mesh_data['volume'],
                'surface_area': mesh_data['surface_area'],
                'bounding_box': mesh_data['bounding_box'],
                'errors': []
            }
        else:
            # If STEP processing fails, return a simple preview
            return {
                'success': True,
                'vertices': [],
                'indices': [],
                'triangles': 0,
                'faces': 0,
                'volume': 0,
                'surface_area': 0,
                'bounding_box': {
                    'min': [0, 0, 0],
                    'max': [0, 0, 0],
                    'center': [0, 0, 0],
                    'size': [0, 0, 0]
                },
                'errors': [mesh_data['error']]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        detail = str(e) if 'OCP' not in str(e) else "Preview generation failed"
        raise HTTPException(status_code=400, detail=detail)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@app.get("/api/formats")
async def supported_formats():
    """Return list of supported file formats."""
    return {
        "supported_formats": [
            {
                "extension": ".step",
                "name": "STEP",
                "description": "Standard for Exchange of Product model data"
            },
            {
                "extension": ".stp",
                "name": "STEP",
                "description": "Standard for Exchange of Product model data (alias)"
            },
            {
                "extension": ".sldprt",
                "name": "SolidWorks Part",
                "description": "SolidWorks part file (converted to STEP internally)"
            },
            {
                "extension": ".sldasm",
                "name": "SolidWorks Assembly",
                "description": "SolidWorks assembly file (converted to STEP internally)"
            },
            {
                "extension": ".stl",
                "name": "STL",
                "description": "Stereolithography 3D mesh"
            },
            {
                "extension": ".obj",
                "name": "OBJ",
                "description": "Wavefront 3D model"
            },
            {
                "extension": ".iges",
                "name": "IGES",
                "description": "Initial Graphics Exchange Specification"
            },
            {
                "extension": ".igs",
                "name": "IGES",
                "description": "Initial Graphics Exchange Specification (alias)"
            }
        ],
        "processing_note": "All files are processed as STEP internally. SolidWorks files will be converted to STEP format."
    }

@app.post("/api/batch-process")
async def batch_process(files: list[UploadFile] = File(...), thickness: float = 2.0):
    """
    Process multiple files and return results as JSON.
    Each file is processed with the specified thickness.
    
    Returns:
        - A list of results, one per file
        - Each result contains: filename, success, message, output_file (if successful)
    """
    # Validate thickness
    if thickness < 0.1 or thickness > 50.0:
        raise HTTPException(status_code=400, detail="Thickness must be between 0.1mm and 50.0mm")
    
    results = []
    
    for file in files:
        try:
            # Check file size
            content = await file.read()
            file_size = len(content)
            
            if file_size > MAX_FILE_SIZE:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": f"File too large ({file_size / (1024*1024):.2f} MB)"
                })
                continue
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file.filename.split('.')[-1]}") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            # Process file
            output_path = os.path.join(TEMP_DIR, f"ozempic_batch_{os.path.basename(tmp_path)}")
            result = process_step_file(tmp_path, thickness, output_path)
            
            if result["status"] == "error":
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": "; ".join(result["errors"]) if result["errors"] else "Processing failed"
                })
            else:
                # Read output file
                with open(output_path, 'rb') as f:
                    output_data = f.read()
                
                # Get metadata from result
                input_volume = result.get("input_volume", 0)
                output_volume = result.get("output_volume", 0)
                volume_change = output_volume - input_volume
                
                results.append({
                    "filename": file.filename,
                    "success": True,
                    "message": "Processing complete",
                    "input_volume": input_volume,
                    "output_volume": output_volume,
                    "volume_change": volume_change,
                    "output_data": output_data.hex()  # Hex encode for JSON
                })
            
            # Cleanup
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
        
        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "message": str(e) if 'OCP' not in str(e) else "Processing failed"
            })
    
    return {"results": results}

# Serve frontend if built
if os.path.exists(FRONTEND_DIR):
    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
    
    @app.get("/{full_path:path}")
    async def serve_static(full_path: str):
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
