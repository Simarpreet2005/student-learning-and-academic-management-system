"""Development settings for Academic LMS project."""
from .base import *

DEBUG = config("DEBUG", default=True, cast=bool)

# SQLite Database for local development
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Console Email Backend for local development and testing
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="Academic LMS <noreply@academiclms.local>"
)

# Optional Debug Toolbar / Internal IPs
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]
