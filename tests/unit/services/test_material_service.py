import unittest
from unittest.mock import patch

from app.models import Material
from app.services import material_service
from tests.unit import BaseTestCase


class UsersUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up method to initialize variables and preconditions.
        """
        super().setUp()

    def test_insert_initial_materials(self):
        """
        Test that initial materials are correctly inserted into the database.
        """
        # When
        with self.app.app_context():
            # Call the function to insert initial materials
            material_service.insert_initial_materials()

            # Fetch materials from the database
            materials = material_service.get_all_materials()

        # Then
        # Ensure that materials are inserted correctly
        self.assertTrue(len(materials) > 0)

    @patch("app.services.material_service.open", side_effect=Exception("File read error"))
    def test_insert_initial_materials_file_error(self, mock_open):
        """
        Test that `insert_initial_materials` logs and aborts when the JSON file cannot be read.
        """
        with self.app.app_context():
            # When: File reading raises an exception
            with self.assertRaises(Exception):
                material_service.insert_initial_materials()

            # Then: Assert logger.error was called
            mock_open.assert_called_once()

    def test_create_new_material(self):
        """
        Test that `create_new_material` creates a new material and checks its properties.
        """
        with self.app.app_context():
            # Given: New material data
            new_material_data = {
                "name": "Test Material",
                "description": "A test material",
                "category": "Test Category",
                "absorptionCoefficients": {},
            }

            # When: Creating a new material
            created_material = material_service.create_new_material(new_material_data)

            # Then: Check the material properties
            self.assertIsNotNone(created_material.id)
            self.assertEqual(created_material.name, "Test Material")
            self.assertEqual(created_material.category, "Test Category")

    def test_create_new_material_with_invalid_data(self):
        """
        Test that `create_new_material` handles invalid data correctly.
        """
        with self.app.app_context():
            # Given: Invalid material data
            invalid_material_data = {
                "name": None,  # Name cannot be None if nullable=False in the model
                "description": "Invalid Material",
                "category": "Invalid Category",
                "absorptionCoefficients": {},
            }

            # When/Then: Attempt to create material should raise an exception
            with self.assertRaises(Exception) as context:
                material_service.create_new_material(invalid_material_data)

            # Ensure the logger was called with the expected message
            self.assertIn("Can not create a new material", str(context.exception))

    def test_get_all_materials(self):
        """
        Test that `get_all_materials` correctly retrieves all materials.
        """
        with self.app.app_context():
            # Given: Inserting two materials into the database
            material1 = Material(
                name="Material1",
                description="Desc1",
                category="Cat1",
                absorptionCoefficients={},
            )
            material2 = Material(
                name="Material2",
                description="Desc2",
                category="Cat2",
                absorptionCoefficients={},
            )
            self.db.session.add_all([material1, material2])
            self.db.session.commit()

            # When: Fetching all materials
            materials = material_service.get_all_materials()

            # Then: Assert the length and contents of materials fetched
            self.assertEqual(len(materials), 2)
            self.assertEqual(materials[0].name, "Material1")
            self.assertEqual(materials[1].name, "Material2")
            self.assertEqual(materials[0].category, "Cat1")
            self.assertEqual(materials[1].category, "Cat2")

    def test_get_material_by_id(self):
        """
        Test that `get_material_by_id` correctly retrieves a material by its ID.
        """
        with self.app.app_context():
            # Given: Inserting a material into the database
            material = Material(
                name="Material for ID",
                description="Desc",
                category="Cat",
                absorptionCoefficients={},
            )
            self.db.session.add(material)
            self.db.session.commit()

            # When: Fetching the material by ID
            fetched_material = material_service.get_material_by_id(material.id)

            # Then: Check if fetched material is correct
            self.assertIsNotNone(fetched_material)
            self.assertEqual(fetched_material.id, material.id)
            self.assertEqual(fetched_material.name, "Material for ID")

    def test_get_material_by_id_not_exists(self):
        """
        Test that `get_material_by_id` raises an exception if the material does not exist.
        """
        with self.app.app_context():
            # When/Then: Fetching a non-existent material should raise an exception
            with self.assertRaises(Exception) as context:
                material_service.get_material_by_id(9999)
            self.assertIn("Material doesn't exists!", str(context.exception))

    @patch("app.services.material_service.logger")
    def test_logger_invocation(self, mock_logger):
        """
        Test that the logger logs an error when a material does not exist.
        """
        with self.app.app_context():
            # When: Trying to get a material that does not exist
            with self.assertRaises(Exception):
                material_service.get_material_by_id(9999)

            # Then: Assert logger.error was called with the expected message
            mock_logger.error.assert_called_with("Material with id 9999 does not exists!")


if __name__ == "__main__":
    unittest.main()
