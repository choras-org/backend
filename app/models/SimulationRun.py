from datetime import datetime

from sqlalchemy import JSON

from app.db import db
from app.types import Setting, Status, Task, TaskType
from app.services.discovery_service import discover_method_names

simulation_methods = discover_method_names()


class SimulationRun(db.Model):
    __tablename__ = "simulationRuns"
    __table_args__ = (
        db.CheckConstraint(
            db.literal_column('"simulationMethod"').in_(simulation_methods),
            name="ck_simulation_method_valid"
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sources = db.Column(JSON, default=[])
    receivers = db.Column(JSON, default=[])
    simulationMethod = db.Column(db.String(), default="DE")
    percentage = db.Column(db.Integer, default=0)
    settingsPreset = db.Column(db.Enum(Setting), default=Setting.Default)
    layerIdByMaterialId = db.Column(JSON, default={})
    solverSettings = db.Column(JSON, nullable=False)

    status = db.Column(db.Enum(Status), default=Status.Created)

    createdAt = db.Column(db.String, default=datetime.now)
    updatedAt = db.Column(db.String, default=datetime.now, onupdate=datetime.now)
    completedAt = db.Column(db.String, nullable=True)
