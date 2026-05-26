import os

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

import config
import manage
from app.blueprint import register_routing
from app.db import db
from app.extention import cors, migrate
from app.job_queue import make_celery  # Import the Celery setup
from app.utils.logging import configure_logging

# Load environment variables from a .env file
load_dotenv()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

db_host = os.getenv(
    "BBDD_HOST", "localhost"
)  # Default to localhost if not set (for local dev)
db_user = os.getenv("POSTGRES_USER", "db_user")
db_password = os.getenv("POSTGRES_PASSWORD", "db_password")
db_name = os.getenv("POSTGRES_DB", "db_dev")


def create_app(settings_module=None):
    local_app = Flask(os.getenv("APP_NAME"))

    local_app.config.from_object(settings_module)
    if local_app.config["APP_ENV"] == "local":
        print("Using PostgreSQL")
        local_app.config["SQLALCHEMY_DATABASE_URI"] = (
            f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}"
        )

    db.init_app(local_app)

    local_celery = make_celery(local_app)
    local_celery.set_default()

    migrate.init_app(local_app, db)
    cors.init_app(
        local_app, supports_credentials="true", resources={r"*": {"origins": "*"}}
    )
    manage.init_app(local_app)

    # Logging configuration
    configure_logging(local_app)

    # Register Blueprint
    register_routing(local_app)

    return local_app, local_celery


app, celery = create_app(os.getenv("APP_SETTINGS_MODULE"))

app.app_context().push()
