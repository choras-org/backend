"""
Integration test base class with Flask test client, Celery eager mode, and seeded project.
"""
import os
import unittest
from sqlalchemy import event

from app import create_app, db
from app.models import Project


class IntegrationBaseTestCase(unittest.TestCase):
    """
    Base class for integration tests.
    
    Provides:
    - Fresh app + Flask test client for each test
    - Celery eager mode so .delay() runs synchronously
    - Seeded project row
    - Table-level isolation (create_all / drop_all per test)
    """

    def setUp(self):
        """
        beforeAll-equivalent: fresh app + client + schema + Celery eager mode.
        """
        # Create app with test settings (reads DATABASE_URL from env or defaults to TestingConfig)
        self.app, self.celery = create_app(
            settings_module=os.environ.get("APP_TEST_SETTINGS_MODULE", "config.TestingConfigs")
        )
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Configure SQLite pragma for foreign key enforcement (if using SQLite in test env)
        @event.listens_for(db.engine, "connect")
        def _pragma(conn, _):
            if db.engine.dialect.name == "sqlite":
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=OFF")
                cur.close()

        # Create all tables for the test run
        db.create_all()

        # Enable Celery eager mode: .delay() executes synchronously, not via broker
        # This is the PRIMARY integration test approach (§6 Option A in the plan)
        self.celery.conf.task_always_eager = True
        self.celery.conf.task_eager_propagates = True

        # Flask test client: calls routes in-process, no real HTTP server
        self.client = self.app.test_client()

        # Seed a project so we can create models against it
        self.project = Project(
            name="Integration Test Project",
            group="IT",
            description="Integration test project",
        )
        db.session.add(self.project)
        db.session.commit()

    def refresh_session(self):
        """Drop the test session so the next query opens a fresh connection.

        The background geometry task (``process_model_geometry``) commits on its
        OWN ``scoped_session``/connection. The test's ``db.session`` keeps a
        stale snapshot and won't see those writes (nor, in some isolation modes,
        rows committed in a prior request) until it re-reads on a new
        connection. Call this after triggering the eager pipeline, before
        asserting on / re-fetching the affected rows.
        """
        db.session.remove()
        # Re-attach self.project to the fresh session so it doesn't become detached
        self.project = db.session.merge(self.project)

    def tearDown(self):
        """
        Clean up: remove session, drop all tables, pop app context.
        """
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
