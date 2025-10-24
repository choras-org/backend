"""Module implementing a CHORAS interface for pyroomacoustics.
"""
import pyroomacoustics as pra
import gmsh
import numpy as np
import warnings


def read_json_input(json_file_path):
    """Read the input JSON file.

    Parameters
    ----------
    json_file_path : str
        Path of the input JSON file

    Returns
    -------
    input_data : dict
        Parsed JSON data as a dictionary

    """
    with open(json_file_path, 'r') as f:
        import json
        input_data = json.load(f)

    return input_data


def import_room_geometry(json_file_path):
    """Import room geometry and absorption coefficients.

    The geometry is read from a .geo file specified in the JSON input file.
    The absorption coefficients are directly read from the JSON file.

    Parameters
    ----------
    json_file_path : str
        Path to the JSON file containing room geometry and absorption
        coefficients.

    Returns
    -------
    walls : list of pyroomacoustics.Wall
        List of walls defining the room geometry and boundary conditions for
        all frequency bands.

    Raises
    ------
    ValueError
        If absorption coefficients for any surface are not found in the
        input JSON file.
    """

    with open(json_file_path, 'r') as f:
        import json
        input_data = json.load(f)

    frequencies = input_data['frequencies']
    n_bands = len(frequencies)

    # initialize gmsh and load the geometry file
    gmsh.initialize()
    geometry_file = input_data['geo_path']
    gmsh.open(geometry_file)

    # generate 2d surface mesh
    dim = 2 # 2D surfaces
    gmsh.model.mesh.generate(dim)

    # get all named surfaces in the geometry
    surface_group_tags = gmsh.model.getPhysicalGroups(dim=dim)
    surface_group_names = [
        gmsh.model.getPhysicalName(dim, tag)
        for (dim, tag) in surface_group_tags
    ]

    # get all nodes of the surface mesh
    node_tags_all, coords_all, _ = gmsh.model.mesh.getNodes()
    coords = coords_all.reshape((len(node_tags_all), 3))

    # get the material names from absorption coefficient input
    absorption_names = list(input_data['absorption_coefficients'].keys())

    # check if absorption coefficient data are available for all surfaces
    for name in surface_group_names:
        if name not in absorption_names:
            raise ValueError(
                "Absorption coefficients for surface "
                f"'{name}' not found in input JSON file.")


    # get the element type for surface mesh
    element_type = gmsh.model.mesh.getElementType("triangle", 1)

    # create pyroomacoustics.walls for all surface elements (triangles)
    walls = []

    # loop through all named surfaces and create walls with corresponding
    # absorption and scattering coefficients

    for surface_name in surface_group_names:
        dim_tags = gmsh.model.getEntitiesForPhysicalName(surface_name)
        dim, tag = dim_tags[0]

        face_nodes = gmsh.model.mesh.getElementFaceNodes(
            element_type, 3, tag=tag)
        faces = np.reshape(face_nodes, (len(face_nodes) // 3, 3))

        material = pra.Material(
            energy_absorption={
                'description': surface_name,
                'center_freqs': input_data['frequencies'],
                'coeffs': input_data['absorption_coefficients'][surface_name],
            }
        )

        walls.extend(
            pra.wall_factory(
                coords[face - 1, :].reshape(-1, 3).T,
                absorption=material.energy_absorption['coeffs'],
                scattering=material.scattering['coeffs'],
            )
            for face in faces
        )

    # finalizing gmsh
    gmsh.finalize()

    return walls


def get_source_positions(input_data):
    """Extract source positions from input data.

    Parameters
    ----------
    input_data : dict
        Input data as a dictionary.

    Returns
    -------
    source_positions : np.ndarray
        Array of source positions with shape (3,).
    """
    return np.array([
        input_data['results'][0]['sourceX'],
        input_data['results'][0]['sourceY'],
        input_data['results'][0]['sourceZ'],
    ])


def get_receiver_positions(input_data):
    """Extract receiver positions from input data.

    Parameters
    ----------
    input_data : dict
        Input data as a dictionary.

    Returns
    -------
    receiver_positions : np.ndarray
        Array of receiver positions with shape (n_receivers, 3).
    """

    num_receivers = len(input_data['results'][0]['responses'])

    response_section = input_data['results'][0]['responses']

    receiver_pos = np.zeros((num_receivers, 3), dtype=float)

    for i in range(num_receivers):
        receiver_pos[i] = np.array([
            response_section[i]['x'],
            response_section[i]['y'],
            response_section[i]['z']
        ])

    return receiver_pos


def set_default_simulation_settings(input_data):
    """Set default simulation settings if not provided in input data.

    Parameters
    ----------
    input_data : dict
        Input data as a dictionary.

    """
    if 'simulationSettings' not in input_data:
        input_data['simulationSettings'] = {}

    settings = input_data['simulationSettings']

    if 'image_source_order' not in settings:
        settings['image_source_order'] = 2
        warnings.warn(
            "Image source order not specified. "
            "Defaulting to 2nd order reflections.",
            stacklevel=2
        )

    if 'sampling_rate' not in settings:
        settings['sampling_rate'] = 20000
        warnings.warn(
            "Sampling rate not specified. "
            "Defaulting to 20000 Hz.",
            stacklevel=2
        )

    if 'ray_tracing' not in settings:
        settings['ray_tracing'] = True
        warnings.warn(
            "Ray tracing setting not specified. "
            "Defaulting to True.",
            stacklevel=2
        )

    if 'air_absorption' not in settings:
        settings['air_absorption'] = True
        warnings.warn(
            "Air absorption setting not specified. "
            "Defaulting to True.",
            stacklevel=2
        )

    return input_data


def setup_simulation(json_file_path, walls):
    """Set up the pyroomacoustics simulation based on the JSON file.

    Parameters
    ----------
    json_file_path : str
        Path of the input JSON file
    walls : list of pyroomacoustics.Wall
        List of walls defining the room geometry and boundary conditions

    Returns
    -------
    room : pyroomacoustics.Room
        The configured pyroomacoustics Room object
    """

    print("setup_simulation: setting up simulation")


    input_data = read_json_input(json_file_path)
    extended_input_data = set_default_simulation_settings(input_data)

    sampling_rate = extended_input_data['simulationSettings'].get('sampling_rate')
    image_source_order = extended_input_data['simulationSettings'].get('image_source_order')
    ray_tracing = extended_input_data['simulationSettings'].get('ray_tracing')
    air_absorption = extended_input_data['simulationSettings'].get('air_absorption')

    room = pra.Room(
        walls,
        fs=sampling_rate,
        max_order=image_source_order,
        ray_tracing=ray_tracing,
        air_absorption=air_absorption,
    )

    # Add sources
    source_pos = get_source_positions(input_data)
    if source_pos.shape != (3,):
        raise ValueError("Source position must be a 3D coordinate.")
    room.add_source(source_pos)

    receiver_pos = get_receiver_positions(input_data)
    room.add_microphone(receiver_pos.T)

    print("setup_simulation: setup done!")

    return room


def export_rir_to_input(json_file_path, rir):
    """Export the computed RIRs to the input data structure.

    Parameters
    ----------
    input_data : dict
        Input data as a dictionary.
    rir : list of list of np.ndarray
        Computed RIRs from pyroomacoustics.

    Returns
    -------
    None
    """

    with open(json_file_path, 'r') as f:
        import json
        input_data = json.load(f)

    # num_receivers = len(input_data['results'][0]['responses'])

    # for i in range(num_receivers):
    input_data['results'][0]['responses'][0]['receiverResults'] = rir.tolist()

    with open(json_file_path, 'w') as f:
        json.dump(input_data, f, indent=4)


def pyroomacoustics_method(json_file_path=None):
    """Run the simulation method for pyroomacoustics based on the JSON file.

    Parameters
    ----------
    json_file_path : str, optional
        Path of the input JSON file, by default None
    """

    print("pyroomacoustics_method: starting simulation")

    walls = import_room_geometry(json_file_path)

    simulation_setup = setup_simulation(json_file_path, walls)

    # Compute the RIRs
    simulation_setup.compute_rir()

    # Get the RIRs for the first source and first microphone
    rir = simulation_setup.rir[0][0]

    # Export the RIRs to the input data structure
    export_rir_to_input(json_file_path, rir)

    print("pyroomacoustics_method: simulation done!")


if __name__ == "__main__":
    import os
    import simulation_backend

    # Load the input file
    file_name = simulation_backend.find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_pyroomacoustics.json"
    )
    json_tmp_file = simulation_backend.create_tmp_from_input(file_name)

    # Run the method
    print(f"Created temporary settings file: {json_tmp_file}")
    pyroomacoustics_method(json_tmp_file)

    # Save the results to a separate file
    simulation_backend.save_results(json_tmp_file)

    # Plot results
    simulation_backend.plot_results(json_tmp_file)
