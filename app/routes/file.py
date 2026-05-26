from flask import send_from_directory
from flask.views import MethodView
from flask_smorest import Blueprint, abort

import config
from app.models import File
from app.schemas.file_schema import FileCreateBodySchema, FileCreateQuerySchema, FileSchema, GetSlotSchema
from app.services import file_service

blp = Blueprint("File", __name__, description="File API")


@blp.route("/files")
class FileList(MethodView):
    @blp.response(200, GetSlotSchema)
    def get(self):
        return file_service.get_slot()

    @blp.arguments(FileCreateQuerySchema, location="query")
    @blp.arguments(FileCreateBodySchema, location="files")
    @blp.response(201, FileSchema)
    def post(self, query_data, body_data):
        if "file" not in body_data:
            abort(404, "No file provided!")

        result = file_service.create_file(query_data, body_data)
        return result

    @blp.arguments(FileCreateQuerySchema, location="query")
    @blp.response(200, FileSchema)
    def delete(self, file_data):
        result = file_service.consume(file_data["slot"])
        return result


@blp.route("/files/<int:file_id>")
class FileOnly(MethodView):
    @blp.response(200)
    def get(self, file_id):
        result = file_service.get_file_url(file_id)
        return result


@blp.route(f"/{config.DefaultConfig.UPLOAD_FOLDER_NAME}/<filename>")
class ServerUploads(MethodView):
    @blp.response(200)
    def get(self, filename):
        return send_from_directory(config.DefaultConfig.UPLOAD_FOLDER, filename)


@blp.route(f"/{config.DefaultConfig.UPLOAD_FOLDER_NAME}/data/<filename>")
class ServerUploadsData(MethodView):
    @blp.response(200)
    def get(self, filename):
        return send_from_directory(f"{config.DefaultConfig.UPLOAD_FOLDER}/data", filename)
