from marshmallow import EXCLUDE, Schema, fields, post_load

from app.schemas.model_schema import ModelInfoBasicSchema
from app.types import Setting, Status, TaskType


class SolverSettingsSchema(Schema):
    simulationSettings = fields.Dict()


class SimulationCreateBodySchema(Schema):
    modelId = fields.Integer(required=True)
    name = fields.String(required=True)
    description = fields.String(required=False)
    layerIdByMaterialId = fields.Dict()
    solverSettings = fields.Nested(SolverSettingsSchema)
    sources = fields.List(fields.Dict(), required=False)
    receivers = fields.List(fields.Dict(), required=False)
    taskType = fields.Enum(TaskType, required=False)
    settingsPreset = fields.Enum(Setting, required=False)


class SimulationSchema(SimulationCreateBodySchema):
    id = fields.Integer()
    hasBeenEdited = fields.Boolean()
    status = fields.Enum(Status, required=True)
    simulationRunId = fields.Integer(allow_none=True)
    meshId = fields.Integer(allow_none=True)
    createdAt = fields.String()
    updatedAt = fields.String()
    completedAt = fields.String(allow_none=True)


class SimulationUpdateBodySchema(SimulationSchema):
    class Meta:
        id = EXCLUDE  # To ignore the field
        status = EXCLUDE
        simulationRunId = EXCLUDE
        simulationRun = EXCLUDE
        createdAt = EXCLUDE
        updatedAt = EXCLUDE
        completedAt = EXCLUDE
        modelId = EXCLUDE


class SimulationByModelQuerySchema(Schema):
    modelId = fields.Integer(required=True)


class SimulationRunCreateSchema(Schema):
    simulationId = fields.Integer()


class SimulationWithModelInfoSchema(SimulationSchema):
    model = fields.Nested(ModelInfoBasicSchema)


class SimulationRunSchema(Schema):
    id = fields.Integer()
    sources = fields.List(fields.Dict())
    receivers = fields.List(fields.Dict())
    taskType = fields.Enum(TaskType, required=True)
    settingsPreset = fields.Enum(Setting, required=True)
    status = fields.Enum(Status, required=True)
    percentage = fields.Integer(required=False)
    layerIdByMaterialId = fields.Dict()
    solverSettings = fields.Dict()
    createdAt = fields.String()
    updatedAt = fields.String()
    completedAt = fields.String()
    simulation = fields.Nested(SimulationWithModelInfoSchema)


class SimulationCancelSchema(Schema):
    simulationId = fields.Integer()


class SimulationWithRunSchema(SimulationSchema):
    simulationRun = fields.Nested(SimulationRunSchema)
