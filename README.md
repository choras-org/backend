# Backend Repository

<p align="center">
<img src="./assets/logo.png" alt="Logo" />
</p>

This repository contains the backend application for the project room
acoustics user interface, implemented in Python using the Flask framework.
Currently, it has been tested only in the development environment.
Future plans include support for Docker and deployment in production
environments. The application supports SQLite3 as the default database,
with provisions for PostgreSQL as an alternative.

## Index

- [Technology](#technology)
- [Requirements](#requirements)
- [Environments](#environments)
  - [Develop](#develop)
  - [Production](#production)
- [Flask Commands](#flask-commands)
  - [Flask-cli](#flask-cli)
- [Database commands](#bbdd-commands)
  - [Flask-migrate](#flask-migrate)
- [Swagger](#swagger)
- [Reference](#reference)
- [Contribution](#contribution)

## Technology

- **Operating System:** Windows, Ubuntu
- **Web Framework:** Flask
- **ORM:** Flask-sqlalchemy
- **Swagger:** Swagger-UI
- **Serialization:** Marshmallow
- **Deserialization:** Marshmallow
- **Validation:** Marshmallow
- **Migration Database:** Flask-migrate
- **Environment manager:** Anaconda/Miniconda
- **Containerization:** Docker, docker-compose
- **Database:** PostgreSQL, SQLite3
- **Python WSGI HTTP Server:** Gunicorn (env specification)
- **Proxy:** Nginx
- **Tests:** Under Planning
- **Deployment platform:** Under planning for AWS
- **CI/CD:** Under planning for Github Actions -**Celery** Job queue

## Requirements

- [Python](https://www.python.org/downloads/)
- [Anaconda/Miniconda](instructions/anaconda-miniconda.md)
- [Docker](instructions/docker-dockercompose.md)
- [Docker-Compose](instructions/docker-dockercompose.md)
- Other requirements such as python libraries and so on.

## Environments

### Develop

Development environment uses SQLite3/Postgresql locally and runs the Flask server in debug mode.
You can customize the environment variables in the corresponding .env file. 0. **Setup Celery**
celery -A app.celery worker --loglevel=info -P eventlet

1. **Create environment and install packages**

In general, I am using conda to handle virtual env and packages installations, however you can
use other alternatives to install the python dependencies as well.

```shell
conda create -n NAME_OF_VENV python=3.10

conda activate NAME_OF_VENV

pip install simulation-backend/.[backends]
```

2. **Create PosgresSQL on Linux[Ubuntu] (optional)**

```shell
# Install PosgresSQL
sudo apt-get install postgresql-12

# Access to PosgresSQL
sudo -u postgres psql

# Create user and password
CREATE USER db_user WITH PASSWORD 'db_password';

# Create Database dev
CREATE DATABASE db_dev;

# Add permission User to Database
GRANT ALL PRIVILEGES ON DATABASE db_dev TO db_user;
```

Note: remember to change the default env configuration to switch from sqllite to postgresql.

Note: if you are using Windows machine, you can simply download and install the postgresql from its website.
However, upon installing the software try to remember what is the password for the superuser.

3. **Create or update `.env` file**

```shell
# APP configuration
APP_NAME=Flask API Rest Template
APP_ENV=develop

# Flask Configuration
FLASK_APP=app:app
FLASK_DEBUG=true
APP_SETTINGS_MODULE=config.DevelopConfig
APP_TEST_SETTINGS_MODULE=config.TestingConfig

FLASK_RUN_HOST=192.168.0.104
FLASK_RUN_PORT=5000

# Database service configuration
DATABASE_URL=postgresql://db_user:db_password@localhost/db_dev
DATABASE_TEST_URL=postgresql://db_user:db_password@localhost/db_test
```

4. **Run application**
   Once you are done with the above steps, you are ready to run the application.

```shell
# Create database
flask create-db

# Run a development server
flask run
```

### Testing

Some of the planned commands:

1. **Run all tests**

```shell
flask tests
```

5. **Run coverage**

```shell
flask coverage
```

6. **Run coverage report**

```shell
flask coverage_report
```

### Local (Dockerize)

Containerized services separately with PostgreSQL databases (db), API (api) and Nginx reverse proxy (nginx) with Docker
and docker-compose.

1. **Create `.env.api.local`, `.env.db.local` files**

   1. **.env.api.local**

      ```shell
      # APP configuration
      APP_NAME=[Name APP] # For example Flask API Rest Template
      APP_ENV=local

      # Flask configuration
      API_ENTRYPOINT=app:app
      APP_SETTINGS_MODULE=config.LocalConfig
      APP_TEST_SETTINGS_MODULE=config.TestingConfig

      # API service configuration
      API_HOST=<api_host> # For example 0.0.0.0
      API_PORT=<port_api> # For example 5000

      # Database service configuration
      DATABASE=postgres
      DB_HOST=<name_container_bbdd> # For example db_service (name service in docker-compose)
      DB_PORT=<port_container_bbdd> # For example 5432 (port service in docker-compose)
      POSTGRES_DB=<name_database> # For example db_dev
      POSTGRES_USER=<name_user> # For example db_user
      PGPASSWORD=<password_user> # For example db_password

      # Secret key
      SECRET_KEY=<your-secret-key>
      JWT_SECRET_KEY=<your-jwt-secret-key>

      DATABASE_TEST_URL=<url database test> # For example postgresql+psycopg2://db_user:db_password@db_service:5432/db_test
      DATABASE_URL=<url database> # For example postgresql+psycopg2://db_user:db_password@db_service:5432/db_dev
      ```

   2. **.env.db.local**:

      ```shell
      POSTGRES_USER=<name_user> # For example db_user
      POSTGRES_PASSWORD=<password> # For example db_password
      POSTGRES_DB=<name_DB> # For example db_dev
      ```

2. **Build and run services**
   `shell docker-compose up --build ` 2. Stop services:
   `shell docker-compose stop ` 3. Delete services:
   `shell docker compose down ` 4. Remove services (removing volumes):
   `shell docker-compose down -v ` 4. Remove services (removing volumes and images):
   `shell docker-compose down -v --rmi all ` 5. View services:
   `shell docker-compose ps `
   **NOTE:** The Rest API defaults to host _localhost_ and port _80_.

### Production

Apply CI/CD with Github Actions to automatically deployed to AWS platform use EC2, RDS PostgresSQL.

1. Create file **.env.pro** and enter the environment variables needed for production. For example:

   ```shell
   # APP configuration
   APP_NAME=Flask API Rest Template
   APP_ENV=production

   # Flask configuration
   API_ENTRYPOINT=app:app
   APP_SETTINGS_MODULE=config.ProductionConfig

   # API service configuration
   API_HOST=<api_host> # For example 0.0.0.0

   # Secret key
   SECRET_KEY=<your-secret-key>
   JWT_SECRET_KEY=<your-jwt-secret-key>

   # Database service configuration
   DATABASE_URL=<url_database> # For example sqlite:///production.db

   # Deploy platform
   PLATFORM_DEPLOY=AWS
   ```

## Commands

You can run the following commands in order to use specific features of the application. Note that all of these
commands are also ran in the pipeline on every commit, but it is recommended to run them locally too. Most notably,
[PEP8 verification](#pep8-verification-flake8), [Import sorting](#import-sorting-isort), and
[test cases](#test-cases-unittest), as committing without satisfying these tools will cause the pipeline to fail.

## PEP8 verification _(flake8)_

You can check whether your code adheres to the [PEP8](https://peps.python.org/pep-0008/) code style standard by doing
`cd painting_explorer`. And then running the following:

```shell
flake8
```

If you want to write the output of this to file as well, you can run the following:

```shell
flake8 --output-file ../reports/flake8/flake8stats.txt
```

## Import sorting _(isort)_

To sort all of your imported Python packages, similarly make sure you are in the `painting_explorer` folder, and then
run the following:

```shell
isort .
```

If you just want to check what changes isort would make, you can run the following:

```shell
isort . --check --diff
```

## Code coverage calculation _(Coverage.py)_

For code coverage as well, make sure you are in the `painting_explorer` folder. You can then run the following command
to first erase any previous coverage reports:

```shell
coverage erase --data-file=../reports/coverage/.coverage
```

Next, calculate the new coverage using:

```shell
coverage run --source='.' --data-file=../reports/coverage/.coverage manage.py test
```

To print a report of this coverage, run:

```shell
coverage report --data-file=../reports/coverage/.coverage
```

Lastly if you want to generate a report in XML format too, you can use this:

```shell
coverage xml --data-file=../reports/coverage/.coverage -o ../reports/coverage/coverage.xml
```

## a pre-commit configuration

Install the git hook scripts
run pre-commit install to set up the git hook scripts
run: pre-commit

## Celery Commands
```
celery -A app.celery worker --loglevel=info -P eventlet
```
## Flask Commands

### Flask-cli

- Create all tables in the database:

  ```sh
  flask create_db
  ```

- Delete all tables in the database:

  ```sh
  flask drop_db
  ```

- Database reset:

  ```sh
  flask reset-db
  ```

- Run tests with coverage without report in html:

  ```sh
  flask cov
  ```

- Run tests with coverage with report in html:
  ```sh
  flask cov-html
  ```

## Database commands

### Flask-migrate

- Create a migration repository:

  ```sh
  flask db init
  ```

- Generate a migration version:

  ```sh
  flask db migrate -m "Init"
  ```

- Apply migration to the Database:
  ```sh
  flask db upgrade
  ```

## Swagger

```
http://localhost:<port>/swagger-ui
```

<p align="center">
<img src="./assets/swagger.png" alt="Swagger" />
</p>

## Reference

- [Github - Uvicorn Gunicorn Fastapi Docker](https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker)

## Contribution

Feel free to make any suggestions or improvements to the project.

## generate docs

1. sphinx-quickstart docs
2. sphinx-build -M html docs/source/ docs/build/
