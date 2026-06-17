import json
import logging
import os

from flask_smorest import abort
from sqlalchemy import asc

from app.db import db
from app.models import UserPreference
from config import app_dir
from datetime import datetime

# Create logger for this module
logger = logging.getLogger(__name__)


def get_all_user_preferences():
    return UserPreference.query.order_by(asc(UserPreference.id)).all()


def create_new_user_preference(user_preference_data):
    new_user_preference = UserPreference(**user_preference_data)

    try:
        db.session.add(new_user_preference)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new user preference: {ex}")
        abort(400, f"Can not create a new user preference: {ex}")

    return new_user_preference

def update_user_preference(user_preference_id, user_preference_data):
    user_preference = UserPreference.query.filter_by(id=user_preference_id).first()
    if not user_preference:
        abort(404, message="User preference doesn't exist, cannot update!")

    try:
        user_preference.settings = user_preference_data["settings"]
        user_preference.updatedAt = datetime.now()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return user_preference


def get_user_preference_by_id(user_preference_id):
    user_preference = UserPreference.query.filter_by(id=user_preference_id).first()
    if not user_preference:
        logger.error("User preference with id " + str(user_preference_id) + " does not exists!")
        abort(400, "User preference doesn't exists!")
    return user_preference


def insert_initial_user_preferences():
    user_preferences = get_all_user_preferences()
    if len(user_preferences):
        return
    logger.info("Inserting initial user preferences")
    with open(os.path.join(app_dir, "models", "data", "user_preferences.json")) as json_user_preferences:
        initial_user_preferences = json.load(json_user_preferences)
        try:
            new_user_preferences = []
            for user_preference in initial_user_preferences:
                new_user_preferences.append(
                    UserPreference(
                        settings=user_preference["settings"],
                    )
                )

            db.session.add_all(new_user_preferences)
            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not insert initial user preferences! Error: {ex}")
            abort(400, f"Can not insert initial user preferences! Error: {ex}")

    return {"message": "Initial user preferences added successfully!"}
