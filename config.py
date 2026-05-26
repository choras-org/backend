import datetime
import os

basedir = os.path.abspath(os.path.dirname(__file__))
app_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "app")


class DefaultConfig:
    """
    Default Configuration
    """

    # Flask Configuration
    APP_NAME = os.environ.get("APP_NAME")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    PROPAGATE_EXCEPTIONS = True
    DEBUG = False
    TESTING = False

    # Configuration of Flask-JWT-Extended
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    # Determines the minutes that the access token remains active
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=30)
    # Determines the days that the refresh token remains active
    JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=30)
    # Algorithm used to generate the token
    JWT_ALGORITHM = "HS256"
    # Algorithm used to decode the token
    JWT_DECODE_ALGORITHMS = "HS256"
    # Header that should contain the JWT in a request
    JWT_HEADER_NAME = "Authorization"
    # Word that goes before the token in the Authorization header in this case empty
    JWT_HEADER_TYPE = "Bearer"
    # Where to look for a JWT when processing a request.
    JWT_TOKEN_LOCATION = "headers"

    # Config API documents
    API_TITLE = "UI Backend RESTAPI"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_SWAGGER_UI_PATH = "/swagger-ui"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    # Database configuration
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SHOW_SQLALCHEMY_LOG_MESSAGES = False

    # App Environments
    APP_ENV_LOCAL = "local"
    APP_ENV_TESTING = "testing"
    APP_ENV_DEVELOP = "develop"
    APP_ENV_PRODUCTION = "production"
    APP_ENV = APP_ENV_DEVELOP

    # Logging
    DATE_FMT = "%Y-%m-%d %H:%M:%S"
    LOG_FILE_API = f"{basedir}/logs/api.log"

    UPLOAD_FOLDER_NAME = "uploads"
    UPLOAD_FOLDER = os.path.join(basedir, UPLOAD_FOLDER_NAME)
    ALLOWED_EXTENSIONS = {"obj", "geo", "dxf"}
    AUDIO_FILE_FOLDER = "example_audios"
    USER_AUDIO_FILE_FOLDER_NAME = os.path.join(UPLOAD_FOLDER_NAME, "audiofiles")
    USER_AUDIO_FILE_FOLDER = os.path.join(basedir, USER_AUDIO_FILE_FOLDER_NAME)
    SETTINGS_FILE_FOLDER = "example_settings"

    # Ensure the upload folder exists
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(USER_AUDIO_FILE_FOLDER):
        os.makedirs(USER_AUDIO_FILE_FOLDER)

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "develop.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CELERY_CONFIG = {
        "broker_url": "sqla+sqlite:///" + os.path.join(basedir, "celerydb.sqlite"),
        "result_backend": "db+sqlite:///" + os.path.join(basedir, "celerydb.sqlite"),
    }


class DevelopConfig(DefaultConfig):
    # App environment
    APP_ENV = DefaultConfig.APP_ENV_DEVELOP

    # Activate debug mode
    DEBUG = True

    # Database configuration
    # SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'develop.db')
    # # SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


class TestingConfig(DefaultConfig):
    # App environment
    APP_ENV = DefaultConfig.APP_ENV_TESTING

    # Flask disables error catching during request handling for better error reporting in tests
    TESTING = True

    # Activate debug mode
    DEBUG = True

    # False to disable CSRF protection during tests
    WTF_CSRF_ENABLED = False

    # Logging
    LOG_FILE_API = f"{basedir}/logs/api_tests.log"

    # Database configuration
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "test.db")


class LocalConfig(DefaultConfig):
    # App environment
    APP_ENV = DefaultConfig.APP_ENV_LOCAL

    # Activate debug mode
    DEBUG = False

    # # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


class ProductionConfig(DefaultConfig):
    # App environment
    APP_ENV = DefaultConfig.APP_ENV_PRODUCTION

    # Activate debug mode
    DEBUG = False

    # # Database configuration
    # SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


class AuralizationParametersConfig(DefaultConfig):
    # some hardcode values for the auralization parameters
    original_fs = 20000
    visualization_fs = 44100
    filter_order = 8
    nth_octave = 1
    W = 0.01
    dist_sr = 1.5
    rho = 1.21
    c0 = 343
    random_seed = 215

    allowedextensions = {'wav'}
    maxSize = 10 * 1024 * 1024  # 10MB


class CustomExportParametersConfig(DefaultConfig):
    # some hardcode values for the custom export
    keys = ["xlsx", "EDC", "Parameters", "Auralization"]
    key_simulationId = "SimulationId"
    impulse_response_fs = ["44100Hz"]
    impulse_response = "Impulse response"
    value_wav_file_auralization = "wav"
    value_wav_file_IR = "wavIR"
    value_csv_file_IR = "csvIR"
    key_xlsx = "xlsx"
    key_t_column = "t"


class FeatureToggle(DefaultConfig):
    # Uncomment this line to enable geo conversion from input geometry
    enable_geo_conversion = True

    @classmethod
    def is_enabled(cls, feature_name: str) -> bool:
        return getattr(cls, feature_name, False)
