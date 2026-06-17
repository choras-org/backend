from datetime import datetime

from sqlalchemy import JSON

from app.db import db
from app.types import Setting, Status, ResourceType

class UserPreference(db.Model):
    __tablename__ = "user_preferences"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    settings = db.Column(JSON, nullable=False)
    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
