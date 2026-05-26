import logging

from flask_smorest import abort

from app.db import db
from app.models import Model
from config import FeatureToggle

# Create logger for this module
logger = logging.getLogger(__name__)


def create_new_model(model_data):
    new_model = Model(
        name=model_data["name"],
        projectId=model_data["projectId"],
        sourceFileId=model_data["sourceFileId"],
        outputFileId=model_data["sourceFileId"],
    )

    if FeatureToggle.is_enabled("enable_geo_conversion"):
        new_model.hasGeo = True

    try:
        db.session.add(new_model)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new model: {ex}")
        abort(400, f"Can not create a new model: {ex}")

    return new_model


def get_model(model_id):
    model = Model.query.filter_by(id=model_id).first()
    if not model:
        logger.error("Model with id " + str(model_id) + "does not exists!")
        abort(404, "Model does not exist")
    return model


def update_model(model_id, model_data):
    model = Model.query.filter_by(id=model_id).first()
    if not model:
        logger.error("Model doesn't exist, cannot update!")
        abort(400, "Model doesn't exist, cannot update!")

    try:
        model.name = model_data["name"]
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return model


def delete_model(model_id):
    try:
        Model.query.filter_by(id=model_id).delete()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting the model!: {ex}")
        abort(500, f"Error deleting the model!: {ex}")
