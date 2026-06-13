"""Celery app for async return grading.

Settings come from Django under the CELERY_ namespace; tasks are
auto-discovered from each app's tasks.py (e.g. grading/tasks.py).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("loop")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
