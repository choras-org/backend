import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Create Logger for this module
logger = logging.getLogger(__name__)


class ExportHelper:
    @staticmethod
    def parse_json_file_to_xlsx_file(json_path: str, xlsx_path: str) -> bool:
        """Convert simulation results to an Excel file"""
        data: Optional[Dict] = ExportHelper.__load_json__(json_path)
        if data is None:
            return False

        return ExportHelper.__parse_json_data_to_xlsx_file__(data, xlsx_path)

    @staticmethod
    def write_data_to_xlsx_file(xlsx_path: str, sheet: str, data: Dict, mode: str = 'a') -> bool:
        try:
            df = pd.DataFrame(data)
            with pd.ExcelWriter(xlsx_path, mode=mode) as writer:
                df.to_excel(writer, sheet_name=sheet, index=False)
            return True

        except Exception as e:
            logger.error(f'Error adding data to xlsx: {e}')
            return False

    @staticmethod
    def extract_from_xlsx_to_csv_to_zip_binary(
        xlsx_path: str, sheets_columns: Dict[str, List[str]], zip_buffer: Optional[io.BytesIO] = None, id: int = 0
    ) -> Optional[io.BytesIO]:
        try:
            xlsx_path: Path = Path(xlsx_path)
            xlsx = pd.ExcelFile(xlsx_path)

            # Create a BytesIO object
            zip_buffer = io.BytesIO() if zip_buffer is None else zip_buffer
            csv_buffer = io.StringIO()

            with zipfile.ZipFile(zip_buffer, 'a') as zip_file:
                # Save xlsx file to zip
                # zip_file.write(xlsx_path, arcname=xlsx_path.name)

                # Convert selected sheets and columns to csv and save them to zip
                for sheet, columns in sheets_columns.items():
                    df = pd.read_excel(xlsx, sheet_name=sheet)
                    csv_buffer.seek(0)
                    df[columns].to_csv(csv_buffer, header=True, index=False)
                    zip_file.writestr(f'{sheet}_simulation_{id}.csv', csv_buffer.getvalue())
                    csv_buffer.truncate(0)

                csv_buffer.close()

            xlsx.close()
            return zip_buffer

        except Exception as e:
            logger.error(f'Error saving data to csv: {e}')
            return None

    @staticmethod
    def write_file_to_zip_binary(zip_buffer: io.BytesIO, file_path: str, mode: str = 'a') -> Optional[io.BytesIO]:
        try:
            file_path: Path = Path(file_path)
            zip_file = zipfile.ZipFile(zip_buffer, mode=mode)
            zip_file.write(file_path, arcname=file_path.name)
            return zip_buffer

        except Exception as e:
            logger.error(f'Error saving file to zip: {e}')
            return None

    @staticmethod
    def extract_from_xlsx_to_dict(xlsx_path: str, sheets_columns: Dict[str, List[str]]) -> Optional[pd.DataFrame]:
        try:
            xlsx_path: Path = Path(xlsx_path)
            xlsx = pd.ExcelFile(xlsx_path)

            data: Dict[str, Dict[str, List]] = {}
            for sheet, columns in sheets_columns.items():
                df = pd.read_excel(xlsx, sheet_name=sheet)
                data[sheet] = {}
                for col in columns:
                    data[sheet][col] = df[col].tolist()

            xlsx.close()
            return data

        except Exception as e:
            xlsx.close()
            logger.error(f'Error extracting data from xlsx: {e}')
            return None

    @staticmethod
    def __load_json__(json_path) -> Optional[Dict]:
        try:
            with open(json_path, 'r') as file:
                data: Dict = json.load(file)
        except FileNotFoundError as e:
            logger.error(f'File not found: {e}')
            return None

        return data

    @staticmethod
    def __parse_json_data_to_xlsx_file__(data: Dict, xlsx_path: str) -> bool:
        try:
            # TODO: Multiple sources and multiple receivers
            receiver_results: List[Dict[str, List[int]]] = data['results'][0]['responses'][0]['receiverResults']
            parameters: Dict[str, List[int]] = data['results'][0]['responses'][0]['parameters']

            parameter_sheet = pd.DataFrame(parameters)

            if data['results'][0]['resultType'] == "DE":
                edc_sheet = pd.DataFrame()

                # fill in edc_sheet and pressure_sheet
                time = receiver_results[0]['t']
                edc_sheet['t'] = time
                for result in receiver_results:
                    edc_sheet[str(result['frequency']) + 'Hz'] = result['data']

            with pd.ExcelWriter(xlsx_path) as writer:
                parameter_sheet.to_excel(writer, sheet_name='Parameters', index=False)
                if data['results'][0]['resultType'] == "DE":
                    edc_sheet.to_excel(writer, sheet_name='EDC', index=False)

        except Exception as e:
            logger.error(f'Error saving data to xlsx: {e}')
            return False

        return True
