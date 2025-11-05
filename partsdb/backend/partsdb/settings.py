"""
Django settings for partsdb project.
"""

import os
import re
from pathlib import Path

import dotenv
from django.core.management.utils import get_random_secret_key

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from repo root (one level above backend/)
dotenv.load_dotenv(Path(BASE_DIR).parent / '.env')

# Core security
SECRET_KEY = os.getenv('SECRET_KEY', get_random_secret_key())
DEBUG = os.getenv('DEBUG', 'true').lower() in ('true', '1', 't')

# Hosts
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

# Apps
INSTALLED_APPS = [
    'corsheaders',  # keep only once, and near top
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'django_filters',
    'drf_spectacular',

    # Local apps
    'apps.core',
    'apps.inventory',
    'apps.files',
    'apps.eagle',
]

# Middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # must be before CommonMiddleware
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'partsdb.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'partsdb.wsgi.application'

# Database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///partsdb.sqlite3')
if DATABASE_URL.startswith('sqlite'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'partsdb.sqlite3',
        }
    }
elif DATABASE_URL.startswith('postgres'):
    m = re.match(r'postgres://(?P<user>.*):(?P<password>.*)@(?P<host>.*):(?P<port>\d+)/(?P<name>.*)', DATABASE_URL)
    if m:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': m.group('name'),
                'USER': m.group('user'),
                'PASSWORD': m.group('password'),
                'HOST': m.group('host'),
                'PORT': m.group('port'),
            }
        }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# I18N
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media
MEDIA_ROOT = os.getenv('MEDIA_ROOT', BASE_DIR / 'media')
MEDIA_URL = '/media/'
os.makedirs(MEDIA_ROOT, exist_ok=True)

# Default PK
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# DRF
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
}

# DRF Spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'PartsDB API',
    'DESCRIPTION': 'API for managing electronic components and inventory',
    'VERSION': '1.0.0',
}

# Feature flags
DATASHEET_FETCH_ENABLED = os.getenv('DATASHEET_FETCH_ENABLED', 'true').lower() in ('true', '1', 't')

# Celery
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = TIME_ZONE

# CORS / CSRF
# Read from env; fall back to dev-friendly defaults
_env_cors = os.getenv('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = _env_cors.split(',') if _env_cors else []
CORS_ALLOW_CREDENTIALS = os.getenv('CORS_ALLOW_CREDENTIALS', 'false').lower() == 'true'

_env_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = _env_csrf.split(',') if _env_csrf else []

# In dev, if no explicit CORS list provided, allow all to avoid 403s while iterating
if DEBUG and not CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True
