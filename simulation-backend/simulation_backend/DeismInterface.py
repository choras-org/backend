import os
import time
import numpy as np
import json
import logging
import traceback
import sys
import subprocess
from contextlib import contextmanager

# from Diffusion.acousticDE.FiniteVolumeMethod.FVMfunctions import create_vgroups_names
import gmsh
from deism.core_deism import *
from deism.data_loader import ConflictChecks, detect_conflicts, compute_rest_params
from deism.room_check import *


logger = logging.getLogger(__name__)
DEISM_SUBPROCESS_ENV = "CHORAS_DEISM_SUBPROCESS"

DEISM_JSON_KEY_MAP = {
    "soundSpeed": ("soundSpeed", float),
    "airDensity": ("airDensity", float),
    "RIRLength": ("rt60", float),
    "samplingRate": ("sampleRate", int),
    "maxReflectionOrder": ("maxReflOrder", int),
    "sourceOrder": ("nSourceOrder", int),
    "receiverOrder": ("vReceiverOrder", int),
    "sourceRadius": ("radiusSource", float),
    "receiverRadius": ("radiusReceiver", float),
    "sourceOrientation": ("orientSource", "array"),
    "receiverOrientation": ("orientReceiver", "array"),
    "sourceDirectivity": ("sourceType", str),
    "receiverDirectivity": ("receiverType", str),
    "ifRemoveDirect": ("ifRemoveDirectPath", int),
    "Method": ("DEISM_mode", str),
    "mixEarlyOrder": ("mixEarlyOrder", int),
    "numParaImages": ("numParaImages", int),
    "ifReceiverNormalize": ("ifReceiverNormalize", int),
    "QFlowStrength": ("qFlowStrength", float),
    "SilentMode": ("silentMode", int),
    # Backward-compatible aliases for the previous CHORAS JSON contract.
    "rt60": ("rt60", float),
    "sampleRate": ("sampleRate", int),
    "maxReflOrder": ("maxReflOrder", int),
    "nSourceOrder": ("nSourceOrder", int),
    "vReceiverOrder": ("vReceiverOrder", int),
    "radiusSource": ("radiusSource", float),
    "radiusReceiver": ("radiusReceiver", float),
    "orientSource": ("orientSource", "array"),
    "orientReceiver": ("orientReceiver", "array"),
    "sourceType": ("sourceType", str),
    "receiverType": ("receiverType", str),
    "ifRemoveDirectPath": ("ifRemoveDirectPath", int),
    "DEISM_mode": ("DEISM_mode", str),
    "qFlowStrength": ("qFlowStrength", float),
    "silentMode": ("silentMode", int),
}


def create_vgroups_names(file_path):
    """
    Create a list of the material names assigned in SketchUp

    Parameters
    ----------
        file_path : str
            Full path to the mesh file

    Returns
    -------
        vGroupsNames : list
            Names of the materials in the msh file (the material name are the same as the one assigned in the SketchUp file)
    """
    gmsh.initialize()  # Initialize msh file
    mesh = gmsh.open(file_path)  # open the file
    dim = (
        -1
    )  # dimensions of the entities, 0 for points, 1 for curves/edge/lines, 2 for surfaces, 3 for volumes, -1 for all the entities
    tag = -1  # all the nodes of the room
    vGroups = gmsh.model.getPhysicalGroups(
        -1
    )  # these are the entity tag and physical groups in the msh file.
    vGroupsNames = (
        []
    )  # these are the entity tag and physical groups in the msh file + their names
    for iGroup in vGroups:
        dimGroup = iGroup[
            0
        ]  # entity tag: 1 lines, 2 surfaces, 3 volumes (1D, 2D or 3D)
        tagGroup = iGroup[
            1
        ]  # physical tag group (depending on material properties defined in SketchUp)
        namGroup = gmsh.model.getPhysicalName(
            dimGroup, tagGroup
        )  # names of the physical groups defined in SketchUp
        alist = [
            dimGroup,
            tagGroup,
            namGroup,
        ]  # creates a list of the entity tag, physical tag group and name
        # print(alist)
        vGroupsNames.append(alist)

    return vGroupsNames


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


