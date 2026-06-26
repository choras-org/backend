from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.model_schema import ModelCreateSchema, ModelInfoSchema, ModelRepairDecisionSchema, ModelSchema, ModelUpdateSchema, ModelUploadImageResponseSchema
from app.schemas.geometry_schema import ModelSimulationCompatibilitySchema
from app.services import model_service
from app.services import geometry_compatibility_service

blp = Blueprint("Model", __name__, description="Model API")


@blp.route("/models")
class ModelList(MethodView):
    @blp.arguments(ModelCreateSchema)
    @blp.response(201, ModelSchema)
    def post(self, body_data):
        result = model_service.create_new_model(body_data)
        return result

@blp.route("/models/upload-image")
class ModelUploadImage(MethodView):
    @blp.response(200, ModelUploadImageResponseSchema)
    def post(self):
        return model_service.upload_image(request.files)


@blp.route("/models/<int:model_id>")
class Model(MethodView):
    @blp.response(200, ModelInfoSchema)
    def get(self, model_id):
        result = model_service.get_model(model_id)
        return result

    @blp.arguments(ModelUpdateSchema)
    @blp.response(200, ModelSchema)
    def patch(self, body_data, model_id):
        result = model_service.update_model(model_id, body_data)
        return result

    @blp.response(200)
    def delete(self, model_id):
        model_service.delete_model(model_id)
        return {"message": "Model deleted successfully!"}


@blp.route("/models/<int:model_id>/repair-decision")
class ModelRepairDecision(MethodView):
    @blp.arguments(ModelRepairDecisionSchema)
    @blp.response(200, ModelInfoSchema)
    def post(self, body_data, model_id):
        """Accept or reject the repaired geometry for a model.

        Body: ``{"decision": "accept" | "reject"}``. Accepting switches the
        model's active geometry (viewer URL and simulation .geo/.msh) to the
        repaired files; rejecting reverts to the original upload.
        """
        accept = body_data["decision"] == "accept"
        return model_service.set_repair_decision(model_id, accept)


@blp.route("/models/<int:model_id>/reprocess-geometry")
class ModelReprocessGeometry(MethodView):
    @blp.response(202, ModelInfoSchema)
    def post(self, model_id):
        """Re-run the background geometry pipeline for a model.

        Useful when a previous run failed. Clears stale issue rows and the
        repair decision, resets the status to ``Pending`` and dispatches the
        background task again. Returns immediately (202).
        """
        return model_service.reprocess_model_geometry(model_id)


@blp.route("/models/<int:model_id>/simulation-compatibility")
class ModelSimulationCompatibility(MethodView):
    @blp.response(200, ModelSimulationCompatibilitySchema)
    def get(self, model_id):
        """Per-method geometry compatibility for this model's repaired geometry.

        Loads the model's AfterRepair issue report and resolves, for every
        simulation method, how its configured compatibility applies to the
        issues that remain in the model.
        """
        return geometry_compatibility_service.get_model_simulation_compatibility(model_id)
