import json
import os
from pathlib import Path
import gmsh
import numpy as np
import h5py
import shutil
import re
import glob
from scipy.io import wavfile

from deeponet_acoustics.end2end.train import train
from deeponet_acoustics.end2end.inference import inference
from simulation_backend.DGinterface import dg_method


def _resolve_path(path: str, base_dir: str) -> str:
    """
    Resolve a path to an absolute path. If the path is relative, resolve it relative to base_dir.

    Args:
        path: The path to resolve (can be relative or absolute)
        base_dir: Base directory for resolving relative paths

    Returns:
        Absolute path
    """
    if os.path.isabs(path):
        return path
    return os.path.join(base_dir, path)


def _convert_relative_to_absolute_paths(
    json_file_path: str | Path, dirname: str
) -> dict:
    """
    Convert relative paths in the JSON configuration to absolute paths.
    Handles both relative and absolute paths - relative paths are resolved
    relative to the dirname (location of this module).

    Args:
        json_file_path: Path to the JSON configuration file
        dirname: Base directory for resolving relative paths

    Returns:
        Dictionary with updated settings including absolute paths
    """
    with open(json_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Resolve paths (handles both relative and absolute)
    data["dg_setup"]["output_path"] = _resolve_path(
        data["dg_setup"]["output_path"], dirname
    )
    data["deeponet_train_setup"]["input_dir"] = _resolve_path(
        data["deeponet_train_setup"]["input_dir"], dirname
    )
    data["deeponet_train_setup"]["output_dir"] = _resolve_path(
        data["deeponet_train_setup"]["output_dir"], dirname
    )

    # Construct derived paths
    data["deeponet_inference_setup"]["validation_data_dir"] = os.path.join(
        data["deeponet_train_setup"]["input_dir"],
        data["deeponet_train_setup"]["testing_data_dir"],
    )
    data["deeponet_inference_setup"]["model_dir"] = os.path.join(
        data["deeponet_train_setup"]["output_dir"], data["deeponet_train_setup"]["id"]
    )

    # Save updated paths back to JSON
    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file, indent=4)

    return data


