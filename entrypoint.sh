#!/bin/sh

echo "Start entrypoint script..."

echo "Database:" $DATABASE

# Wait for PostgreSQL to be available
if [ "$DATABASE" = "postgres" ]; then
    echo "Waiting for PostgreSQL..."
    while ! PGPASSWORD=$POSTGRES_PASSWORD psql -h $BBDD_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c '\q'; do
        echo "Waiting for PostgreSQL..."
        sleep 0.5
    done
    echo "PostgreSQL started"
fi

echo "Environment:" $APP_ENV

# If in local environment, set up the database and admin user
if [ "$APP_ENV" = "local" ]; then
    echo "Start creating the database"
    flask create-db
    echo "Done creating the database"

    echo "Start checking user-admin"
    # flask create-user-admin
    echo "Done initializing user-admin"
fi

# Start the Flask app using Gunicorn
if [ "$APP_ENV" = "local" ] || [ "$APP_ENV" = "production" ]; then
    echo "Running the Flask app with Gunicorn..."
    # gunicorn -c ./gunicorn/gunicorn_config.py "$API_ENTRYPOINT" --env APP_SETTINGS_MODULE=$APP_SETTINGS_MODULE
    echo "API_ENTRYPOINT: $API_ENTRYPOINT"
    echo "APP_SETTINGS_MODULE: $APP_SETTINGS_MODULE"
    echo "SQLALCHEMY_DATABASE_URI: $SQLALCHEMY_DATABASE_URI"

    gunicorn -c ./gunicorn/gunicorn_config.py "app:app" --bind 0.0.0.0:5001 &

    # Start Celery worker if needed
    echo "Starting Celery worker..."
    celery -A $CELERY_APP worker --loglevel=info -P eventlet &
    
    # Start Celery Beat if needed
    if [ "$APP_ENV" = "local" ]; then
        echo "Starting Celery Beat..."
        celery -A $CELERY_APP beat --loglevel=info &
    fi

    # Wait for processes to exit (Flask, Celery, Celery Beat)
    wait
fi
