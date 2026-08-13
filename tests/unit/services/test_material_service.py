import unittest
from unittest.mock import patch

from app.models import Material, MaterialCategory
from app.services import material_service, material_category_service
from tests.unit import BaseTestCase
from werkzeug.exceptions import BadRequest


class UsersUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up method to initialize variables and preconditions.
        """
        super().setUp()

    def _make_category(self, name="Test Category"):
        with self.app.app_context():
            category = MaterialCategory(name=name)
            self.db.session.add(category)
            self.db.session.commit()
            return category.id  # return id; object detaches when context exits

    def test_insert_initial_materials(self):
        """
        Test that initial materials are correctly inserted into the database.
        """
        # When
        with self.app.app_context():
            # Categories must exist before materials (service does a lookup by name)
            material_category_service.insert_initial_material_categories()

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
            # Given: A category and new material data
            category = MaterialCategory(name="Test Category")
            self.db.session.add(category)
            self.db.session.commit()

            new_material_data = {
                "name": "Test Material",
                "description": "A test material",
                "categoryId": category.id,
                "absorptionCoefficients": {},
            }

            # When: Creating a new material
            created_material = material_service.create_new_material(new_material_data)

            # Then: Check the material properties
            self.assertIsNotNone(created_material.id)
            self.assertEqual(created_material.name, "Test Material")
            self.assertEqual(created_material.categoryId, category.id)

    def test_create_new_material_with_invalid_data(self):
        """
        Test that `create_new_material` raises BadRequest for invalid data.
        """
        with self.app.app_context():
            # Given: Invalid material data
            invalid_material_data = {
                "name": None,  # Name cannot be None if nullable=False in the model
                "description": "Invalid Material",
                "categoryId": 1,  # FK is OFF in test SQLite; value doesn't need to exist
                "absorptionCoefficients": {},
            }

            # When/Then: Attempt to create material should raise an exception
            with self.assertRaises(BadRequest) as context:
                material_service.create_new_material(invalid_material_data)
            # Just check that it raises an error, don't check exact message
            self.assertEqual(context.exception.code, 400)

    def test_get_all_materials(self):
        """
        Test that `get_all_materials` correctly retrieves all materials.
        """
        with self.app.app_context():
            # Given: Inserting two materials into the database
            cat1 = MaterialCategory(name="Cat1")
            cat2 = MaterialCategory(name="Cat2")
            self.db.session.add_all([cat1, cat2])
            self.db.session.commit()

            material1 = Material(
                name="Material1",
                description="Desc1",
                categoryId=cat1.id,
                absorptionCoefficients={},
            )
            material2 = Material(
                name="Material2",
                description="Desc2",
                categoryId=cat2.id,
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
            self.assertEqual(materials[0].materialCategory.name, "Cat1")
            self.assertEqual(materials[1].materialCategory.name, "Cat2")

    def test_get_material_by_id(self):
        """
        Test that `get_material_by_id` correctly retrieves a material by its ID.
        """
        with self.app.app_context():
            # Given: Inserting a material into the database
            category = MaterialCategory(name="Cat")
            self.db.session.add(category)
            self.db.session.commit()

            material = Material(
                name="Material for ID",
                description="Desc",
                categoryId=category.id,
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
        Test that `get_material_by_id` raises BadRequest if the material does not exist.
        """
        with self.app.app_context():
            # When/Then: Fetching a non-existent material should raise an exception
            with self.assertRaises(BadRequest) as context:
                material_service.get_material_by_id(9999)
            # Just check that it raises an error, don't check exact message
            self.assertEqual(context.exception.code, 400)

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
