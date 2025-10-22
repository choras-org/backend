import logging
import os
import re

import gmsh
import rhino3dm
from acousticDE.FiniteVolumeMethod.CreateMeshFVM import generate_mesh
from flask_smorest import abort

import config
from app.db import db
from app.models import File, Mesh, Simulation, Task
from app.services import file_service, model_service
from app.types import Status, TaskType

from app.services.geometry_service import convert_3dm_to_geo

# Create logger for this module
logger = logging.getLogger(__name__)


def get_meshes_by_model_id(model_id):
    model = model_service.get_model(model_id)
    if model.mesh and (model.mesh.task.status == Status.Error):
        return []
    return [model.mesh] if model.mesh else []


def get_mesh_by_id(mesh_id):
    mesh = Mesh.query.filter_by(id=mesh_id).first()
    if not mesh:
        logger.error("Mesh with id " + str(mesh_id) + "does not exists!")
        abort(404, message="Mesh does not exist")
    return mesh


def attach_geo_file(model_id, file_input_id):
    model_Model = model_service.get_model(model_id)
    directory = config.DefaultConfig.UPLOAD_FOLDER
    geo_file = file_service.get_file_by_id(file_input_id)
    model_file = file_service.get_file_by_id(model_Model.outputFileId)
    file_name, file_extension = os.path.splitext(os.path.basename(model_file.fileName))
    file3dm = rhino3dm.File3dm()
    model = file3dm.Read(os.path.join(directory, model_file.fileName))

    rhino_file_name = os.path.join(directory, model_file.fileName)
    geo_file_name = os.path.join(directory, file_name) + ".geo"
    try:
        if not convert_3dm_to_geo(rhino_file_name, geo_file_name):
            logger.error("Can not generate a geo file")
            return False

        file_geo = File(fileName=f"{file_name}.geo")
        db.session.add(file_geo)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not attach a geo file: {ex}")
        return False

    try:
        model_Model.hasGeo = True
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not attach the geo file to the model! Error: {ex}")
        abort(400, message=f"Can not attach the geo file to the model! Error: {ex}")

    return {"status": True, "message": "geo file added to the model successfully!"}

    ## old code for importing .geo file
    # with open(os.path.join(directory, geo_file.fileName), "r") as file:
    #     geo_content = file.readlines()

    # # Create a mapping of material_name to obj.Attributes.Id
    # material_to_id = {}
    # for obj in model.Objects:
    #     if isinstance(obj.Geometry, rhino3dm.Mesh):
    #         material_name = obj.Geometry.GetUserString("material_name")
    #         if material_name:
    #             material_to_id[f"{obj.Attributes.Id}"] = material_name

    # # Reverse the mapping to be from material name to list of IDs
    # material_name_to_ids = {}
    # for id, material_name in material_to_id.items():
    #     if material_name not in material_name_to_ids:
    #         material_name_to_ids[material_name] = []
    #     material_name_to_ids[material_name].append(id)

    # def pop_and_update_braces(content):
    #     pattern = re.compile(r"{\s*(\d+(?:\s*,\s*\d+)*)\s*}")
    #     match = pattern.search(content)
    #     if match:
    #         numbers = match.group(1).split(",")
    #         numbers = [num.strip() for num in numbers]
    #         if numbers:
    #             return numbers
    #     return []

    # # Replace physical surface keys in the geo file content
    # new_geo_content = []
    # try:
    #     for line in geo_content:
    #         if line.strip().startswith("Physical Surface"):
    #             parts = line.split('"')
    #             if len(parts) > 1:
    #                 material_name = parts[1].strip()
    #                 if material_name in material_name_to_ids:
    #                     ids = material_name_to_ids[material_name]
    #                     numbers = pop_and_update_braces(line)
    #                     for i, number in enumerate(numbers):
    #                         new_geo_content.append(f'Physical Surface("{ids.pop(0)}") = {{ {number} }};\n')
    #                 else:
    #                     return {
    #                         "status": False,
    #                         "message": f"Mismatch between name of the material and the boundary name {material_name}",
    #                     }
    #                     new_geo_content.append(line)
    #             else:
    #                 new_geo_content.append(line)
    #         else:
    #             new_geo_content.append(line)
    # except Exception as ex:
    #     print(f"Geo import error: {ex}")
    #     return {
    #         "status": False,
    #         "message": f"Geo import error: {ex}",
    #     }

    # with open(os.path.join(directory, f"{file_name}.geo"), "w") as file:
    #     file.writelines(new_geo_content)

    # try:
    #     model_Model.hasGeo = True
    #     db.session.commit()
    # except Exception as ex:
    #     db.session.rollback()
    #     logger.error(f"Can not attach the geo file to the model! Error: {ex}")
    #     abort(400, message=f"Can not attach the geo file to the model! Error: {ex}")

    # return {"status": True, "message": "geo file added to the model successfully!"}


gmsh.initialize()


def start_mesh_task(model_id):
    model_db = model_service.get_model(model_id)
    file = file_service.get_file_by_id(model_db.outputFileId)

    directory = config.DefaultConfig.UPLOAD_FOLDER
    file_name, file_extension = os.path.splitext(os.path.basename(file.fileName))
    geo_path = os.path.join(directory, f"{file_name}.geo")
    msh_path = os.path.join(directory, f"{file_name}.msh")
    try:
        if model_db.meshId:
            Mesh.query.filter_by(id=model_db.meshId).delete()
        task = Task(
            taskType=TaskType.Mesh,
        )
        db.session.add(task)
        db.session.commit()
        mesh = Mesh(taskId=task.id)

        db.session.add(mesh)
        db.session.commit()
        model_db.meshId = mesh.id
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error in mesh generation (db)! Error: {ex}")
        abort(400, message=f"Error in mesh generation (db)! Error: {ex}")

    try:
        generate_mesh(geo_path, msh_path, 1)
    except Exception as ex:
        logger.error(f"Error in mesh generation (msh)! Error: {ex}")
        abort(400, message=f"Error in mesh generation (msh)! Error: {ex}")

    if os.path.exists(msh_path):
        try:
            task.status = Status.Completed
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            logger.error(f"Error in mesh generation (db)! Error: {ex}")
            abort(400, message=f"Error in mesh generation (db)! Error: {ex}")
    else:
        try:
            task.status = Status.Error
            message = "Possibly you don't have Gmsh installed on your device,"
            message += "or Gmsh has not been initialized!"
            task.message = message
            logger.error("Someone is trying to create mesh but they can't!")
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            logger.error(f"Error in mesh generation (db)! Error: {ex}")
            abort(400, message=f"Error in mesh generation (db)! Error: {ex}")

    return mesh
