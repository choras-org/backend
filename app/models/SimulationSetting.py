from datetime import datetime

from app.db import db
from config import DefaultConfig


class SimulationSetting(db.Model):
    __tablename__ = "simulation_settings"

    simulationType = db.Column(db.String(), primary_key=True)
    path = db.Column(db.String(), nullable=False, default=DefaultConfig.SETTINGS_FILE_FOLDER)
    name = db.Column(db.String(), nullable=False)
    label = db.Column(db.String(), nullable=False)
    description = db.Column(db.String)
    repositoryURL = db.Column(db.String)
    documentationURL = db.Column(db.String)

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
