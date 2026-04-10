"""
Django settings for the Virtual Company multi-agent system.
"""
from pathlib import Path
import os

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-secret-change-me")
DEBUG = env("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",  # must come before django.contrib.staticfiles
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "channels",
]

LOCAL_APPS = [
    "agents",
    "projects",
    "provider_settings",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware / URLs / Templates
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="virtual_company"),
        "USER": env("POSTGRES_USER", default="vc_user"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="vc_pass"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}

# ---------------------------------------------------------------------------
# Auth / i18n / static
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ---------------------------------------------------------------------------
# Channels (WebSockets)
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("CHANNELS_REDIS_URL", default="redis://localhost:6379/3")],
        },
    },
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 30  # 30 min hard limit per task
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25

# Queue routing — agents/tasks.py registers tasks into these queues.
CELERY_TASK_ROUTES = {
    "agents.tasks.run_orchestrator": {"queue": "orchestrator"},
    "agents.tasks.run_research": {"queue": "research"},
    "agents.tasks.run_pm": {"queue": "agents"},
    "agents.tasks.run_system_designer": {"queue": "agents"},
    "agents.tasks.run_db_schema": {"queue": "agents"},
    "agents.tasks.run_api_designer": {"queue": "agents"},
    "agents.tasks.run_code_review": {"queue": "review"},
    "agents.tasks.run_bug_fixer": {"queue": "review"},
    "agents.tasks.run_testing": {"queue": "testing"},
    "agents.tasks.run_documentation": {"queue": "docs"},
}

# ---------------------------------------------------------------------------
# Provider settings
# ---------------------------------------------------------------------------
DEFAULT_PROVIDER = env("DEFAULT_PROVIDER", default="groq")

# Fernet key for ProviderConfig.api_key encryption.
# In dev, fall back to a deterministic key derived from SECRET_KEY so that
# `manage.py runserver` works without extra setup. In production set
# FIELD_ENCRYPTION_KEY explicitly.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

PROVIDER_DEFAULTS = {
    "groq": {
        "api_key": env("GROQ_API_KEY", default=""),
        "model": env("GROQ_MODEL", default="llama-3.3-70b-versatile"),
    },
    "ollama": {
        "host": env("OLLAMA_HOST", default="http://localhost:11434"),
        "model": env("OLLAMA_MODEL", default="llama3.1"),
    },
    "openrouter": {
        "api_key": env("OPENROUTER_API_KEY", default=""),
        "model": env("OPENROUTER_MODEL", default="meta-llama/llama-3.1-70b-instruct"),
    },
    "anthropic": {
        "api_key": env("ANTHROPIC_API_KEY", default=""),
        "model": env("ANTHROPIC_MODEL", default="claude-sonnet-4-6"),
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "agents": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "projects": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "provider_settings": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
