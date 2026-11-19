from unittest.mock import patch, MagicMock

from app.services import simulation_service
from app.types import Status
from tests.unit import BaseTestCase


def _make_run(status, percentage):
    run = MagicMock()
    run.status = status
    run.percentage = percentage
    return run


class GetSimulationRunTests(BaseTestCase):
    """get_simulation_run only re-reads the results JSON of runs that can still change."""

    @patch('app.services.simulation_service.update_simulation_run_status')
    @patch('app.services.simulation_service.joinedload')
    @patch('app.services.simulation_service.SimulationRun')
    def test_only_unfinished_runs_are_updated(self, mock_simulation_run, mock_joinedload, mock_update):
        in_progress = _make_run(Status.InProgress, 40)
        completed = _make_run(Status.Completed, 100)
        completed_stale = _make_run(Status.Completed, 97)
        error = _make_run(Status.Error, 12)
        cancelled = _make_run(Status.Cancelled, 50)
        runs = [in_progress, completed, completed_stale, error, cancelled]
        mock_simulation_run.query.options.return_value.filter.return_value.all.return_value = runs

        result = simulation_service.get_simulation_run()

        self.assertEqual(result, runs, "❌ all runs should still be returned")
        updated = [c.args[0] for c in mock_update.call_args_list]
        self.assertIn(in_progress, updated, "❌ a running run should be updated")
        self.assertIn(completed_stale, updated, "❌ a completed run below 100 % should be corrected once")
        self.assertNotIn(completed, updated, "❌ a completed run at 100 % should be skipped")
        self.assertNotIn(error, updated, "❌ an errored run should be skipped")
        self.assertNotIn(cancelled, updated, "❌ a cancelled run should be skipped")
        print("✅ get_simulation_run updates only runs that can still change")
