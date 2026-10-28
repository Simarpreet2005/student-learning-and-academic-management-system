"""Base settings for Academic LMS project.

These settings are shared across development and production environments.
"""
from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Quick-start development settings - unsuitable for production
SECRET_KEY = config(
    "SECRET_KEY",
    default="academic-lms-insecure-dev-key-change-in-production-1928374650",
)

DEBUG = config("DEBUG", default=True, cast=bool)
ENVIRONMENT = config("ENVIRONMENT", default="development")

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost,testserver",
    cast=Csv(),
)

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "crispy_forms",
    "crispy_bootstrap5",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.academics",
    "apps.courseware",
    "apps.quizzes",
    "apps.assessments",
    "apps.planner",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Custom User Model
AUTH_USER_MODEL = "accounts.User"


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization & Localization
# English only throughout the application UI and documentation
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="UTC")
USE_I18N = False
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default static files storage for development and testing
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Media files (File uploads, courseware materials, assignment submissions)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Courseware File Upload Security & Limitations
COURSEWARE_MAX_UPLOAD_SIZE = config(
    "COURSEWARE_MAX_UPLOAD_SIZE",
    default=20 * 1024 * 1024,
    cast=int,
)  # 20 Megabytes
COURSEWARE_ALLOWED_EXTENSIONS = [
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".odp",
    ".ods",
    ".txt",
    ".rtf",
    ".zip",
]
DANGEROUS_EXTENSIONS = [
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".py",
    ".js",
    ".vbs",
    ".msi",
    ".php",
    ".phtml",
    ".html",
    ".htm",
    ".dll",
    ".com",
    ".scr",
    ".jar",
    ".ps1",
]

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Crispy Forms configuration with Bootstrap 5
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Authentication redirection defaults
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Logging Configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
}
