import json
import os
from pathlib import Path
import gmsh
import numpy as np
import h5py
import shutil

from deeponet_room_acoustics.end2end.train3D import train
from deeponet_room_acoustics.end2end.eval3D import evaluate
from simulation_backend.DGinterface import dg_method
from simulation_backend.headless_backend.HelperFunctions import plot_results

def deeponet_method(json_file_path: str | Path):        
    with open(json_file_path, "r") as json_file:
        settings = json.load(json_file)

    # generate data for deeponet training
    gmsh.initialize()
    dg_method(json_file_path)
    gmsh.finalize()

    dg_settings = settings["dg_setup"]
    output_path = dg_settings["output_path"]
    output_filename = dg_settings["output_filename"]
    file_format = dg_settings["file_format"]

    os.makedirs(dg_settings["output_path"], exist_ok=True)

    results_dg = np.load(os.path.join(output_path, f"{output_filename}.{file_format}"))

    mesh = np.array(results_dg["rec"]).T.astype(np.float64)
    pressures = np.array(results_dg["IR_Uncorrected"]).T.astype(np.float16)
    time_steps = np.linspace(0, results_dg["total_time"], results_dg["Ntimesteps"])

    source_positions = np.array([results_dg["source_xyz"]]).astype(np.float64)

    # TODO: DG only supports 1 source
    for i, source_position in enumerate(source_positions):
        umesh = np.array(results_dg["IC_mesh"]).T.astype(np.float64)
        upressures = np.array(results_dg["IC_pressure"]).astype(np.float16)
        # TODO: the umesh should be uniformly distributed and the 
        # x, y, z dim passed here for using e.g. CNNs for the branch net
        ushape = np.array([-1,-1,-1]).astype(np.int64)

        # TODO: dg should be fixed to only returning unique mesh points
        print(f"# coordinates from DG: {umesh.shape[0]}")
        umesh, unique_indices = np.unique(umesh, axis=0, return_index=True)
        upressures = upressures[unique_indices]
        print(f"# coordinates after removing duplicates: {umesh.shape[0]}")

        ###!!! TODO IMPORTANT: data needs to be normalized to perform well !!!###

        # Save to HDF5
        file_path_train_h5 = os.path.join(output_path, "train_data", f"src{i}", f"{output_filename}.h5")
        os.makedirs(os.path.dirname(file_path_train_h5), exist_ok=True)
        Path(file_path_train_h5).unlink(missing_ok=True)    

        with h5py.File(file_path_train_h5, "w") as f:
            # Original mesh and pressures
            f.create_dataset("mesh", data=mesh)
            ds_p = f.create_dataset("pressures", data=pressures)
            ds_p.attrs["time_steps"] = time_steps  # attach as attribute
            
            # Source position
            f.create_dataset("source_position", data=source_position)
            
            ds_p = f.create_dataset("umesh", data=umesh)
            ds_p.attrs["umesh_shape"] = ushape  # attach as attribute
            f.create_dataset("upressures", data=upressures)

        simulation_params_path_train_json = os.path.join(output_path, "train_data", f"src{i}", "simulation_parameters.json")
        with open(simulation_params_path_train_json, "w") as json_file:
            json_file.write(
                json.dumps(
                    {
                        "SimulationParameters": {
                            "SourcePosition": source_position.tolist(),
                            "c": dg_settings["c0"],
                            "dt": results_dg["dt_old"].tolist(),
                            "fmax": dg_settings["freq_upper_limit"],
                            "rho": dg_settings["rho0"],
                            "sigma": dg_settings["R"],
                        }
                    },
                    indent=4,
                )
            )

        # for now, use the same data for training and validation
        file_path_val_h5 = os.path.join(output_path, "val_data", f"src{i}", f"{output_filename}.h5")
        os.makedirs(os.path.dirname(file_path_val_h5), exist_ok=True)
        Path(file_path_val_h5).unlink(missing_ok=True)
        shutil.copy(file_path_train_h5, file_path_val_h5)

        # we need the simulation_parameters.json at the train data root
        simulation_params_path_root_json = os.path.join(output_path, "train_data", "simulation_parameters.json")
        Path(simulation_params_path_root_json).unlink(missing_ok=True)
        shutil.copy(simulation_params_path_train_json, simulation_params_path_root_json)

        # ... and for the validation data
        simulation_params_path_val_json = os.path.join(output_path, "val_data", f"src{i}", "simulation_parameters.json")
        Path(simulation_params_path_val_json).unlink(missing_ok=True)
        shutil.copy(simulation_params_path_train_json, simulation_params_path_val_json)
    
    train(settings["deeponet_train_setup"])
    evaluate(settings["deeponet_train_setup"], settings["deeponet_inference_setup"])
        

if __name__ == "__main__":
    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
    )

    # Load the input file
    file_name = find_input_file_in_subfolders(  
        os.path.dirname(__file__), "exampleInput_deeponet.json"
    )
    json_tmp_file = create_tmp_from_input(file_name)

    # Run the method
    deeponet_method(json_tmp_file)

    # Save the results to a separate file
    save_results(json_tmp_file)

    # Plot the results
    plot_results(json_tmp_file)