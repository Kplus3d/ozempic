# Ozempic API Documentation

## Base URL
```
http://localhost:8001
```

## Authentication
Currently, no authentication is required for API access.

---

## Endpoints

### Health Check
```
GET /api/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "ozempic",
  "version": "1.1.0"
}
```

---

### Validate File
```
POST /api/validate
Content-Type: multipart/form-data
```

**Body:**
- `file` (required): CAD file to validate (STEP, SolidWorks, STL, OBJ, IGES)

**Response:**
```json
{
  "valid": true,
  "num_shapes": 1,
  "num_faces": 6,
  "num_edges": 24,
  "num_vertices": 48,
  "volume": 1000000.0,
  "surface_area": 60000.0,
  "bounding_box": {
    "min": [0.0, 0.0, 0.0],
    "max": [100.0, 100.0, 100.0]
  },
  "errors": []
}
```

---

### Process File
```
POST /api/process?thickness=2.0
Content-Type: multipart/form-data
```

**Query Parameters:**
- `thickness` (required): Wall thickness in millimeters (0.1 - 50.0mm)

**Body:**
- `file` (required): CAD file to process

**Response:**
- Returns the modified STEP file as a binary download
- Headers:
  - `X-Processing-Info: ok`
  - `X-Input-Volume: 1000000.0`
  - `X-Output-Volume: 884736.0`
  - `X-Volume-Change: -115264.0`

---

### Generate Preview
```
POST /api/preview
Content-Type: multipart/form-data
```

**Body:**
- `file` (required): CAD file to generate preview for

**Response:**
```json
{
  "success": true,
  "vertices": [[0.0, 0.0, 0.0], [0.0, 0.0, 100.0], ...],
  "indices": [0, 1, 2, 3, 4, 5, ...],
  "triangles": 12,
  "faces": 6,
  "volume": 1000000.0,
  "surface_area": 60000.0,
  "bounding_box": {
    "min": [-1e-07, -1e-07, -1e-07],
    "max": [100.0000001, 100.0000001, 100.0000001],
    "center": [50.0, 50.0, 50.0],
    "size": [100.00000019999999, 100.00000019999999, 100.00000019999999]
  }
}
```

---

### Batch Process Files
```
POST /api/batch-process?thickness=2.0
Content-Type: multipart/form-data
```

**Query Parameters:**
- `thickness` (required): Wall thickness in millimeters (0.1 - 50.0mm)

**Body:**
- `files` (required): Multiple CAD files to process

**Response:**
```json
{
  "results": [
    {
      "filename": "file1.step",
      "success": true,
      "message": "Processing complete",
      "input_volume": 1000000.0,
      "output_volume": 884736.0,
      "volume_change": -115264.0,
      "output_data": "49534f2d3130333033..."
    },
    {
      "filename": "file2.step",
      "success": false,
      "message": "Processing failed"
    }
  ]
}
```

**Note:** `output_data` is hex-encoded STEP file content.

---

### Get Supported Formats
```
GET /api/formats
```

**Response:**
```json
{
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
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Thickness must be between 0.1mm and 50.0mm"
}
```

### 413 Payload Too Large
```json
{
  "detail": "File size exceeds 50MB limit"
}
```

### 429 Too Many Requests
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds."
}
```

---

## Rate Limiting
- 30 requests per minute per IP address
- Sliding window algorithm

---

## File Size Limits
- Maximum file size: 50MB
- Supported formats: STEP, SolidWorks, STL, OBJ, IGES

---

## Notes
- All files are processed using OpenCASCADE 7.9
- SolidWorks files are converted to STEP format internally
- Output files are always in STEP format
- Mesh extraction uses `TShape.ActiveTriangulation()` for OCP 7.9 compatibility
- Volume and surface area calculations use `GProp_GProps`