def _prepare_dg_json(json_file_path: str) -> str:
    """
    Create a new JSON file from the configuration file to be used by the DG method.

    Args:
        json_file_path: Path to the JSON configuration file

    Returns:
        Path to new json file that will be used by the DG method
    """

    # Retrieve data from json
    with open(json_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Create a new json file for DG
    dg_json = os.path.join(os.path.join(dirname, "tmp"), "dg_tmp.json")

    # Copy the data of the DeepONet json into the DG json
    with open(dg_json, "w") as dg_output:
        dg_output.write(json.dumps(data, indent=4))

    # Obtain the data from the file
    with open(dg_json, "r", encoding="utf-8") as file:
        dg_data = json.load(file)

    # Extract everything inside "dg_setup"
    dg_setup_contents = data.get("dg_setup", {})

    # Append the dg_data with the contents of dg_setup
    dg_data.update(dg_setup_contents)

    # Remove unneeded DeepONet settings
    dg_data.pop("dg_setup")
    dg_data.pop("deeponet_train_setup")
    dg_data.pop("deeponet_inference_setup")

    # Write this to the JSON
    with open(dg_json, "w") as dg_file:
        json.dump(dg_data, dg_file, indent=4)

    # Return the filepath
    return dg_json


def _run_dg_simulation(json_file_path: str | Path) -> None:
    """
    Run the DG simulation using the provided JSON configuration.
    Only generates the NPZ file without updating the JSON with results.

    Args:
        json_file_path: Path to the JSON configuration file
    """
    gmsh.initialize()
    dg_method(json_file_path, save_results_to_json=False)
    gmsh.finalize()


def _load_and_process_dg_results(
    output_path: str, output_filename: str, file_format: str
) -> tuple:
    """
    Load DG simulation results and extract mesh, pressure, and time data.

    Args:
        output_path: Directory containing the DG results
        output_filename: Name of the results file
        file_format: File format (e.g., 'npz')

    Returns:
        Tuple of (mesh, pressures, time_steps, source_positions, results_dg)
    """
    results_dg = np.load(os.path.join(output_path, f"{output_filename}.{file_format}"))

    mesh = np.array(results_dg["rec"]).T.astype(np.float64)
    pressures = np.array(results_dg["IR_Uncorrected"]).T.astype(np.float16)
    time_steps = np.linspace(0, results_dg["total_time"], results_dg["Ntimesteps"])
    source_positions = np.array([results_dg["source_xyz"]]).astype(np.float64)

    return mesh, pressures, time_steps, source_positions, results_dg


def _process_source_data(results_dg: dict, source_position: np.ndarray) -> tuple:
    """
    Process source-specific data including mesh and pressure information.

    Args:
        results_dg: DG simulation results
        source_position: Position of the source (TODO)

    Returns:
        Tuple of (umesh, upressures, ushape)
    """
    umesh = np.array(results_dg["IC_mesh"]).T.astype(np.float64)
    upressures = np.array(results_dg["IC_pressure"]).astype(np.float16)

    # TODO: the umesh generated by DGFEM should be uniformly distributed.
    # For now we should be using MLPs not requiring uniform grids.
    # Should be the number of points/elements in the x, y, z dimensions used if e.g.
    # CNNs are used in the branch net
    ushape = np.array([-1, -1, -1]).astype(np.int64)

    # TODO: dg should be fixed to only returning unique mesh points
    print(f"# coordinates from DG: {umesh.shape[0]}")
    umesh, unique_indices = np.unique(umesh, axis=0, return_index=True)
    upressures = upressures[unique_indices]
    print(f"# coordinates after removing duplicates: {umesh.shape[0]}")

    return umesh, upressures, ushape


def _save_h5_training_data(
    file_path_h5: str,
    mesh: np.ndarray,
    pressures: np.ndarray,
    time_steps: np.ndarray,
    source_position: np.ndarray,
    umesh: np.ndarray,
    upressures: np.ndarray,
    ushape: np.ndarray,
) -> None:
    """
    Save training data to HDF5 format.

    Args:
        file_path_h5: Path to the output HDF5 file
        mesh: Receiver mesh coordinates
        pressures: Pressure values at receivers
        time_steps: Time steps array
        source_position: Position of the source
        umesh: Unique mesh points
        upressures: Unique pressure values
        ushape: Shape of unique mesh
    """
    os.makedirs(os.path.dirname(file_path_h5), exist_ok=True)
    Path(file_path_h5).unlink(missing_ok=True)

    with h5py.File(file_path_h5, "w") as f:
        # Original mesh and pressures
        f.create_dataset("mesh", data=mesh)
        ds_p = f.create_dataset("pressures", data=pressures)
        ds_p.attrs["time_steps"] = time_steps  # attach as attribute

        # Source position
        f.create_dataset("source_position", data=source_position)

        # Unique mesh and pressures
        ds_umesh = f.create_dataset("umesh", data=umesh)
        ds_umesh.attrs["umesh_shape"] = ushape  # attach as attribute
        f.create_dataset("upressures", data=upressures)


def _save_simulation_parameters(
    file_path_json: str,
    source_position: np.ndarray,
    dg_settings: dict,
    results_dg: dict,
) -> None:
    """
    Save simulation parameters to JSON file.

    Args:
        file_path_json: Path to the output JSON file
        source_position: Position of the source
        dg_settings: DG simulation settings
        results_dg: DG simulation results
    """
    os.makedirs(os.path.dirname(file_path_json), exist_ok=True)

    simulation_params = {
        "SimulationParameters": {
            "SourcePosition": source_position.tolist(),
            "c": dg_settings["dg_c0"],
            "dt": results_dg["dt_old"].tolist(),
            "fmax": dg_settings["dg_freq_upper_limit"],
            "rho": dg_settings["dg_rho0"],
        }
    }

    with open(file_path_json, "w") as json_file:
        json.dump(simulation_params, json_file, indent=4)


def _prepare_validation_data(
    output_path: str,
    settings: dict,
    source_index: int,
    train_h5_path: str,
    train_params_path: str,
) -> None:
    """
    Prepare validation data by copying training data.

    Args:
        output_path: Base output directory
        settings: Configuration settings
        source_index: Index of the current source
        train_h5_path: Path to training HDF5 file
        train_params_path: Path to training parameters JSON
    """
    # Copy HDF5 validation data
    file_path_val_h5 = os.path.join(
        output_path,
        settings["deeponet_train_setup"]["testing_data_dir"],
        f"src{source_index}",
        os.path.basename(train_h5_path),
    )
    os.makedirs(os.path.dirname(file_path_val_h5), exist_ok=True)
    Path(file_path_val_h5).unlink(missing_ok=True)
    shutil.copy(train_h5_path, file_path_val_h5)

    # Copy simulation parameters to train data root
    simulation_params_path_root_json = os.path.join(
        output_path, "train_data", "simulation_parameters.json"
    )
    Path(simulation_params_path_root_json).unlink(missing_ok=True)
    shutil.copy(train_params_path, simulation_params_path_root_json)

    # Copy simulation parameters to validation data
    simulation_params_path_val_json = os.path.join(
        output_path, "val_data", f"src{source_index}", "simulation_parameters.json"
    )
    Path(simulation_params_path_val_json).unlink(missing_ok=True)
    shutil.copy(train_params_path, simulation_params_path_val_json)


def _parse_receiver_position_from_filename(
    filename: str,
) -> tuple[list[float], list[float]]:
    """
    Parse source and receiver positions from WAV filename.

    Filename format: 0_x0=['0.40', '1.00', '1.20']_r0=['1.00', '1.00', '1.10']_pred.wav

    Args:
        filename: WAV filename with embedded position information

    Returns:
        Tuple of (source_position, receiver_position) as lists of floats
    """
    # Extract source position x0
    x0_match = re.search(r"x0=\['([^']+)',\s*'([^']+)',\s*'([^']+)'\]", filename)
    # Extract receiver position r0
    r0_match = re.search(r"r0=\['([^']+)',\s*'([^']+)',\s*'([^']+)'\]", filename)

    if not x0_match or not r0_match:
        raise ValueError(f"Could not parse positions from filename: {filename}")

    source_pos = [
        float(x0_match.group(1)),
        float(x0_match.group(2)),
        float(x0_match.group(3)),
    ]
    receiver_pos = [
        float(r0_match.group(1)),
        float(r0_match.group(2)),
        float(r0_match.group(3)),
    ]

    return source_pos, receiver_pos


def _read_wav_impulse_response(wav_path: str) -> list[float]:
    """
    Read impulse response from WAV file.

    Args:
        wav_path: Path to the WAV file

    Returns:
        Impulse response as a list of floats
    """
    sample_rate, data = wavfile.read(wav_path)

    # Convert to float and normalize if needed
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0

    # If stereo, take first channel
    if len(data.shape) > 1:
        data = data[:, 0]

    return data.tolist()


def _write_results_json(
    json_file_path: str | Path, settings: dict, output_json_path: str | Path
) -> None:
    """
    Write results.json with DeepONet-generated impulse responses.

    Reads the predicted WAV files from the DeepONet output directory and
    populates the results section of the JSON configuration.

    Args:
        json_file_path: Path to the JSON configuration file
        settings: Configuration settings dictionary
        output_json_path: Path where the results.json should be written
    """
    # Construct path to the receivers directory
    model_id = settings["deeponet_train_setup"]["id"]
    receivers_dir = os.path.join(
        settings["deeponet_train_setup"]["output_dir"], model_id, "figs", "receivers"
    )

    # Find all pred.wav files
    pred_wav_files = glob.glob(os.path.join(receivers_dir, "*_pred.wav"))

    if not pred_wav_files:
        print(f"Warning: No prediction WAV files found in {receivers_dir}")
        return

    # Load the current JSON
    with open(json_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Group by source position
    results_by_source = {}

    for wav_file in pred_wav_files:
        filename = os.path.basename(wav_file)

        try:
            source_pos, receiver_pos = _parse_receiver_position_from_filename(filename)
            ir_data = _read_wav_impulse_response(wav_file)

            # Use source position as key
            source_key = tuple(source_pos)

            if source_key not in results_by_source:
                results_by_source[source_key] = {
                    "sourceX": source_pos[0],
                    "sourceY": source_pos[1],
                    "sourceZ": source_pos[2],
                    "resultType": "DON",
                    "percentage": 100,
                    "responses": [],
                }

            # Add receiver response
            results_by_source[source_key]["responses"].append(
                {
                    "x": receiver_pos[0],
                    "y": receiver_pos[1],
                    "z": receiver_pos[2],
                    "receiverResults": [],
                    "receiverResultsUncorrected": ir_data,
                }
            )

        except Exception as e:
            print(f"Warning: Could not process {filename}: {e}")
            continue

    # Update the results section
    data["results"] = list(results_by_source.values())

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_json_path), exist_ok=True)

    # Delete existing file if it exists
    Path(output_json_path).unlink(missing_ok=True)

    # Write results to the specified path
    with open(output_json_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    print(f"Results written to: {output_json_path}")


def deeponet_method(json_file_path: str | Path, output_json_path: str | Path = None):
    """
    Execute the complete DeepONet pipeline: DG simulation, data preparation, training, and inference.

    Pipeline steps:
    1. Convert relative paths to absolute paths in configuration
    2. Run DG simulation to generate high-fidelity data
    3. Load and process DG results
    4. Prepare training and validation data in HDF5 format
    5. Train the DeepONet model
    6. Run inference with the trained model
    7. Write results.json with DeepONet predictions

    Args:
        json_file_path: Path to the JSON configuration file
        output_json_path: Path where results.json should be written.
                         If None, defaults to headless_backend/output/results.json
    """
    # Step 1: Convert relative paths to absolute paths
    dirname = os.path.dirname(__file__)
    settings = _convert_relative_to_absolute_paths(json_file_path, dirname)

    # Set default output path if not provided
    if output_json_path is None:
        output_json_path = os.path.join(
            dirname, "headless_backend", "output", "results.json"
        )

    # Step 2: Run DG simulation
    dg_json = _prepare_dg_json(json_file_path)
    _run_dg_simulation(dg_json)

    # Step 3: Load and process DG results
    dg_settings = settings["dg_setup"]

    output_path = dg_settings["output_path"]
    output_filename = dg_settings["output_filename"]
    file_format = dg_settings["file_format"]
    dg_simulation_settings = dg_settings["simulationSettings"]

    os.makedirs(output_path, exist_ok=True)

    mesh, pressures, time_steps, source_positions, results_dg = (
        _load_and_process_dg_results(output_path, output_filename, file_format)
    )

    # Step 4: Process each source and prepare training/validation data
    # TODO: DG only supports 1 source
    for i, source_position in enumerate(source_positions):
        # Process source-specific data
        umesh, upressures, ushape = _process_source_data(results_dg, source_position)

        # Save training data to HDF5
        file_path_train_h5 = os.path.join(
            output_path,
            settings["deeponet_train_setup"]["training_data_dir"],
            f"src{i}",
            f"{output_filename}.h5",
        )
        _save_h5_training_data(
            file_path_train_h5,
            mesh,
            pressures,
            time_steps,
            source_position,
            umesh,
            upressures,
            ushape,
        )

        # Save simulation parameters
        simulation_params_path_train_json = os.path.join(
            output_path, "train_data", f"src{i}", "simulation_parameters.json"
        )
        _save_simulation_parameters(
            simulation_params_path_train_json,
            source_position,
            dg_simulation_settings,
            results_dg,
        )

        # Prepare validation data (copy from training data)
        _prepare_validation_data(
            output_path,
            settings,
            i,
            file_path_train_h5,
            simulation_params_path_train_json,
        )

    # Step 5: Train DeepONet model
    train(settings["deeponet_train_setup"])

    # Step 6: Run inference with trained model
    inference(settings["deeponet_train_setup"], settings["deeponet_inference_setup"])

    # Step 7: Write results.json with DeepONet predictions
    _write_results_json(json_file_path, settings, output_json_path)


if __name__ == "__main__":
    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
        plot_dg_results,
    )

    # Clean up output folder
    dirname = os.path.dirname(__file__)
    output_dir = os.path.join(dirname, "headless_backend", "output")
    if os.path.exists(output_dir):
        for file in os.listdir(output_dir):
            file_path = os.path.join(output_dir, file)
            if os.path.isfile(file_path):
                os.unlink(file_path)

    # Load the input file
    file_name = find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_deeponet_acoustics.json"
    )
    json_tmp_file = create_tmp_from_input(file_name)

    # Define output path
    results_json_path = os.path.join(
        dirname, "headless_backend", "output", "results.json"
    )

    # Run the complete DeepONet pipeline (includes DG simulation and results writing)
    deeponet_method(json_tmp_file, results_json_path)

    # Plot the results
    plot_dg_results(results_json_path)
