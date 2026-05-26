import shutil
import unittest
from io import BytesIO
from pathlib import Path

from werkzeug.datastructures import FileStorage, ImmutableDict
from werkzeug.exceptions import HTTPException

from app.models.AudioFile import AudioFile
from app.models.Auralization import Auralization
from app.models.Export import Export
from app.models.Model import Model
from app.models.Project import Project
from app.models.Simulation import Simulation
from app.services import auralization_service
from app.types import Status
from config import AuralizationParametersConfig, DefaultConfig
from tests.unit import BaseTestCase


class UsersUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up method to initialize variables and preconditions.
        """
        super().setUp()

    def test_insert_initial_audio_files(self):
        """
        Test that initial audio_files are correctly inserted into the database.
        """
        with self.app.app_context():
            auralization_service.insert_initial_audios_examples()
            audio_files = auralization_service.get_all_audio_files()

        self.assertTrue(len(audio_files) > 0)

    def test_update_audios_examples(self):
        with self.app.app_context():
            auralization_service.update_audios_examples()
            audio_files = auralization_service.get_all_audio_files()

        self.assertTrue(len(audio_files) > 0)

    def test_get_auralization_by_id(self):
        """
        Test that auralization is correctly retrieved by araulization_id.
        """
        with self.app.app_context():
            arulization: Auralization = Auralization(simulationId=1, audioFileId=1, wavFileName="test.wav")
            self.db.session.add(arulization)
            self.db.session.commit()
            araulization_id = arulization.id

            arulization_db = auralization_service.get_auralization_by_id(araulization_id)
            self.assertEqual(arulization_db.status, Status.Created)

            self.db.session.delete(arulization)
            self.db.session.commit()
            arulization_db = auralization_service.get_auralization_by_id(araulization_id)

            self.assertEqual(arulization_db.status, Status.Uncreated)

    def test_get_auralization_by_simulation_audiofile_ids(self):
        """
        Test that auralization is correctly retrieved by simulation_id and audio_file_id combination.
        """
        with self.app.app_context():
            arulization: Auralization = Auralization(simulationId=1, audioFileId=1, wavFileName="test.wav")
            self.db.session.add(arulization)
            self.db.session.commit()
            simulation_id = arulization.simulationId
            audio_file_id = arulization.audioFileId

            arulization_db = auralization_service.get_auralization_by_simulation_audiofile_ids(
                simulation_id, audio_file_id
            )
            self.assertEqual(arulization_db.status, Status.Created)

            self.db.session.delete(arulization)
            self.db.session.commit()
            arulization_db = auralization_service.get_auralization_by_simulation_audiofile_ids(
                simulation_id, audio_file_id
            )

            self.assertEqual(arulization_db.status, Status.Uncreated)

    def test_get_auralization_wav_path(self):
        """
        Test that auralization wav path is correctly retrieved.
        """
        with self.app.app_context():
            arulization: Auralization = Auralization(
                simulationId=1, audioFileId=1, status=Status.Completed, wavFileName="test.wav"
            )
            self.db.session.add(arulization)
            self.db.session.commit()
            araulization_id = arulization.id

            wav_path = auralization_service.get_auralization_wav_path(araulization_id)
            self.assertEqual(wav_path.name, "test.wav")

            self.db.session.delete(arulization)
            self.db.session.commit()
            self.assertRaises(
                HTTPException, auralization_service.get_auralization_wav_path, araulization_id
            )  # test that abort correctly raises exception

    def test_get_impulse_response_plot(self):
        """
        Test that impulse response plot is correctly retrieved.
        """
        with self.app.app_context():
            simulation: Simulation = Simulation(name="test", solverSettings={}, modelId=1, status=Status.Completed)
            self.db.session.add(simulation)
            self.db.session.commit()
            simulation_id = simulation.id

            export: Export = Export(name="test.xlsx", simulationId=simulation_id)
            self.db.session.add(export)
            self.db.session.commit()

            test_file_path = Path('tests', 'unit', 'services', 'data', 'test.xlsx')
            temp_destination = Path(DefaultConfig.UPLOAD_FOLDER_NAME)
            temp_destination.mkdir(parents=True, exist_ok=True)
            temp_file_path = Path(shutil.copy(test_file_path, temp_destination))

            impulse_response_plot = auralization_service.get_impulse_response_plot(simulation_id=simulation_id)

            self.assertTrue(len(impulse_response_plot['impulseResponse']) > 0)
            self.assertEqual(impulse_response_plot['fs'], AuralizationParametersConfig.visualization_fs)
            self.assertEqual(impulse_response_plot['simulationId'], simulation_id)

            # test for file deletion
            temp_file_path.unlink()
            self.assertRaises(HTTPException, auralization_service.get_impulse_response_plot, simulation_id)

            # test for in-progress
            simulation.status = Status.InProgress
            self.db.session.commit()
            self.assertRaises(HTTPException, auralization_service.get_impulse_response_plot, simulation_id)

            # test for non-exising simulation
            self.db.session.delete(export)
            self.db.session.delete(simulation)
            self.db.session.commit()
            self.assertRaises(HTTPException, auralization_service.get_impulse_response_plot, simulation_id)

    def test_upload_audio_file(self):
        """
        Test that audio file is correctly uploaded.
        """
        with self.app.app_context():
            simulation_id = self.helper_create_simulation()

            form_data = ImmutableDict(
                {
                    "simulation_id": simulation_id,
                    "name": "piano",
                    "description": "Aerith's theme piano version",
                    "extension": "wav",
                }
            )

            test_file_path = Path('tests', 'unit', 'services', 'data', 'test_piano.wav')
            with open(test_file_path, 'rb') as file:
                test_file = FileStorage(file, filename='test_piano.wav')
                files_data = ImmutableDict({"file": test_file})
                audio_file: AudioFile = auralization_service.upload_audio_file(form_data, files_data)

            test_file_destination = Path(DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, audio_file.filename)

            # test for successful upload
            self.assertTrue(test_file_destination.exists())
            test_file_destination.unlink()

            # test for the uploading file with the identical name in one project
            previous_test_file_id = audio_file.id
            previous_test_file_name = audio_file.name
            previous_test_file_filename = audio_file.filename
            with open(test_file_path, 'rb') as file:
                test_file = FileStorage(file, filename='test_piano.wav')
                files_data = ImmutableDict({"file": test_file})
                audio_file: AudioFile = auralization_service.upload_audio_file(form_data, files_data)
            test_file_destination = Path(DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, audio_file.filename)
            self.assertEqual(previous_test_file_id, audio_file.id)
            self.assertEqual(previous_test_file_name, audio_file.name)
            self.assertNotEqual(previous_test_file_filename, audio_file.filename)
            test_file_destination.unlink()

            # test for the uploading file with the identical name in different projects
            another_simulation_id = self.helper_create_simulation()
            form_data = ImmutableDict(
                {
                    "simulation_id": another_simulation_id,
                    "name": "piano",
                    "description": "Aerith's theme piano version",
                    "extension": "wav",
                }
            )
            test_file_path = Path('tests', 'unit', 'services', 'data', 'test_piano.wav')
            with open(test_file_path, 'rb') as file:
                test_file = FileStorage(file, filename='test_piano.wav')
                files_data = ImmutableDict({"file": test_file})
                audio_file: AudioFile = auralization_service.upload_audio_file(form_data, files_data)
            test_file_destination = Path(DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, audio_file.filename)
            self.assertNotEqual(previous_test_file_id, audio_file.id)
            self.assertEqual(previous_test_file_name, audio_file.name)
            self.assertNotEqual(previous_test_file_filename, audio_file.filename)
            test_file_destination.unlink()
            self.db.session.rollback()

            # test for large file
            large_file = BytesIO()
            with open(test_file_path, 'rb') as file:
                for _ in range(10):
                    large_file.write(file.read())
                    file.seek(0)
                test_file = FileStorage(large_file, filename='test_piano.wav')
                files_data = ImmutableDict({"file": test_file})
                self.assertRaises(HTTPException, auralization_service.upload_audio_file, form_data, files_data)

            # test for invalid extension
            form_data = ImmutableDict(
                {
                    "simulation_id": simulation_id,
                    "name": "piano",
                    "description": "Aerith's theme piano version",
                    "extension": "mp3",
                }
            )
            with open(test_file_path, 'rb') as file:
                test_file = FileStorage(file, filename='test_piano.mp3')
                files_data = ImmutableDict({"file": test_file})
                self.assertRaises(HTTPException, auralization_service.upload_audio_file, form_data, files_data)

    def test_get_audio_files_by_simulation_id(self):
        """
        Test that audio files are correctly retrieved by simulation_id (project_id).
        """
        with self.app.app_context():
            simulation_id = self.helper_create_simulation()
            another_simulation_id = self.helper_create_simulation("another")

            form_data = ImmutableDict(
                {
                    "simulation_id": simulation_id,
                    "name": f"piano_{simulation_id}",
                    "description": "Aerith's theme piano version",
                    "extension": "wav",
                }
            )
            another_form_data = ImmutableDict(
                {
                    "simulation_id": another_simulation_id,
                    "name": f"piano_{another_simulation_id}",
                    "description": "Aerith's theme piano version",
                    "extension": "wav",
                }
            )

            test_file_path = Path('tests', 'unit', 'services', 'data', 'test_piano.wav')
            with open(test_file_path, 'rb') as file:
                test_file = FileStorage(file, filename='test_piano.wav')
                files_data = ImmutableDict({"file": test_file})
                auralization_service.upload_audio_file(form_data, files_data)
                auralization_service.upload_audio_file(another_form_data, files_data)

            audio_files = auralization_service.get_audio_files_by_simulation_id(simulation_id)
            another_audio_files = auralization_service.get_audio_files_by_simulation_id(another_simulation_id)

            # test that audio files are project-isolated
            self.assertEqual(len(audio_files), 1)
            self.assertEqual(len(another_audio_files), 1)
            self.assertEqual(audio_files[0].name, f"piano_{simulation_id}")
            self.assertEqual(another_audio_files[0].name, f"piano_{another_simulation_id}")

            test_file_destination = Path(DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, audio_files[0].filename)
            another_test_file_destination = Path(
                DefaultConfig.USER_AUDIO_FILE_FOLDER_NAME, another_audio_files[0].filename
            )
            test_file_destination.unlink()
            another_test_file_destination.unlink()
            self.db.session.rollback()

    def helper_create_simulation(self, name: str = "test") -> int:
        project = Project(name=name, description=f"{name} decription", group=name)
        self.db.session.add(project)
        self.db.session.commit()
        project_id = project.id

        model = Model(name=name, sourceFileId=1, outputFileId=1, projectId=project_id, meshId=1, hasGeo=False)
        self.db.session.add(model)
        self.db.session.commit()
        model_id = model.id

        simulation = Simulation(name=name, solverSettings={}, modelId=model_id, status=Status.Completed)
        self.db.session.add(simulation)
        self.db.session.commit()

        return simulation.id

    # TODO: testing procedure for: create_new_auralization -> run_auralization -> auralization_calculation
    def test_create_new_auralization(
        self,
    ):
        pass


if __name__ == "__main__":
    unittest.main()
