# This file is for quick debugging purposes
import gmsh

from simulation_backend.DEinterface import de_method
from simulation_backend.DGinterface import dg_method
# Currently valid strings: DE, DG
simulation_method_to_test = "DG" 

JSONtoTest = "/Users/SilvinW/repositories/backend/uploads/MeasurementRoom_6ac4df41866940688befd2e948fa8d22_1.json"
match simulation_method_to_test:
    case "DE":
        gmsh.initialize()  # Initialize msh file
        de_method(json_file_path=JSONtoTest)
        gmsh.finalize()

    case "DG":
        dg_method(json_file_path=JSONtoTest)
