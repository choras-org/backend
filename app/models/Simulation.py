from datetime import datetime

from sqlalchemy import JSON

from app.db import db
from app.types import Setting, Status, TaskType, ResourceType
from app.services.discovery_service import discover_method_names

simulation_methods = discover_method_names()

class Simulation(db.Model):
    __tablename__ = "simulations"
    __table_args__ = (
        db.CheckConstraint(
            db.literal_column('"simulationMethod"').in_(simulation_methods),
            name="ck_simulation_method_valid"
        ),
    )


    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)

    hasBeenEdited = db.Column(db.Boolean, nullable=False, default=False)
    sources = db.Column(JSON, default=[])
    receivers = db.Column(JSON, default=[])
    resourceType = db.Column(db.Enum(ResourceType), default=ResourceType.LOCAL)  # NEW

    simulationMethod = db.Column(db.String(), default="DE")
    layerIdByMaterialId = db.Column(JSON, default={})
    settingsPreset = db.Column(db.Enum(Setting), default=Setting.Default)
    solverSettings = db.Column(JSON, nullable=False)
    status = db.Column(db.Enum(Status), default=Status.Created)

    modelId = db.Column(db.Integer, db.ForeignKey("models.id", ondelete="CASCADE"), nullable=False)

    simulationRunId = db.Column(
        db.Integer,
        db.ForeignKey("simulationRuns.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Relationship to SimulationRun
    simulationRun = db.relationship(
        "SimulationRun",
        backref=db.backref("simulation", uselist=False),
        cascade="all, delete",
        foreign_keys=[simulationRunId],
    )

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
    completedAt = db.Column(db.String(), nullable=True)
