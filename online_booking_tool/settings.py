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


def default_email_backend(is_production):
    """Use SES in deployments and a non-delivering console backend locally."""
    if is_production:
        return "django_ses.SESBackend"
    return "django.core.mail.backends.console.EmailBackend"


EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default=default_email_backend(IS_PRODUCTION)
)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER)
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
BREVO_API_KEY = env("BREVO_API_KEY", default="")
BREVO_API_URL = env(
    "BREVO_API_URL", default="https://api.brevo.com/v3/smtp/email"
)
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", default=EMAIL_HOST_USER)
BREVO_SENDER_NAME = env("BREVO_SENDER_NAME", default="Online Booking Tool")
EMAIL_FALLBACK_BACKEND = env(
    "EMAIL_FALLBACK_BACKEND",
    default="",
)

# django-ses can use explicit SES-only keys or the normal boto3 credential
# chain. SES-prefixed settings prevent email credentials from being confused
# with Backblaze B2's S3-compatible media credentials.
if any(
    backend.startswith("django_ses.")
    for backend in (EMAIL_BACKEND, EMAIL_FALLBACK_BACKEND)
):
    AWS_SES_REGION_NAME = env("AWS_SES_REGION_NAME", default="us-east-1")
    AWS_SES_REGION_ENDPOINT = env(
        "AWS_SES_REGION_ENDPOINT",
        default=f"email.{AWS_SES_REGION_NAME}.amazonaws.com",
    )
    ses_access_key = env(
        "AWS_SES_ACCESS_KEY_ID",
        default=env("AWS_ACCESS_KEY_ID", default=""),
    )
    ses_secret_key = env(
        "AWS_SES_SECRET_ACCESS_KEY",
        default=env("AWS_SECRET_ACCESS_KEY", default=""),
    )
    ses_session_token = env(
        "AWS_SES_SESSION_TOKEN",
        default=env("AWS_SESSION_TOKEN", default=""),
    )
    if ses_access_key:
        AWS_SES_ACCESS_KEY_ID = ses_access_key
    if ses_secret_key:
        AWS_SES_SECRET_ACCESS_KEY = ses_secret_key
    if ses_session_token:
        AWS_SES_SESSION_TOKEN = ses_session_token

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


