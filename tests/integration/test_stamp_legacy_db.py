from alembic.migration import MigrationContext
from sqlalchemy import text

from app import db
from manage import stamp_legacy_db
from tests.unit import BaseTestCase


def current_revision():
    with db.engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


class StampLegacyDbTests(BaseTestCase):
    # BaseTestCase creates the tables with create_all(), like CHORAS <= v0.2.1 did.
    # Called directly: app.test_cli_runner() would load the module-level app (develop.db).

    def tearDown(self):
        with self.app.app_context():
            with db.engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        super().tearDown()

    def test_database_without_migrations_is_stamped_at_baseline(self):
        with self.app.app_context():
            stamp_legacy_db()

            self.assertEqual(current_revision(), "v0_2_0")

    def test_empty_database_is_not_stamped(self):
        with self.app.app_context():
            db.drop_all()

            stamp_legacy_db()

            self.assertIsNone(current_revision())
