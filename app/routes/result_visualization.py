from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.ResultVisualization import VisualizationLineData
from app.services import visualization_service

blp = Blueprint(
    "ResultVisualization",
    __name__,
    description="Result Visualization API"
)


@blp.route("/simulations/<int:simulation_id>/visualization/<string:visualization_type>")
class ResultVisualization(MethodView):
    @blp.response(200, VisualizationLineData)
    def get(self, simulation_id: int, visualization_type: str):
        return visualization_service.get_visualization_data(simulation_id, visualization_type)
