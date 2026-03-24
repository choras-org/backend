import unittest
import json
import os
import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from app.services import discovery_service, simulation_service
from app.types import Status, ResourceType
from app.models import SimulationRun, Simulation
from tests.unit import BaseTestCase
from config import DefaultConfig


# =============================================================================
# EP-DB4: session.commit() raises SQLAlchemyError
# Component: simulation_service.py → run_solver()
# =============================================================================

class RunSolverDBFailureTests(BaseTestCase):
    """
    Tests covering database commit failures inside run_solver().
    Partition: EP-DB4
    """

    def setUp(self):
        super().setUp()
        self.simulation_run_id = 123
        self.json_path = "/tmp/test_db_failure.json"

        self.test_json = {
            "task_id": "test-task-db-fail",
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

    def _make_mock_simrun(self):
        mock_simrun = MagicMock()
        mock_simrun.id = self.simulation_run_id
        mock_simrun.status = Status.Created
        mock_simrun.simulationMethod = "DE"
        return mock_simrun

    def _make_mock_simulation(self):
        mock_simulation = MagicMock()
        mock_simulation.id = 456
        mock_simulation.solverSettings = {"simulationSettings": {}}
        mock_simulation.settingsPreset = MagicMock(value="Default")
        mock_simulation.simulationMethod = "DE"
        mock_simulation.resourceType = ResourceType.LOCAL
        mock_simulation.status = Status.Created
        mock_simulation.simulationRunId = self.simulation_run_id
        return mock_simulation

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_db_commit_fails_on_status_update(self, mock_sessionmaker, mock_scoped):
        """
        EP-DB4
        session.commit() raises SQLAlchemyError on the first status update →
        outer except catches it, session is rolled back, session is closed.

        What is being tested:
            When the database commit fails during the initial status update
            to Queued, the outer exception handler rolls back the session
            and closes it cleanly without leaving an open transaction.

        Input:
            session.commit() raises SQLAlchemyError("DB commit failed")
            SimulationRun exists in DB

        Process:
            1. Mock session.query to return valid SimulationRun and Simulation
            2. Mock session.commit to raise SQLAlchemyError
            3. Call run_solver()
            4. Assert session.rollback() called
            5. Assert session.close() called

        Expected Output:
            session.rollback() called at least once
            session.close() called exactly once

        Pass Criteria:
            Both mock assertions pass — no open transaction left behind
        """
        from sqlalchemy.exc import SQLAlchemyError

        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()

        mock_session = MagicMock()

        def query_side_effect(model_class):
            mock_query = MagicMock()
            if model_class.__name__ == 'SimulationRun':
                mock_query.get.return_value = mock_simrun
            elif model_class.__name__ == 'Simulation':
                mock_query.filter_by.return_value.first.return_value = mock_simulation
            return mock_query

        mock_session.query.side_effect = query_side_effect
        mock_session.commit.side_effect = SQLAlchemyError("DB commit failed")
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        mock_session.rollback.assert_called()
        mock_session.close.assert_called_once()
        print("✅ DB commit failure → rollback called, session closed")

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_db_commit_fails_does_not_propagate_exception(
        self, mock_sessionmaker, mock_scoped
    ):
        """
        EP-DB4
        session.commit() raises SQLAlchemyError →
        exception is caught internally and does NOT propagate to the caller.

        What is being tested:
            run_solver() catches all exceptions including DB failures.
            The Celery worker calling run_solver() should not crash due to
            an unhandled DB exception.

        Input:
            session.commit() raises SQLAlchemyError

        Process:
            1. Mock session.commit to raise SQLAlchemyError
            2. Call run_solver() and assert no exception is raised

        Expected Output:
            run_solver() returns normally without raising

        Pass Criteria:
            No exception propagates out of run_solver()
        """
        from sqlalchemy.exc import SQLAlchemyError

        mock_session = MagicMock()
        mock_session.query.return_value.get.return_value = self._make_mock_simrun()
        mock_session.commit.side_effect = SQLAlchemyError("DB commit failed")
        mock_scoped.return_value.return_value = mock_session

        try:
            simulation_service.run_solver(self.simulation_run_id, self.json_path)
        except Exception as e:
            self.fail(
                f"run_solver() should not propagate DB exceptions but raised: {e}"
            )
        print("✅ DB commit failure → caught internally, no propagation")


# =============================================================================
# EP-DS3: Method removed from repo disappears from discovery
# Component: discovery_service.py → discover_methods()
# =============================================================================

class DiscoveryServiceRemovedMethodTests(BaseTestCase):
    """
    Tests covering EP-DS3 — method removed from config no longer appears.
    Partition: EP-DS3
    """

    def setUp(self):
        super().setUp()

    def test_removed_method_does_not_appear_in_discovery(self, tmp_path=None):
        """
        EP-DS3
        A method that exists in the config is then removed (config updated
        to exclude it) → discover_methods() no longer returns it.

        What is being tested:
            When the methods-config.json is updated to remove a method,
            subsequent calls to discover_methods() do not return that method.
            This simulates the real scenario where a developer removes a
            method from the repo and the config is updated accordingly.

        Input:
            First config: contains DG, DE, MyNewMethod
            Second config: contains only DG, DE (MyNewMethod removed)

        Process:
            1. Mock open() to return config with MyNewMethod present
            2. Call discover_methods() and assert MyNewMethod is present
            3. Mock open() to return config without MyNewMethod
            4. Call discover_methods() again and assert MyNewMethod absent

        Expected Output:
            First call: MyNewMethod in results
            Second call: MyNewMethod NOT in results

        Pass Criteria:
            Both assertions pass
        """
        config_with_method = json.dumps([
            {
                "simulationType": "DG",
                "containerImage": "dg_image:latest",
                "entryFile": "DGinterface.py",
                "label": "DG"
            },
            {
                "simulationType": "DE",
                "containerImage": "de_image:latest",
                "entryFile": "DEinterface.py",
                "label": "DE"
            },
            {
                "simulationType": "MyNewMethod",
                "containerImage": "mynew_image:latest",
                "entryFile": "MyNewMethodInterface.py",
                "label": "My New Method"
            }
        ])

        config_without_method = json.dumps([
            {
                "simulationType": "DG",
                "containerImage": "dg_image:latest",
                "entryFile": "DGinterface.py",
                "label": "DG"
            },
            {
                "simulationType": "DE",
                "containerImage": "de_image:latest",
                "entryFile": "DEinterface.py",
                "label": "DE"
            }
        ])

        with self.app.app_context():
            # Step 1: config includes MyNewMethod
            with patch("builtins.open",
                       unittest.mock.mock_open(read_data=config_with_method)), \
                 patch("os.path.exists", return_value=True):
                methods_before = discovery_service.discover_methods()

            types_before = [m.get("simulationType") for m in methods_before]
            self.assertIn(
                "MyNewMethod", types_before,
                f"❌ MyNewMethod should be present before removal. Got: {types_before}"
            )

            # Step 2: config no longer includes MyNewMethod (simulates removal)
            with patch("builtins.open",
                       unittest.mock.mock_open(read_data=config_without_method)), \
                 patch("os.path.exists", return_value=True):
                methods_after = discovery_service.discover_methods()

            types_after = [m.get("simulationType") for m in methods_after]
            self.assertNotIn(
                "MyNewMethod", types_after,
                f"❌ MyNewMethod should be absent after removal. Got: {types_after}"
            )

        print("✅ Method removed from config → no longer appears in discovery")

    def test_unknown_method_returns_none_from_discover_container_image(self):
        """
        EP-M4
        discover_container_image() called with a method not in the config →
        returns None without raising.

        What is being tested:
            When simulation_service calls discover_container_image() for a
            method that is not registered, it receives None. This is the
            signal to abort before calling executor_factory().

        Input:
            simulation_type = "UnknownMethod" (not in any config)

        Process:
            1. Call discover_container_image("UnknownMethod")
            2. Assert return value is None

        Expected Output:
            None

        Pass Criteria:
            result is None
        """
        with self.app.app_context():
            result = discovery_service.discover_container_image("UnknownMethod")
        self.assertIsNone(
            result,
            "❌ Unknown method → discover_container_image should return None"
        )
        print("✅ discover_container_image('UnknownMethod') → None")

    def test_unknown_method_returns_none_from_discover_entry_file(self):
        """
        EP-M4, EP-M6
        discover_entry_file() called with a method not in the config →
        returns None without raising.

        What is being tested:
            When simulation_service calls discover_entry_file() for an
            unknown method, it receives None. Passing entry_file=None to
            CloudExecutor will break _execute_singularity_image — this
            test confirms the None is returned so the caller can detect it.

        Input:
            simulation_type = "UnknownMethod"

        Process:
            1. Call discover_entry_file("UnknownMethod")
            2. Assert return value is None

        Expected Output:
            None

        Pass Criteria:
            result is None
        """
        with self.app.app_context():
            result = discovery_service.discover_entry_file("UnknownMethod")
        self.assertIsNone(
            result,
            "❌ Unknown method → discover_entry_file should return None"
        )
        print("✅ discover_entry_file('UnknownMethod') → None")