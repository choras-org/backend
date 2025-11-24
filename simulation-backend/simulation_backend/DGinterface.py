# region Import Libraries
import os
from pathlib import Path
import numpy
import gmsh
import shutil

from acousticDE.FiniteVolumeMethod.CreateMeshFVM import generate_mesh

import json
import numpy as np
from math import log, sqrt, factorial, pow
import edg_acoustics
import pandas as pd

print(edg_acoustics.__file__)

# endregion


# Absorption term for boundary conditions
def abs_term(th, c0, abscoeff_list):
    Absx_array = np.array([])
    for abs_coeff in abscoeff_list:
        # print(abs_coeff)
        if th == 1:
            Absx = (c0 * abs_coeff) / 4  # Sabine
        elif th == 2:
            Absx = (c0 * (-log(1 - abs_coeff))) / 4  # Eyring
        elif th == 3:
            Absx = (c0 * abs_coeff) / (2 * (2 - abs_coeff))  # Modified by Xiang
        Absx_array = np.append(Absx_array, Absx)
    return Absx_array


def surface_materials(result_container, c0):
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

    # Initialize a list to store surface tags and their absorption coefficients
    surface_absorption = (
        []
    )  # initialization absorption term (alpha*surfaceofwall) for each wall of the room
    triangle_face_absorption = (
        []
    )  # initialization absorption term for each triangle face at the boundary and per each wall
    absorption_coefficient = {}

    materialNames = []
    for group in vGroupsNames:
        if group[0] != 2:
            continue
        name_group = group[2]
        name_split = name_group.split("$")
        name_abs_coeff = name_split[0]
        materialNames.append(name_abs_coeff)

        abscoeff = result_container["absorption_coefficients"][name_abs_coeff]

        abscoeff = abscoeff.split(",")

        if result_container:
            simulation_settings = result_container["simulationSettings"]

            # abscoeff = [float(i) for i in abscoeff][-1] #for one frequency
            abscoeff_list = [float(i) for i in abscoeff]  # for multiple frequencies

        physical_tag = group[1]  # Get the physical group tag
        entities = gmsh.model.getEntitiesForPhysicalGroup(
            2, physical_tag
        )  # Retrieve all the entities in this physical group (the entities are the number of walls in the physical group)

        Abs_term = abs_term(
            3, c0, abscoeff_list
        )  # calculates the absorption term based on the type of boundary condition th
        for entity in entities:
            absorption_coefficient[entity] = abscoeff_list
            surface_absorption.append(
                (entity, Abs_term)
            )  # absorption term (alpha*surfaceofwall) for each wall of the room
            surface_absorption = sorted(surface_absorption, key=lambda x: x[0])

    for entity, Abs_term in surface_absorption:
        triangle_faces, _ = gmsh.model.mesh.getElementsByType(
            2, entity
        )  # Get all the triangle faces for the current surface
        triangle_face_absorption.extend(
            [Abs_term] * len(triangle_faces)
        )  # Append the Abs_term value for each triangle face

    return (
        materialNames,
        absorption_coefficient,
        surface_absorption,
        triangle_face_absorption,
    )


