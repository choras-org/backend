from flask_smorest import Api

from app.routes.auralization import blp as auralization_blueprint
from app.routes.export import blp as export_blueprint
from app.routes.file import blp as file_blueprint
from app.routes.geometry import blp as geometry_blueprint
from app.routes.material import blp as material_blueprint
from app.routes.mesh import blp as mesh_blueprint
from app.routes.model import blp as model_blueprint
from app.routes.project import blp as project_blueprint
from app.routes.setting import blp as setting_blueprint
from app.routes.simulation import blp as simulation_blueprint


# Register Blueprint
def register_routing(app):
    api = Api(app)
    api.register_blueprint(material_blueprint)
    api.register_blueprint(file_blueprint)
    api.register_blueprint(model_blueprint)
    api.register_blueprint(project_blueprint)
    api.register_blueprint(geometry_blueprint)
    api.register_blueprint(simulation_blueprint)
    api.register_blueprint(mesh_blueprint)
    api.register_blueprint(export_blueprint)
    api.register_blueprint(auralization_blueprint)
    api.register_blueprint(setting_blueprint)
