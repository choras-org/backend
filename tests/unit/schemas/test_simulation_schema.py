import unittest

from app.schemas.simulation_schema import SimulationRunSchema, SimulationSchema
from app.types import Setting, Status


class SimulationSchemaErrorMessageTests(unittest.TestCase):
    """Tests for the errorMessage field added to SimulationSchema and SimulationRunSchema."""

    def test_error_message_present_in_simulation_output(self):
        """SimulationSchema serialises errorMessage when set."""
        message = "Room geometry is invalid"
        result = SimulationSchema().dump({
            "status": Status.Error,
            "errorMessage": message,
        })
        self.assertEqual(result["errorMessage"], message)

    def test_error_message_present_in_simulation_run_output(self):
        """SimulationRunSchema serialises errorMessage when set."""
        message = "Solver failed"
        result = SimulationRunSchema().dump({
            "status": Status.Error,
            "simulationMethod": "DE",
            "settingsPreset": Setting.Default,
            "errorMessage": message,
        })
        self.assertEqual(result["errorMessage"], message)

    def test_error_message_dump_only(self):
        """
        errorMessage provided in load input raises ValidationError.

        dump_only=True causes Marshmallow to treat the field as unknown during
        deserialisation. Marshmallow raises ValidationError for unknown fields
        by default, so a client sending errorMessage in a request body receives
        a validation error rather than having the value silently accepted.
        """
        from marshmallow.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            SimulationSchema().load({
                "name": "Test Simulation",
                "modelId": 1,
                "status": Status.Created,
                "errorMessage": "should be rejected",
            })
        self.assertIn("errorMessage", ctx.exception.messages)
