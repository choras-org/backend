import json
import os
from pathlib import Path
import gmsh
import numpy as np
import h5py
import shutil

from deeponet_acoustics.end2end.train import train
from deeponet_acoustics.end2end.inference import inference
from simulation_backend.DGinterface import dg_method

def deeponet_method(json_file_path: str | Path):        

    dirname = os.path.dirname(__file__)
    with open(json_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)


    # Convert relative paths and directory names to absolute paths and save them in the temporary json
    data["dg_setup"]["output_path"] = os.path.join(dirname, data["dg_setup"]["relative_output_path"])
    data["deeponet_train_setup"]["input_dir"] = os.path.join(dirname, data["deeponet_train_setup"]["relative_input_dir"])
    data["deeponet_train_setup"]["output_dir"] = os.path.join(dirname, data["deeponet_train_setup"]["relative_output_dir"])
    data["deeponet_inference_setup"]["validation_data_dir"] = os.path.join(data["deeponet_train_setup"]["input_dir"], data["deeponet_train_setup"]["testing_data_dir"])
    data["deeponet_inference_setup"]["model_dir"] = os.path.join(data["deeponet_train_setup"]["output_dir"], data["deeponet_train_setup"]["id"])

    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file, indent=4)

    ### Discontinuous Galerkin ###

    # create a new json file for DG
    dg_json = os.path.join(os.path.join(dirname, "tmp"), "dg_tmp.json")

    # copy the data of the DeepONet json into the DG json
    with open(dg_json, "w") as dg_output:
        dg_output.write(json.dumps(data, indent=4))

    # obtain the data from the file
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

    # generate data for deeponet training
    gmsh.initialize()
    dg_method(dg_json)
    gmsh.finalize()

    # obtain the results from DG
    with open(dg_json, "r", encoding="utf-8") as file:
        dg_results_data = json.load(file)
    
    # write them to the original json file
    data.update(dg_results_data)
    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file, indent=4)



    ### DeepONet ###

    # Obtain the setting from the original json file
    with open(json_file_path, "r") as json_file:
        settings = json.load(json_file)

    dg_settings = settings["dg_setup"]

    output_path = dg_settings["output_path"]
    output_filename = dg_settings["output_filename"]
    file_format = dg_settings["file_format"]

    os.makedirs(output_path, exist_ok=True)

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
        file_path_train_h5 = os.path.join(output_path, settings["deeponet_train_setup"]["training_data_dir"], f"src{i}", f"{output_filename}.h5")
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
                            "c": dg_settings["simulationSettings"]["dg_c0"],
                            "dt": results_dg["dt_old"].tolist(),
                            "fmax": dg_settings["simulationSettings"]["dg_freq_upper_limit"],
                            "rho": dg_settings["simulationSettings"]["dg_rho0"]
                        }
                    },
                    indent=4,
                )
            )

        # for now, use the same data for training and validation
        file_path_val_h5 = os.path.join(output_path, settings["deeponet_train_setup"]["testing_data_dir"], f"src{i}", f"{output_filename}.h5")
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
    inference(settings["deeponet_train_setup"], settings["deeponet_inference_setup"])
        

if __name__ == "__main__":
    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
        plot_dg_results
    )

    # Load the input file
    file_name = find_input_file_in_subfolders(  
        os.path.dirname(__file__), "exampleInput_deeponet_acoustics.json"
    )
    json_tmp_file = create_tmp_from_input(file_name)

    # Run the method
    deeponet_method(json_tmp_file)

    # Save the results to a separate file
    save_results(json_tmp_file)

    # Plot the results
    plot_dg_results(json_tmp_file)