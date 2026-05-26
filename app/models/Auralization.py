from datetime import datetime

from app.db import db
from app.types import Status


class Auralization(db.Model):
    __tablename__ = "auralizations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    simulationId = db.Column(db.Integer, db.ForeignKey("simulations.id", ondelete="SET NULL"), nullable=True)
    simulation = db.relationship(
        "Simulation", backref=db.backref("auralizations", uselist=True), foreign_keys=[simulationId]
    )

    audioFileId = db.Column(db.Integer, db.ForeignKey("audio_files.id", ondelete="NO ACTION"), nullable=True)
    audioFile = db.relationship("AudioFile", foreign_keys=[audioFileId])

    status = db.Column(db.Enum(Status), default=Status.Created)

    wavFileName = db.Column(db.String(), nullable=True)

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
