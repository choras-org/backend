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
    """
    Retrieve all user preference records from the database ordered by ID.

    Returns
    -------
    list of UserPreference
        A list of all user preference database model objects ordered ascending by ID.
    """
    return UserPreference.query.order_by(asc(UserPreference.id)).all()


def create_new_user_preference(user_preference_data):
    """
    Create and persist a new user preference record in the database.

    Parameters
    ----------
    user_preference_data : dict
        A dictionary containing the field values required to instantiate 
        a new UserPreference model instance.

    Returns
    -------
    UserPreference
        The newly created and committed UserPreference database object.

    Raises
    ------
    HTTPException
        Aborts with a 400 status code if a database transaction error occurs.
    """
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
    """
    Update the settings and timestamp of an existing user preference record.

    Parameters
    ----------
    user_preference_id : int
        The unique identifier of the user preference record to update.
    user_preference_data : dict
        A dictionary containing the updated configuration data, specifically 
        expecting a "settings" key.

    Returns
    -------
    UserPreference
        The updated and committed UserPreference database object.

    Raises
    ------
    HTTPException
        Aborts with a 404 status code if the record is not found, or a 400 
        status code if a database transaction error occurs.
    """
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
    """
    Retrieve a specific user preference record by its unique ID.

    Parameters
    ----------
    user_preference_id : int
        The unique identifier of the user preference record to fetch.

    Returns
    -------
    UserPreference
        The matching UserPreference database object.

    Raises
    ------
    HTTPException
        Aborts with a 400 status code if no record matches the given ID.
    """
    user_preference = UserPreference.query.filter_by(id=user_preference_id).first()
    if not user_preference:
        logger.error("User preference with id " + str(user_preference_id) + " does not exists!")
        abort(400, "User preference doesn't exists!")
    return user_preference


def insert_initial_user_preferences():
    """
    Seed the database with initial user preference data from a JSON file.

    If any records already exist in the user preferences table, the seeding 
    process is skipped entirely to prevent duplication.

    Returns
    -------
    dict or None
        A success message dictionary if initialization is performed, 
        or None if skipped.

    Raises
    ------
    HTTPException
        Aborts with a 400 status code if a database or file system error occurs.
    """
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
    