from marshmallow import EXCLUDE, Schema, fields, post_load


class CustomExportSchema(Schema):
    SimulationId = fields.List(fields.Integer(required=True))
    Parameters = fields.List(fields.String(required=False))
    EDC = fields.List(fields.String(required=False))
    Auralization = fields.List(fields.String(required=False))
    xlsx = fields.List(fields.Bool(required=False))
