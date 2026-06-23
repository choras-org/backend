from marshmallow import Schema, fields


class UserPreferenceSchema(Schema):
    """
    Serialization and deserialization schema for the complete UserPreference model.

    This schema is used to validate and format the full user preference data
    when transferring it across application layers or API endpoints.

    Attributes
    ----------
    id : int
        The unique identifier for the preference record.
    settings : dict
        The dictionary containing user-specific configuration settings.
    createdAt : str
        The timestamp indicating when the preference record was created.
    updatedAt : str
        The timestamp indicating when the preference record was last updated.
    """

    id = fields.Integer()
    settings = fields.Dict()
    createdAt = fields.String()
    updatedAt = fields.String()


class UserPreferenceUpdateBodySchema(Schema):
    """
    Deserialization schema for validating user preference update payloads.

    This schema is specifically used to validate incoming request bodies 
    when a user updates their configuration settings, ensuring only permissible 
    fields are processed.

    Attributes
    ----------
    settings : dict
        The dictionary containing the updated user-specific configuration settings.
    """

    settings = fields.Dict()