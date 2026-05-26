import shutil
import unittest
import zipfile
from pathlib import Path

from werkzeug.exceptions import HTTPException

from app.models.Auralization import Auralization
from app.models.Export import Export
from app.models.Simulation import Simulation
from app.services import export_service
from app.types import Status
from config import CustomExportParametersConfig, DefaultConfig
from tests.unit import BaseTestCase


class UsersUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up method to initialize variables and preconditions.
        """
        super().setUp()

    def test_execute_export(self):
        """
        Test that export is correctly executed.
        """
        with self.app.app_context():
            simulation: Simulation = Simulation(name="test", solverSettings={}, modelId=1, status=Status.Completed)
            self.db.session.add(simulation)
            self.db.session.commit()
            simulation_id = simulation.id

            export: Export = Export(name="test.xlsx", simulationId=simulation_id)
            self.db.session.add(export)
            self.db.session.commit()

            test_xlsx_path = Path('tests', 'unit', 'services', 'data', 'test.xlsx')
            test_wav_path = Path('tests', 'unit', 'services', 'data', 'test.wav')

            temp_destination = Path(DefaultConfig.UPLOAD_FOLDER_NAME)
            temp_destination.mkdir(parents=True, exist_ok=True)

            temp_xlsx_path = Path(shutil.copy(test_xlsx_path, temp_destination))
            temp_wav_path = Path(shutil.copy(test_wav_path, temp_destination))

            export_dict = {
                "Auralization": [
                    CustomExportParametersConfig.value_wav_file_IR,
                    CustomExportParametersConfig.value_csv_file_IR,
                ],
                "EDC": ["t", '125Hz', '250Hz', '500Hz', '1000Hz', '2000Hz'],
                "Parameters": ["edt", "t20", "t30", "c80", "d50", "ts", "spl_t0_freq"],
                "xlsx": [True],
                "SimulationId": [simulation_id],
            }

            zip_binary = export_service.execute_export(export_dict)
            self.assertIsNotNone(zip_binary)

            # test if bytesIO contains .xlsx, .wav and .csv files
            with zipfile.ZipFile(zip_binary, 'r') as zip_ref:
                self.assertTrue(any(name.endswith('.xlsx') for name in zip_ref.namelist()))
                self.assertTrue(any(name.endswith('.wav') for name in zip_ref.namelist()))
                self.assertEqual(sum(name.endswith('.csv') for name in zip_ref.namelist()), 3)

            temp_xlsx_path.unlink()
            temp_wav_path.unlink()


if __name__ == "__main__":
    unittest.main()
