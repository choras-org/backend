from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.material_category_schema import MaterialCategoryCreateSchema, MaterialCategorySchema, MaterialCategoryUpdateSchema
from app.services import material_category_service

blp = Blueprint("Material Category", __name__, description="Material Category API")


@blp.route("/material-categories")
class MaterialCategoryList(MethodView):
    @blp.response(200, MaterialCategorySchema(many=True))
    def get(self):
        return material_category_service.get_all_material_categories()

    @blp.arguments(MaterialCategoryCreateSchema)
    @blp.response(201, MaterialCategorySchema)
    def post(self, body_data):
        result = material_category_service.create_new_material_category(body_data)
        return result
    
@blp.route("/material-categories/<int:material_category_id>")
class MaterialCategoryDetail(MethodView):
    @blp.arguments(MaterialCategoryUpdateSchema)
    @blp.response(200, MaterialCategorySchema)
    def put(self, body_data, material_category_id):
        result = material_category_service.update_material_category(material_category_id, body_data)
        return result