def backblaze_storage_options(
    *,
    bucket_name,
    application_key_id,
    application_key,
    region,
    endpoint_url="",
    location="media",
    querystring_auth=True,
    querystring_expire=3600,
    file_overwrite=False,
    addressing_style="path",
    custom_domain="",
):
    """Build a django-storages configuration locked to Backblaze B2."""
    bucket_name = str(bucket_name or "").strip()
    application_key_id = str(application_key_id or "").strip()
    application_key = str(application_key or "").strip()
    region = str(region or "").strip().lower()
    missing = [
        name
        for name, value in (
            ("B2_BUCKET_NAME", bucket_name),
            ("B2_APPLICATION_KEY_ID", application_key_id),
            ("B2_APPLICATION_KEY", application_key),
            ("B2_REGION", region),
        )
        if not value
    ]
    if missing:
        raise ImproperlyConfigured(
            "Backblaze B2 storage is missing: " + ", ".join(missing)
        )

    if (
        not region.isascii()
        or not region[0].isalnum()
        or not region[-1].isalnum()
        or not all(
            character.isalnum() or character == "-" for character in region
        )
    ):
        raise ImproperlyConfigured("B2_REGION is not a valid Backblaze B2 region.")

    expected_host = f"s3.{region}.backblazeb2.com"
    endpoint_url = str(endpoint_url or "").strip() or f"https://{expected_host}"
    try:
        parsed_endpoint = urlsplit(endpoint_url)
        endpoint_port = parsed_endpoint.port
    except ValueError as exc:
        raise ImproperlyConfigured(
            "B2_ENDPOINT_URL is not a valid Backblaze B2 endpoint."
        ) from exc
    if (
        parsed_endpoint.scheme != "https"
        or parsed_endpoint.hostname != expected_host
        or endpoint_port is not None
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or parsed_endpoint.path not in {"", "/"}
        or parsed_endpoint.query
        or parsed_endpoint.fragment
    ):
        raise ImproperlyConfigured(
            "B2_ENDPOINT_URL must be https://s3.<B2_REGION>.backblazeb2.com."
        )

    addressing_style = str(addressing_style or "").strip().lower()
    if addressing_style not in {"path", "virtual"}:
        raise ImproperlyConfigured(
            "B2_ADDRESSING_STYLE must be either 'path' or 'virtual'."
        )

    try:
        querystring_expire = int(querystring_expire)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "B2_QUERYSTRING_EXPIRE must be a positive integer."
        ) from exc
    if not 0 < querystring_expire <= 604800:
        raise ImproperlyConfigured(
            "B2_QUERYSTRING_EXPIRE must be between 1 and 604800 seconds."
        )

    options = {
        "bucket_name": bucket_name,
        "access_key": application_key_id,
        "secret_key": application_key,
        # Never mix B2 application keys with AWS IAM/STS state used by SES.
        "security_token": None,
        "session_profile": None,
        "region_name": region,
        "endpoint_url": f"https://{expected_host}",
        "location": str(location or "").strip("/"),
        # B2 permissions are bucket-level; do not send per-object ACLs.
        "default_acl": None,
        "querystring_auth": bool(querystring_auth),
        "querystring_expire": querystring_expire,
        "file_overwrite": bool(file_overwrite),
        "addressing_style": addressing_style,
        "signature_version": "s3v4",
    }

    custom_domain = str(custom_domain or "").strip()
    if custom_domain:
        if querystring_auth:
            raise ImproperlyConfigured(
                "B2_CUSTOM_DOMAIN requires a public bucket and "
                "B2_QUERYSTRING_AUTH=False."
            )
        try:
            parsed_domain = urlsplit(
                custom_domain if "://" in custom_domain else f"//{custom_domain}"
            )
            custom_domain_port = parsed_domain.port
        except ValueError as exc:
            raise ImproperlyConfigured(
                "B2_CUSTOM_DOMAIN must be an HTTPS host name without a path."
            ) from exc
        if (
            parsed_domain.scheme not in {"", "https"}
            or not parsed_domain.hostname
            or custom_domain_port is not None
            or parsed_domain.username is not None
            or parsed_domain.password is not None
            or parsed_domain.path not in {"", "/"}
            or parsed_domain.query
            or parsed_domain.fragment
        ):
            raise ImproperlyConfigured(
                "B2_CUSTOM_DOMAIN must be an HTTPS host name without a path."
            )
        options["custom_domain"] = parsed_domain.hostname
        options["url_protocol"] = "https:"

    return options


b2_bucket_name = env("B2_BUCKET_NAME", default="").strip()
USE_B2_STORAGE = env.bool("USE_B2_STORAGE", default=bool(b2_bucket_name))
if USE_B2_STORAGE:
    b2_options = backblaze_storage_options(
        bucket_name=b2_bucket_name,
        application_key_id=env("B2_APPLICATION_KEY_ID", default=""),
        application_key=env("B2_APPLICATION_KEY", default=""),
        region=env("B2_REGION", default=""),
        endpoint_url=env("B2_ENDPOINT_URL", default=""),
        location=env("B2_MEDIA_LOCATION", default="media"),
        querystring_auth=env.bool("B2_QUERYSTRING_AUTH", default=True),
        querystring_expire=env.int("B2_QUERYSTRING_EXPIRE", default=3600),
        file_overwrite=env.bool("B2_FILE_OVERWRITE", default=False),
        addressing_style=env("B2_ADDRESSING_STYLE", default="path"),
        custom_domain=env("B2_CUSTOM_DOMAIN", default=""),
    )
    STORAGES["default"] = {
        # Backblaze B2 exposes an S3-compatible API; this backend does not send
        # files to AWS because its endpoint is fixed above to backblazeb2.com.
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": b2_options,
    }
elif IS_PRODUCTION:
    raise ImproperlyConfigured(
        "Persistent Backblaze B2 media storage is required in production. Set "
        "B2_BUCKET_NAME, B2_APPLICATION_KEY_ID, B2_APPLICATION_KEY, and B2_REGION."
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
