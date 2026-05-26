from typing import Dict

from flask import request, send_file, send_from_directory
from flask.views import MethodView
from flask_smorest import Blueprint

from app.schemas.auralization_schema import AudioFileSchema, AuralizationResponsePlotSchema, AuralizationSchema
from app.services import auralization_service

blp = Blueprint("Auralization", __name__, description="Auralization API")


@blp.route("/auralizations/audiofiles")
class AudioFileList(MethodView):
    @blp.response(200, AudioFileSchema(many=True))
    def get(self):
        audio_files = auralization_service.get_all_audio_files()
        return audio_files


@blp.route("/auralizations/<int:simulation_id>/audiofiles")
class AudioFileBySimulationIdList(MethodView):
    @blp.response(200, AudioFileSchema(many=True))
    def get(self, simulation_id):
        audio_files = auralization_service.get_audio_files_by_simulation_id(simulation_id)
        return audio_files


@blp.route("/auralizations")
class AuralizationTask(MethodView):
    @blp.arguments(AuralizationSchema)
    @blp.response(200, AuralizationSchema)
    def post(self, body_data: Dict):
        result = auralization_service.create_new_auralization(body_data["simulationId"], body_data["audioFileId"])
        return result


@blp.route("/auralizations/<int:auralization_id>/status")
class AuralizationStatus(MethodView):
    @blp.response(200, AuralizationSchema)
    def get(self, auralization_id):
        result = auralization_service.get_auralization_by_id(auralization_id)
        return result


@blp.route("/auralizations/<int:auralization_id>/wav")
class AuralizationWav(MethodView):
    @blp.response(200)
    def get(self, auralization_id):
        wav_path = auralization_service.get_auralization_wav_path(auralization_id)
        return send_from_directory(wav_path.parent, wav_path.name, as_attachment=True, mimetype="audio/wav")


@blp.route("/auralizations/<int:simulation_id>/impulse/wav")
class AuralizationImpulseReponseWav(MethodView):
    @blp.response(200)
    def get(self, simulation_id):
        wav_path = auralization_service.get_impulse_response_wav_path(simulation_id)
        return send_from_directory(wav_path.parent, wav_path.name, as_attachment=True, mimetype="audio/wav")


@blp.route("/auralizations/<int:simulation_id>/impulse/plot")
class AuralizationImpulseReponsePlot(MethodView):
    @blp.response(200, AuralizationResponsePlotSchema)
    def get(self, simulation_id):
        plot_data = auralization_service.get_impulse_response_plot(simulation_id)
        return plot_data


@blp.route("/auralizations/upload/audiofile")
# FIXME: this api does not follow the Swagger format
class AuralizationUploadAudioFile(MethodView):
    @blp.response(200, AudioFileSchema)
    def post(self):
        return auralization_service.upload_audio_file(request.form, request.files)
