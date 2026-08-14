import unittest
import json
import os
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from datetime import datetime

from app.services import simulation_service
from app.types import Status, ResourceType
from app.models import SimulationRun, Simulation
from tests.unit import BaseTestCase

class RunSolverUnitTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Set up any necessary data for the tests, such as creating a simulation run
        super().setUp()
        self.simulation_run_id = 123
        self.json_path = "/tmp/test_simulation.json"

        # Minimal valid JSON matching run_solver expectations
        self.test_json = {
            "task_id": "test-task-123",
            "simulationSettings": {},
            "results": [{
                "resultType": "DE",
                "responses": [{"receiverResults": []}]
            }]
        }
        Path(self.json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.json_path, "w") as f:
            json.dump(self.test_json, f)
    
    def tearDown(self):
        if os.path.exists(self.json_path):
            os.chmod(self.json_path, 0o644)
            os.unlink(self.json_path)
        super().tearDown()

    def _make_mock_session(self, mock_simrun, mock_simulation):
        """Helper: wire mock_session with simrun and simulation."""
        mock_session = MagicMock()

        # session.query(SimulationRun).get(id) → mock_simrun
        # session.query(Simulation).filter_by().first() → mock_simulation
        def query_side_effect(model_class):
            mock_query = MagicMock()
            if model_class.__name__ == 'SimulationRun':
                mock_query.get.return_value = mock_simrun
            elif model_class.__name__ == 'Simulation':
                mock_query.filter_by.return_value.first.return_value = mock_simulation
            return mock_query

        mock_session.query.side_effect = query_side_effect
        return mock_session
    
    def _make_mock_simrun(self):
        """Helper: create a mock SimulationRun."""
        mock_simrun = MagicMock()
        mock_simrun.id = self.simulation_run_id
        mock_simrun.status = Status.Created
        mock_simrun.simulationMethod = "DE"
        return mock_simrun

    def _make_mock_simulation(self):
        """Helper: create a mock Simulation."""
        mock_simulation = MagicMock()
        mock_simulation.id = 456
        mock_simulation.solverSettings = {"simulationSettings": {}}
        mock_simulation.settingsPreset = MagicMock(value="Default")
        mock_simulation.simulationMethod = "DG"
        mock_simulation.resourceType = ResourceType.LOCAL
        mock_simulation.status = Status.Created
        mock_simulation.simulationRunId = self.simulation_run_id
        return mock_simulation
    
    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_simulation_run_not_found_early_return(self, mock_sessionmaker, mock_scoped):
        """
        SimulationRun.get(id) → None → early return, no commit, no status update.
        """
        mock_session = MagicMock()
        mock_session.query.return_value.get.return_value = None  # Not found
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()
        print("✅ SimulationRun not found → early return, no DB commits")

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_simulation_none_crash(self, mock_sessionmaker, mock_scoped):
        """
        SimulationRun found but Simulation query returns None
        → AttributeError crash on simulation.status = Status.Queued.
        """
        mock_simrun = self._make_mock_simrun()
        mock_session = self._make_mock_session(mock_simrun, None)  # Simulation = None
        mock_scoped.return_value.return_value = mock_session

        # Should crash: simulation.status = Status.Queued → NoneType has no .status
        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        # Error is caught internally → status set to Error, session closed
        mock_session.close.assert_called_once()
        print("❌ simulation=None → crash (AttributeError caught internally)")

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_solver_settings_none_sets_error_status(self, mock_sessionmaker, mock_scoped):
        """
        solverSettings=None → solverSettings["simulationSettings"] crashes
        → Exception caught → status set to Error.
        """
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_simulation.solverSettings = None  # Trigger KeyError

        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        # Inner exception sets Error status
        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ solver settings None → SimulationRun status should be Error")
        self.assertEqual(mock_simulation.status, Status.Error,
            "❌ solver settings None → Simulation status should be Error")
        mock_session.commit.assert_called()
        print("✅ solverSettings=None → Error status set")

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_json_unreadable_sets_error_status(self, mock_sessionmaker, mock_scoped):
        """
        JSON file exists but is unreadable → PermissionError
        → caught → status set to Error.
        """
        os.chmod(self.json_path, 0o000)  # No permissions

        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ Unreadable JSON → SimulationRun status should be Error")
        print("✅ Unreadable JSON → Error status set correctly")

    @patch('app.services.simulation_service.ExportHelper')
    @patch('app.services.simulation_service.executor_factory')
    @patch('app.services.simulation_service.discover_entry_file')
    @patch('app.services.simulation_service.discover_container_image')
    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_auralization_fails_error_status_orphaned_xlsx(
        self, mock_sessionmaker, mock_scoped, mock_discover_image,
        mock_discover_entry, mock_executor_factory, mock_export_helper
    ):
        """
        write_data_to_xlsx_file raises after session.add(export) → status=Error
        BUT Export record already written to DB → orphaned record (partial state).

        Uses a non-DE resultType so the case _ branch runs: imp_tot is computed
        from the JSON and session.add(export) is reached before the failure.
        """
        test_json = {
            **self.test_json,
            "results": [{"resultType": "DG", "responses": [{"receiverResults": []}]}],
        }
        with open(self.json_path, "w") as f:
            json.dump(test_json, f)

        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        mock_discover_image.return_value = "dg_image:latest"
        mock_discover_entry.return_value = "DGInterface.py"
        mock_executor_factory.return_value.execute.return_value.wait.return_value = {"StatusCode": 0}
        mock_export_helper.parse_json_file_to_xlsx_file.return_value = True
        mock_export_helper.write_data_to_xlsx_file.side_effect = Exception("Auralization failed")  # FAILS after session.add

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ write_data_to_xlsx_file fail → SimulationRun should be Error")
        # Orphaned Export record was already added to the session before the failure
        mock_session.add.assert_called()
        print("✅ write_data_to_xlsx_file fails → Error status")
        print("⚠️  Orphaned Export record added to DB before failure!")


    @patch('app.services.simulation_service.ExportHelper')
    @patch('app.services.simulation_service.executor_factory')
    @patch('app.services.simulation_service.discover_entry_file')
    @patch('app.services.simulation_service.discover_container_image')
    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_export_false_sets_error_status(
        self, mock_sessionmaker, mock_scoped, mock_discover_image,
        mock_discover_entry, mock_executor_factory, mock_export_helper
    ):
        """
        ExportHelper.parse_json_file_to_xlsx_file() → False
        → `raise "string"` is invalid Python → TypeError
        → caught by inner except → status set to Error.
        """
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        mock_discover_image.return_value = "de_image:latest"
        mock_discover_entry.return_value = "DEInterface.py"
        mock_executor_factory.return_value.execute.return_value.wait.return_value = {"StatusCode": 0}
        mock_export_helper.parse_json_file_to_xlsx_file.return_value = False  # Trigger bug

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ Export False → status should be Error (raise string is invalid Python!)")
        print("❌ Export False → TypeError from raise 'string' → Error status")

    @patch('app.services.simulation_service.auralization_calculation')
    @patch('app.services.simulation_service.ExportHelper')
    @patch('app.services.simulation_service.executor_factory')
    @patch('app.services.simulation_service.discover_entry_file')
    @patch('app.services.simulation_service.discover_container_image')
    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_container_non_zero_exit_sets_error_status(
        self, mock_sessionmaker, mock_scoped, mock_discover_image,
        mock_discover_entry, mock_executor_factory,
        mock_export_helper, mock_auralization
    ):
        """
        container.wait() returns exit code 1 (failure)
        → RuntimeError raised → caught → simulation marked Error.
        """
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        mock_discover_image.return_value = "dg_image:latest"
        mock_discover_entry.return_value = "DGinterface.py"
        mock_executor_factory.return_value.execute.return_value.wait.return_value = {"StatusCode": 1}  # FAIL
        mock_export_helper.parse_json_file_to_xlsx_file.return_value = True
        mock_export_helper.write_data_to_xlsx_file.return_value = True
        mock_auralization.return_value = ([0.1, 0.2], 44100)

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ Non-zero container exit → SimulationRun status should be Error")
        self.assertEqual(mock_simulation.status, Status.Error,
            "❌ Non-zero container exit → Simulation status should be Error")
        print("✅ container.wait()={'StatusCode': 1} → Error status set correctly")
    
    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_json_path_nonexistent_sets_error_status(self, mock_sessionmaker, mock_scoped):
        """EP-C3 — JSON_PATH points to a file that does not exist → FileNotFoundError caught → Error status."""
        nonexistent_path = "/tmp/does_not_exist_at_all.json"
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, nonexistent_path)

        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ Non-existent JSON path → SimulationRun status should be Error")
        print("✅ Non-existent JSON path → Error status set correctly")

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_solver_settings_malformed_sets_error_status(self, mock_sessionmaker, mock_scoped):
        """EP-C7 — solverSettings is not None but missing 'simulationSettings' key → KeyError → Error status."""
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_simulation.solverSettings = {"bad_key": "unexpected_structure"}
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.status, Status.Error,
            "❌ Malformed solverSettings → SimulationRun status should be Error")
        self.assertEqual(mock_simulation.status, Status.Error,
            "❌ Malformed solverSettings → Simulation status should be Error")
        print("✅ Malformed solverSettings → Error status set correctly")


