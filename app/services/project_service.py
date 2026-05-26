import logging

from flask import jsonify
from flask_smorest import abort
from sqlalchemy import asc

from app.db import db
from app.models import Project
from app.services import simulation_service

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
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return project


def delete_project(project_id):
    try:
        Project.query.filter_by(id=project_id).delete()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting project!: {ex}")
        abort(500, message=f"Error deleting project!: {ex}")


def delete_project_by_group(group):
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
