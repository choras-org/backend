from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.material_category_schema import MaterialCategoryCreateSchema, MaterialCategorySchema, MaterialCategoryUpdateSchema
from app.services import material_category_service

blp = Blueprint("Material Category", __name__, description="Material Category API")


@blp.route("/material-categories")
class MaterialCategoryList(MethodView):
    """Resource for the material categories collection endpoint."""

    @blp.response(200, MaterialCategorySchema(many=True))
    def get(self):
        """Retrieve all material categories.

        Returns
        -------
        list of MaterialCategorySchema
            A list of all material category records.
        """
        return material_category_service.get_all_material_categories()

    @blp.arguments(MaterialCategoryCreateSchema)
    @blp.response(201, MaterialCategorySchema)
    def post(self, body_data):
        """Create a new material category.

        Parameters
        ----------
        body_data : dict
            Validated request body conforming to MaterialCategoryCreateSchema.

        Returns
        -------
        MaterialCategorySchema
            The newly created material category record.
        """
        result = material_category_service.create_new_material_category(body_data)
        return result
    
@blp.route("/material-categories/<int:material_category_id>")
class MaterialCategoryDetail(MethodView):
    """Resource for a single material category identified by its ID."""

    @blp.arguments(MaterialCategoryUpdateSchema)
    @blp.response(200, MaterialCategorySchema)
    def put(self, body_data, material_category_id):
        """Update an existing material category.

        Parameters
        ----------
        body_data : dict
            Validated request body conforming to MaterialCategoryUpdateSchema.
        material_category_id : int
            The ID of the material category to update.

        Returns
        -------
        MaterialCategorySchema
            The updated material category record.
        """
        result = material_category_service.update_material_category(material_category_id, body_data)
        return result
