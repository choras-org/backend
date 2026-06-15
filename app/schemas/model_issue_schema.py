from marshmallow import Schema, fields
from app.types import DetectionStage

class ModelIssueSchema(Schema):
    id = fields.Int(dump_only=True)
    modelId = fields.Int(required=False, allow_none=True)
    fileName = fields.Str(required=True)
    issueCount = fields.Int(default=0)
    detectionStage = fields.Enum(DetectionStage, required=True)
    createdAt = fields.Str(dump_only=True)
    updatedAt = fields.Str(dump_only=True)