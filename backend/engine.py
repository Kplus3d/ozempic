"""
Ozempic STEP file processing engine.

Uses OCP (OpenCASCADE Python bindings) to load, validate, and modify STEP files
for wall thickness adjustment via the MakeThickSolid operation.
"""

import os
from dataclasses import dataclass, field


@dataclass
class StepGeometryInfo:
    """Validation result containing geometry information about a STEP file."""
    valid: bool = False
    num_shapes: int = 0
    num_faces: int = 0
    num_edges: int = 0
    num_vertices: int = 0
    volume: float = 0.0
    surface_area: float = 0.0
    bounding_box: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


def _compute_volume(shape) -> float:
    """Compute volume of a shape using OCP."""
    try:
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        return float(props.Mass())
    except Exception:
        return 0.0


def _count_faces(shape) -> int:
    """Count faces in a shape."""
    try:
        from OCP.TopAbs import TopAbs_ShapeEnum
        from OCP.TopExp import TopExp_Explorer
        count = 0
        explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
        while explorer.More():
            count += 1
            explorer.Next()
        return count
    except Exception:
        return 0


def validate_step_file(path: str) -> StepGeometryInfo:
    """
    Validate a STEP file and return geometry information.

    Args:
        path: Path to the STEP file.

    Returns:
        StepGeometryInfo with validation results.
    """
    info = StepGeometryInfo()

    try:
        if not os.path.isfile(path):
            info.errors.append(f"File not found: {path}")
            return info

        # Read file header to check for STEP signature
        with open(path, "rb") as f:
            content = f.read(256)
            header = content.decode("ascii", errors="ignore").strip().lower()
            if "step" not in header and "begin_file" not in header:
                info.errors.append("File does not appear to be a valid STEP file")
                return info

        # Import STEP using OCP
        from OCP.STEPControl import STEPControl_Reader
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.TopAbs import TopAbs_ShapeEnum
        from OCP.TopExp import TopExp_Explorer
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.IFSelect import IFSelect_RetDone

        reader = STEPControl_Reader()
        status = reader.ReadFile(path)

        if status != IFSelect_RetDone:
            info.errors.append("Failed to read STEP file")
            return info

        # Transfer all roots
        nbr_shapes = reader.NbRootsForTransfer()
        reader.TransferRoots()

        shapes = []
        for i in range(1, nbr_shapes + 1):
            shape = reader.Shape(i)
            if not shape.IsNull():
                shapes.append(shape)

        if not shapes:
            info.errors.append("STEP file contains no valid geometry")
            return info

        # Analyze shapes
        total_faces = 0
        total_edges = 0
        total_vertices = 0
        total_volume = 0.0
        total_area = 0.0

        for shape in shapes:
            # Validate shape
            analyzer = BRepCheck_Analyzer(shape)
            if not analyzer.IsValid():
                info.errors.append(f"Invalid shape detected at index {len(shapes)}")

            # Count faces, edges, vertices
            for topo_type in [
                TopAbs_ShapeEnum.TopAbs_FACE,
                TopAbs_ShapeEnum.TopAbs_EDGE,
                TopAbs_ShapeEnum.TopAbs_VERTEX,
            ]:
                explorer = TopExp_Explorer(shape, topo_type)
                while explorer.More():
                    if topo_type == TopAbs_ShapeEnum.TopAbs_FACE:
                        total_faces += 1
                    elif topo_type == TopAbs_ShapeEnum.TopAbs_EDGE:
                        total_edges += 1
                    else:
                        total_vertices += 1
                    explorer.Next()

            # Compute volume and area
            try:
                props = GProp_GProps()
                BRepGProp.VolumeProperties_s(shape, props)
                total_volume += float(props.Mass())
            except Exception:
                pass

            try:
                area_props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(shape, area_props)
                total_area += float(area_props.Mass())
            except Exception:
                pass

        # Compute bounding box
        bbox = Bnd_Box()
        for shape in shapes:
            BRepBndLib.Add_s(shape, bbox)

        if not bbox.IsVoid():
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            info.bounding_box = {
                "min": [round(float(xmin), 4), round(float(ymin), 4), round(float(zmin), 4)],
                "max": [round(float(xmax), 4), round(float(ymax), 4), round(float(zmax), 4)],
            }
        else:
            info.bounding_box = {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}

        info.valid = True
        info.num_shapes = nbr_shapes
        info.num_faces = total_faces
        info.num_edges = total_edges
        info.num_vertices = total_vertices
        info.volume = round(total_volume, 6)
        info.surface_area = round(total_area, 6)

    except Exception as e:
        info.errors.append(f"Error validating STEP file: {str(e)}")

    return info


