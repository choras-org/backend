# APP configuration
APP_NAME=Flask API Rest Template
APP_ENV=production

# Flask Configuration
API_ENTRYPOINT=app:app
APP_SETTINGS_MODULE=config.ProductionConfig

# API service configuration
API_HOST=localhost
API_PORT=5001

# Secret key
SECRET_KEY=<your-secret-key>
JWT_SECRET_KEY=<your-jwt-secret-key>

# Database service configuration
DATABASE_URL=sqlite:///production.db

# Deployment platform
PLATFORM_DEPLOY=AWS

POSTGRES_DB=db_dev
POSTGRES_USER=db_user
POSTGRES_PASSWORD=db_password # Ensure this is set
