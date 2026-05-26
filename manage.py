import unittest
from pathlib import Path

import click
import coverage
from passlib.hash import pbkdf2_sha256

from app.db import db
from app.services import auralization_service, material_service, setting_service
from config import DefaultConfig


@click.option("--pattern", default="test*.py", help="Test search pattern", required=False)
def cov(pattern):
    """
    Run the unit tests with coverage
    """
    cov = coverage.coverage(branch=True, include="app/*")
    cov.start()

    # Discover tests in both the unit and integration directories
    unit_tests = unittest.TestLoader().discover("tests/unit", pattern=pattern)
    integration_tests = unittest.TestLoader().discover("tests/integration", pattern=pattern)
    all_tests = unittest.TestSuite([unit_tests, integration_tests])

    result = unittest.TextTestRunner(verbosity=2).run(all_tests)
    if result.wasSuccessful():
        cov.stop()
        cov.save()
        print("Coverage Summary:")
        cov.report()
        cov.erase()
        return 0
    return 1


@click.option("--pattern", default="test*.py", help="Test search pattern", required=False)
def cov_html(pattern):
    """
    Run the unit tests with coverage and generate an HTML report.
    """
    cov = coverage.coverage(branch=True, include="app/*")
    cov.start()

    # Discover tests in both the unit and integration directories
    unit_tests = unittest.TestLoader().discover("tests/unit", pattern=pattern)
    integration_tests = unittest.TestLoader().discover("tests/integration", pattern=pattern)
    all_tests = unittest.TestSuite([unit_tests, integration_tests])

    result = unittest.TextTestRunner(verbosity=2).run(all_tests)
    if result.wasSuccessful():
        cov.stop()
        cov.save()

        print("Coverage Summary:")
        cov.report()
        cov.html_report(directory="report/htmlcov")
        cov.erase()
        return 0

    return 1


@click.option("--pattern", default="test_*.py", help="Test pattern", required=False)
def tests(pattern):
    """
    Run the tests without code coverage
    """
    # Discover tests in both the unit and integration directories
    unit_tests = unittest.TestLoader().discover("tests/unit", pattern=pattern)
    integration_tests = unittest.TestLoader().discover("tests/integration", pattern=pattern)
    all_tests = unittest.TestSuite([unit_tests, integration_tests])

    result = unittest.TextTestRunner(verbosity=2).run(all_tests)
    if result.wasSuccessful():
        return 0
    return 1


def create_db():
    """
    Create Database.
    """
    db.create_all()
    material_service.insert_initial_materials()
    auralization_service.insert_initial_audios_examples()
    setting_service.insert_initial_settings()
    db.session.commit()


def reset_db():
    """
    Reset Database.
    """
    db.drop_all()
    db.create_all()
    material_service.insert_initial_materials()
    auralization_service.insert_initial_audios_examples()
    setting_service.insert_initial_settings()
    db.session.commit()


def drop_db():
    """
    Drop Database.
    """
    db.drop_all()
    db.session.commit()


def clean_cache():
    """
    Clean cache in the folder.
    """

    def remove_file(directory: Path):
        for item in directory.iterdir():
            if item.is_file():
                item.unlink()
            else:
                remove_file(item)
                item.rmdir()

    cache_folder = Path(DefaultConfig.UPLOAD_FOLDER_NAME)
    if cache_folder.exists() and cache_folder.is_dir():
        remove_file(cache_folder)


def update_audio():
    """
    Update audio files based on Json file.
    """
    auralization_service.update_audios_examples()


def update_setting():
    """
    Update setting files based on Json file.
    """
    setting_service.update_settings()


def init_app(app):
    if app.config["APP_ENV"] == "production":
        commands = [create_db, reset_db, drop_db, clean_cache, update_audio, update_setting]
    else:
        commands = [
            create_db,
            reset_db,
            drop_db,
            clean_cache,
            update_audio,
            update_setting,
            tests,
            cov_html,
            cov,
        ]

    for command in commands:
        app.cli.add_command(app.cli.command()(command))
