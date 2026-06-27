from datetime import datetime

from sqlalchemy import JSON

from app.db import db
from app.types import Setting, Status, ResourceType

class UserPreference(db.Model):
    """
    Represents the database model for storing user-specific configurations.

    Attributes
    ----------
    id : int
        The primary key for the preference record. Automatically incremented.
    settings : dict
        A JSON object containing various configuration settings for the user.
    createdAt : str
        The timestamp indicating when the preference record was created.
    updatedAt : str
        The timestamp indicating when the preference record was last updated.
    """
    __tablename__ = "user_preferences"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    settings = db.Column(JSON, nullable=False)
    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())