# This is the example interface file for connecting CHORAS to your simulation method

# Import the relevant functions from your package (/submodule)
from My_New_Method import simulation_method


# This function will be called from app/services/simulation_service.py 
# and the main function below
def mynewmethod_method(json_file_path=None):

    print("mynewmethod_method: starting simulation")

    # Call the appropriate function(s) in your package to simulate
    simulation_method(json_file_path)

    print("mynewmethod_method: simulation done!")


if __name__ == "__main__":
    import os

    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
    )

    # Load the input file
    file_name = find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_MyNewMethod.json"
    )
    json_tmp_file = create_tmp_from_input(file_name)

    # Run the method
    mynewmethod_method(json_tmp_file)

    # Save the results to a separate file
    save_results(json_tmp_file)
