from datetime import datetime

from app.db import db


class Model(db.Model):
    __tablename__ = "models"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)

    sourceFileId = db.Column(db.Integer, nullable=False)
    outputFileId = db.Column(db.Integer, nullable=False)

    projectId = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    meshId = db.Column(db.Integer, db.ForeignKey("meshes.id", ondelete="SET NULL"), nullable=True)
    mesh = db.relationship("Mesh", cascade="all, delete", foreign_keys=[meshId])

    simulations = db.relationship("Simulation", backref="model", cascade="all, delete")
    hasGeo = db.Column(db.Boolean, nullable=False, default=False)

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())

    @property
    def simulation_count(self):
        return len(self.simulations)  # Assuming 'simulations' is the backref in Simulation model
