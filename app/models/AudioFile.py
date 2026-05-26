from datetime import datetime

from app.db import db
from config import DefaultConfig


class AudioFile(db.Model):
    __tablename__ = "audio_files"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    path = db.Column(db.String(), nullable=False, default=DefaultConfig.AUDIO_FILE_FOLDER)
    name = db.Column(db.String(), nullable=False)
    filename = db.Column(db.String(), nullable=False, unique=True)
    description = db.Column(db.String(), nullable=False, default="not provided")
    isUserFile = db.Column(db.Boolean(), default=False)
    fileExtension = db.Column(db.String(), nullable=False)

    projectId = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    project = db.relationship(
        "Project",
        backref=db.backref("audioFiles", uselist=True),
        cascade="all, delete",
    )

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