class RunSolverErrorMessageTests(BaseTestCase):
    """Verify errorMessage is written to both SimulationRun and Simulation on failure."""

    def setUp(self):
        super().setUp()
        self.simulation_run_id = 123
        fd, self.json_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self._base_json = {
            "task_id": "test-task-error",
            "simulationSettings": {},
            "results": [{"resultType": "DE", "responses": [{"receiverResults": []}]}],
        }
        with open(self.json_path, "w") as f:
            json.dump(self._base_json, f)

    def tearDown(self):
        if os.path.exists(self.json_path):
            os.chmod(self.json_path, 0o644)
            os.unlink(self.json_path)
        super().tearDown()

    def _make_mock_session(self, mock_simrun, mock_simulation):
        mock_session = MagicMock()
        def query_side_effect(model_class):
            mock_query = MagicMock()
            if model_class.__name__ == "SimulationRun":
                mock_query.get.return_value = mock_simrun
            elif model_class.__name__ == "Simulation":
                mock_query.filter_by.return_value.first.return_value = mock_simulation
            return mock_query
        mock_session.query.side_effect = query_side_effect
        return mock_session

    def _make_mock_simrun(self):
        m = MagicMock()
        m.id = self.simulation_run_id
        m.status = Status.Created
        return m

    def _make_mock_simulation(self):
        m = MagicMock()
        m.id = 456
        m.solverSettings = {"simulationSettings": {}}
        m.settingsPreset = MagicMock(value="Default")
        m.simulationMethod = "DE"
        m.resourceType = ResourceType.LOCAL
        m.status = Status.Created
        m.simulationRunId = self.simulation_run_id
        return m

    @patch("app.services.simulation_service.executor_factory")
    @patch("app.services.simulation_service.discover_entry_file")
    @patch("app.services.simulation_service.discover_container_image")
    @patch("app.services.simulation_service.scoped_session")
    @patch("app.services.simulation_service.sessionmaker")
    def test_json_error_message_written_to_both_models(
        self, mock_sessionmaker, mock_scoped,
        mock_discover_image, mock_discover_entry, mock_executor_factory
    ):
        """Exit code 1 + JSON {"error": {"message": "..."}} → exact string on both models."""
        error_message = "Room geometry is invalid"
        with open(self.json_path, "w") as f:
            json.dump({**self._base_json, "error": {"message": error_message}}, f)

        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_scoped.return_value.return_value = self._make_mock_session(mock_simrun, mock_simulation)
        mock_discover_image.return_value = "de_image:latest"
        mock_discover_entry.return_value = "DEInterface.py"
        mock_executor_factory.return_value.execute.return_value.wait.return_value = {"StatusCode": 1}

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.errorMessage, error_message)
        self.assertEqual(mock_simulation.errorMessage, error_message)

    @patch("app.services.simulation_service.executor_factory")
    @patch("app.services.simulation_service.discover_entry_file")
    @patch("app.services.simulation_service.discover_container_image")
    @patch("app.services.simulation_service.scoped_session")
    @patch("app.services.simulation_service.sessionmaker")
    def test_missing_error_key_uses_fallback_message(
        self, mock_sessionmaker, mock_scoped,
        mock_discover_image, mock_discover_entry, mock_executor_factory
    ):
        """Exit code 1 + JSON has no \"error\" key → fallback message on both models."""
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_scoped.return_value.return_value = self._make_mock_session(mock_simrun, mock_simulation)
        mock_discover_image.return_value = "de_image:latest"
        mock_discover_entry.return_value = "DEInterface.py"
        mock_executor_factory.return_value.execute.return_value.wait.return_value = {"StatusCode": 1}

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.errorMessage, "Simulation failed with exit code 1")
        self.assertEqual(mock_simulation.errorMessage, "Simulation failed with exit code 1")

    @patch("app.services.simulation_service.executor_factory")
    @patch("app.services.simulation_service.discover_entry_file")
    @patch("app.services.simulation_service.discover_container_image")
    @patch("app.services.simulation_service.scoped_session")
    @patch("app.services.simulation_service.sessionmaker")
    def test_unreadable_json_uses_fallback_message(
        self, mock_sessionmaker, mock_scoped,
        mock_discover_image, mock_discover_entry, mock_executor_factory
    ):
        """
        Exit code 1 + JSON not readable when error path runs → fallback message on both models.

        run_solver reads the JSON twice: once at startup to load the task config, and
        again after a non-zero exit code to extract the structured error message. This
        test covers the case where the second read fails (e.g. the simulation container
        overwrote or removed the file before exiting).

        Timing is controlled via wait()'s side_effect: the file is deleted at the
        moment wait() returns, which is after the initial reads and write-back but
        before the error-path read — the exact window where this failure can occur
        in production.
        """
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_scoped.return_value.return_value = self._make_mock_session(mock_simrun, mock_simulation)
        mock_discover_image.return_value = "de_image:latest"
        mock_discover_entry.return_value = "DEInterface.py"

        def remove_json_and_fail(*args, **kwargs):
            os.unlink(self.json_path)
            return {"StatusCode": 1}

        mock_executor_factory.return_value.execute.return_value.wait.side_effect = remove_json_and_fail

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.errorMessage, "Simulation failed with exit code 1")
        self.assertEqual(mock_simulation.errorMessage, "Simulation failed with exit code 1")

    @patch("app.services.simulation_service.executor_factory")
    @patch("app.services.simulation_service.discover_entry_file")
    @patch("app.services.simulation_service.discover_container_image")
    @patch("app.services.simulation_service.scoped_session")
    @patch("app.services.simulation_service.sessionmaker")
    def test_unexpected_exception_writes_error_message(
        self, mock_sessionmaker, mock_scoped,
        mock_discover_image, mock_discover_entry, mock_executor_factory
    ):
        """Unexpected exception (non-RuntimeError) in inner try → \"An unexpected error occurred: ...\" on both models."""
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_scoped.return_value.return_value = self._make_mock_session(mock_simrun, mock_simulation)
        mock_discover_image.return_value = "de_image:latest"
        mock_discover_entry.return_value = "DEInterface.py"
        mock_executor_factory.return_value.execute.side_effect = ValueError("Connection lost")

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertEqual(mock_simrun.errorMessage, "An unexpected error occurred: Connection lost")
        self.assertEqual(mock_simulation.errorMessage, "An unexpected error occurred: Connection lost")

    @patch("app.services.simulation_service.executor_factory")
    @patch("app.services.simulation_service.discover_entry_file")
    @patch("app.services.simulation_service.discover_container_image")
    @patch("app.services.simulation_service.scoped_session")
    @patch("app.services.simulation_service.sessionmaker")
    def test_error_message_committed(
        self, mock_sessionmaker, mock_scoped,
        mock_discover_image, mock_discover_entry, mock_executor_factory
    ):
        """
        errorMessage is set on both models before session.commit() is called.

        Setting errorMessage on the in-memory object is not enough — it must be
        committed to actually reach the database. This test verifies the ordering
        by recording the value of simulation_run.errorMessage each time commit()
        fires. Early commits (status → Queued, status → InProgress) happen before
        errorMessage is set, so they record the default MagicMock attribute. Only
        the commit inside the error handler fires after the assignment, recording
        the actual error string. The assertion passes only if that string appears
        in the captured list, i.e. only if commit was called after the assignment.
        """
        error_message = "Simulation method failure"
        with open(self.json_path, "w") as f:
            json.dump({**self._base_json, "error": {"message": error_message}}, f)

        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = self._make_mock_session(mock_simrun, mock_simulation)
        mock_scoped.return_value.return_value = mock_session
        mock_discover_image.return_value = "de_image:latest"
        mock_discover_entry.return_value = "DEInterface.py"
        mock_executor_factory.return_value.execute.return_value.wait.return_value = {"StatusCode": 1}

        # Record the value of errorMessage on simrun at the moment each commit fires
        committed_messages = []
        mock_session.commit.side_effect = lambda: committed_messages.append(mock_simrun.errorMessage)

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        self.assertIn(
            error_message, committed_messages,
            "errorMessage was not set on SimulationRun before session.commit() was called",
        )
