"""Django settings for the online booking application.

Local development uses SQLite and local media files. Vercel (and any explicitly
configured production environment) uses PostgreSQL and requires persistent
object storage for user uploads.
"""

from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
env_file = BASE_DIR / ".env"
if env_file.is_file():
    # Real environment variables must win over local .env values.
    environ.Env.read_env(env_file, overwrite=False)


def parse_csv(value):
    """Return a clean list from a comma-separated environment variable."""
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def database_config_from_url(database_url: str) -> dict:
    """Convert a PostgreSQL URL into a Django database configuration."""
    try:
        parsed = urlsplit(database_url)
        port = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured("DATABASE_URL is not a valid URL.") from exc

    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            "DATABASE_URL must use the postgres:// or postgresql:// scheme."
        )

    database_name = unquote(parsed.path.lstrip("/"))
    if not parsed.hostname or not database_name:
        raise ImproperlyConfigured(
            "DATABASE_URL must include a PostgreSQL host and database name."
        )

    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(port or ""),
    }
    options = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if options:
        config["OPTIONS"] = options
    return config


deployment_environment = env(
    "DJANGO_ENV",
    default=env("VERCEL_ENV", default="local"),
).strip().lower()
IS_VERCEL = env.bool("VERCEL", default=False)
IS_PRODUCTION = env.bool(
    "DJANGO_PRODUCTION",
    default=(
        IS_VERCEL
        or deployment_environment in {"prod", "production", "preview", "staging"}
    ),
)

# Never expose Django debug pages from a production deployment, even if a stale
# local .env file happens to say DEBUG=True.
DEBUG = False if IS_PRODUCTION else env.bool("DEBUG", default=False)

SECRET_KEY = env("SECRET_KEY", default="")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise ImproperlyConfigured("SECRET_KEY must be set in production.")
    SECRET_KEY = "django-insecure-local-development-only"


def _host_from_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value if "://" in value else f"//{value}")
    return parsed.hostname or parsed.path.split("/", 1)[0]


ALLOWED_HOSTS = parse_csv(env("ALLOWED_HOSTS", default=""))
vercel_host = _host_from_url(env("VERCEL_URL", default=""))
if vercel_host and vercel_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(vercel_host)

if not ALLOWED_HOSTS:
    if IS_PRODUCTION:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must contain the production domain names."
        )
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "::1", "0.0.0.0", "testserver"]

CSRF_TRUSTED_ORIGINS = parse_csv(env("CSRF_TRUSTED_ORIGINS", default=""))
if vercel_host:
    vercel_origin = f"https://{vercel_host}"
    if vercel_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(vercel_origin)


# Provider and search settings
FLIGHT_SEARCH_PROVIDER = env(
    "FLIGHT_SEARCH_PROVIDER", default="duffel"
).strip().lower()
DUFFEL_ACCESS_TOKEN = env("DUFFEL_ACCESS_TOKEN", default="")
DUFFEL_API_BASE_URL = env("DUFFEL_API_BASE_URL", default="https://api.duffel.com")
DUFFEL_API_VERSION = env("DUFFEL_API_VERSION", default="v2")
DUFFEL_SUPPLIER_TIMEOUT_MS = env.int("DUFFEL_SUPPLIER_TIMEOUT_MS", default=15000)
FLIGHT_SEARCH_TIMEOUT_SECONDS = env.int(
    "FLIGHT_SEARCH_TIMEOUT_SECONDS", default=25
)
FLIGHT_SEARCH_RELAX_TLS_STRICT = env.bool(
    "FLIGHT_SEARCH_RELAX_TLS_STRICT", default=False
)
FLIGHT_SEARCH_CACHE_SECONDS = env.int("FLIGHT_SEARCH_CACHE_SECONDS", default=60)
ALLOW_DUFFEL_TEST_DATA = env.bool("ALLOW_DUFFEL_TEST_DATA", default=True)

