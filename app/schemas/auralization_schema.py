from marshmallow import Schema, fields

from app.types import Status


class AudioFileSchema(Schema):
    id = fields.Integer()
    projectId = fields.Integer()
    path = fields.String(load_only=True, required=True)
    name = fields.String(required=True)
    description = fields.String()
    fileExtension = fields.String()
    isUserFile = fields.Boolean(required=True)
    createdAt = fields.String()
    updatedAt = fields.String()


class AudioFileUpdateSchema(Schema):
    """Schema for updating an audio file's metadata.

    Attributes
    ----------
    name : str, optional
        The new name of the audio file. If not provided, the existing name is kept.
    description : str, optional
        The new description of the audio file. If not provided, the existing description is kept.
    """

    name = fields.String(load_default=None)
    description = fields.String(load_default=None)


class AuralizationSchema(Schema):
    id = fields.Integer()
    simulationId = fields.Integer()
    audioFileId = fields.Integer()
    status = fields.Enum(Status, default=Status.Uncreated)
    createdAt = fields.String()
    updatedAt = fields.String()


class AuralizationResponsePlotSchema(Schema):
    simulationId = fields.Integer()
    fs = fields.Integer()
    impulseResponse = fields.List(fields.Integer())
