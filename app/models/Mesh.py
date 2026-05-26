from datetime import datetime

from app.db import db


class Mesh(db.Model):
    __tablename__ = "meshes"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    taskId = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    task = db.relationship("Task", backref="mesh", cascade="all, delete", foreign_keys=[taskId])

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())
    completedAt = db.Column(db.String(), nullable=True)
