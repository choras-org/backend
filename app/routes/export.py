import logging
from io import BytesIO

from flask import send_file, send_from_directory
from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.export_schema import CustomExportSchema
from app.services import export_service

# Create Logger for this module
logger = logging.getLogger(__name__)


blp = Blueprint("Export", __name__, description="Export API")


@blp.route("/exports/custom_export")
class CustomExport(MethodView):
    @blp.arguments(CustomExportSchema)
    @blp.response(200, content_type="application/zip")
    def post(self, body_data):
        zip_buffer = export_service.execute_export(body_data)
        if isinstance(zip_buffer, BytesIO):
            zip_buffer.seek(0)  # Ensure buffer is at the start
        return send_file(zip_buffer, as_attachment=True, download_name="results.zip", mimetype="application/zip")
