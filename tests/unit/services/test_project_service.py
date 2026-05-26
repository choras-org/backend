import unittest
from unittest.mock import MagicMock, patch

from app import db
from app.models import Model, Project, Simulation
from app.services import project_service, simulation_service
from tests.unit import BaseTestCase


class ProjectServiceTests(BaseTestCase):
    def setUp(self):
        """
        Set up test variables and initialize a new app context.
        """
        super().setUp()

        # Create a new app context for the tests
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Create a test database entry
        self.test_project = Project(name="Test Project", group="Test Group", description="Test Description")
        db.session.add(self.test_project)
        db.session.commit()

    def tearDown(self):
        """
        Clean up database and pop app context.
        """
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

        super().tearDown()

    def test_get_all_projects(self):
        """
        Test retrieving all projects.
        """
        projects = project_service.get_all_projects()
        self.assertGreaterEqual(len(projects), 1)
        self.assertEqual(projects[0].name, "Test Project")

    @patch("app.services.simulation_service.get_simulation_by_model_id", return_value=[])
    def test_get_all_projects_simulations(self, mock_get_simulation_by_model_id):
        """
        Test retrieving all projects with simulations.
        """
        results = project_service.get_all_projects_simulations()
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 0)

    def test_create_new_project(self):
        """
        Test creating a new project.
        """
        new_project_data = {
            "name": "New Project",
            "group": "New Group",
            "description": "New Description",
        }
        new_project = project_service.create_new_project(new_project_data)
        self.assertIsNotNone(new_project.id)
        self.assertEqual(new_project.name, "New Project")

    def test_get_project(self):
        """
        Test retrieving a specific project.
        """
        project = project_service.get_project(self.test_project.id)
        self.assertIsNotNone(project)
        self.assertEqual(project.name, "Test Project")

    def test_update_project(self):
        """
        Test updating an existing project.
        """
        updated_data = {"name": "Updated Project", "description": "Updated Description"}
        updated_project = project_service.update_project(self.test_project.id, updated_data)
        self.assertEqual(updated_project.name, "Updated Project")
        self.assertEqual(updated_project.description, "Updated Description")

    def test_delete_project(self):
        """
        Test deleting a project.
        """
        project_service.delete_project(self.test_project.id)
        project = Project.query.filter_by(id=self.test_project.id).first()
        self.assertIsNone(project)

    def test_delete_project_by_group(self):
        """
        Test deleting projects by group.
        """
        project_service.delete_project_by_group("Test Group")
        projects = Project.query.filter_by(group="Test Group").all()
        self.assertEqual(len(projects), 0)

    def test_update_project_by_group(self):
        """
        Test updating projects by group.
        """
        project_service.update_project_by_group("Test Group", "Updated Group")
        updated_project = Project.query.filter_by(id=self.test_project.id).first()
        self.assertEqual(updated_project.group, "Updated Group")


if __name__ == "__main__":
    unittest.main()