def dg_method(json_file_path: str | Path, save_results_to_json: bool = True):
    """
    Run DG simulation for acoustic wave propagation.

    Args:
        json_file_path: Path to the JSON configuration file
        save_results_to_json: If True, saves impulse responses back to the JSON file.
                              If False, only creates the json file. Default is True for standalone use.
    """
    with open(json_file_path, "r") as json_file:
        result_container = json.load(json_file)

    # --------------------
    # Block 1: User input
    # --------------------
    simulation_settings = result_container["simulationSettings"]

    # TODO: should make a better solution for this that calls the dg_method function as if there was no deeponet
    called_from_deeponet = False
    if result_container["results"][0]["resultType"] == "DON":
        called_from_deeponet = True

    if called_from_deeponet:
        output_path = result_container["output_path"]
        output_results = result_container["output_filename"]
        file_format = result_container["file_format"]

        # clean up
        os.makedirs(output_path, exist_ok=True)
        Path(os.path.join(output_path, f"{output_results}.{file_format}")).unlink(missing_ok=True)
        Path(os.path.join(output_path, "results.json")).unlink(missing_ok=True)
        
    freq_upper_limit = simulation_settings["dg_freq_upper_limit"]

    mesh_filename = result_container["msh_path"]
    geo_filename = result_container["geo_path"]

    c0 = simulation_settings["dg_c0"]  # speed of sound in air
    rho0 = simulation_settings["dg_rho0"] # density of air in kg/m^3

      # total simulation time in seconds
    impulse_length = simulation_settings["dg_ir_length"]    

    CFL = simulation_settings.get("dg_cfl", 1)
    Nx = simulation_settings.get("dg_poly_order", 4)
    PPW = simulation_settings.get("dg_ppw", 2)
    minWavelength = c0 / freq_upper_limit

    # Eq. (26) in Wang, H., Sihar, I., Pagan Munoz, R., & Hornikx, M. (2019). 
    # Room acoustics modelling in the time-domain with the nodal discontinuous Galerkin method. 
    # Journal of the Acoustical Society of America, 145(4), 2650–2663.
    # https://doi.org/10.1121/1.5096154

    # Np is calculated using the equation in the text above Eq. (7):
    # Np = (Nx + d)!/(Nx!d!) where d is the number of dimensions, i.e., 3.
    # K/V in Eq. (26) is \approx 1/lc^3. Rewriting this results in the equation below:
    points_per_unit_length = factorial(Nx + 3)/(factorial(Nx)*6)
    lc = minWavelength / PPW * pow(points_per_unit_length, 1/3)
    print("lc = " + str(lc))
    generate_mesh(geo_filename, mesh_filename, lc)

    # FUNCTION CALLED HERE
    (
        materialNames,
        absorption_coefficient,
        surface_absorption,
        triangle_face_absorption,
    ) = surface_materials(result_container, c0)
    BC_labels = {}
    RIvals = {}
    i = 0
    for ac in absorption_coefficient:
        BC_labels[materialNames[i]] = ac

        # r = sqrt(1-a)
        RIvals[materialNames[i]] = sqrt(
            1 - sum(absorption_coefficient[ac]) / len(absorption_coefficient[ac])
        )

        i += 1

    real_valued_impedance_boundary = [
        # {"label": 11, "RI": 0.9}
    ]  # extra labels for real-valued impedance boundary condition, if needed. The label should be the similar to the label in BC_labels. Since it's frequency-independent, only "RI", the real-valued reflection coefficient, is required. If not needed, just clear the elements of this list and keep the empty list.

    monopole_xyz = numpy.array(
        [
            result_container["results"][0]["sourceX"],
            result_container["results"][0]["sourceY"],
            result_container["results"][0]["sourceZ"],
        ]
    )
    numrec = len(result_container["results"][0]["responses"])
    recx = numpy.zeros((1, numrec))
    recy = numpy.zeros((1, numrec))
    recz = numpy.zeros((1, numrec))
    for i in range(numrec):
        recx[0][i] = result_container["results"][0]["responses"][i]["x"]
        recy[0][i] = result_container["results"][0]["responses"][i]["y"]
        recz[0][i] = result_container["results"][0]["responses"][i]["z"]
    rec = numpy.vstack((recx, recy, recz))  # dim:[3,n_rec]

    save_every_Nstep = 10  # save thce results every N steps
    temporary_save_Nstep = 500  # save the results every N steps temporarily during the simulation. The temporary results will be saved in the root directory of this repo.

    # --------------------------------------------------------------------------------
    # Block 2: Initialize the simulation，run the simulation and save the results
    # --------------------------------------------------------------------------------

    # load Boundary conditions and parameters
    BC_para = []  # clear the BC_para list
    for uid, label in BC_labels.items():
        # if material == "hard wall":
        BC_para.append({"label": label, "RI": RIvals[uid]})
        # else:
        #     mat_files = glob.glob(f"/Users/SilvinW/repositories/backend/edg-acoustics/examples/scenario1/{material}*.mat")

        #     # if mat_files is empty, raise an error
        #     if not mat_files:
        #         raise FileNotFoundError(f"No .mat file found for material '{material}'")

        #     mat_file = scipy.io.loadmat(mat_files[0])

        #     material_dict = {"label": label}

        #     # Check if each variable exists in the .mat file and add it to the dictionary if it does
        #     if "RI" in mat_file:
        #         material_dict["RI"] = mat_file["RI"][0]
        #     else:
        #         material_dict["RI"] = 0

        #     if "AS" in mat_file and "lambdaS" in mat_file:
        #         material_dict["RP"] = numpy.array([mat_file["AS"][0], mat_file["lambdaS"][0]])  # type: ignore
        #     if "BS" in mat_file and "CS" in mat_file and "alphaS" in mat_file and "betaS" in mat_file:
        #         material_dict["CP"] = numpy.array(  # type: ignore
        #             [mat_file["BS"][0], mat_file["CS"][0], mat_file["alphaS"][0], mat_file["betaS"][0]]
        #         )

        #     BC_para.append(material_dict)
    BC_para += real_valued_impedance_boundary

    # mesh_data_folder is the current folder by default
    # mesh_data_folder = os.path.split(os.path.abspath(__file__))[0]
    # mesh_filename = os.path.join(mesh_data_folder, mesh_name)
    mesh = edg_acoustics.Mesh(mesh_filename, BC_labels)

    IC = edg_acoustics.Monopole_IC(monopole_xyz, freq_upper_limit)
    sim = edg_acoustics.AcousticsSimulation(rho0, c0, Nx, mesh, BC_labels)

    flux = edg_acoustics.UpwindFlux(rho0, c0, sim.n_xyz)
    AbBC = edg_acoustics.AbsorbBC(sim.BCnode, BC_para)

    sim.init_BC(AbBC)
    sim.init_IC(IC)
    sim.init_Flux(flux)
    sim.init_rec(
        rec, "brute_force"
    )  # brute_force or scipy(default) approach to locate the receiver points in the mesh

    if called_from_deeponet:
        # write initial conditition
        if file_format == "npz":
            ic_mesh = np.array([sim.xyz[0].flatten(), sim.xyz[0].flatten(), sim.xyz[0].flatten()])
            numpy.savez(
                os.path.join(output_path, output_results),
                IC_pressure=sim.P.flatten(),
                IC_mesh=ic_mesh,
                )
        else:
            raise NotImplementedError("file_format")

    tsi_time_integrator = edg_acoustics.TSI_TI(sim.RHS_operator, sim.dtscale, CFL, Nt=3)
    sim.init_TimeIntegrator(tsi_time_integrator)
    sim.time_integration(
        total_time=impulse_length,
        delta_step=save_every_Nstep,
        save_step=temporary_save_Nstep,
        format="mat",
        json_file_path=json_file_path,
    )

    results = edg_acoustics.Monopole_postprocessor(sim, 1)

    results.apply_correction()

    # Only save results back to JSON if in standalone mode
    if save_results_to_json:
        try:
            with open(json_file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            data["results"][0]["responses"][0]["receiverResults"] = results.IRnew[0:round(len(results.IRold[0]) * results.dt_old / results.dt_new)].tolist()
            for i in range(rec.shape[1]):
                data["results"][0]["responses"][i]["receiverResultsUncorrected"] = results.IRold[i].tolist()
            with open(json_file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)

        except Exception:
            print("Error saving the simulation solver settings")
            raise Exception("Error saving the simulation solver settings")

        df = pd.DataFrame()
        df["t"] = impulse_length * np.arange(0, len(data["results"][0]["responses"][0]["receiverResults"]))/len(data["results"][0]["responses"][0]["receiverResults"])
        df["pressure"] = data["results"][0]["responses"][0]["receiverResults"] 

        with open(
            json_file_path.replace(".json", "_pressure.csv"), "w", newline=""
        ) as pressure_result_csv:
            df.to_csv(pressure_result_csv, index=False)

    if called_from_deeponet:
        results.write_results(os.path.join(output_path, output_results), file_format, append=True)
    print("Finished!")


if __name__ == "__main__":
    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
        plot_dg_results
    )

    # Load the input file
    file_name = find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_DG.json"
    )
    json_tmp_file = create_tmp_from_input(file_name)

    # Run the method
    gmsh.initialize()
    dg_method(json_tmp_file)
    gmsh.finalize()

    # Save the results to a separate file
    save_results(json_tmp_file)

    # Plot the results
    plot_dg_results(json_tmp_file)
