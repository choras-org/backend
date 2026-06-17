from marshmallow import Schema, fields


class UserPreferenceSchema(Schema):
    id = fields.Integer()
    settings = fields.Dict()
    createdAt = fields.String()
    updatedAt = fields.String()


class UserPreferenceUpdateBodySchema(Schema):
    settings = fields.Dict()

