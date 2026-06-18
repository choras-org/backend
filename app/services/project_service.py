import logging
import os
import shutil
import uuid
import config
import rhino3dm
import json

from flask import jsonify
from flask_smorest import abort
from sqlalchemy import asc

from app.db import db
from app.models import Project, File
from config import app_dir
from app.services import simulation_service, file_service, model_service, geometry_service, mesh_service, material_service
from datetime import datetime

# Create logger for this module
logger = logging.getLogger(__name__)


def get_all_projects():
    return Project.query.order_by(asc(Project.createdAt)).all()


def get_all_projects_simulations():
    projects = get_all_projects()
    project_simulations = []
    for project in projects:
        for model in project.models:
            simulations = simulation_service.get_simulation_by_model_id(model.id)
            project_simulations.append(
                {
                    "simulations": simulations,
                    "modelId": model.id,
                    "modelName": model.name,
                    "modelCreatedAt": model.createdAt,
                    "projectId": project.id,
                    "projectName": project.name,
                    "group": project.group,
                }
            )

    return project_simulations


def create_new_project(project_data):
    new_project = Project(
        name=project_data["name"],
        group=project_data["group"].strip(),
        description=project_data["description"],
    )

    try:
        db.session.add(new_project)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new project: {ex}")
        abort(400, message=f"Can not create a new project: {ex}")

    return new_project


def get_project(project_id):
    results = Project.query.filter_by(id=project_id).first()
    return results


def update_project(project_id, project_data):
    project = Project.query.filter_by(id=project_id).first()
    if not project:
        logger.error("Project doesn't exist, cannot update!")
        abort(400, message="Project doesn't exist, cannot update!")

    try:
        project.name = project_data["name"]
        project.description = project_data["description"]
        project.group = project_data["group"].strip()
        project.updatedAt = datetime.now()
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return project


def delete_project(project_id):
    project = Project.query.filter_by(id=project_id).first()
    if not project:
        logger.error("Project doesn't exist, cannot delete!")
        abort(404, message="Project doesn't exist, cannot delete!")
    
    # Clean up image assets from associated models
    for model in project.models:
        if model.imagePath:
            image_path = model.imagePath
            if not os.path.isabs(image_path):
                image_path = os.path.join(config.basedir, image_path)
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as ex:
                logger.warning(f"Failed to remove image asset '{image_path}': {ex}")
    
    try:
        db.session.delete(project)
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting project!: {ex}")
        abort(500, message=f"Error deleting project!: {ex}")


def delete_project_by_group(group):
    projects = Project.query.filter_by(group=group).all()
    
    # Clean up image assets from all associated models
    for project in projects:
        for model in project.models:
            if model.imagePath:
                image_path = model.imagePath
                if not os.path.isabs(image_path):
                    image_path = os.path.join(config.basedir, image_path)
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as ex:
                    logger.warning(f"Failed to remove image asset '{image_path}': {ex}")
    
    try:
        Project.query.filter_by(group=group).delete()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting project groups!: {ex}")
        abort(500, message=f"Error deleting project groups!: {ex}")


def update_project_by_group(group, new_group):
    result = Project.query.filter_by(group=group).all()

    print(result)

    try:
        for project in result:
            project.group = new_group.strip()

        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return result


