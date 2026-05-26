import unittest
from typing import Dict

from werkzeug.exceptions import HTTPException

from app.services import setting_service
from app.types.Task import TaskType
from tests.unit import BaseTestCase


class UsersUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up method to initialize variables and preconditions.
        """
        super().setUp()

    def test_insert_initial_settings(self):
        """
        Test that initial settings are correctly inserted into the database.
        """
        with self.app.app_context():
            setting_service.insert_initial_settings()
            settings = setting_service.get_all_simulation_settings()

        self.assertTrue(len(settings) > 0)

    def test_update_settings(self):
        with self.app.app_context():
            setting_service.update_settings()
            settings = setting_service.get_all_simulation_settings()

        self.assertTrue(len(settings) > 0)

    # def test_get_setting_by_type(self):
    #     """
    #     Test that setting is correctly retrieved by simulationType.
    #     """
    #     with self.app.app_context():
    #         setting_service.insert_initial_settings()

    #         for task_type in {"DE", "DG", "BOTH"}:
    #             if task_type in TaskType.__members__.keys():
    #                 setting = setting_service.get_setting_by_type(task_type)
    #                 self.assertIsInstance(setting, Dict)
    #                 self.assertTrue(len(setting) > 0)

    #         self.assertRaises(HTTPException, setting_service.get_setting_by_type, "SOMTHING_DOES_NOT_EXIST")