# Amadeus remains available for hotels and as an explicitly selected legacy
# flight provider, but its credentials are not required for Duffel flight search.
AMADEUS_CLIENT_ID = env("AMADEUS_CLIENT_ID", default="")
AMADEUS_CLIENT_SECRET = env("AMADEUS_CLIENT_SECRET", default="")
AMADEUS_HOSTNAME = env("AMADEUS_HOSTNAME", default="test")
USE_LIVE_FLIGHT_API = env.bool("USE_LIVE_FLIGHT_API", default=True)
USE_LIVE_HOTEL_API = env.bool(
    "USE_LIVE_HOTEL_API", default=USE_LIVE_FLIGHT_API
)
HOTEL_SEARCH_PROVIDER = env("HOTEL_SEARCH_PROVIDER", default="amadeus").strip().lower()
ALLOW_HOTEL_TEST_DATA = env.bool("ALLOW_HOTEL_TEST_DATA", default=True)
HOTEL_SEARCH_TIMEOUT_SECONDS = env.int("HOTEL_SEARCH_TIMEOUT_SECONDS", default=30)
HOTEL_SEARCH_CACHE_SECONDS = env.int("HOTEL_SEARCH_CACHE_SECONDS", default=300)
MIN_HOTEL_RESULTS = env.int("MIN_HOTEL_RESULTS", default=12)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "widget_tweaks",
    "demo",
]

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

ROOT_URLCONF = "online_booking_tool.urls"
WSGI_APPLICATION = "online_booking_tool.wsgi.application"

AUTH_USER_MODEL = "demo.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "demo.context_processors.booking_cart",
            ],
        },
    },
]


# Database
database_url = env("DATABASE_URL", default="").strip()
if database_url:
    database = database_config_from_url(database_url)
    database["CONN_MAX_AGE"] = env.int(
        "DATABASE_CONN_MAX_AGE", default=60 if IS_PRODUCTION else 0
    )
    database["CONN_HEALTH_CHECKS"] = env.bool(
        "DATABASE_CONN_HEALTH_CHECKS", default=IS_PRODUCTION
    )
    if env.bool("DATABASE_SSL_REQUIRE", default=IS_PRODUCTION):
        database.setdefault("OPTIONS", {}).setdefault("sslmode", "require")
    DATABASES = {"default": database}
elif IS_PRODUCTION:
    raise ImproperlyConfigured("DATABASE_URL must be set in production.")
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
CSRF_FAILURE_VIEW = "demo.views.csrf_failure"


# Email
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="demo.brevo_email_backend.BrevoEmailBackend"
)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
BREVO_API_KEY = env("BREVO_API_KEY", default="")
BREVO_API_URL = env(
    "BREVO_API_URL", default="https://api.brevo.com/v3/smtp/email"
)
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", default=EMAIL_HOST_USER)
BREVO_SENDER_NAME = env("BREVO_SENDER_NAME", default="Online Booking Tool")
EMAIL_FALLBACK_BACKEND = env(
    "EMAIL_FALLBACK_BACKEND",
    default=(
        "django_ses.SESBackend"
        if IS_PRODUCTION
        else "django.core.mail.backends.console.EmailBackend"
    ),
)

# django-ses can use explicit keys or the normal boto3 credential chain. None of
# these variables are required merely to import the Django settings module.
if any(
    backend.startswith("django_ses.")
    for backend in (EMAIL_BACKEND, EMAIL_FALLBACK_BACKEND)
):
    AWS_SES_REGION_NAME = env("AWS_SES_REGION_NAME", default="us-east-1")
    AWS_SES_REGION_ENDPOINT = env(
        "AWS_SES_REGION_ENDPOINT",
        default=f"email.{AWS_SES_REGION_NAME}.amazonaws.com",
    )
    aws_access_key = env("AWS_ACCESS_KEY_ID", default="")
    aws_secret_key = env("AWS_SECRET_ACCESS_KEY", default="")
    aws_session_token = env("AWS_SESSION_TOKEN", default="")
    if aws_access_key:
        AWS_ACCESS_KEY_ID = aws_access_key
    if aws_secret_key:
        AWS_SECRET_ACCESS_KEY = aws_secret_key
    if aws_session_token:
        AWS_SESSION_TOKEN = aws_session_token

