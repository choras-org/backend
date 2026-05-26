from marshmallow import Schema, fields

from app.types import Status, TaskType


class TaskSchema(Schema):
    id = fields.Integer()
    taskType = fields.Enum(TaskType)  # Assuming TaskType is an Enum, change to String for simplicity
    status = fields.Enum(Status)  # Assuming Status is an Enum, change to String for simplicity
    message = fields.String()
    createdAt = fields.Str()
    updatedAt = fields.Str()
    completedAt = fields.Str(allow_none=True)
