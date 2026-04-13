from marshmallow import Schema, ValidationError, fields


class FileSchema(Schema):
    id = fields.Integer()
    fileName = fields.Str()
    slot = fields.Str()
    size = fields.Integer()


class GetSlotSchema(Schema):
    id = fields.String(dump_only=True)
    uploadUrl = fields.String(dump_only=True)


class FileCreateQuerySchema(Schema):
    slot = fields.String(required=True)


class FileField(fields.Field):
    def _deserialize(self, value, attr, data, **kwargs):
        if not hasattr(value, "filename"):
            raise ValidationError("Invalid file.")
        return value


class FileCreateBodySchema(Schema):
    file = FileField(required=True)