def process_step_file(
    input_path: str,
    target_wall_thickness: float,
    output_path: str,
) -> dict:
    """
    Load a STEP file, hollow it out with the specified wall thickness, and export.

    Uses BRepOffsetAPI_MakeThickSolid with an EMPTY face list to hollow the
    entire solid uniformly (no openings/holes). This creates a shell with
    uniform wall thickness equal to the specified value.

    Args:
        input_path: Path to the input STEP file.
        target_wall_thickness: Desired wall thickness (mm).
        output_path: Path to write the modified STEP file.

    Returns:
        dict with processing results including input/output volumes, face counts,
        and any warnings/errors.
    """
    result = {
        "status": "success",
        "input_path": input_path,
        "output_path": output_path,
        "wall_thickness": target_wall_thickness,
        "input_volume": 0.0,
        "output_volume": 0.0,
        "volume_change": 0.0,
        "input_faces": 0,
        "output_faces": 0,
        "hollow_mode": True,
        "warnings": [],
        "errors": [],
    }

    try:
        from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_StepModelType
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
        from OCP.TopAbs import TopAbs_ShapeEnum
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopTools import TopTools_ListOfShape
        from OCP.IFSelect import IFSelect_RetDone

        # --- Input validation ---
        if not os.path.isfile(input_path):
            result["status"] = "error"
            result["errors"].append(f"Input file not found: {input_path}")
            return result

        if target_wall_thickness <= 0:
            result["status"] = "error"
            result["errors"].append("Wall thickness must be positive")
            return result

        if target_wall_thickness > 500:
            result["status"] = "error"
            result["errors"].append("Wall thickness too large (max 500mm)")
            return result

        # --- Read STEP ---
        reader = STEPControl_Reader()
        status = reader.ReadFile(input_path)

        if status != IFSelect_RetDone:
            result["status"] = "error"
            result["errors"].append("Failed to read STEP file")
            return result

        reader.TransferRoots()
        nbr_shapes = reader.NbRootsForTransfer()

        # Collect all shapes
        all_shapes = []
        for i in range(1, nbr_shapes + 1):
            shape = reader.Shape(i)
            if not shape.IsNull():
                all_shapes.append(shape)

        if not all_shapes:
            result["status"] = "error"
            result["errors"].append("No shapes found in STEP file")
            return result

        # --- Extract solids, then shells, then use as-is ---
        solids = []
        for shape in all_shapes:
            explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SOLID)
            while explorer.More():
                solids.append(explorer.Current())
                explorer.Next()

        if not solids:
            # Try shells
            shells = []
            for shape in all_shapes:
                explorer = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SHELL)
                while explorer.More():
                    shells.append(explorer.Current())
                    explorer.Next()
            if shells:
                solids = shells
            else:
                # Fallback: use the shapes directly
                solids = [s for s in all_shapes if not s.IsNull()]

        if not solids:
            result["status"] = "error"
            result["errors"].append("No solids or shells found in STEP file")
            return result

        # --- Select largest solid ---
        largest = solids[0]
        largest_vol = _compute_volume(largest)
        for s in solids[1:]:
            v = _compute_volume(s)
            if v > largest_vol:
                largest_vol = v
                largest = s

        result["input_volume"] = round(largest_vol, 6)
        result["input_faces"] = _count_faces(largest)

        # --- Hollow the solid ---
        # Pass EMPTY face list = hollow entire solid uniformly (no openings)
        face_list = TopTools_ListOfShape()

        thick_solid = BRepOffsetAPI_MakeThickSolid()
        thick_solid.MakeThickSolidByJoin(largest, face_list, -target_wall_thickness, 1e-4)
        thick_solid.Build()

        if not thick_solid.IsDone():
            result["status"] = "error"
            result["errors"].append("MakeThickSolid failed to produce a shape")
            return result

        # Check if we got a valid shape back (OCP bindings don't have HasShape())
        try:
            result_shape = thick_solid.Shape()
            if result_shape.IsNull():
                result["status"] = "error"
                result["errors"].append("MakeThickSolid produced no valid shape")
                return result
        except Exception:
            result["status"] = "error"
            result["errors"].append("MakeThickSolid produced no valid shape")
            return result


        # --- Verify the result is different ---
        output_vol = _compute_volume(result_shape)
        result["output_volume"] = round(output_vol, 6)
        result["volume_change"] = round(output_vol - largest_vol, 6)
        result["output_faces"] = _count_faces(result_shape)

        if abs(output_vol - largest_vol) < 1e-6:
            result["status"] = "error"
            result["errors"].append(
                f"Volume unchanged ({output_vol:.2f} mm³). "
                "The input may not be a valid watertight solid, or the wall thickness "
                "is too large for the part geometry."
            )
            return result

        # --- Write output STEP ---
        writer = STEPControl_Writer()
        writer.Transfer(result_shape, STEPControl_StepModelType.STEPControl_AsIs)

        result_status = writer.Write(output_path)

        if not os.path.isfile(output_path):
            result["status"] = "error"
            result["errors"].append("Output file was not created")
            return result

        if result["output_faces"] < 4:
            result["warnings"].append("Output has very few faces — the part may have collapsed")

        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(f"Error processing STEP file: {str(e)}")

    return result
