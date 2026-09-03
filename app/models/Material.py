from datetime import datetime

from sqlalchemy import JSON

from app.db import db


class Material(db.Model):
    """SQLAlchemy model representing an acoustic material.

    Attributes
    ----------
    id : int
        Primary key, auto-incremented.
    name : str
        Name of the material. Cannot be null.
    description : str or None
        Optional description of the material.
    categoryId : int
        Foreign key referencing ``material_categories.id``. Cascades on delete.
    absorptionCoefficients : dict
        JSON object storing absorption coefficient values. Cannot be null.
    origin : str
        Source of the material record; defaults to ``"user"``. Cannot be null.
    createdAt : str
        Timestamp string of when the record was created.
    updatedAt : str
        Timestamp string of when the record was last updated.
    materialCategory : MaterialCategory
        Relationship to the associated :class:`MaterialCategory` instance.
    """

    __tablename__ = "materials"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(), nullable=False)
    description = db.Column(db.String(), nullable=True)
    categoryId = db.Column(db.Integer, db.ForeignKey("material_categories.id", ondelete="CASCADE"), nullable=False)
    absorptionCoefficients = db.Column(JSON, nullable=False)
    origin = db.Column(db.String(10), default="user", nullable=False)
    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())

    materialCategory = db.relationship("MaterialCategory", foreign_keys=[categoryId])
