from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.project_schema import (
    ProjectCreateSchema,
    ProjectSchema,
    ProjectSimulationsSchema,
    ProjectUpdateByGroupBodySchema,
    ProjectUpdateByGroupQuerySchema,
    ProjectUpdateSchema,
    ProjectWithModelsSchema,
)
from app.services import project_service

blp = Blueprint("Project", __name__, description="Project API")


@blp.route("/projects")
class ProjectList(MethodView):
    @blp.response(200, ProjectWithModelsSchema(many=True))
    def get(self):
        projects = project_service.get_all_projects()
        return projects

    @blp.arguments(ProjectCreateSchema)
    @blp.response(201, ProjectSchema)
    def post(self, body_data):
        result = project_service.create_new_project(body_data)
        return result


@blp.route("/projects/updateByGroup")
class ProjectGroupUpdate(MethodView):
    @blp.arguments(ProjectUpdateByGroupQuerySchema, location="query")
    @blp.arguments(ProjectUpdateByGroupBodySchema)
    @blp.response(200)
    def patch(self, query_data, body_data):
        project_service.update_project_by_group(query_data["group"], body_data["newGroup"])
        return {"message": "group name updated successfully"}


@blp.route("/projects/deleteByGroup")
class ProjectGroupDelete(MethodView):
    @blp.arguments(ProjectUpdateByGroupQuerySchema, location="query")
    @blp.response(200)
    def delete(self, query_data):
        project_service.delete_project_by_group(query_data["group"])
        return {"message": "group deleted successfully"}


@blp.route("/projects/simulations")
class ProjectSimulations(MethodView):
    @blp.response(200, ProjectSimulationsSchema(many=True))
    def get(self):
        return project_service.get_all_projects_simulations()


@blp.route("/projects/<int:project_id>")
class Project(MethodView):
    @blp.response(200, ProjectWithModelsSchema)
    def get(self, project_id):
        result = project_service.get_project(project_id)
        return result

    @blp.arguments(ProjectUpdateSchema)
    @blp.response(200, ProjectSchema)
    def patch(self, query_data, project_id):
        result = project_service.update_project(project_id, query_data)
        return result

    @blp.response(200)
    def delete(self, project_id):
        project_service.delete_project(project_id)
        return {"message": "Project deleted successfully!"}
