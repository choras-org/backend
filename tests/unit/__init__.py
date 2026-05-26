import os
import unittest

from sqlalchemy import event

from app import create_app, db


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        """
        This method runs once before any test in this class.
        It sets up the application context and creates the necessary database tables.
        """
        self.app, _ = create_app(settings_module=os.environ.get("APP_TEST_SETTINGS_MODULE"))
        with self.app.app_context():
            self.db = db

            @event.listens_for(self.db.engine, "connect")  # execute the function when every connection is made
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=OFF")
                cursor.close()

            self.db.create_all()

    def tearDown(self):
        """
        This method runs once after all tests in this class have been executed.
        It removes the database session and drops the database tables.
        """
        with self.app.app_context():
            self.db.session.remove()
            self.db.drop_all()
