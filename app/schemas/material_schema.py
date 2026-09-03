from marshmallow import Schema, fields


class MaterialCreateSchema(Schema):
    """Schema for creating a new material.

    Attributes
    ----------
    name : str
        Name of the material. Required.
    categoryId : int
        ID of the associated material category. Required.
    description : str or None
        Optional description of the material.
    absorptionCoefficients : list of float
        List of absorption coefficient values.
    """

    name = fields.String(required=True)
    categoryId = fields.Integer(required=True)
    description = fields.String(allow_none=True)
    absorptionCoefficients = fields.List(fields.Float())

class MaterialUpdateSchema(Schema):
    """Schema for updating an existing material.

    Attributes
    ----------
    name : str
        New name for the material. Required.
    categoryId : int
        ID of the associated material category. Required.
    description : str or None
        Optional description of the material.
    absorptionCoefficients : list of float
        Updated list of absorption coefficient values.
    """

    name = fields.String(required=True)
    categoryId = fields.Integer(required=True)
    description = fields.String(allow_none=True)
    absorptionCoefficients = fields.List(fields.Float())

class MaterialSchema(MaterialCreateSchema):
    """Schema for serializing a material record.

    Extends :class:`MaterialCreateSchema` with read-only fields.

    Attributes
    ----------
    id : float
        Unique identifier of the material.
    origin : str
        Source of the material record (e.g. ``"user"`` or ``"system"``)
    category : str
        Name of the associated material category, sourced from
        ``materialCategory.name``.
    createdAt : str
        Timestamp string of when the record was created.
    updatedAt : str
        Timestamp string of when the record was last updated.
    """

    id = fields.Integer()
    origin = fields.String()
    category = fields.String(data_key="category", attribute="materialCategory.name")
    createdAt = fields.String()
    updatedAt = fields.String()
