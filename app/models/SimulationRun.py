from datetime import datetime

from sqlalchemy import JSON

from app.db import db
from app.types import Setting, Status, Task, TaskType


class SimulationRun(db.Model):
    __tablename__ = "simulationRuns"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sources = db.Column(JSON, default=[])
    receivers = db.Column(JSON, default=[])
    taskType = db.Column(db.Enum(TaskType), default=TaskType.DE)
    percentage = db.Column(db.Integer, default=0)
    settingsPreset = db.Column(db.Enum(Setting), default=Setting.Default)
    layerIdByMaterialId = db.Column(JSON, default={})
    solverSettings = db.Column(JSON, nullable=False)

    status = db.Column(db.Enum(Status), default=Status.Created)

    createdAt = db.Column(db.String, default=datetime.now)
    updatedAt = db.Column(db.String, default=datetime.now, onupdate=datetime.now)
    completedAt = db.Column(db.String, nullable=True)
