import os
import environ

# Initialize environment variables
env = environ.Env(
    # Set casting and default values
    DEBUG=(bool, False)
)

# Take environment variables from the .env file
environ.Env.read_env(
    os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), '.env'),
    overwrite=True,
)

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

# HOST_URL = env('HOST_URL', default='localhost')
# ALLOWED_HOSTS = ['localhost', '0.0.0.0', '127.0.0.1', HOST_URL]
ALLOWED_HOSTS = ['*']
AMADEUS_CLIENT_ID = env('AMADEUS_CLIENT_ID')
AMADEUS_CLIENT_SECRET = env('AMADEUS_CLIENT_SECRET')
AMADEUS_HOSTNAME = os.environ.get(
    'AMADEUS_HOSTNAME', 'test')  # Default to 'test'
USE_LIVE_FLIGHT_API = env.bool('USE_LIVE_FLIGHT_API', default=True)
USE_LIVE_HOTEL_API = env.bool('USE_LIVE_HOTEL_API', default=USE_LIVE_FLIGHT_API)
MIN_HOTEL_RESULTS = env.int('MIN_HOTEL_RESULTS', default=12)


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    "widget_tweaks",
    'demo',
    
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'online_booking_tool.urls'

SETTINGS_PATH = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_DIRS = (
    os.path.join(SETTINGS_PATH, 'templates'),
)

AUTH_USER_MODEL = 'demo.User'  # Custom user model
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# AWS Credentials and SES Configurationbefore i used this guy
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')  #
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_SES_REGION_NAME = env('AWS_SES_REGION_NAME')
AWS_SES_REGION_ENDPOINT = env('AWS_SES_REGION_ENDPOINT')

# Email Backend Configuration
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'demo.brevo_email_backend.BrevoEmailBackend',
)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
BREVO_API_URL = os.environ.get(
    'BREVO_API_URL',
    'https://api.brevo.com/v3/smtp/email',
)
BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', EMAIL_HOST_USER)
BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'Online Booking Tool')
EMAIL_FALLBACK_BACKEND = os.environ.get(
    'EMAIL_FALLBACK_BACKEND',
    'django_ses.SESBackend',
)
TRAVEL_AGENCY_DEFAULT_COMPANY_CODE = os.environ.get(
    'TRAVEL_AGENCY_DEFAULT_COMPANY_CODE',
    'OBT1234',
)


def parse_csv(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


ROLE_EMAIL_RECIPIENTS = {
    'admin': parse_csv(os.environ.get('ADMIN_EMAIL_RECIPIENTS', '')),
    'staff': parse_csv(os.environ.get('STAFF_EMAIL_RECIPIENTS', '')),
    'travel_agency': parse_csv(
        os.environ.get('TRAVEL_AGENCY_EMAIL_RECIPIENTS', '')
    ),
}
ROLE_EMAIL_FALLBACK_RECIPIENTS = parse_csv(
    os.environ.get('ROLE_EMAIL_FALLBACK_RECIPIENTS', EMAIL_HOST_USER)
)
FLIGHT_APPROVAL_REQUEST_RECIPIENT_ROLES = parse_csv(
    os.environ.get('FLIGHT_APPROVAL_REQUEST_RECIPIENT_ROLES', 'admin')
)
BOOKING_NOTIFICATION_RECIPIENT_ROLES = parse_csv(
    os.environ.get('BOOKING_NOTIFICATION_RECIPIENT_ROLES', 'travel_agency')
)
HOTEL_BOOKING_NOTIFICATION_RECIPIENT_ROLES = parse_csv(
    os.environ.get('HOTEL_BOOKING_NOTIFICATION_RECIPIENT_ROLES', 'travel_agency')
)


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'demo.context_processors.booking_cart',
            ],
        },
    },
]

WSGI_APPLICATION = 'online_booking_tool.wsgi.application'

# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}


# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'verceldb',
#         'USER':   'default',
#         'PASSWORD': 'urVcXC8SRM0q',
#         'HOST': 'ep-wild-forest-a4zarkyz.us-east-1.aws.neon.tech',
#         'PORT': '5432'
#     }
# }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Login and logout redirects
LOGIN_REDIRECT_URL = 'home'  # Redirect after successful login
LOGOUT_REDIRECT_URL = 'login'  # Redirect to login page after logout
CSRF_FAILURE_VIEW = 'demo.views.csrf_failure'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_TMP = os.path.join(BASE_DIR, 'static')
STATIC_URL = '/static/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

os.makedirs(STATIC_TMP, exist_ok=True)
os.makedirs(STATIC_ROOT, exist_ok=True)

STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'static'),
)

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
