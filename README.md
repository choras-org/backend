[![Backend Tests](https://github.com/choras-org/backend/actions/workflows/engd2026.yml/badge.svg)](https://github.com/choras-org/backend/actions/workflows/engd2026.yml)
[![Pytest](https://github.com/choras-org/backend/actions/workflows/pytest.yml/badge.svg)](https://github.com/choras-org/backend/actions/workflows/pytest.yml)
[![Documentation Status](https://readthedocs.org/projects/choras/badge/?version=latest)](https://choras.readthedocs.io/en/latest/?badge=latest)

# CHORAS Backend

This is the backend of CHORAS, implemented in Python using the Flask framework. This repository handles the REST API, database management, and job queuing for the platform.

Note that the backend is not intended as a standalone. For full functionality, all parts of CHORAS are required. Follow the setup instructions in the [documentation pages](https://choras.readthedocs.io/en/).

## Framework

- **Web Framework:** Flask
- **ORM:** Flask-SQLAlchemy
- **Swagger:** Swagger-UI
- **Serialization / Deserialization / Validation:** Marshmallow
- **Database Migrations:** Flask-Migrate
- **Environment Manager:** Anaconda / Miniconda
- **Containerization:** Docker, docker-compose
- **Database:** PostgreSQL, SQLite3
- **WSGI Server:** Gunicorn
- **Proxy:** Nginx
- **Job Queue:** Celery

# Interested in contributing?

If you are interested in contributing to the CHORAS backend and becoming part of the community, please refer to the [contributing guide](https://choras.readthedocs.io/en/latest/includes/contributing.html).
