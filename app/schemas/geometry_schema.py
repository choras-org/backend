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
    fileUploadId = fields.Number(required=True)


class GeometryGetQuerySchema(Schema):
    geometryCheckId = fields.Integer(required=True)


class GeometryResultQuerySchema(Schema):
    taskId = fields.Integer(required=True)


class IssueCompatibilitySchema(Schema):
    label = fields.Str()
    description = fields.Str()
    compatibility = fields.Str()


class MethodCompatibilitySchema(Schema):
    simulationType = fields.Str()
    label = fields.Str(allow_none=True)
    notes = fields.Str(allow_none=True)
    issues = fields.Dict(
        keys=fields.Str(),
        values=fields.Nested(IssueCompatibilitySchema),
    )


class SimulationCompatibilitySchema(Schema):
    version = fields.Integer(allow_none=True)
    compatibilityLevels = fields.Dict(keys=fields.Str(), values=fields.Str())
    methods = fields.List(fields.Nested(MethodCompatibilitySchema))
