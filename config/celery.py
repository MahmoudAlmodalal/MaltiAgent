"""
Celery application bootstrap.

Discovers tasks from each installed app's tasks.py module.
Queues are routed via CELERY_TASK_ROUTES in settings.py.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("virtual_company")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # pragma: no cover - smoke task
    print(f"Request: {self.request!r}")
