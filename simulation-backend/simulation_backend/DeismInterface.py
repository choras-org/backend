import os
import time
import numpy as np
import json
import logging
import traceback

from deism.core_deism import *
from deism.data_loader import *
from deism.room_check import (
    get_room_geometry,
    update_surface_areas,
    update_wall_centers,
)


logger = logging.getLogger(__name__)


def parse_value(val):
    """Handle strings of comma-separated floats OR single float values."""
    if isinstance(val, str):
        return np.array([float(x.strip()) for x in val.split(",") if x.strip()])
    elif isinstance(val, (int, float)):
        return np.array([val])
    elif isinstance(val, (list, tuple)):
        return np.array(val, dtype=float)
    else:
        raise ValueError(f"Unsupported type for parse_value: {type(val)}")


def deism_method(json_file_path=None):
    """
    DEISM simulation method that processes a JSON file containing simulation parameters.

    Parameters
    ----------
    json_file_path : str, optional
        Path to the JSON file containing simulation parameters and results.
        If None, the method will not run.
    """
    print("deism_method: starting simulation")
    st = time.time()  # start time of calculation

    if json_file_path is None:
        print("No JSON file path provided. Exiting.")
        return

    # Change to the directory containing the config file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    original_cwd = os.getcwd()
    os.chdir(script_dir)

    try:
        # Step 1: read JSON to get geo_path
        with open(json_file_path, "r") as json_file:
            result_container = json.load(json_file)
            geo_path = result_container["geo_path"]  # This should now be absolute path

        # Step 2: update areas, wall centers, volume
        update_surface_areas(json_file_path, geo_path)
        update_wall_centers(json_file_path, geo_path)
        Volume, room = get_room_geometry(geo_file=geo_path)

        # Step 3: write volume to JSON
        with open(json_file_path, "r+") as json_file:
            data = json.load(json_file)
            data["geometry"][0]["room_volumn"] = Volume
            json_file.seek(0)
            json.dump(data, json_file, indent=4)
            json_file.truncate()

        # Step 4: use the already-updated data instead of re-loading
        result_container = data

        # Checking whether the 'should_cancel' flag has been set to True by the user
        # Do not call this function all the time, as it is quite heavy
        # This function should be called in the main calculation loop
        def check_should_cancel(json_file_path_in):
            try:
                if json_file_path_in is not None:
                    with open(json_file_path_in, "r") as json_file_to_check:
                        data = json.load(json_file_to_check)
                        # Update the specified field value
                        if "should_cancel" in data:
                            return data["should_cancel"]
                return False
            except Exception as e:
                print("check_should_cancel returned: " + str(e))
                print(traceback.format_exc())
                return False

        if check_should_cancel(json_file_path):
            return

        # Load from the json file
        print("Obtaining simulation settings from the json file ... \n")
        simulation_settings = None
        coord_source = None
        coord_rec = None
        abs_coeffs_loaded = None
        freq_bands = None

        if result_container:
            simulation_settings = result_container["simulationSettings"]
            coord_source = [
                result_container["results"][0]["sourceX"],
                result_container["results"][0]["sourceY"],
                result_container["results"][0]["sourceZ"],
            ]

            coord_rec = [
                result_container["results"][0]["responses"][0]["x"],
                result_container["results"][0]["responses"][0]["y"],
                result_container["results"][0]["responses"][0]["z"],
            ]
            abs_coeffs_loaded = result_container["absorption_coefficients"]
            freq_bands = np.array(result_container["results"][0]["frequencies"])

        # Convert data to the ones needed in DEISM
        print("Converting data to the ones needed in DEISM ... \n")
        # -----------------------------------------------------------
        # About room geometry and wall properties
        # N is the number of vertices of the room
        # M is the number of wall centers
        # -----------------------------------------------------------
        vertices = np.array(
            result_container["geometry"][0]["vertices"]
        )  # Nx3 numpy array
        wall_centers_loaded = result_container["geometry"][0]["wall_centers"]
        room_volumn = result_container["geometry"][0]["room_volumn"]  # float
        room_areas_loaded = result_container["geometry"][0][
            "room_areas"
        ]  # (M,) numpy array
        # we want the absorption has size 6 * len(frequency bands)
        # The first dimension is for the walls, viz., x1, x2, y1, y2, z1, z2
        # Corresponding to wall 1, wall 3, wall 2, wall 4, floor, ceiling
        wall_order = ["wall1", "wall3", "wall2", "wall4", "floor", "ceiling"]
        # Create an empty array for the absorption coefficients
        absorption_coefficients = np.zeros((6, len(freq_bands)))
        wall_centers = np.zeros((6, 3))
        room_areas = np.zeros((6, 1))
        for wall in wall_order:
            absorption_coefficients[wall_order.index(wall), :] = parse_value(
                abs_coeffs_loaded[wall]
            )
            wall_centers[wall_order.index(wall), :] = parse_value(
                wall_centers_loaded[wall]
            )
            room_areas[wall_order.index(wall), :] = parse_value(room_areas_loaded[wall])

        # Apply DEISM
        deism = DEISM("RIR", room)
        print("valuess of deism")  #
        print("vertices", vertices)
        print("wall center", wall_centers)
        print("room areas", room_areas)

        deism.update_room(
            vertices,
            wall_centers,
            room_volumn,
            room_areas,
        )
        deism.update_wall_materials(
            absorption_coefficients, freq_bands, "absorpCoefficient"
        )
        deism.update_freqs()
        # deism.update_images()
        # update source and receiver positions in deism
        deism.params["posSource"] = np.array(coord_source)
        deism.params["posRec"] = np.array(coord_rec)
        deism.update_images()
        deism.update_directivities()
        pressure = deism.run_DEISM()
        # -----------------------------------------------------------
        # Save the simulation results
        # -----------------------------------------------------------
        # Save the simulation results in the json file
        result_container["results"][0]["responses"][0][
            "receiverResults"
        ] = pressure.tolist()
        with open(json_file_path, "w") as new_result_json:
            new_result_json.write(json.dumps(result_container, indent=4))
        print("deism_method: simulation done!")

    except Exception as e:
        print(f"Error in deism_method: {str(e)}")
        print(traceback.format_exc())
    finally:
        # Restore original working directory
        os.chdir(original_cwd)


# -------------------------------------------------------
if __name__ == "__main__":
    import os
    import sys

    # Add the parent directory to Python path to allow importing simulation_backend
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    from headless_backend.HelperFunctions import (
        find_input_file_in_subfolders,
        create_tmp_from_input_deism,
        save_results,
    )

    # Load the input file
    file_name = find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_Deism.json"
    )
    json_tmp_file = create_tmp_from_input_deism(file_name)

    # Run the method
    deism_method(json_tmp_file)

    # Results are already saved in the temporary JSON file
    print(f"Simulation completed. Results saved to: {json_tmp_file}")
