from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.geometry_schema import (
    GeometryGetQuerySchema,
    GeometryResultQuerySchema,
    GeometrySchema,
    GeometryStartQuerySchema,
)
from app.services import geometry_service

blp = Blueprint("Geometry", __name__, description="Geometry API")


@blp.route("/geometryCheck")
class GeometryList(MethodView):
    @blp.arguments(GeometryGetQuerySchema, location="query")
    @blp.response(200, GeometrySchema)
    def get(self, query_data):
        result = geometry_service.get_geometry_by_id(query_data["geometryCheckId"])
        return result

    @blp.arguments(GeometryStartQuerySchema, location="query")
    @blp.response(201, GeometrySchema)
    def post(self, geometry_data):
        result = geometry_service.start_geometry_check_task(geometry_data["fileUploadId"])
        return result


@blp.route("/geometryCheck/result")
class Geometry(MethodView):
    @blp.arguments(GeometryResultQuerySchema, location="query")
    @blp.response(200, GeometrySchema)
    def get(self, query_data):
        result = geometry_service.get_geometry_result(query_data["taskId"])
        return result
