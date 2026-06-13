"""Ensure the Celery app loads with Django so @shared_task works everywhere."""

from .celery import app as celery_app

__all__ = ("celery_app",)
