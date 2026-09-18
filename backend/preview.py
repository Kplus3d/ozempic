"""
Ozempic — 3D Geometry Preview Module
Generates simplified 3D mesh data from STEP files for frontend visualization.
Uses OCP 7.9 compatible API (no topods casting needed).
"""

from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_StepModelType
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.BRepMesh import BRepMesh_IncrementalMesh


def step_file_to_mesh_data(step_file_path, max_triangles=5000):
    """
    Convert a STEP file to simplified mesh data for 3D preview.
    
    Returns:
        dict with mesh data (vertices, indices) and metadata
    """
    try:
        # Read the STEP file
        reader = STEPControl_Reader()
        status = reader.ReadFile(step_file_path)
        
        if status != IFSelect_RetDone:
            raise Exception("Failed to read STEP file")
        
        # Transfer roots first!
        reader.TransferRoots()
        
        # Get the shape
        shape = reader.OneShape()
        
        if not shape or shape.ShapeType() == 0:
            raise Exception("No shapes found in STEP file")
        
        # Calculate properties BEFORE meshing (more reliable)
        volume_props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, volume_props)
        
        surface_props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(shape, surface_props)
        
        volume = volume_props.Mass()
        surface_area = surface_props.Mass()
        
        # Mesh the shape
        tol = 0.001
        mesh = BRepMesh_IncrementalMesh(shape, tol, False, 0.5, False)
        mesh.Perform()
        
        if not mesh.IsDone():
            raise Exception("Failed to mesh shape")
        
        # Extract vertices and faces using TShape.ActiveTriangulation()
        # This works with OCP 7.9 without needing topods casting
        vertices = []
        faces = []
        
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        
        while explorer.More():
            face_shape = explorer.Current()
            tshape = face_shape.TShape()
            
            # Get triangulation directly from TShape (no face casting needed)
            triangulation = tshape.ActiveTriangulation()
            
            if triangulation:
                nbr_nodes = triangulation.NbNodes()
                nbr_triangles = triangulation.NbTriangles()
                
                # Store this triangulation's base vertex index
                base_index = len(vertices)
                
                # Add vertices using InternalNodes() and Node()
                for i in range(1, nbr_nodes + 1):
                    p = triangulation.Node(i)
                    vertices.append([p.X(), p.Y(), p.Z()])
                
                # Add triangles using Triangle() and Value()
                for i in range(1, nbr_triangles + 1):
                    tri = triangulation.Triangle(i)
                    
                    # Poly_Triangle has Value(i) for i=1,2,3
                    v1 = tri.Value(1)
                    v2 = tri.Value(2)
                    v3 = tri.Value(3)
                    
                    indices = [
                        base_index + v1 - 1,
                        base_index + v2 - 1,
                        base_index + v3 - 1
                    ]
                    faces.append(indices)
            
            explorer.Next()
        
        # Limit triangles
        if len(faces) > max_triangles:
            faces = faces[:max_triangles]
        
        # Build flat vertex and index arrays
        indices = []
        for face in faces:
            indices.extend(face)
        
        # Calculate bounding box using BRepBndLib.Add_s
        bb = Bnd_Box()
        BRepBndLib.Add_s(shape, bb)
        x_min, y_min, z_min, x_max, y_max, z_max = bb.Get()
        
        bbox = {
            'min': [x_min, y_min, z_min],
            'max': [x_max, y_max, z_max],
            'center': [
                (x_min + x_max) / 2,
                (y_min + y_max) / 2,
                (z_min + z_max) / 2
            ],
            'size': [
                x_max - x_min,
                y_max - y_min,
                z_max - z_min
            ]
        }
        
        return {
            'success': True,
            'vertices': vertices,
            'indices': indices,
            'triangles': len(faces),
            'faces': len(faces),
            'volume': round(volume, 2),
            'surface_area': round(surface_area, 2),
            'bounding_box': bbox
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'vertices': [],
            'indices': [],
            'triangles': 0,
            'faces': 0,
            'volume': 0,
            'surface_area': 0,
            'bounding_box': None
        }
