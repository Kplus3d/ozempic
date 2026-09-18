from OCP.STEPControl import STEPControl_Writer, STEPControl_StepModelType
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone

# Create a simple box
box = BRepPrimAPI_MakeBox(100, 100, 100).Shape()

# Export to STEP
writer = STEPControl_Writer()
status = writer.Transfer(box, STEPControl_StepModelType.STEPControl_AsIs)
result = writer.Write('~/ozempic/test_step.step')

if result == IFSelect_RetDone:
    print("Test STEP file created successfully!")
else:
    print("Failed to create STEP file")
