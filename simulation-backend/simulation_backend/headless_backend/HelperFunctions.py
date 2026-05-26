import os
import json
import matplotlib.pyplot as plt

def find_input_file_in_subfolders(
    dirname=os.path.dirname(__file__), file_name="exampleInput.json"
):
    """
    (Recursively) finds a given file name in subfolders of a given dirname.
    
    Parameters
    ----------
    dirname : str
        The directory to (recursively) search.

    filename : str
        The file to search.

    """

    for subdir, dirs, files in os.walk(dirname):
        for file in files:
            filepath = os.path.join(subdir, file)

            if filepath.endswith(file_name):
                print(f"{file_name} has been found")
                return filepath

    raise FileNotFoundError(f"{file_name} has NOT been found")


def create_tmp_from_input(json_input_file):
    """
    Creates a temporary json file by copying an input json file. The returned file is intended to be provided as an argument to a simulation method (interface) function, and will be filled with results.
    
    Parameters
    ----------
    json_input_file : str
        The json file to create a temporary copy of.

    Returns
    ------
    str
        The path to the temporary json file.
    """

    dirname = os.path.dirname(__file__)

    with open(json_input_file, "r") as json_input:
        data = json.load(json_input)

    # Make the relative geometry file path absolute
    data["geo_path"] = find_input_file_in_subfolders(dirname, data["geo_path"])
    
    # Generate .msh path from the .geo path
    data["msh_path"] = os.path.splitext(data["geo_path"])[0] + ".msh"

    # Prepare the output file by copying the input into it. We need a separate output file to not overwrite the input file
    json_tmp_file = os.path.join(dirname, "MeasurementRoomTmp.json")
    with open(json_tmp_file, "w") as json_output:
        json_output.write(json.dumps(data, indent=4))

    return json_tmp_file


def save_results(json_tmp_file):
    """Saves the contents of a json file to the output folder.

    Parameters
    ----------
    json_tmp_file : str
        The json file to save the contents of.

    """

    def get_unique_filename(base_name="results", extension="json", subfolder="output"):
        """
        Generate a unique filename inside a subfolder relative to this script.

        Parameters
        ----------
        base_name : str
            File name (excluding the extension).

        extension : str
            The file extension.

        subfolder : str
            The subfolder to check for the file(name)s.

        """
        # Get the folder where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Make sure subfolder exists
        folder_path = os.path.join(script_dir, subfolder)
        os.makedirs(folder_path, exist_ok=True)

        # Start with results.json
        filename = os.path.join(folder_path, f"{base_name}.{extension}")
        counter = 1
        while os.path.exists(filename):
            filename = os.path.join(folder_path, f"{base_name} ({counter}).{extension}")
            counter += 1
        return filename

    file_name = get_unique_filename()

    with open(json_tmp_file, "r") as j:
        data = json.load(j)

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"Data written to {file_name}")

def plot_dg_results(json_output):

    result_container = {}
    if json_output is not None:
        with open(json_output, "r") as json_file:
            result_container = json.load(json_file)
    plt.figure()

    if result_container["results"][0]["resultType"] == "DG" or result_container["results"][0]["resultType"] == "DON":
        for i in range(len(result_container["results"][0]["responses"])):
            plt.plot(result_container["results"][0]["responses"][i]["receiverResultsUncorrected"])
    elif result_container["results"][0]["resultType"] == "DE":
        for i in range(len(result_container["results"][0]["responses"][0]["receiverResults"])):
            plt.plot(result_container["results"][0]["responses"][0]["receiverResults"][i]["data"])
        
    plt.show()

def plot_results(json_output):

    result_container = {}
    if json_output is not None:
        with open(json_output, "r") as json_file:
            result_container = json.load(json_file)

    plt.figure()
    plt.plot(result_container["results"][0]["responses"][0]["receiverResults"][0]["data"])
    plt.show()