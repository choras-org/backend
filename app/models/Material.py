from datetime import datetime

from sqlalchemy import JSON

from app.db import db


class Material(db.Model):
    __tablename__ = "materials"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(), nullable=False)
    description = db.Column(db.String(), nullable=True)
    category = db.Column(db.String(80), nullable=False)
    absorptionCoefficients = db.Column(JSON, nullable=False)
    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