def parse_array_value(val):
    """Parse JSON array-like settings into a numpy vector."""
    if isinstance(val, str):
        return np.array([float(x.strip()) for x in val.split(",") if x.strip()])
    if isinstance(val, (list, tuple, np.ndarray)):
        return np.array(val, dtype=float)
    raise ValueError(f"Unsupported array setting type: {type(val)}")


def apply_simulation_settings_to_deism(deism, simulation_settings):
    """
    Override DEISM yaml-loaded params with values coming from the runtime JSON.

    The JSON keys intentionally follow the final parameter names used in
    `deism.data_loader`.
    """
    if not simulation_settings:
        return
    if not isinstance(simulation_settings, dict):
        raise TypeError("simulationSettings must be a JSON object")

    for key, value in simulation_settings.items():
        if value is None:
            continue
        if key not in DEISM_JSON_KEY_MAP:
            logger.warning("Ignoring unsupported DEISM setting key: %s", key)
            continue

        target_key, caster = DEISM_JSON_KEY_MAP[key]
        if caster == "array":
            deism.params[target_key] = parse_array_value(value)
        else:
            deism.params[target_key] = caster(value)

    # Recompute dependent parameters after overriding the yaml defaults.
    deism.params = compute_rest_params(deism.params)


def apply_choras_runtime_overrides(deism, coord_source, coord_rec, freq_bands):
    """
    Apply CHORAS-owned runtime values after the DEISM yaml/json merge.
    """
    deism.params["posSource"] = np.array(coord_source, dtype=float)
    deism.params["posReceiver"] = np.array(coord_rec, dtype=float)

    if freq_bands is not None:
        deism.params["freqs"] = np.array(freq_bands, dtype=float)
        deism.params["waveNumbers"] = (
            2 * np.pi * deism.params["freqs"] / deism.params["soundSpeed"]
        )

        if deism.params.get("ifReceiverNormalize") == 1:
            deism.params["pointSrcStrength"] = (
                1j
                * deism.params["waveNumbers"]
                * deism.params["soundSpeed"]
                * deism.params["airDensity"]
                * deism.params["qFlowStrength"]
            )


def create_deism_instance(mode, room_type):
    """Create DEISM without exposing host process CLI args."""
    original_argv = sys.argv[:]
    try:
        sys.argv = [original_argv[0]] if original_argv else ["deism"]
        return DEISM(mode, room_type)
    finally:
        sys.argv = original_argv


@contextmanager
def use_real_stdio():
    """Temporarily restore real stdio for libraries needing fileno()."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    fallback_stream = None

    try:
        stdout_stream = (
            sys.__stdout__
            if getattr(sys.__stdout__, "fileno", None) is not None
            else None
        )
        stderr_stream = (
            sys.__stderr__
            if getattr(sys.__stderr__, "fileno", None) is not None
            else None
        )

        if stdout_stream is None or stderr_stream is None:
            fallback_stream = open(os.devnull, "w")
            if stdout_stream is None:
                stdout_stream = fallback_stream
            if stderr_stream is None:
                stderr_stream = fallback_stream

        sys.stdout = stdout_stream
        sys.stderr = stderr_stream
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if fallback_stream is not None:
            fallback_stream.close()


def get_deism_surface_order(vgroups_names):
    """Map Gmsh physical surfaces to DEISM's expected wall order."""
    surface_names_by_tag = {
        int(tag): name for dim, tag, name in vgroups_names if int(dim) == 2
    }
    deism_tag_order = [2, 5, 4, 6, 1, 3]
    missing_tags = [tag for tag in deism_tag_order if tag not in surface_names_by_tag]
    if missing_tags:
        raise KeyError(
            f"Missing physical surface tags required by DEISM: {missing_tags}"
        )
    return [surface_names_by_tag[tag] for tag in deism_tag_order]


def update_result_percentage(result_container, json_file_path, percentage):
    """Persist simulation progress for the first result entry."""
    if not result_container or "results" not in result_container:
        return
    if not result_container["results"]:
        return

    result_container["results"][0]["percentage"] = int(percentage)
    with open(json_file_path, "w") as json_file:
        json.dump(result_container, json_file, indent=4)


