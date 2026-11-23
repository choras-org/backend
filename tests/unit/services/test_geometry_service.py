import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from geometry_pipeline import GeometryError

from app.services.geometry_service import run_geometry_pipeline

FINAL_RESULT = SimpleNamespace(report={"post": {"tjunctions": [1, 2, 3]}})
CHECKPOINT = {"stage": "t_junctions", "issue_report": {}, "issue_count": 7}


class RunGeometryPipelineTests(unittest.TestCase):
    @patch("geometry_pipeline.process_geometry")
    def test_retries_without_cavity_detection(self, process_geometry):
        process_geometry.side_effect = [GeometryError("detector timed out"), FINAL_RESULT]

        success, remaining = run_geometry_pipeline("room.obj", "out", "RoomVolume")

        self.assertTrue(success)
        self.assertEqual(remaining, 3)
        self.assertEqual(process_geometry.call_count, 2)
        self.assertTrue(process_geometry.call_args_list[0].kwargs["detect_cavities"])
        self.assertFalse(process_geometry.call_args_list[1].kwargs["detect_cavities"])

    @patch("geometry_pipeline.process_geometry")
    def test_fails_when_retry_fails_too(self, process_geometry):
        process_geometry.side_effect = [GeometryError("detector timed out"), GeometryError("broken")]

        success, remaining = run_geometry_pipeline("room.obj", "out", "RoomVolume")

        self.assertFalse(success)
        self.assertEqual(remaining, 0)

    @patch("geometry_pipeline.process_geometry")
    def test_checkpoint_persisted_once_across_retry(self, process_geometry):
        def _checkpoint_then_fail_first_run(*args, on_checkpoint, **kwargs):
            on_checkpoint(CHECKPOINT)
            if process_geometry.call_count == 1:
                raise GeometryError("repaired .geo failed")
            return FINAL_RESULT

        process_geometry.side_effect = _checkpoint_then_fail_first_run
        on_checkpoint = MagicMock()

        success, _ = run_geometry_pipeline(
            "room.obj", "out", "RoomVolume", on_checkpoint=on_checkpoint
        )

        self.assertTrue(success)
        on_checkpoint.assert_called_once_with(CHECKPOINT)
