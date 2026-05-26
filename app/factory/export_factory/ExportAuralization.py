import io
import logging
import os
from typing import List

from flask_smorest import abort

from app.factory.export_factory.ExportHelper import ExportHelper
from app.factory.export_factory.Strategy import Strategy
from app.models import Export
from app.models.Auralization import Auralization
from app.models.Simulation import Simulation
from config import CustomExportParametersConfig as CustomExportParameters
from config import DefaultConfig

# Create logger for this module
logger = logging.getLogger(__name__)


class ExportAuralization(Strategy):
    def export(self, export_type: str, params: List, simulationIds: List, zip_buffer: io.BytesIO) -> io.BytesIO:
        try:
            if params:
                for id in simulationIds:
                    simulation: Simulation = Simulation.query.filter_by(id=id).first()

                    if CustomExportParameters.value_wav_file_auralization in params:
                        auralizations: List[Auralization] = simulation.auralizations

                        for auralization in auralizations:
                            auralization_wav_file_name: str = auralization.wavFileName
                            auralization_wav_file_path = os.path.join(
                                DefaultConfig.UPLOAD_FOLDER_NAME, auralization_wav_file_name
                            )

                            if not auralization_wav_file_name:
                                logger.error("Auralization export with simulation is " + str(id) + "does not exists!")
                                abort(400, message="Wav file doesn't exists!")

                            zip_buffer = ExportHelper.write_file_to_zip_binary(zip_buffer, auralization_wav_file_path)

                    if CustomExportParameters.value_wav_file_IR or CustomExportParameters.value_csv_file_IR in params:
                        export: Export = simulation.export
                        xlsx_file_name: str = export.name
                        impulse_wav_file_name = xlsx_file_name.split('.')[0] + ".wav"

                        impulse_wav_file_path = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, impulse_wav_file_name)
                        xlsx_file_path = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, xlsx_file_name)

                        if not impulse_wav_file_name:
                            logger.error(
                                "Impulse response .wav export with simulation is " + str(id) + "does not exists!"
                            )
                            abort(400, message="Excel file doesn't exists!")

                        if not xlsx_file_name:
                            logger.error(
                                "Impulse response .csv export with simulation is " + str(id) + "does not exists!"
                            )
                            abort(400, message="Excel file doesn't exists!")

                        if CustomExportParameters.value_wav_file_IR in params:
                            zip_buffer = ExportHelper.write_file_to_zip_binary(
                                zip_buffer=zip_buffer, file_path=impulse_wav_file_path
                            )

                        if CustomExportParameters.value_csv_file_IR in params:
                            zip_buffer = ExportHelper.extract_from_xlsx_to_csv_to_zip_binary(
                                xlsx_file_path,
                                {CustomExportParameters.impulse_response: CustomExportParameters.impulse_response_fs},
                                zip_buffer,
                                id,
                            )

            return zip_buffer

        except Exception as e:
            logger.error("Error while writing wav or csv file to zip buffer: " + str(e))
            abort(400, message="Error while writing wav file to zip buffer: " + str(e))
