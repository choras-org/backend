Write-Host "Start entrypoint script..."

Write-Host "Database: $env:DATABASE"

# Wait for PostgreSQL to be available
if ($env:DATABASE -eq "postgres") {
    Write-Host "Waiting for PostgreSQL..."
    while (-not (Invoke-Expression "psql -h $env:BBDD_HOST -U $env:POSTGRES_USER -d $env:POSTGRES_DB -c `\q`")) {
        Write-Host "Waiting for PostgreSQL..."
        Start-Sleep -Seconds 1
    }
    Write-Host "PostgreSQL started"
}

Write-Host "Environment: $env:APP_ENV"

# If in local environment, set up the database and admin user
if ($env:APP_ENV -eq "local") {
    Write-Host "Start creating the database"
    python -m flask create-db
    Write-Host "Done creating the database"

    Write-Host "Start checking user-admin"
    # python -m flask create-user-admin
    Write-Host "Done initializing user-admin"
}

# Start the Flask app using Gunicorn (via WSL or equivalent on Windows)
if ($env:APP_ENV -eq "local" -or $env:APP_ENV -eq "production") {
    Write-Host "Running the Flask app with Gunicorn..."
    Write-Host "API_ENTRYPOINT: $env:API_ENTRYPOINT"
    Write-Host "APP_SETTINGS_MODULE: $env:APP_SETTINGS_MODULE"
    Write-Host "SQLALCHEMY_DATABASE_URI: $env:SQLALCHEMY_DATABASE_URI"

    # Gunicorn is Linux-only; on Windows, use Waitress or Python's built-in server
    Start-Process python -ArgumentList "-m flask run --host=0.0.0.0 --port=5001" -NoNewWindow -PassThru

    # Start Celery worker
    Write-Host "Starting Celery worker..."
    Start-Process celery -ArgumentList "-A $env:CELERY_APP worker --loglevel=info -P eventlet" -NoNewWindow -PassThru

    # Start Celery Beat if in local
    if ($env:APP_ENV -eq "local") {
        Write-Host "Starting Celery Beat..."
        Start-Process celery -ArgumentList "-A $env:CELERY_APP beat --loglevel=info" -NoNewWindow -PassThru
    }

    # Wait for all processes (simplest: just wait)
    Start-Sleep -Seconds 3600
}
