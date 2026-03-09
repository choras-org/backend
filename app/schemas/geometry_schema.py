from marshmallow import Schema, fields

from app.schemas.task_schema import TaskSchema


class GeometrySchema(Schema):
    id = fields.Integer()
    inputModelUploadId = fields.Integer()
    outputModelId = fields.Integer()

    taskId = fields.Integer()
    task = fields.Nested(TaskSchema)

    createdAt = fields.Str()
    updatedAt = fields.Str()


class GeometryStartQuerySchema(Schema):
    fileUploadId = fields.Integer(required=True)


class GeometryGetQuerySchema(Schema):
    geometryCheckId = fields.Integer(required=True)


class GeometryResultQuerySchema(Schema):
    taskId = fields.Integer(required=True)
