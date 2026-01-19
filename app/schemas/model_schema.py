from marshmallow import Schema, fields, post_load

from app.services import file_service


class ModelSchema(Schema):
    id = fields.Number()
    name = fields.Str(required=True)
    sourceFileId = fields.Integer()
    outputFileId = fields.Integer()
    hasGeo = fields.Boolean()

    projectId = fields.Integer()
    imagePath = fields.String()

    createdAt = fields.Str()
    updatedAt = fields.Str()


class ModelInfoBasicSchema(Schema):
    id = fields.Integer(data_key="id")
    projectTag = fields.String(data_key="projectTag", attribute="project.group")
    projectId = fields.Integer(data_key="projectId", attribute="project.id")
    name = fields.String(data_key="modelName")
    projectName = fields.String(data_key="projectName", attribute="project.name")


class ModelInfoSchema(ModelInfoBasicSchema):
    hasGeo = fields.Boolean(data_key="hasGeo")
    sourceFileId = fields.Integer(data_key="modelUploadId")
    modelUrl = fields.Method("get_model_url", dump_only=True)
    meshId = fields.String(data_key="meshId", attribute="mesh.id")
    simulationCount = fields.Function(lambda obj: obj.simulation_count)

    def get_model_url(self, obj):
        # obj here is the object being serialized
        return file_service.get_file_url(obj.sourceFileId)


class ModelCreateSchema(Schema):
    name = fields.Str(required=True)
    projectId = fields.Integer(required=True)
    sourceFileId = fields.Integer(required=True)
    imagePath = fields.String(required=False)


class ModelUpdateSchema(Schema):
    name = fields.Str(required=True)

class ModelUploadImageResponseSchema(Schema):
    imagePath = fields.Str(required=True)