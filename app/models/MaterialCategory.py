from datetime import datetime

from sqlalchemy import JSON

from app.db import db
from app.types import Setting, Status, ResourceType

class MaterialCategory(db.Model):
    __tablename__ = "material_categories"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(), nullable=False)
    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
