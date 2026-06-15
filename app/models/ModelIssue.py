from datetime import datetime

from app.db import db
from app.types import DetectionStage


class ModelIssue(db.Model):
    __tablename__ = "model_issues"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    modelId = db.Column(db.Integer, db.ForeignKey("models.id", ondelete="CASCADE"), nullable=True)
    model = db.relationship("Model", backref="issues")

    
    fileName = db.Column(db.String, nullable=False)
    issueCount = db.Column(db.Integer, default=0)
    detectionStage = db.Column(db.Enum(DetectionStage), nullable=False)

    createdAt = db.Column(db.String(), default=datetime.now())
    updatedAt = db.Column(db.String(), default=datetime.now())