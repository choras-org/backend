from marshmallow import Schema, fields

class MaterialCategoryCreateSchema(Schema):
    """Schema for creating a new material category.

    Attributes
    ----------
    name : str
        Name of the material category. Required.
    """

    name = fields.String(required=True)


class MaterialCategoryUpdateSchema(Schema):
    """Schema for updating an existing material category.

    Attributes
    ----------
    name : str
        New name for the material category. Required.
    """

    name = fields.String(required=True)


class MaterialCategorySchema(Schema):
    """Schema for serializing a material category record.

    Attributes
    ----------
    id : int
        Unique identifier of the material category.
    name : str
        Name of the material category.
    createdAt : str
        Timestamp string of when the record was created.
    updatedAt : str
        Timestamp string of when the record was last updated.
    """

    id = fields.Integer()
    name = fields.String()
    createdAt = fields.String()
    updatedAt = fields.String()