TRAVEL_AGENCY_DEFAULT_COMPANY_CODE = env(
    "TRAVEL_AGENCY_DEFAULT_COMPANY_CODE", default="OBT1234"
)
ROLE_EMAIL_RECIPIENTS = {
    "admin": parse_csv(env("ADMIN_EMAIL_RECIPIENTS", default="")),
    "staff": parse_csv(env("STAFF_EMAIL_RECIPIENTS", default="")),
    "travel_agency": parse_csv(
        env("TRAVEL_AGENCY_EMAIL_RECIPIENTS", default="")
    ),
}
ROLE_EMAIL_FALLBACK_RECIPIENTS = parse_csv(
    env("ROLE_EMAIL_FALLBACK_RECIPIENTS", default=EMAIL_HOST_USER)
)
FLIGHT_APPROVAL_REQUEST_RECIPIENT_ROLES = parse_csv(
    env("FLIGHT_APPROVAL_REQUEST_RECIPIENT_ROLES", default="admin")
)
BOOKING_NOTIFICATION_RECIPIENT_ROLES = parse_csv(
    env("BOOKING_NOTIFICATION_RECIPIENT_ROLES", default="travel_agency")
)
HOTEL_BOOKING_NOTIFICATION_RECIPIENT_ROLES = parse_csv(
    env("HOTEL_BOOKING_NOTIFICATION_RECIPIENT_ROLES", default="travel_agency")
)


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static assets are collected at build time and served by WhiteNoise. Runtime
# directory creation is deliberately avoided because Vercel is read-only.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

s3_bucket_name = env("AWS_STORAGE_BUCKET_NAME", default="").strip()
USE_S3_STORAGE = env.bool("USE_S3_STORAGE", default=bool(s3_bucket_name))
if USE_S3_STORAGE:
    if not s3_bucket_name:
        raise ImproperlyConfigured(
            "AWS_STORAGE_BUCKET_NAME is required when USE_S3_STORAGE is enabled."
        )

    s3_options = {
        "bucket_name": s3_bucket_name,
        "location": env("AWS_MEDIA_LOCATION", default="media").strip("/"),
        "default_acl": env("AWS_DEFAULT_ACL", default="").strip() or None,
        "querystring_auth": env.bool("AWS_QUERYSTRING_AUTH", default=True),
        "file_overwrite": env.bool("AWS_S3_FILE_OVERWRITE", default=False),
    }
    optional_s3_options = {
        "access_key": env(
            "AWS_STORAGE_ACCESS_KEY_ID",
            default=env("AWS_ACCESS_KEY_ID", default=""),
        ),
        "secret_key": env(
            "AWS_STORAGE_SECRET_ACCESS_KEY",
            default=env("AWS_SECRET_ACCESS_KEY", default=""),
        ),
        "security_token": env(
            "AWS_STORAGE_SESSION_TOKEN",
            default=env("AWS_SESSION_TOKEN", default=""),
        ),
        "region_name": env("AWS_S3_REGION_NAME", default=""),
        "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=""),
        "addressing_style": env("AWS_S3_ADDRESSING_STYLE", default=""),
    }
    s3_options.update(
        {key: value for key, value in optional_s3_options.items() if value}
    )

    custom_domain = env("AWS_S3_CUSTOM_DOMAIN", default="").strip()
    if custom_domain:
        custom_domain = custom_domain.removeprefix("https://").removeprefix(
            "http://"
        ).rstrip("/")
        s3_options["custom_domain"] = custom_domain
        s3_options["url_protocol"] = env(
            "AWS_S3_URL_PROTOCOL", default="https:"
        )

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": s3_options,
    }
elif IS_PRODUCTION:
    raise ImproperlyConfigured(
        "Persistent media storage is required in production. Set "
        "AWS_STORAGE_BUCKET_NAME (and S3-compatible credentials/endpoint)."
    )


# HTTPS and cookie protections default on in production but can be tuned during
# a staged rollout through environment variables.
if env.bool("TRUST_X_FORWARDED_PROTO", default=IS_PRODUCTION):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=IS_PRODUCTION)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=IS_PRODUCTION)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=IS_PRODUCTION)
SECURE_HSTS_SECONDS = env.int(
    "SECURE_HSTS_SECONDS", default=3600 if IS_PRODUCTION else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