def create_example_projects():
    projects = get_all_projects()
    if len(projects):
        return

    logger.info("Inserting initial example projects")
    with open(os.path.join(app_dir, "models", "data", "example_projects.json")) as json_projects:
        example_projects = json.load(json_projects)
        try:
            for example_data in example_projects:
                # Step 1: Create group + project
                logger.info("Step 1: Create project")

                project_init = example_data["project"]
                project = create_new_project({
                    "name": project_init["name"],
                    "description": project_init["description"],
                    "group": project_init["group"],
                })

                # Step 2: Get upload slot
                logger.info("Step 2: Get upload slot")

                slot_data = file_service.get_slot()
                slot_id = slot_data["id"]

                # Step 3: Upload model file (copy example model to uploads folder)
                logger.info("Step 3: Upload model file")

                model_init = example_data["model"]
                example_model_path = os.path.join(config.basedir, model_init["directory"], model_init["fileName"])
                unique_name = f"MeasurementRoom_{uuid.uuid4().hex}.obj"
                dst_path = os.path.join(config.DefaultConfig.UPLOAD_FOLDER, unique_name)
                shutil.copy2(example_model_path, dst_path)

                file_record = File.query.filter_by(slot=slot_id).first()
                file_record.fileName = unique_name
                db.session.commit()
                file_upload_id = file_record.id

                # Step 4: Consume / delete slot
                logger.info("Step 4: Consume upload slot")

                file_service.consume(slot_id)

                # Step 5: Geometry check (synchronous)
                logger.info("Step 5: Geometry check")
                geometry = geometry_service.start_geometry_check_task(file_upload_id)
                source_file_id = geometry.outputModelId  # .3dm file created by geometry check

                # Step 6: Create model
                logger.info("Step 6: Create model")
                model = model_service.create_new_model({
                    "name": model_init["name"],
                    "projectId": project.id,
                    "sourceFileId": source_file_id,
                    "imagePath": model_init["imagePath"]
                })

                # Step 7: Create simulation
                logger.info("Step 7: Create simulation")

                simulation_init = example_data["simulation"]
                simulation = simulation_service.create_new_simulation({
                    "modelId": model.id,
                    "name": simulation_init["name"],
                    "description": simulation_init["description"],
                    "simulationMethod": simulation_init["simulationMethod"],
                    "layerIdByMaterialId": {},
                    "solverSettings": simulation_init["solverSettings"],
                    "sources": [],
                    "receivers": [],
                })

                # Step 8: Add source and receiver
                logger.info("Step 8: Add source and receiver")

                sources = []
                for source in simulation_init["sources"]:
                    sources.append(
                        {
                            "id": str(uuid.uuid4()),
                            "label": source["label"],
                            "orderNumber": source["orderNumber"],
                            "x": source["x"],
                            "y": source["y"],
                            "z": source["z"],
                            "isValid": True,
                        }
                    )
                
                receivers = []
                for receiver in simulation_init["receivers"]:
                    receivers.append(
                        {
                            "id": str(uuid.uuid4()),
                            "label": receiver["label"],
                            "orderNumber": receiver["orderNumber"],  # Fixed typo
                            "x": receiver["x"],                      # Fixed typo
                            "y": receiver["y"],
                            "z": receiver["z"],
                            "isValid": True,
                        }
                    )

                simulation_service.update_simulation_by_id(
                    {
                        "sources": sources,
                        "receivers": receivers,
                        "hasBeenEdited": True,
                    },
                    simulation.id,
                )

                # Step 9: Set materials — read material_name from 3DM mesh userStrings
                logger.info("Step 9: Set materials")

                material_init = example_data["material"]
                layer_map: dict = {}
                materials = material_service.get_all_materials()
                if materials:
                    target = next(
                        (m for m in materials if m.name == material_init["name"]),
                        materials[0],
                    )
                    material_id = target.id

                    tdm_file = file_service.get_file_by_id(source_file_id)
                    tdm_path = os.path.join(config.DefaultConfig.UPLOAD_FOLDER, tdm_file.fileName)
                    if os.path.exists(tdm_path):
                        model_3dm = rhino3dm.File3dm.Read(tdm_path)
                        for obj in model_3dm.Objects:
                            if isinstance(obj.Geometry, rhino3dm.Mesh):
                                stable_id = str(obj.Attributes.Id)
                                layer_map[stable_id] = material_id

                simulation_service.update_simulation_by_id(
                    {"layerIdByMaterialId": layer_map, "hasBeenEdited": True},
                    simulation.id,
                )

                # Step 10: Create mesh (synchronous)
                logger.info("Step 10: Create mesh")
                mesh_service.start_mesh_task(model.id)

                # Step 11: Run simulation
                logger.info("Step 11: Run simulation")
                simulation_service.start_solver_task(simulation.id)

                logger.info("Example project created successfully!")

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not insert initial projects! Error: {ex}")
            abort(400, f"Can not insert initial projects! Error: {ex}")

    return {"message": "Initial full projects successfully!"}