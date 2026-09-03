import io
import logging
import os
import zipfile
from typing import List

import pandas as pd
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
                xlsx_file_name_in_zip = (
                    xlsx_file_name.split('.')[0] + '_simulation_' + str(id) + '.' + xlsx_file_name.split('.')[1]
                )

                try:
                    # Read XLSX and uppercase Parameters sheet headers
                    xlsx = pd.ExcelFile(xlsx_path)
                    with pd.ExcelWriter(io.BytesIO(), mode='w') as temp_writer:
                        for sheet_name in xlsx.sheet_names:
                            df = pd.read_excel(xlsx, sheet_name=sheet_name)
                            # Uppercase Parameters sheet headers
                            if sheet_name.lower() == 'parameters':
                                df = df.rename(columns={col: str(col).upper() for col in df.columns})
                            df.to_excel(temp_writer, sheet_name=sheet_name, index=False)
                    xlsx.close()
                    
                    # Save modified XLSX to bytes and add to zip
                    temp_buffer = io.BytesIO()
                    with pd.ExcelWriter(temp_buffer, engine='openpyxl') as temp_writer:
                        for sheet_name in xlsx.sheet_names:
                            df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
                            if sheet_name.lower() == 'parameters':
                                df = df.rename(columns={col: str(col).upper() for col in df.columns})
                            df.to_excel(temp_writer, sheet_name=sheet_name, index=False)
                    
                    temp_buffer.seek(0)
                    with zipfile.ZipFile(zip_buffer, 'a') as zip_file:
                        zip_file.writestr(xlsx_file_name_in_zip, temp_buffer.getvalue())
                        
                except Exception as e:
                    logger.error("Error while writing excel file to zip buffer: " + str(e))
                    abort(400, message="Error while writing excel file to zip buffer: " + str(e))

        return zip_buffer
