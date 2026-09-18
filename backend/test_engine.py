"""Test script to create a test STEP file and verify the backend."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.STEPControl import STEPControl_Writer, STEPControl_StepModelType
from OCP.IFSelect import IFSelect_RetDone
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp

def create_test_step(filepath):
    """Create a simple solid box STEP file for testing."""
    # Create a solid box 100x100x50
    box = BRepPrimAPI_MakeBox(100.0, 100.0, 50.0).Shape()
    
    # Compute and print volume
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(box, props)
    vol = props.Mass()
    print(f"Created solid box with volume: {vol:.2f} mm³")
    
    # Export to STEP
    writer = STEPControl_Writer()
    writer.Transfer(box, STEPControl_StepModelType.STEPControl_AsIs)
    status = writer.Write(filepath)
    
    if status == IFSelect_RetDone:
        print(f"Test STEP file created at: {filepath}")
        print(f"File size: {os.path.getsize(filepath)} bytes")
    else:
        print(f"Failed to write STEP file: {status}")
    
    return status == IFSelect_RetDone

def main():
    test_dir = os.path.dirname(__file__)
    test_path = os.path.join(test_dir, "test_box.solid.step")
    
    # Create test file if it doesn't exist
    if not os.path.exists(test_path):
        success = create_test_step(test_path)
        if not success:
            print("Failed to create test file")
            return 1
    else:
        print(f"Using existing test file: {test_path}")
    
    print("\n=== Testing engine.py ===")
    from engine import validate_step_file, process_step_file
    
    # Test validation
    print("\n--- Validating test STEP file ---")
    info = validate_step_file(test_path)
    print(f"Valid: {info.valid}")
    print(f"Shapes: {info.num_shapes}")
    print(f"Faces: {info.num_faces}")
    print(f"Edges: {info.num_edges}")
    print(f"Vertices: {info.num_vertices}")
    print(f"Volume: {info.volume:.2f} mm³")
    print(f"Surface Area: {info.surface_area:.2f} mm²")
    print(f"Bounding Box: {info.bounding_box}")
    print(f"Errors: {info.errors}")
    
    if not info.valid:
        print("ERROR: File validation failed!")
        return 1
    
    # Test processing with different thicknesses
    print("\n--- Processing with different wall thicknesses ---")
    results = []
    for thickness in [1.0, 3.0, 5.0, 10.0]:
        output_path = os.path.join(test_dir, f"test_output_{thickness}mm.step")
        result = process_step_file(test_path, thickness, output_path)
        
        print(f"\nThickness {thickness}mm:")
        print(f"  Status: {result['status']}")
        print(f"  Input Volume: {result.get('input_volume', 0):.2f} mm³")
        print(f"  Output Volume: {result.get('output_volume', 0):.2f} mm³")
        print(f"  Volume Change: {result.get('volume_change', 0):.2f} mm³")
        print(f"  Input Faces: {result.get('input_faces', 0)}")
        print(f"  Output Faces: {result.get('output_faces', 0)}")
        print(f"  Warnings: {result.get('warnings', [])}")
        print(f"  Errors: {result.get('errors', [])}")
        
        if result['status'] == 'success':
            print(f"  Output file size: {os.path.getsize(output_path)} bytes")
            results.append(result)
        else:
            print(f"  ERROR: Processing failed!")
            return 1
    
    # Verify that different thicknesses produce different results
    print("\n--- Verifying thickness propagation ---")
    if len(results) >= 2:
        volumes = [r.get('output_volume', 0) for r in results]
        unique_volumes = len(set([round(v, 2) for v in volumes]))
        print(f"Unique output volumes: {unique_volumes} (from {len(volumes)} thicknesses)")
        
        if unique_volumes >= 2:
            print("✓ Thickness propagation is working correctly!")
        else:
            print("✗ ERROR: All thicknesses produced the same output!")
            return 1
    
    # Test error cases
    print("\n--- Testing error cases ---")
    
    # Test with invalid thickness
    print("\nTesting invalid thickness (0.0):")
    result = process_step_file(test_path, 0.0, os.path.join(test_dir, "test_invalid.step"))
    print(f"  Status: {result['status']}")
    print(f"  Errors: {result['errors']}")
    if result['status'] == 'error' and 'positive' in str(result['errors']).lower():
        print("  ✓ Correctly rejected invalid thickness")
    else:
        print("  ✗ ERROR: Should have rejected invalid thickness")
        return 1
    
    print("\n=== All tests passed! ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
