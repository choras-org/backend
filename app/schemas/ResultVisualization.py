from marshmallow import Schema, fields, validate

class VisualizationLineData(Schema):
    """
    Schema for visualization of line data.

    This is a schema that can be used for most line plots of
    time and frequency domain data.
    It contains the x and y data, labels for the axes,
    limits for the axes, scale for the x-axis, and legend information.

    """
    x = fields.List(fields.Float, required=True)
    y = fields.List(fields.List(fields.Float), required=True)  # (n_channels, n_samples)
    xlabel = fields.String()
    ylabel = fields.String()
    x_limits = fields.Tuple((fields.Float, fields.Float))
    y_limits = fields.Tuple((fields.Float, fields.Float))
    x_scale = fields.String(
        load_default='linear',
        validate=validate.OneOf(["linear", "log"])
    )
    legend = fields.List(fields.String())
