import io
import logging
import os
import zipfile
from typing import List

from flask_smorest import abort

from app.factory.export_factory.Strategy import Strategy
from app.models.Export import Export
from app.models.Simulation import Simulation
from config import DefaultConfig

# Create logger for this module
logger = logging.getLogger(__name__)


class ExportExcel(Strategy):
    def export(self, export_type: str, params: List, simulationIds: List, zip_buffer: io.BytesIO) -> io.BytesIO:
        param = bool(params[0])
        if param:
            for id in simulationIds:
                simulation: Simulation = Simulation.query.filter_by(id=id).first()
                export: Export = simulation.export
                xlsx_file_name: str = export.name

                if not xlsx_file_name:
                    logger.error("Export with simulation is " + str(id) + "does not exists!")
                    abort(400, message="Excel file doesn't exists!")

                xlsx_path = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, xlsx_file_name)
                xlsx_file_name = (
                    xlsx_file_name.split('.')[0] + '_simulation_' + str(id) + '.' + xlsx_file_name.split('.')[1]
                )

                try:
                    with zipfile.ZipFile(zip_buffer, 'a') as zip_file:
                        # Save xlsx file to zip
                        zip_file.write(xlsx_path, arcname=xlsx_file_name)
                except Exception as e:
                    logger.error("Error while writing excel file to zip buffer: " + str(e))
                    abort(400, message="Error while writing excel file to zip buffer: " + str(e))

        return zip_buffer
