import json
import os
import pandas as pd

from acousticDE.FiniteVolumeMethod.FVM import run_fvm_sim

def de_method(json_file_path=None):
    result_container = {}
    if json_file_path is not None:
        with open(json_file_path, "r") as json_file:
            result_container = json.load(json_file)

    dirname = os.path.dirname(__file__)

    # Prepare the output file by copying the input into it. We need a separate output file to not overwrite the input file
    json_tmp_file = os.path.join(dirname, "tmp_DEinputs.json")

    data = {}

    ## Prepare json input data for run_fvm_sim from the json input data

    # Source coordinates
    data["coord_source"] = [
        result_container["results"][0]["sourceX"],
        result_container["results"][0]["sourceY"],
        result_container["results"][0]["sourceZ"],
    ]

    # Receiver coordinates 
    data["coord_rec"] = [
        result_container["results"][0]["responses"][0]["x"],
        result_container["results"][0]["responses"][0]["y"],
        result_container["results"][0]["responses"][0]["z"],
    ]

    # Frequency bands
    freqs = result_container["results"][0]["frequencies"]
    data["fc_low"] = freqs[0]
    data["fc_high"] = freqs[-1]

    # Absorption coefficients (create csv necessary for run_fvm_sim)
    csv_path = os.path.join(os.path.dirname(json_file_path), "absorption_coefficients.csv")

    surface_names = []
    for key, value in result_container["absorption_coefficients"].items():
        surface_names.append(key)

    column_names = ["Material"] + [f"{int(fc)}Hz" for fc in freqs]

    # Convert JSON dict to dataframe
    records = []
    for material, coeffs in result_container["absorption_coefficients"].items():
        coeff_list = [float(c.strip()) for c in coeffs.split(",")]
        records.append([material] + coeff_list)

    df = pd.DataFrame(records, columns=column_names)

    # Save dataframe to CSV
    df.to_csv(csv_path, index=False)

    # Octave bands? (Ask Ilaria)
    data["num_octave"] = 1

    # Time step
    data["dt"] = 1 / 20000

    # Air absorption coefficient
    data["m_atm"] = 0

    # Absorption condition (options Sabine (th=1), Eyring (th=2) and modified by Xiang (th=3))
    data["th"] = 3

    # Write the data to the json file
    with open(json_tmp_file, "w") as json_output:
        json_output.write(json.dumps(data, indent=4))

    # Run the simulation and obtain the results
    results = run_fvm_sim(
        result_container["msh_path"], json_tmp_file, csv_path
    )
    print("Done!")

    ## Write the results to the correct locations in the result container

    # No T20? (Ask Ilaria)
    result_container["results"][0]["responses"][0]["parameters"]["t20"] = results[
        "t30_band"
    ].tolist()
    result_container["results"][0]["responses"][0]["parameters"]["t30"] = results[
        "t30_band"
    ].tolist()
    result_container["results"][0]["responses"][0]["parameters"]["c80"] = results[
        "c80_band"
    ].tolist()
    result_container["results"][0]["responses"][0]["parameters"]["d50"] = results[
        "d50_band"
    ].tolist()
    result_container["results"][0]["responses"][0]["parameters"]["ts"] = results[
        "ts_band"
    ].tolist()
    # No spl_r_t0_band (or spl_t0_freq)? (ask Ilaria)

    for i in range(len(freqs)):
        result_container["results"][0]["responses"][0]["receiverResults"].append(
            {
                "data": results["spl_r_off_band"][i].tolist(),
                "t": results["t"].tolist(),
                "frequency": result_container["results"][0]["frequencies"][i],
                "type": "edc",
            }
        )

    # Write results to the json file
    try:
        with open(json_file_path, "w", encoding="utf-8") as file:
            json.dump(result_container, file, indent=4)

    except Exception as e:
        raise Exception("Error saving the simulation solver settings:") from e


if __name__ == "__main__":
    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
        plot_results,
    )

    # Load the input file
    json_file_name = find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_DE.json"
    )

    json_tmp_file = create_tmp_from_input(json_file_name)

    # Run the method
    de_method(json_tmp_file)

    # Save the results to a separate file
    save_results(json_tmp_file)

    # Plot the results
    plot_results(json_tmp_file)
