# region Import Libraries
import os
import glob
import numpy
import scipy.io
import gmsh
import shutil

from acousticDE.FiniteVolumeMethod.CreateMeshFVM import generate_mesh

import json

import numpy as np
from math import log, sqrt

import importlib
import edg_acoustics

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
            if simulation_settings["dg_absorption_override"] == "yes":
                abscoeff_list = [1 - simulation_settings["dg_R"] ** 2] * len(abscoeff)
            else:
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


def dg_method(json_file_path=None):

    result_container = {}
    if json_file_path is not None:
        with open(json_file_path, "r") as json_file:
            result_container = json.load(json_file)

    # --------------------
    # Block 1: User input
    # --------------------
    rho0 = 1.213  # density of air at 20 degrees Celsius in kg/m^3

    if result_container:
        simulation_settings = result_container["simulationSettings"]
        freq_upper_limit = simulation_settings["freq_upper_limit"]

        mesh_filename = result_container["msh_path"]
        geo_filename = result_container["geo_path"]

        c0 = simulation_settings["dg_c0"]  # speed of sound in air

        uploads_folder = os.path.dirname(mesh_filename)  ## directory of file

        PPW = 2
        minWavelength = c0 / freq_upper_limit

        print("lc = " + str(minWavelength / PPW))
        generate_mesh(geo_filename, mesh_filename, minWavelength / PPW)

        test = gmsh.open(mesh_filename)

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

    else:
        mesh_filename = "/Users/SilvinW/repositories/backend/edg-acoustics/examples/scenario1/scenario1_coarser.msh"

        BC_labels = {
            "hard wall": 11,
            "carpet": 13,
            "panel": 14,
        }

    real_valued_impedance_boundary = [
        # {"label": 11, "RI": 0.9}
    ]  # extra labels for real-valued impedance boundary condition, if needed. The label should be the similar to the label in BC_labels. Since it's frequency-independent, only "RI", the real-valued reflection coefficient, is required. If not needed, just clear the elements of this list and keep the empty list.

    # Approximation degrees
    Nx = 4  # in space
    Nt = 4  # in time

    if result_container:
        # Obtain parameters from front end
        CFL = 1
        impulse_length = simulation_settings[
            "dg_ir_length"
        ]  # total simulation time in seconds

        monopole_xyz = numpy.array(
            [
                result_container["results"][0]["sourceX"],
                result_container["results"][0]["sourceY"],
                result_container["results"][0]["sourceZ"],
            ]
        )
        recx = numpy.array([result_container["results"][0]["responses"][0]["x"]])
        recy = numpy.array([result_container["results"][0]["responses"][0]["y"]])
        recz = numpy.array([result_container["results"][0]["responses"][0]["z"]])
        rec = numpy.vstack((recx, recy, recz))  # dim:[3,n_rec]

    else:
        CFL = 0.5  # CFL number, default is 0.5.
        c0 = 343  # speed of sound in air at 20 degrees Celsius in m/s

        freq_upper_limit = 200  # upper limit of the frequency content of the source signal in Hz. The source signal is a Gaussian pulse with a frequency content up to this limit.

        impulse_length = 0.1  # total simulation time in seconds

        monopole_xyz = numpy.array(
            [3.04, 2.59, 1.62]
        )  # x,y,z coordinate of the source in the room

        recx = numpy.array([4.26])
        recy = numpy.array([1.76])
        recz = numpy.array([1.62])
        rec = numpy.vstack((recx, recy, recz))  # dim:[3,n_rec]

    save_every_Nstep = 10  # save thce results every N steps
    temporary_save_Nstep = 500  # save the results every N steps temporarily during the simulation. The temporary results will be saved in the root directory of this repo.

    result_filename = "result"  # name of the result file. The result file will be saved in the same folder as this script. The result file will be saved in .mat format.

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

    if result_container:
        try:
            with open(json_file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            data["results"][0]["responses"][0]["receiverResults"] = results.IRnew.tolist()
            data["results"][0]["responses"][0]["receiverResultsUncorrected"] = results.IRold.tolist()[0]
            with open(json_file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)

        except Exception:
            print("Error saving the simulation solver settings")
            raise Exception("Error saving the simulation solver settings")
    # if result_container:
    #     result_container['results'][0]['responses'][0]['IR']['IR_Uncorrected'] = results.IRold

    result_filename = os.path.join(uploads_folder, result_filename)
    results.write_results(result_filename, "mat")

    # load newresult.npy
    # data = numpy.load("./examples/newresult.npz", allow_pickle=True)
    # tempdata = numpy.load("./results_on_the_run.npz", allow_pickle=True)
    print("Finished!")


if __name__ == "__main__":
    from simulation_backend import (
        find_input_file_in_subfolders,
        create_tmp_from_input,
        save_results,
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
