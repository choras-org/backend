from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.material_schema import MaterialCreateSchema, MaterialSchema, MaterialUpdateSchema
from app.services import material_service

blp = Blueprint("Material", __name__, description="Material API")


@blp.route("/materials")
class MaterialList(MethodView):
    @blp.response(200, MaterialSchema(many=True))
    def get(self):
        return material_service.get_all_materials()

    @blp.arguments(MaterialCreateSchema)
    @blp.response(201, MaterialSchema)
    def post(self, body_data):
        result = material_service.create_new_material(body_data)
        return result
    
@blp.route("/materials/<int:material_id>")
class MaterialDetail(MethodView):
    @blp.arguments(MaterialUpdateSchema)
    @blp.response(200, MaterialSchema)
    def put(self, body_data, material_id):
        result = material_service.update_material(material_id, body_data)
        return result
