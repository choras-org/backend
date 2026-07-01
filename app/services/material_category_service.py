# app/services/material_category_service.py

import json
import logging
import os

from flask_smorest import abort
from sqlalchemy import asc

from app.db import db
from app.models import MaterialCategory 
from config import app_dir
from datetime import datetime

logger = logging.getLogger(__name__)

def get_all_material_categories():
    return MaterialCategory.query.order_by(asc(MaterialCategory.id)).all()

def create_new_material_category(material_category_data):
    new_material_category = MaterialCategory(**material_category_data)
    try:
        db.session.add(new_material_category)
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new material category: {ex}")
        abort(400, f"Can not create a new material category: {ex}")
    return new_material_category

def update_material_category(material_category_id, material_category_data):
    material_category = MaterialCategory.query.filter_by(id=material_category_id).first()
    if not material_category:
        abort(404, message="Material category doesn't exist, cannot update!")

    try:
        material_category.name = material_category_data["name"]
        material_category.updatedAt = datetime.now()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return material_category

def get_material_category_by_id(material_category_id):
    material_category = MaterialCategory.query.filter_by(id=material_category_id).first()
    if not material_category:
        logger.error("Material category with id " + str(material_category_id) + " does not exists!")
        abort(400, "Material category doesn't exists!")
    return material_category

def get_material_category_by_name(material_category_name):
    material_category = MaterialCategory.query.filter_by(name=material_category_name).first()
    if not material_category:
        logger.error("Material category with name " + str(material_category_name) + " does not exists!")
        abort(400, "Material category doesn't exists!")
    return material_category

def insert_initial_material_categories():
    material_categories = get_all_material_categories()
    if len(material_categories):
        return
    logger.info("Inserting initial material categories")
    with open(os.path.join(app_dir, "models", "data", "material_categories.json")) as json_material_categories:
        initial_material_categories = json.load(json_material_categories)
        try:
            new_material_categories = []
            for material_category in initial_material_categories:
                new_material_categories.append(
                    MaterialCategory( # DIUBAH: Material -> MaterialCategory
                        name=material_category["name"],
                    )
                )
            db.session.add_all(new_material_categories)
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not insert initial material categories! Error: {ex}")
            abort(400, f"Can not insert initial material categories! Error: {ex}")

    return {"message": "Initial material categories added successfully!"}