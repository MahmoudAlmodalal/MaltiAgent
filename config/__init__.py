try:
    from .celery import app as celery_app  # noqa: F401

    __all__ = ("celery_app",)
except ImportError:
    # Celery not installed yet — safe to continue for makemigrations / tests.
    pass
