import unittest
from unittest.mock import patch

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound

from app.models import Model, Project
from app.services import model_service
from tests.unit import BaseTestCase


class ModelServiceUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up test variables and initialize a new app context.
        """
        super().setUp()

        # Create a new app context for the tests
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Create a dummy project to be used in the tests
        self.project = Project(name="Test Project", description="A test project", group="Test Group")
        self.db.session.add(self.project)
        self.db.session.commit()

    def tearDown(self):
        # Remove the database session and drop all tables
        self.db.session.remove()
        self.db.drop_all()
        self.ctx.pop()  # Remove the app context

        super().tearDown()

    def test_create_new_model_success(self):
        """
        Test that creating a new model is successful with valid data.
        """
        with self.app.app_context():
            # Given: Valid model data
            model_data = {
                "name": "Test Model",
                "projectId": self.project.id,
                "sourceFileId": 101,
                "outputFileId": 102,
            }

            # When: Creating a new model
            new_model = model_service.create_new_model(model_data)

            # Then: Assert the model is created correctly
            self.assertIsNotNone(new_model.id)
            self.assertEqual(new_model.name, "Test Model")
            self.assertEqual(new_model.projectId, self.project.id)

    @patch(
        "app.services.model_service.db.session.commit",
        side_effect=SQLAlchemyError("DB Error"),
    )
    def test_create_new_model_failure(self, mock_commit):
        """
        Test that creating a new model handles database errors correctly.
        """
        with self.app.app_context():
            # Given: Valid model data
            model_data = {
                "name": "Test Model",
                "projectId": self.project.id,
                "sourceFileId": 101,
                "outputFileId": 102,
            }

            # When/Then: Expect BadRequest due to DB Error
            with self.assertRaises(BadRequest) as context:
                model_service.create_new_model(model_data)

            # Ensure the logger was called with the expected message
            self.assertIn("400 Bad Request", str(context.exception))

    def test_get_model_success(self):
        """
        Test getting a model by id successfully.
        """
        with self.app.app_context():
            # Given: An existing model
            model = Model(
                name="Existing Model",
                projectId=self.project.id,
                sourceFileId=101,
                outputFileId=102,
            )
            self.db.session.add(model)
            self.db.session.commit()

            # When: Retrieving the model
            retrieved_model = model_service.get_model(model.id)

            # Then: The model should be retrieved successfully
            self.assertEqual(retrieved_model.id, model.id)
            self.assertEqual(retrieved_model.name, "Existing Model")

    def test_get_model_not_found(self):
        """
        Test that getting a non-existent model raises a NotFound exception.
        """
        with self.app.app_context():
            # When/Then: Expect NotFound error
            with self.assertRaises(NotFound) as context:
                model_service.get_model(999)  # Non-existent ID

            # Ensure the logger was called with the expected message
            self.assertIn("404 Not Found", str(context.exception))

    def test_update_model_success(self):
        """
        Test that updating a model is successful with valid data.
        """
        with self.app.app_context():
            # Given: An existing model
            model = Model(
                name="Old Model Name",
                projectId=self.project.id,
                sourceFileId=101,
                outputFileId=102,
            )
            self.db.session.add(model)
            self.db.session.commit()

            # When: Updating the model's name
            updated_data = {"name": "Updated Model Name"}
            updated_model = model_service.update_model(model.id, updated_data)

            # Then: The model should be updated correctly
            self.assertEqual(updated_model.name, "Updated Model Name")

    def test_update_model_not_found(self):
        """
        Test that updating a non-existent model raises a BadRequest exception.
        """
        with self.app.app_context():
            # When/Then: Expect BadRequest error
            with self.assertRaises(BadRequest) as context:
                model_service.update_model(999, {"name": "Updated Model Name"})  # Non-existent ID

            # Ensure the logger was called with the expected message
            self.assertIn("400 Bad Request", str(context.exception))

    def test_delete_model_success(self):
        """
        Test that deleting a model is successful.
        """
        with self.app.app_context():
            # Given: An existing model
            model = Model(
                name="Model to Delete",
                projectId=self.project.id,
                sourceFileId=101,
                outputFileId=102,
            )
            self.db.session.add(model)
            self.db.session.commit()

            # When: Deleting the model
            model_service.delete_model(model.id)

            # Then: The model should be deleted successfully
            deleted_model = Model.query.filter_by(id=model.id).first()
            self.assertIsNone(deleted_model)


if __name__ == "__main__":
    unittest.main()
