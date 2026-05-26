import json
import logging
import os

from flask import abort
from sqlalchemy import asc

from app.db import db
from app.models import Material
from config import app_dir

# Create logger for this module
logger = logging.getLogger(__name__)


def get_all_materials():
    return Material.query.order_by(asc(Material.id)).all()


def create_new_material(material_data):
    new_material = Material(**material_data)

    try:
        db.session.add(new_material)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new material: {ex}")
        abort(400, f"Can not create a new material: {ex}")

    return new_material


def get_material_by_id(material_id):
    material = Material.query.filter_by(id=material_id).first()
    if not material:
        logger.error("Material with id " + str(material_id) + " does not exists!")
        abort(400, "Material doesn't exists!")
    return material


def insert_initial_materials():
    materials = get_all_materials()
    if len(materials):
        return
    logger.info("Inserting initial materials")
    with open(os.path.join(app_dir, "models", "data", "materials.json")) as json_materials:
        initial_materials = json.load(json_materials)
        try:
            new_materials = []
            for material in initial_materials:
                new_materials.append(
                    Material(
                        name=material["name"],
                        description=material["description"],
                        category=material["category"],
                        absorptionCoefficients=material["absorptionCoefficients"],
                    )
                )

            db.session.add_all(new_materials)
            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not insert initial materials! Error: {ex}")
            abort(400, f"Can not insert initial materials! Error: {ex}")

    return {"message": "Initial materials added successfully!"}
