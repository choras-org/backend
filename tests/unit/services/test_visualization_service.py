import math
import os

import numpy as np
import pyfar as pf
from werkzeug.exceptions import HTTPException

from app.models.Export import Export
from app.models.Simulation import Simulation
from app.services import visualization_service
from app.types import Status
from config import DefaultConfig
from tests.unit import BaseTestCase


class VisualizationServiceUnitTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.json_path = os.path.join(DefaultConfig.UPLOAD_FOLDER_NAME, "test_visualization.json")
        self.generated_files = [
            self.json_path.replace(".json", f"_{visualization_type}.json")
            for visualization_type in visualization_service.VISUALIZATION_TYPES
        ]

    def tearDown(self):
        for file_path in self.generated_files:
            if os.path.exists(file_path):
                os.unlink(file_path)
        super().tearDown()

    def test_generate_and_get_visualization_data(self):
        """
        A generated impulse response can be turned into visualization data
        for every visualization type, and that data can be read back through
        `get_visualization_data`.
        """
        fs = 8000
        times = np.arange(0, 2**12) / fs
        imp_tot = np.exp(-3 * math.log(10) / 0.5 * times) * np.sin(2 * np.pi * 200 * times)
        signal = pf.Signal(imp_tot, fs)

        visualization_service.generate_visualization_data(signal, self.json_path)

        for file_path in self.generated_files:
            self.assertTrue(os.path.exists(file_path), f"Expected {file_path} to be generated")

        with self.app.app_context():
            simulation = Simulation(name="test", solverSettings={}, modelId=1, status=Status.Completed)
            self.db.session.add(simulation)
            self.db.session.commit()

            export = Export(name="test_visualization.xlsx", simulationId=simulation.id)
            self.db.session.add(export)
            self.db.session.commit()

            for visualization_type in visualization_service.VISUALIZATION_TYPES:
                plot_data = visualization_service.get_visualization_data(simulation.id, visualization_type)

                self.assertEqual(len(plot_data["x"]), len(plot_data["y"][0]))
                self.assertTrue(all(math.isfinite(limit) for limit in plot_data["y_limits"]))
                self.assertTrue(all(math.isfinite(limit) for limit in plot_data["x_limits"]))

    def test_get_visualization_data_invalid_type(self):
        with self.app.app_context():
            self.assertRaises(
                HTTPException, visualization_service.get_visualization_data, 1, "not-a-real-type"
            )

    def test_get_visualization_data_simulation_not_completed(self):
        with self.app.app_context():
            simulation = Simulation(name="test", solverSettings={}, modelId=1, status=Status.Created)
            self.db.session.add(simulation)
            self.db.session.commit()

            self.assertRaises(
                HTTPException, visualization_service.get_visualization_data, simulation.id, "rir"
            )

    def test_get_visualization_data_missing_file(self):
        with self.app.app_context():
            simulation = Simulation(name="test", solverSettings={}, modelId=1, status=Status.Completed)
            self.db.session.add(simulation)
            self.db.session.commit()

            export = Export(name="no_such_export.xlsx", simulationId=simulation.id)
            self.db.session.add(export)
            self.db.session.commit()

            self.assertRaises(
                HTTPException, visualization_service.get_visualization_data, simulation.id, "rir"
            )
