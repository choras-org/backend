from marshmallow import Schema, fields

class MaterialCategoryCreateSchema(Schema):
    name = fields.String(required=True)


class MaterialCategoryUpdateSchema(Schema):
    name = fields.String(required=True)


class MaterialCategorySchema(Schema):
    id = fields.Integer()
    name = fields.String()
    createdAt = fields.String()
    updatedAt = fields.String()