def run_deism_subprocess(json_file_path):
    """Run DEISM in a child process to isolate it from eventlet."""
    script_path = os.path.abspath(__file__)
    env = os.environ.copy()
    env[DEISM_SUBPROCESS_ENV] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    completed = subprocess.run(
        [sys.executable, script_path, os.path.abspath(json_file_path)],
        cwd=os.path.dirname(script_path),
        env=env,
        capture_output=True,
        text=True,
    )

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    if completed.returncode != 0:
        raise RuntimeError(
            f"DEISM subprocess failed with exit code {completed.returncode}"
        )


def _deism_method_impl(json_file_path=None):
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

        # Step 2: update areas, wall centers, vertices, and volume in one pass
        sync_room_geometry(json_file_path, geo_path)
        Volume, room = get_room_geometry(geo_file=geo_path)

        with open(json_file_path, "r") as json_file:
            result_container = json.load(json_file)
        update_result_percentage(result_container, json_file_path, 10)

        vGroupsNames = create_vgroups_names(result_container["geo_path"])
        print("vGroupsNames", vGroupsNames)

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
            simulation_settings = result_container.get("simulationSettings", {})
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

        wall_order = get_deism_surface_order(vGroupsNames)
        # Create an empty array for the absorption coefficients
        absorption_coefficients = np.zeros((6, len(freq_bands)))
        wall_centers = np.zeros((6, 3))
        room_areas = np.zeros((6, 1))
        for index, wall in enumerate(wall_order):
            absorption_coefficients[index, :] = parse_value(abs_coeffs_loaded[wall])
            wall_centers[index, :] = parse_value(wall_centers_loaded[wall])
            room_areas[index, :] = parse_value(room_areas_loaded[wall])
        update_result_percentage(result_container, json_file_path, 25)

        # Apply DEISM
        with use_real_stdio():
            deism = create_deism_instance("RIR", room)
        apply_simulation_settings_to_deism(deism, simulation_settings)
        apply_choras_runtime_overrides(deism, coord_source, coord_rec, freq_bands)
        update_result_percentage(result_container, json_file_path, 35)
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
        # Apply parameter conflict checks in deism class
        ConflictChecks.check_all_conflicts(deism.params)
        detect_conflicts(deism.params)
        update_result_percentage(result_container, json_file_path, 45)
        deism.update_wall_materials(
            absorption_coefficients, freq_bands, "absorpCoefficient"
        )
        update_result_percentage(result_container, json_file_path, 55)
        deism.update_freqs()
        update_result_percentage(result_container, json_file_path, 65)
        # deism.update_images()
        # update source and receiver positions in deism
        with use_real_stdio():
            deism.update_source_receiver()
        update_result_percentage(result_container, json_file_path, 75)
        with use_real_stdio():
            deism.update_directivities()
        update_result_percentage(result_container, json_file_path, 85)
        with use_real_stdio():
            deism.run_DEISM()
        update_result_percentage(result_container, json_file_path, 95)
        rir = deism.get_results()
        # normalize the rir
        rir = rir / np.max(np.abs(rir))
        # -----------------------------------------------------------
        # Save the simulation results
        # -----------------------------------------------------------
        # Save the simulation results in the json file
        result_container["results"][0]["responses"][0]["receiverResults"] = rir.tolist()
        # Add a plot that shows the rir in the output folder
        plt.plot(rir)
        plt.savefig(os.path.join(os.path.dirname(json_file_path), "rir.png"))
        plt.close()
        update_result_percentage(result_container, json_file_path, 100)
        print("deism_method: simulation done!")

    except Exception as e:
        print(f"Error in deism_method: {str(e)}")
        print(traceback.format_exc())
        raise
    finally:
        # Restore original working directory
        os.chdir(original_cwd)


def deism_method(json_file_path=None):
    if os.environ.get(DEISM_SUBPROCESS_ENV) == "1":
        return _deism_method_impl(json_file_path)
    return run_deism_subprocess(json_file_path)


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
        create_tmp_from_input,
        save_results,
    )

    if os.environ.get(DEISM_SUBPROCESS_ENV) == "1" and len(sys.argv) > 1:
        deism_method(sys.argv[1])
    else:
        # Load the input file
        file_name = find_input_file_in_subfolders(
            os.path.dirname(__file__), "exampleInput_Deism.json"
        )
        json_tmp_file = create_tmp_from_input(file_name, "exampletmp_deism.json")

        # Run the method
        deism_method(json_tmp_file)

        # Save the results to a separate file
        save_results(json_tmp_file)
