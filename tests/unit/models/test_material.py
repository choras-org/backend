import unittest

from sqlalchemy.exc import IntegrityError

from app.models import Material, MaterialCategory
from tests.unit import BaseTestCase


class MaterialModelUnitTests(BaseTestCase):
    def _make_category(self, name="Test Category"):
        category = MaterialCategory(name=name)
        self.db.session.add(category)
        self.db.session.commit()
        return category

    def test_create_material_success(self):
        """
        Test creating a material with valid data is successful.
        """
        with self.app.app_context():
            # Given: A category and valid material data
            category = self._make_category()
            material = Material(
                name="Test Material",
                description="A test material",
                categoryId=category.id,
                absorptionCoefficients=[0.1, 0.2, 0.3],
            )

            # When: Adding and committing the material to the database
            self.db.session.add(material)
            self.db.session.commit()

            # Then: The material should have been saved successfully
            self.assertIsNotNone(material.id)
            self.assertEqual(material.name, "Test Material")
            self.assertEqual(material.categoryId, category.id)
            self.assertEqual(material.materialCategory.name, "Test Category")
            self.assertEqual(material.absorptionCoefficients, [0.1, 0.2, 0.3])

    def test_create_material_missing_name(self):
        """
        Test creating a material without a name raises an IntegrityError.
        """
        with self.app.app_context():
            # Given: Material data missing the name
            category = self._make_category()
            material = Material(
                name=None,  # Name is required, should raise an error
                description="A test material",
                categoryId=category.id,
                absorptionCoefficients=[0.1, 0.2, 0.3],
            )

            # When/Then: Adding and committing the material should raise an IntegrityError
            with self.assertRaises(IntegrityError):
                self.db.session.add(material)
                self.db.session.commit()

            self.db.session.rollback()  # Rollback the session after exception

    def test_create_material_missing_category(self):
        """
        Test creating a material without a categoryId raises an IntegrityError.
        """
        with self.app.app_context():
            # Given: Material data missing the categoryId
            material = Material(
                name="Test Material",
                description="A test material",
                categoryId=None,  # categoryId is required, should raise an error
                absorptionCoefficients=[0.1, 0.2, 0.3],
            )

            # When/Then: Adding and committing the material should raise an IntegrityError
            with self.assertRaises(IntegrityError):
                self.db.session.add(material)
                self.db.session.commit()

            self.db.session.rollback()  # Rollback the session after exception

    def test_default_values(self):
        """
        Test that default values for createdAt and updatedAt are set correctly.
        """
        with self.app.app_context():
            # Given: A material without createdAt or updatedAt provided
            category = self._make_category()
            material = Material(
                name="Test Material",
                description="A test material",
                categoryId=category.id,
                absorptionCoefficients=[0.1, 0.2, 0.3],
            )

            # When: Adding and committing the material to the database
            self.db.session.add(material)
            self.db.session.commit()

            # Then: Check that default values are set
            self.assertIsNotNone(material.createdAt)
            self.assertIsNotNone(material.updatedAt)


if __name__ == "__main__":
    unittest.main()
