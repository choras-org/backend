from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.mesh_schema import GeoQuerySchema, MeshQuerySchema, MeshSchema, MeshWithTaskSchema
from app.services import mesh_service

blp = Blueprint("Mesh", __name__, description="Mesh API")


@blp.route("/meshes")
class MeshList(MethodView):
    @blp.arguments(MeshQuerySchema, location="query")
    @blp.response(200, MeshWithTaskSchema(many=True))
    def get(self, query_data):
        result = mesh_service.get_meshes_by_model_id(query_data["modelId"])
        return result

    @blp.arguments(MeshQuerySchema, location="query")
    @blp.response(201, MeshWithTaskSchema)
    def patch(self, query_data):
        result = mesh_service.start_mesh_task(query_data["modelId"])
        return result


@blp.route("/meshes/geo")
class MeshGeo(MethodView):
    @blp.arguments(GeoQuerySchema, location="query")
    @blp.response(200)
    def post(self, query_data):
        return mesh_service.attach_geo_file(query_data["modelId"], query_data["fileUploadId"])


@blp.route("/meshes/<int:mesh_id>")
class Mesh(MethodView):
    @blp.response(200, MeshWithTaskSchema)
    def get(self, mesh_id):
        result = mesh_service.get_mesh_by_id(mesh_id)
        return result
