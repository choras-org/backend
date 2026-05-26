from marshmallow import Schema, fields


class SettingSchema(Schema):
    simulationType = fields.String()
    path = fields.String(load_only=True)
    name = fields.String(load_only=True)
    label = fields.String()
    description = fields.String()
    repositoryURL = fields.String()
    documentationURL = fields.String()
    createdAt = fields.String()
    updatedAt = fields.String()
